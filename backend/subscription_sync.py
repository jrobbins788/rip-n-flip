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

    period_end = data.get("current_period_end")
    period_end_iso = None
    if isinstance(period_end, (int, float)) and not isinstance(period_end, bool) and period_end > 0:
        period_end_iso = datetime.fromtimestamp(int(period_end), tz=timezone.utc).isoformat()

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
