"""Release marketplace listings stuck pending after an abandoned checkout.

`POST /payments/checkout` sets the listing to pending as soon as a Stripe
Checkout Session exists. The only path that puts it back to active is
`GET /payments/status/{session_id}`, and the client calls that only from the
payment-success page. A buyer who closes the Stripe tab never hits that page,
so the listing stays pending and disappears from the marketplace.

Stripe expires an unpaid Checkout Session after 24 hours. After that window
we re-fetch the session and, when Stripe says it is expired and unpaid, put
the listing back on sale. Cash App trades also use pending; an open trade
keeps its hold.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

CHECKOUT_HOLD = timedelta(hours=24)

# Stripe session statuses that can no longer be paid.
_TERMINAL_UNPAID = frozenset({"expired", "failed"})

# A Checkout Session can be `complete` while payment_status stays `unpaid`
# for Klarna, Afterpay, and Affirm. The PaymentIntent then ends on one of
# these when the delayed payment fails. `processing` is still in flight and
# must keep the hold.
_FAILED_PAYMENT_INTENTS = frozenset({"canceled", "requires_payment_method"})


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _as_utc(now: datetime) -> datetime:
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now


def session_state(session) -> tuple[Optional[str], Optional[str]]:
    """Return (session.status, session.payment_status) from a Stripe object or dict."""
    if session is None:
        return None, None
    if isinstance(session, dict):
        return session.get("status"), session.get("payment_status")
    return getattr(session, "status", None), getattr(session, "payment_status", None)


def _payment_intent(session):
    if session is None:
        return None
    if isinstance(session, dict):
        return session.get("payment_intent")
    return getattr(session, "payment_intent", None)


def payment_intent_status(session) -> Optional[str]:
    """Status of an expanded PaymentIntent. An unexpanded id returns None."""
    raw = _payment_intent(session)
    if raw is None or isinstance(raw, str):
        return None
    if isinstance(raw, dict):
        status = raw.get("status")
    else:
        status = getattr(raw, "status", None)
    return status if isinstance(status, str) else None


def payment_intent_id(session) -> Optional[str]:
    """Id to retrieve when the session did not expand the PaymentIntent."""
    raw = _payment_intent(session)
    if isinstance(raw, str) and raw.startswith("pi_"):
        return raw
    return None


def delayed_payment_failed(
    session_status: Optional[str],
    payment_status: Optional[str],
    intent_status: Optional[str],
) -> bool:
    """True when a finished Checkout Session's delayed payment has failed.

    `complete` + `unpaid` is also the in-flight state (`processing`). Releasing
    on that alone lets a second buyer pay for a card the first payment can
    still capture.
    """
    return (
        session_status == "complete"
        and payment_status != "paid"
        and intent_status in _FAILED_PAYMENT_INTENTS
    )


def session_expires_at(session) -> Optional[datetime]:
    raw = session.get("expires_at") if isinstance(session, dict) else getattr(session, "expires_at", None)
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if raw is None:
        return None
    try:
        return datetime.fromtimestamp(int(raw), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _is_checkout_txn(txn: dict) -> bool:
    return (
        isinstance(txn, dict)
        and txn.get("type") != "subscription"
        and isinstance(txn.get("session_id"), str)
        and bool(txn.get("session_id"))
    )


def decide_pending_listing(
    *,
    pending_since: Optional[str],
    transactions: Sequence[dict],
    session_states: dict,
    has_open_trade: bool,
    now: datetime,
    hold: timedelta = CHECKOUT_HOLD,
    intent_states: Optional[dict] = None,
) -> str:
    """Return the listing status to store: 'sold', 'active', or 'pending'.

    `session_states` maps session_id -> (status, payment_status) for sessions
    Stripe actually returned. A missing entry means we did not confirm the
    session, and the hold stays so a failed lookup cannot relist a paid card.
    `intent_states` maps session_id -> PaymentIntent status. A completed
    session whose intent is canceled or requires_payment_method is no longer
    a hold. An unknown or processing intent stays a hold.
    """
    now = _as_utc(now)
    cutoff = now - hold
    intent_states = intent_states or {}
    checkout_txns = [t for t in transactions if _is_checkout_txn(t)]

    def _stripe_paid(txn: dict) -> bool:
        if txn.get("payment_status") == "paid":
            return True
        state = session_states.get(txn.get("session_id"))
        return bool(state and state[1] == "paid")

    if any(_stripe_paid(t) for t in checkout_txns):
        return "sold"
    if has_open_trade:
        return "pending"

    def _holds_listing(txn: dict) -> bool:
        if txn.get("payment_status") in ("expired", "failed"):
            return False
        state = session_states.get(txn.get("session_id"))
        if state is not None:
            session_status, payment_status = state
            if session_status in _TERMINAL_UNPAID:
                return False
            if delayed_payment_failed(
                session_status,
                payment_status,
                intent_states.get(txn.get("session_id")),
            ):
                return False
            # Still open, or a delayed payment that is complete but unpaid.
            return True
        created = _parse_iso(txn.get("created_at"))
        if created is None or created > cutoff:
            return True
        # Older than the hold, and Stripe was not consulted. Keep the hold.
        return True

    if checkout_txns and not any(_holds_listing(t) for t in checkout_txns):
        return "active"
    if checkout_txns:
        return "pending"

    claimed_at = _parse_iso(pending_since)
    if claimed_at is not None and claimed_at <= cutoff:
        # Claimed for checkout, then the process died before writing a transaction.
        return "active"
    return "pending"


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def reconcile_abandoned_checkouts(db, retrieve_session, now: Optional[datetime] = None) -> list[str]:
    """Put abandoned checkout listings back on sale. Returns listing ids changed.

    `retrieve_session(session_id)` may be sync or async. Failures are skipped
    so a Stripe outage leaves the hold in place.
    """
    now = _as_utc(now or datetime.now(timezone.utc))
    cutoff_iso = (now - CHECKOUT_HOLD).isoformat()
    now_iso = now.isoformat()
    changed: list[str] = []

    stale_cursor = db.payment_transactions.find(
        {
            "listing_id": {"$type": "string"},
            "session_id": {"$type": "string"},
            "payment_status": {"$nin": ["paid", "expired", "failed"]},
            "created_at": {"$lt": cutoff_iso},
            "$and": [
                {"$or": [
                    {"type": {"$exists": False}},
                    {"type": {"$ne": "subscription"}},
                ]},
                {"$or": [
                    {"hold_recheck_after": {"$exists": False}},
                    {"hold_recheck_after": None},
                    {"hold_recheck_after": {"$lte": now_iso}},
                ]},
            ],
        },
        {"_id": 0, "listing_id": 1, "session_id": 1},
    ).limit(20)
    stale_txns = await stale_cursor.to_list(20)

    listing_ids: list[str] = []
    seen: set[str] = set()
    for txn in stale_txns:
        listing_id = txn.get("listing_id")
        if isinstance(listing_id, str) and listing_id not in seen:
            seen.add(listing_id)
            listing_ids.append(listing_id)

    orphan_cursor = db.listings.find(
        {"status": "pending", "pending_since": {"$lt": cutoff_iso}},
        {"_id": 0, "listing_id": 1},
    ).limit(20)
    for listing in await orphan_cursor.to_list(20):
        listing_id = listing.get("listing_id")
        if isinstance(listing_id, str) and listing_id not in seen:
            seen.add(listing_id)
            listing_ids.append(listing_id)

    for listing_id in listing_ids:
        listing = await db.listings.find_one(
            {"listing_id": listing_id},
            {"_id": 0, "status": 1, "pending_since": 1},
        )
        if not listing or listing.get("status") != "pending":
            if listing and listing.get("status") == "active":
                await db.payment_transactions.update_many(
                    {"listing_id": listing_id, "payment_status": {"$nin": ["paid", "expired", "failed"]}},
                    {"$set": {"payment_status": "expired"}},
                )
            elif listing:
                await db.payment_transactions.update_many(
                    {"listing_id": listing_id, "payment_status": {"$nin": ["paid", "expired", "failed"]}},
                    {"$set": {"hold_recheck_after": (now + timedelta(days=7)).isoformat()}},
                )
            continue

        txns = await db.payment_transactions.find(
            {"listing_id": listing_id},
            {"_id": 0},
        ).to_list(50)
        trade = await db.trades.find_one(
            {"listing_id": listing_id, "status": {"$in": ["awaiting_payment", "paid"]}},
            {"_id": 0, "trade_id": 1},
        )

        session_states: dict = {}
        intent_states: dict = {}
        open_recheck: dict[str, datetime] = {}
        for txn in txns:
            if not _is_checkout_txn(txn):
                continue
            if txn.get("payment_status") in ("paid", "expired", "failed"):
                continue
            created = _parse_iso(txn.get("created_at"))
            if created is not None and created > now - CHECKOUT_HOLD:
                continue
            session_id = txn["session_id"]
            try:
                session = await _maybe_await(retrieve_session(session_id))
            except Exception:
                continue
            state = session_state(session)
            session_states[session_id] = state
            session_status, payment_status = state
            intent_status = payment_intent_status(session)
            if intent_status:
                intent_states[session_id] = intent_status
            if session_status == "open":
                expires = session_expires_at(session)
                open_recheck[session_id] = expires if expires and expires > now else now + timedelta(hours=1)
            elif (
                session_status == "complete"
                and payment_status != "paid"
                and not delayed_payment_failed(session_status, payment_status, intent_status)
            ):
                # Money may still be in flight. Look again, but do not relist.
                open_recheck[session_id] = now + timedelta(hours=6)

        decision = decide_pending_listing(
            pending_since=listing.get("pending_since"),
            transactions=txns,
            session_states=session_states,
            has_open_trade=trade is not None,
            now=now,
            intent_states=intent_states,
        )
        if decision == "sold":
            result = await db.listings.update_one(
                {"listing_id": listing_id, "status": "pending"},
                {"$set": {"status": "sold"}, "$unset": {"pending_since": ""}},
            )
            for session_id, (_session_status, payment_status) in session_states.items():
                if payment_status == "paid":
                    await db.payment_transactions.update_one(
                        {"session_id": session_id, "payment_status": {"$ne": "paid"}},
                        {"$set": {"payment_status": "paid"}},
                    )
            if getattr(result, "modified_count", 0):
                changed.append(listing_id)
            continue

        if decision == "active":
            result = await db.listings.update_one(
                {"listing_id": listing_id, "status": "pending"},
                {"$set": {"status": "active"}, "$unset": {"pending_since": ""}},
            )
            if getattr(result, "modified_count", 0):
                changed.append(listing_id)
                await db.payment_transactions.update_many(
                    {"listing_id": listing_id, "payment_status": {"$nin": ["paid"]}},
                    {"$set": {"payment_status": "expired"}},
                )
            continue

        # Still pending. Remember terminal or still-open sessions so the next
        # page view does not call Stripe again for the same answer.
        for session_id, (session_status, payment_status) in session_states.items():
            if payment_status == "paid":
                await db.payment_transactions.update_one(
                    {"session_id": session_id, "payment_status": {"$ne": "paid"}},
                    {"$set": {"payment_status": "paid"}},
                )
            elif session_status in _TERMINAL_UNPAID:
                await db.payment_transactions.update_one(
                    {"session_id": session_id, "payment_status": {"$nin": ["paid"]}},
                    {"$set": {"payment_status": "expired", "status": session_status}},
                )
            elif session_id in open_recheck:
                await db.payment_transactions.update_one(
                    {"session_id": session_id},
                    {"$set": {"hold_recheck_after": open_recheck[session_id].isoformat()}},
                )
        if trade is not None:
            await db.payment_transactions.update_many(
                {"listing_id": listing_id, "payment_status": {"$nin": ["paid", "expired", "failed"]}},
                {"$set": {"hold_recheck_after": (now + timedelta(hours=24)).isoformat()}},
            )
    return changed


async def release_failed_checkout_hold(db, *, session_id: str, transaction: dict) -> bool:
    """Put a listing back on sale after its delayed payment has failed.

    A newer checkout or an open Cash App trade keeps the card. The failed
    session is recorded either way so it cannot keep holding the listing.
    """
    if not isinstance(transaction, dict) or transaction.get("payment_status") == "paid":
        return False
    listing_id = transaction.get("listing_id")
    if not isinstance(listing_id, str) or not listing_id:
        return False

    newer_query = {
        "listing_id": listing_id,
        "session_id": {"$ne": session_id},
        "payment_status": {"$nin": ["expired", "failed"]},
    }
    created_at = transaction.get("created_at")
    if isinstance(created_at, str) and created_at:
        newer_query["created_at"] = {"$gt": created_at}
    newer_hold = await db.payment_transactions.find_one(
        newer_query, {"_id": 0, "session_id": 1}
    )
    open_trade = await db.trades.find_one(
        {
            "listing_id": listing_id,
            "status": {"$in": ["awaiting_payment", "paid"]},
        },
        {"_id": 0, "trade_id": 1},
    )
    await db.payment_transactions.update_one(
        {"session_id": session_id, "payment_status": {"$nin": ["paid"]}},
        {"$set": {"payment_status": "failed", "status": "complete"}},
    )
    if newer_hold or open_trade:
        return False
    result = await db.listings.update_one(
        {"listing_id": listing_id, "status": "pending"},
        {"$set": {"status": "active"}, "$unset": {"pending_since": ""}},
    )
    return bool(getattr(result, "modified_count", 0))
