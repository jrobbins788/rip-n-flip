"""Subscription writes taken from a Stripe Subscription object.

Webhook bodies are not a source of truth. Callers must pass the object returned
by Subscription.retrieve. A forged event can name any customer and status;
only the retrieved subscription is applied.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


def _as_mapping(sub: Any) -> Optional[dict]:
    if isinstance(sub, dict):
        return sub
    if hasattr(sub, "to_dict_recursive"):
        converted = sub.to_dict_recursive()
        return converted if isinstance(converted, dict) else None
    if hasattr(sub, "to_dict"):
        converted = sub.to_dict()
        return converted if isinstance(converted, dict) else None
    return None


def _positive_unix(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value <= 0:
        return None
    return int(value)


def _period_end_unix(data: dict) -> Optional[int]:
    """Stripe API 2025-03-31+ stores current_period_end on the subscription item.

    Older API versions still send it on the subscription. stripe-python 14
    requests 2026-01-28.clover, which only returns the item field. Without
    that timestamp an active subscription would not set pro_until.
    """
    top = _positive_unix(data.get("current_period_end"))
    if top is not None:
        return top
    items = data.get("items")
    rows = items.get("data") if isinstance(items, dict) else None
    if not isinstance(rows, list):
        return None
    ends = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        parsed = _positive_unix(row.get("current_period_end"))
        if parsed is not None:
            ends.append(parsed)
    return max(ends) if ends else None


def metadata_user_id(sub: Any) -> Optional[str]:
    """User id this app stored on the Stripe subscription, if it is one of ours.

    Checkout copies ``metadata.user_id`` onto the subscription. The webhook
    must read it from Subscription.retrieve, never from the event body.
    """
    data = _as_mapping(sub) or {}
    meta = data.get("metadata")
    if not isinstance(meta, dict):
        return None
    user_id = meta.get("user_id")
    if isinstance(user_id, str) and user_id.startswith("user_"):
        return user_id
    return None


def subscription_write_from_stripe(sub: Any) -> Optional[dict]:
    """Return ``{"customer_id", "set"}`` or None when nothing may be written.

    ``set`` is a Mongo ``$set`` document. Callers stamp ``subscription.updated_at``.
    """
    data = _as_mapping(sub)
    if not data:
        return None

    customer_id = data.get("customer")
    if isinstance(customer_id, dict):
        customer_id = customer_id.get("id")
    if not isinstance(customer_id, str) or not customer_id.startswith("cus_"):
        return None

    status = data.get("status")
    if not isinstance(status, str) or not status:
        return None

    sub_id = data.get("id")
    if not isinstance(sub_id, str) or not sub_id.startswith("sub_"):
        return None

    period_end = _period_end_unix(data)
    period_end_iso = None
    if period_end is not None:
        period_end_iso = datetime.fromtimestamp(period_end, tz=timezone.utc).isoformat()

    fields = {
        "subscription.status": "canceled" if status == "canceled" else status,
        "subscription.stripe_subscription_id": sub_id,
        "subscription.current_period_end": period_end_iso,
        "subscription.cancel_at_period_end": bool(data.get("cancel_at_period_end", False)),
    }
    if status == "active" and period_end_iso:
        fields["tier"] = "pro"
        fields["pro_until"] = period_end_iso
        fields["pro_source"] = "stripe_subscription"
    elif status == "canceled":
        fields["tier"] = "free"
    return {"customer_id": customer_id, "set": fields}
