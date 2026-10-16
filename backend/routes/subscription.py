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
    • Subscription user updates are never taken from the request body. The
      handler re-fetches the subscription from Stripe and applies that object.
"""
from __future__ import annotations

import json
import os
import logging
from datetime import datetime, timezone
from typing import Optional

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
from subscription_sync import subscription_write_from_stripe

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


def _event_dict(event) -> Optional[dict]:
    if isinstance(event, dict):
        return event
    if hasattr(event, "to_dict_recursive"):
        converted = event.to_dict_recursive()
        return converted if isinstance(converted, dict) else None
    if hasattr(event, "to_dict"):
        converted = event.to_dict()
        return converted if isinstance(converted, dict) else None
    return None


def _stripe_miss(exc: Exception) -> bool:
    """True when Stripe has no such subscription. Other failures should retry."""
    status = getattr(exc, "http_status", None)
    code = getattr(exc, "code", None)
    return status == 404 or code == "resource_missing"


@router.post("/webhook/stripe-subscription")
async def stripe_subscription_webhook(request: Request):
    """Stripe lifecycle webhook for subscription events.

    The request body is only used to learn the event type and subscription id.
    Pro access is copied from Subscription.retrieve, never from the JSON a
    caller posted. STRIPE_WEBHOOK_STRICT=true still rejects a bad signature
    before that lookup.
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
                f"[webhook] signature mismatch (lenient mode, will not trust body fields): {e}"
            )

    if event is None:
        try:
            event = json.loads(body.decode("utf-8"))
        except Exception as e:
            logger.error(f"[webhook] body parse failed: {e}")
            return JSONResponse({"received": False, "error": "bad_json"}, status_code=400)

    event = _event_dict(event)
    if not isinstance(event, dict):
        return JSONResponse({"received": False, "error": "bad_json"}, status_code=400)

    etype = event.get("type")
    obj = (event.get("data") or {}).get("object") or {}
    if not isinstance(obj, dict):
        obj = {}

    if etype not in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        # Invoice and other events are acknowledged. Payment status in the body
        # is not applied; a forged invoice used to be able to mark rows paid.
        return {"received": True, "verified": verified, "applied": False}

    sub_id = obj.get("id")
    if not isinstance(sub_id, str) or not sub_id.startswith("sub_"):
        return {"received": True, "verified": verified, "applied": False}

    try:
        retrieved = stripe_sdk.Subscription.retrieve(sub_id)
    except Exception as e:
        if _stripe_miss(e):
            logger.info(f"[webhook] ignoring unknown subscription {sub_id}: {e}")
            return {"received": True, "verified": verified, "applied": False}
        logger.error(f"[webhook] could not retrieve subscription {sub_id}: {e}")
        return JSONResponse({"received": False, "error": "stripe_unavailable"}, status_code=503)

    decision = subscription_write_from_stripe(retrieved)
    if not decision:
        logger.info(f"[webhook] retrieved subscription {sub_id} had no applicable customer/status")
        return {"received": True, "verified": verified, "applied": False}

    customer_id = decision["customer_id"]
    user = await db.users.find_one(
        {"subscription.stripe_customer_id": customer_id}, {"_id": 0}
    )
    if not user:
        return {"received": True, "verified": verified, "applied": False}

    sub_set = dict(decision["set"])
    retrieved_status = sub_set.get("subscription.status")
    retrieved_sub_id = sub_set.get("subscription.stripe_subscription_id")
    # The event type in the body is not a source of truth. A forged
    # "deleted" event must not skip this check while Stripe still says active.
    from entitlements import webhook_regrant_blocked
    if webhook_regrant_blocked(user, None, retrieved_sub_id, retrieved_status):
        logger.info(
            f"[webhook] ignoring {etype} for admin-revoked subscription {retrieved_sub_id}"
        )
        return {"received": True, "verified": verified, "applied": False, "ignored": "admin_revoke"}
    if retrieved_status == "active":
        sub_set["subscription.revoked_by_admin"] = False
    sub_set["subscription.updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": sub_set})
    logger.info(
        f"[webhook] {etype} user={user['user_id']} status={sub_set.get('subscription.status')} verified={verified}"
    )
    return {"received": True, "verified": verified, "applied": True}


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
