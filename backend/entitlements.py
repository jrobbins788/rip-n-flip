"""Pro entitlement rules shared by feature gates, the admin user list, and
admin grant/revoke.

Paid Stripe rows, admin comps, and DUB STREAK rewards all have to agree.
A subscription marked active is only Pro through current_period_end when
that timestamp is present. A reward is only Pro through pro_until.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

TRIAL_DURATION_DAYS = 10


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def parse_iso_datetime(value: object) -> Optional[datetime]:
    if isinstance(value, datetime):
        return _as_utc(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return _as_utc(datetime.fromisoformat(value))
    except ValueError:
        return None


def subscription_grants_pro(user: dict, now: datetime) -> bool:
    sub = user.get("subscription") or {}
    if sub.get("status") != "active":
        return False
    raw_end = sub.get("current_period_end")
    if raw_end is None or raw_end == "":
        return True
    end = parse_iso_datetime(raw_end)
    if end is None:
        return False
    return end > now


def reward_grants_pro(user: dict, now: datetime) -> bool:
    if user.get("tier") != "pro":
        return False
    raw_until = user.get("pro_until")
    if not isinstance(raw_until, str) or not raw_until.strip():
        return True
    until = parse_iso_datetime(raw_until)
    if until is None:
        return True
    return until > now


def user_record_is_pro(user: dict, now: Optional[datetime] = None) -> bool:
    """Paid, comped, or rewarded Pro. The signup trial is separate."""
    now = now or datetime.now(timezone.utc)
    return subscription_grants_pro(user, now) or reward_grants_pro(user, now)


def signup_trial_active(user: dict, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    created = parse_iso_datetime(user.get("created_at"))
    if not created:
        return False
    return (now - created) <= timedelta(days=TRIAL_DURATION_DAYS)


def admin_display_tier(user: dict, now: Optional[datetime] = None) -> str:
    """Label shown in the admin user table. Trial is not Pro."""
    now = now or datetime.now(timezone.utc)
    if user_record_is_pro(user, now):
        return "pro"
    if signup_trial_active(user, now):
        return "trial"
    return "free"


def build_admin_grant_update(user: dict, days: int, now: datetime) -> dict:
    """Extend Pro to at least now+days without shortening a longer window."""
    if days < 1:
        raise ValueError("days must be at least 1")
    period_end = now + timedelta(days=days)
    for raw in (
        user.get("pro_until"),
        (user.get("subscription") or {}).get("current_period_end"),
    ):
        parsed = parse_iso_datetime(raw)
        if parsed and parsed > period_end:
            period_end = parsed
    iso_end = period_end.isoformat()
    return {
        "$set": {
            "tier": "pro",
            "pro_until": iso_end,
            "pro_source": "admin_grant",
            "subscription.status": "active",
            "subscription.granted_by_admin": True,
            "subscription.revoked_by_admin": False,
            "subscription.current_period_end": iso_end,
            "subscription.granted_at": now.isoformat(),
        }
    }


def build_admin_revoke_update(now: datetime) -> dict:
    """Clear every field the Pro checks read."""
    iso_now = now.isoformat()
    return {
        "$set": {
            "tier": "free",
            "pro_until": iso_now,
            "pro_source": "admin_revoke",
            "subscription.status": "canceled",
            "subscription.granted_by_admin": False,
            "subscription.revoked_by_admin": True,
            "subscription.revoked_at": iso_now,
            "subscription.current_period_end": iso_now,
        }
    }


_COMP_OR_REWARD_SOURCES = frozenset({"admin_grant", "dub_streak_reward"})


def preserve_comp_and_reward_pro(user: dict, fields: dict, now: datetime) -> dict:
    """Keep a live admin comp or DUB STREAK reward across a Stripe subscription write.

    Those windows live in ``tier`` and ``pro_until``. An active subscription
    webhook copies Stripe's period end over them, and a canceled webhook sets
    ``tier`` to free. The next renewal, invoice, or cancellation then ends a
    longer comp early. Stripe's status and period end are still recorded.
    A longer Stripe period is allowed to take over, since it already covers
    the comp.
    """
    merged = dict(fields)
    if (user or {}).get("pro_source") not in _COMP_OR_REWARD_SOURCES:
        return merged
    existing_until = parse_iso_datetime((user or {}).get("pro_until"))
    if existing_until is None or existing_until <= _as_utc(now):
        return merged
    incoming_until = parse_iso_datetime(merged.get("pro_until"))
    if incoming_until is not None and incoming_until >= existing_until:
        return merged
    merged["pro_until"] = existing_until.isoformat()
    if merged.get("tier") == "free":
        merged["tier"] = "pro"
    # Leave the stored source in place so a later cancel still sees the comp.
    merged.pop("pro_source", None)
    return merged


def webhook_regrant_blocked(
    user: dict,
    event_type: Optional[str],
    subscription_id: Optional[str],
    status: Optional[str],
) -> bool:
    """An admin revoke must survive a later 'active' webhook for that same subscription."""
    sub = (user or {}).get("subscription") or {}
    if not sub.get("revoked_by_admin"):
        return False
    if event_type == "customer.subscription.deleted":
        return False
    if status != "active":
        return False
    stored_id = sub.get("stripe_subscription_id")
    if not subscription_id or not stored_id:
        return False
    return subscription_id == stored_id
