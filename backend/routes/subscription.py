"""
Stripe Pro Subscription — $3.99/mo Rip N' Flip Pro.

Endpoints:
    POST /api/subscription/checkout              — create Stripe Checkout session (subscription mode)
    GET  /api/subscription/status                — current user's tier/sub/trial state
    POST /api/subscription/cancel                — cancel at period end
    POST /api/webhook/stripe-subscription        — Stripe lifecycle webhook
    GET  /api/subscription/admin/info            — admin-only Stripe price lookup
    GET  /api/subscription/webhook-mode          — admin diagnostic: verify mode

Webhook hardening:
    • If STRIPE_WEBHOOK_SECRET is set we attempt signature verification.
    • If STRIPE_WEBHOOK_STRICT=true and verification fails → 400 (Stripe retries).
    • Otherwise (test/dev mode), failed signature is logged & we fall back to
      plain JSON parse so a test-key/live-secret mismatch never wedges the app.
"""
from __future__ import annotations

import json
import os
import logging
from datetime import datetime, timezone

import stripe as stripe_sdk
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core import (
    db,
    logger,
    require_auth,
    require_admin,
    user_tier,
    STRIPE_API_KEY,
    PRO_PRICE_AMOUNT_USD,
)

router = APIRouter(prefix="/api", tags=["subscription"])

stripe_sdk.api_key = STRIPE_API_KEY
_PRO_PRICE_CACHE: dict = {"price_id": None}

# ─── Startup banner — surfaces webhook mode in logs at first import ───
_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
_WEBHOOK_STRICT = os.environ.get("STRIPE_WEBHOOK_STRICT", "false").strip().lower() == "true"
_IS_TEST_KEY = bool(STRIPE_API_KEY and STRIPE_API_KEY.startswith("sk_test_"))
if _WEBHOOK_SECRET:
    mode = "STRICT (signature required)" if _WEBHOOK_STRICT else "LENIENT (verify + fallback)"
    logger.info(
        f"[stripe] webhook signature verification ENABLED — mode={mode}, "
        f"key_type={'test' if _IS_TEST_KEY else 'live/restricted/missing'}"
    )
else:
    logger.warning(
        "[stripe] STRIPE_WEBHOOK_SECRET not set — webhook will parse JSON without verification (dev only)"
    )


async def _get_or_create_pro_price() -> str:
    """Idempotently ensure a $3.99/month recurring Stripe Price exists."""
    if _PRO_PRICE_CACHE["price_id"]:
        return _PRO_PRICE_CACHE["price_id"]
    products = stripe_sdk.Product.list(limit=100)
    product = next((p for p in products.data if p.get("name") == "Rip N' Flip Pro"), None)
    if not product:
        product = stripe_sdk.Product.create(
            name="Rip N' Flip Pro",
            description="Unlimited binder slots, 5 predictor rips/day, marketplace selling.",
        )
    prices = stripe_sdk.Price.list(product=product.id, active=True, limit=10)
    price = next((
        p for p in prices.data
        if p.get("recurring", {}).get("interval") == "month"
        and p.get("unit_amount") == int(PRO_PRICE_AMOUNT_USD * 100)
        and p.get("currency") == "usd"
    ), None)
    if not price:
        price = stripe_sdk.Price.create(
            product=product.id,
            unit_amount=int(PRO_PRICE_AMOUNT_USD * 100),
            currency="usd",
            recurring={"interval": "month"},
            nickname="Rip N' Flip Pro Monthly",
        )
    _PRO_PRICE_CACHE["price_id"] = price.id
    return price.id


class SubscriptionCheckoutRequest(BaseModel):
    origin_url: str


@router.post("/subscription/checkout")
async def subscription_checkout(payload: SubscriptionCheckoutRequest, request: Request):
    """Create a Stripe Checkout Session in subscription mode for $3.99/mo Pro."""
    user = await require_auth(request)
    if not STRIPE_API_KEY or STRIPE_API_KEY == "sk_test_emergent":
        raise HTTPException(
            status_code=503,
            detail="Subscriptions need a real Stripe test key. Get one at https://dashboard.stripe.com/test/apikeys and replace STRIPE_API_KEY in backend/.env, then restart backend.",
        )
    try:
        price_id = await _get_or_create_pro_price()
    except Exception as e:
        logger.error(f"Failed to get/create Pro price: {e}")
        raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)[:200]}")

    origin = payload.origin_url.rstrip('/')
    success_url = f"{origin}/vault?subscription=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin}/vault?subscription=canceled"

    try:
        customer_id = (user.get("subscription") or {}).get("stripe_customer_id")
        if not customer_id:
            existing = stripe_sdk.Customer.list(email=user["email"], limit=1)
            if existing.data:
                customer_id = existing.data[0].id
            else:
                customer = stripe_sdk.Customer.create(email=user["email"], name=user.get("name"))
                customer_id = customer.id
            await db.users.update_one(
                {"user_id": user["user_id"]},
                {"$set": {"subscription.stripe_customer_id": customer_id}},
            )

        session = stripe_sdk.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"user_id": user["user_id"], "plan": "pro_monthly"},
        )

        await db.payment_transactions.insert_one({
            "session_id": session.id,
            "user_id": user["user_id"],
            "type": "subscription",
            "amount": PRO_PRICE_AMOUNT_USD,
            "currency": "usd",
            "payment_status": "initiated",
            "metadata": {"plan": "pro_monthly"},
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        return {"url": session.url, "session_id": session.id}
    except stripe_sdk.error.StripeError as e:
        logger.error(f"Stripe subscription checkout error: {e}")
        raise HTTPException(status_code=502, detail=f"Stripe error: {str(e)}")


@router.get("/subscription/status")
async def subscription_status(request: Request):
    """Return current user's subscription state. Includes 10-day trial info."""
    user = await require_auth(request)
    fresh = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    sub = (fresh or {}).get("subscription") or {}

    created = fresh.get("created_at") if fresh else None
    if isinstance(created, str):
        try:
            created = datetime.fromisoformat(created)
        except ValueError:
            created = None
    if created and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    trial_days_left = 0
    if created:
        elapsed = datetime.now(timezone.utc) - created
        trial_days_left = max(0, 10 - elapsed.days)

    tier = await user_tier(user["user_id"])
    return {
        "tier": tier,
        "trial_days_left": trial_days_left,
        "subscription_status": sub.get("status"),
        "current_period_end": sub.get("current_period_end"),
        "stripe_customer_id": sub.get("stripe_customer_id"),
        "stripe_subscription_id": sub.get("stripe_subscription_id"),
        "cancel_at_period_end": sub.get("cancel_at_period_end", False),
        "pro_until": (fresh or {}).get("pro_until"),
        "pro_source": (fresh or {}).get("pro_source"),
    }


@router.post("/subscription/cancel")
async def subscription_cancel(request: Request):
    """Cancel subscription at period end (user keeps access until current_period_end)."""
    user = await require_auth(request)
    fresh = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    sub_id = ((fresh or {}).get("subscription") or {}).get("stripe_subscription_id")
    if not sub_id:
        raise HTTPException(status_code=400, detail="No active subscription to cancel")
    try:
        stripe_sdk.Subscription.modify(sub_id, cancel_at_period_end=True)
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"subscription.cancel_at_period_end": True}},
        )
        return {"canceled": True, "access_until_period_end": True}
    except stripe_sdk.error.StripeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/webhook/stripe-subscription")
async def stripe_subscription_webhook(request: Request):
    """Stripe lifecycle webhook for subscription events.

    Signature verification flow:
      • Secret set + STRICT=true → construct_event() must succeed (else 400)
      • Secret set + lenient    → try construct_event, log on failure & fall
                                   back to JSON so test/live mismatches don't
                                   take the endpoint down.
      • Secret missing          → JSON parse only (dev mode).
    """
    body = await request.body()
    sig = request.headers.get("Stripe-Signature", "")

    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    strict = os.environ.get("STRIPE_WEBHOOK_STRICT", "false").strip().lower() == "true"

    event = None
    verified = False

    if secret:
        try:
            event = stripe_sdk.Webhook.construct_event(body, sig, secret)
            verified = True
        except Exception as e:
            if strict:
                logger.error(f"[webhook] signature verification FAILED (strict): {e}")
                return JSONResponse({"received": False, "error": "invalid_signature"}, status_code=400)
            logger.warning(
                f"[webhook] signature mismatch (lenient mode, falling back to JSON parse): {e}"
            )

    if event is None:
        try:
            event = json.loads(body.decode("utf-8"))
        except Exception as e:
            logger.error(f"[webhook] body parse failed: {e}")
            return JSONResponse({"received": False, "error": "bad_json"}, status_code=400)

    etype = event.get("type")
    obj = (event.get("data") or {}).get("object") or {}

    if etype in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        sub_id = obj.get("id")
        customer_id = obj.get("customer")
        status = obj.get("status")
        cancel_at_period_end = obj.get("cancel_at_period_end", False)
        period_end = obj.get("current_period_end")
        if period_end:
            period_end = datetime.fromtimestamp(period_end, tz=timezone.utc).isoformat()
        user = await db.users.find_one(
            {"subscription.stripe_customer_id": customer_id}, {"_id": 0}
        )
        if user:
            sub_set = {
                "subscription.status": status,
                "subscription.stripe_subscription_id": sub_id,
                "subscription.current_period_end": period_end,
                "subscription.cancel_at_period_end": cancel_at_period_end,
                "subscription.updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if etype == "customer.subscription.deleted":
                sub_set["subscription.status"] = "canceled"
            # Reflect on top-level tier/pro_until so user_tier() honors it
            if status == "active" and period_end:
                sub_set["tier"] = "pro"
                sub_set["pro_until"] = period_end
                sub_set["pro_source"] = "stripe_subscription"
            elif etype == "customer.subscription.deleted":
                sub_set["tier"] = "free"
            await db.users.update_one({"user_id": user["user_id"]}, {"$set": sub_set})
            logger.info(
                f"[webhook] {etype} user={user['user_id']} status={status} verified={verified}"
            )

    elif etype == "invoice.payment_succeeded":
        customer_id = obj.get("customer")
        await db.payment_transactions.update_one(
            {"metadata.stripe_customer_id": customer_id, "type": "subscription_invoice"},
            {"$set": {"payment_status": "paid"}},
            upsert=False,
        )

    return {"received": True, "verified": verified}


@router.get("/subscription/admin/info")
async def subscription_admin_info(request: Request):
    """Admin: get the Stripe Price ID + product info for verification."""
    await require_admin(request)
    try:
        price_id = await _get_or_create_pro_price()
        return {
            "price_id": price_id,
            "amount": PRO_PRICE_AMOUNT_USD,
            "currency": "usd",
            "interval": "month",
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/subscription/webhook-mode")
async def subscription_webhook_mode(request: Request):
    """Admin-only — return current Stripe webhook verification mode for diagnostics."""
    await require_admin(request)
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    strict = os.environ.get("STRIPE_WEBHOOK_STRICT", "false").strip().lower() == "true"
    return {
        "secret_configured": bool(secret),
        "secret_prefix": (secret[:6] + "…") if secret else None,
        "strict_mode": strict,
        "api_key_type": "test" if (STRIPE_API_KEY or "").startswith("sk_test_") else (
            "live_or_restricted" if STRIPE_API_KEY else "missing"
        ),
    }
