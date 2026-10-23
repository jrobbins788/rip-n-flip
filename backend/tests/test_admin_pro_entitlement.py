"""Admin Pro grant expires, and revoke actually removes Pro."""
import asyncio
import copy
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ripnflip_test")
os.environ.setdefault("JWT_SECRET", "test")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vendor"))

from entitlements import (
    admin_display_tier,
    build_admin_grant_update,
    build_admin_revoke_update,
    preserve_comp_and_reward_pro,
    user_record_is_pro,
    webhook_regrant_blocked,
)


def _apply(user: dict, update: dict) -> dict:
    out = copy.deepcopy(user)
    for key, value in update["$set"].items():
        cursor = out
        parts = key.split(".")
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[parts[-1]] = value
    return out


def _user(**extra):
    base = {
        "user_id": "user_test",
        "created_at": (datetime.now(timezone.utc) - timedelta(days=40)).isoformat(),
        "tier": "free",
        "subscription": {},
    }
    base.update(extra)
    return base


def test_active_subscription_with_past_period_end_is_not_pro():
    now = datetime.now(timezone.utc)
    user = _user(
        subscription={
            "status": "active",
            "current_period_end": (now - timedelta(days=1)).isoformat(),
        }
    )
    assert user_record_is_pro(user, now) is False
    assert admin_display_tier(user, now) == "free"


def test_active_subscription_inside_period_is_pro():
    now = datetime.now(timezone.utc)
    user = _user(
        subscription={
            "status": "active",
            "current_period_end": (now + timedelta(days=10)).isoformat(),
        }
    )
    assert user_record_is_pro(user, now) is True


def test_reward_pro_survives_until_pro_until_then_stops():
    now = datetime.now(timezone.utc)
    user = _user(
        tier="pro",
        pro_until=(now + timedelta(days=7)).isoformat(),
        pro_source="dub_streak_reward",
        subscription={"status": "canceled"},
    )
    assert user_record_is_pro(user, now) is True
    later = now + timedelta(days=8)
    assert user_record_is_pro(user, later) is False


def test_admin_grant_sets_fields_feature_gates_read_and_expires():
    now = datetime.now(timezone.utc)
    user = _user()
    granted = _apply(user, build_admin_grant_update(user, 30, now))
    assert granted["tier"] == "pro"
    assert granted["subscription"]["status"] == "active"
    assert granted["subscription"]["revoked_by_admin"] is False
    assert user_record_is_pro(granted, now + timedelta(days=29)) is True
    assert user_record_is_pro(granted, now + timedelta(days=31)) is False
    assert admin_display_tier(granted, now + timedelta(days=31)) == "free"


def test_admin_grant_does_not_shorten_a_longer_window():
    now = datetime.now(timezone.utc)
    longer = (now + timedelta(days=60)).isoformat()
    user = _user(
        tier="pro",
        pro_until=longer,
        subscription={"status": "active", "current_period_end": longer},
    )
    granted = _apply(user, build_admin_grant_update(user, 30, now))
    assert granted["pro_until"] == longer
    assert granted["subscription"]["current_period_end"] == longer


def test_revoke_removes_stripe_and_reward_pro_and_blocks_same_subscription_webhook():
    now = datetime.now(timezone.utc)
    user = _user(
        tier="pro",
        pro_until=(now + timedelta(days=20)).isoformat(),
        pro_source="stripe_subscription",
        subscription={
            "status": "active",
            "stripe_subscription_id": "sub_live",
            "current_period_end": (now + timedelta(days=20)).isoformat(),
        },
    )
    assert user_record_is_pro(user, now) is True
    assert admin_display_tier(user, now) == "pro"

    revoked = _apply(user, build_admin_revoke_update(now))
    assert revoked["tier"] == "free"
    assert revoked["subscription"]["status"] == "canceled"
    assert revoked["subscription"]["revoked_by_admin"] is True
    assert revoked["subscription"]["stripe_subscription_id"] == "sub_live"
    assert user_record_is_pro(revoked, now) is False
    assert admin_display_tier(revoked, now) == "free"

    assert webhook_regrant_blocked(revoked, "customer.subscription.updated", "sub_live", "active") is True
    assert webhook_regrant_blocked(revoked, "customer.subscription.deleted", "sub_live", "canceled") is False
    assert webhook_regrant_blocked(revoked, "customer.subscription.created", "sub_new", "active") is False


def test_signup_trial_is_not_labeled_pro():
    now = datetime.now(timezone.utc)
    user = _user(created_at=(now - timedelta(days=2)).isoformat())
    assert user_record_is_pro(user, now) is False
    assert admin_display_tier(user, now) == "trial"


def test_grant_endpoint_writes_expiring_pro_fields():
    import server
    from fastapi import HTTPException

    user = _user()
    updates = []

    class Users:
        async def find_one(self, *args, **kwargs):
            return user

        async def update_one(self, filt, update):
            updates.append(update)

    class DB:
        users = Users()

    async def run():
        with patch.object(server, "require_admin", new=AsyncMock(return_value={"user_id": "admin"})), \
             patch.object(server, "db", DB()):
            try:
                await server.admin_grant_pro("user_test", MagicMock(), days=0)
                raise AssertionError("days=0 should be rejected")
            except HTTPException as exc:
                assert exc.status_code == 400
            result = await server.admin_grant_pro("user_test", MagicMock(), days=30)
        assert result["granted"] is True
        written = updates[0]["$set"]
        assert written["tier"] == "pro"
        assert written["subscription.status"] == "active"
        assert written["subscription.revoked_by_admin"] is False
        granted = _apply(user, updates[0])
        assert user_record_is_pro(granted) is True

    asyncio.run(run())


def test_revoke_endpoint_clears_pro_and_cancels_stripe():
    import server

    user = _user(
        tier="pro",
        pro_until="2099-01-01T00:00:00+00:00",
        subscription={"status": "active", "stripe_subscription_id": "sub_live"},
    )
    updates = []

    class Users:
        async def find_one(self, *args, **kwargs):
            return user

        async def update_one(self, filt, update):
            updates.append((filt, update))

    class DB:
        users = Users()

    async def run():
        with patch.object(server, "require_admin", new=AsyncMock(return_value={"user_id": "admin"})), \
             patch.object(server, "db", DB()), \
             patch.object(server, "STRIPE_API_KEY", "sk_test_real"), \
             patch.object(server.stripe_sdk.Subscription, "cancel", return_value={"id": "sub_live"}) as cancel:
            result = await server.admin_revoke_pro("user_test", MagicMock())
        assert result == {"revoked": True, "user_id": "user_test"}
        cancel.assert_called_once_with("sub_live")
        written = updates[0][1]["$set"]
        assert updates[0][0] == {"user_id": "user_test"}
        assert written["tier"] == "free"
        assert written["pro_source"] == "admin_revoke"
        assert written["subscription.status"] == "canceled"
        assert written["subscription.revoked_by_admin"] is True
        revoked = _apply(user, updates[0][1])
        assert user_record_is_pro(revoked) is False

    asyncio.run(run())


def test_revoke_endpoint_still_clears_pro_when_stripe_cancel_fails():
    import server

    user = _user(
        tier="pro",
        pro_until="2099-01-01T00:00:00+00:00",
        subscription={"status": "active", "stripe_subscription_id": "sub_live"},
    )
    updates = []

    class Users:
        async def find_one(self, *args, **kwargs):
            return user

        async def update_one(self, filt, update):
            updates.append(update)

    class DB:
        users = Users()

    async def run():
        with patch.object(server, "require_admin", new=AsyncMock(return_value={"user_id": "admin"})), \
             patch.object(server, "db", DB()), \
             patch.object(server, "STRIPE_API_KEY", "sk_test_real"), \
             patch.object(server.stripe_sdk.Subscription, "cancel", side_effect=RuntimeError("stripe down")):
            result = await server.admin_revoke_pro("user_test", MagicMock())
        assert result["revoked"] is True
        assert updates[0]["$set"]["tier"] == "free"

    asyncio.run(run())


def test_webhook_does_not_restore_pro_after_admin_revoke():
    import routes.subscription as subscription

    user = _user(
        tier="free",
        subscription={
            "status": "canceled",
            "stripe_customer_id": "cus_1",
            "stripe_subscription_id": "sub_live",
            "revoked_by_admin": True,
        },
    )
    updates = []

    class Users:
        async def find_one(self, *args, **kwargs):
            return user

        async def update_one(self, *args, **kwargs):
            updates.append(args)

    class DB:
        users = Users()

    body = json.dumps({
        "type": "customer.subscription.updated",
        "data": {"object": {
            "id": "sub_live",
            "customer": "cus_1",
            "status": "active",
            "current_period_end": 1893456000,
            "cancel_at_period_end": False,
        }},
    }).encode()

    class Request:
        headers = {}

        async def body(self):
            return body

    retrieved = {
        "id": "sub_live",
        "customer": "cus_1",
        "status": "active",
        "current_period_end": 1893456000,
        "cancel_at_period_end": False,
    }

    async def run():
        with patch.object(subscription, "db", DB()), patch.object(
            subscription.stripe_sdk.Subscription, "retrieve", return_value=retrieved
        ) as retrieve:
            result = await subscription.stripe_subscription_webhook(Request())
        retrieve.assert_called_once_with("sub_live")
        assert result["ignored"] == "admin_revoke"
        assert result["applied"] is False
        assert updates == []

    asyncio.run(run())


def test_forged_deleted_event_cannot_bypass_admin_revoke():
    """Body type is not trusted. Stripe still reporting active must not restore Pro."""
    import routes.subscription as subscription

    user = _user(
        tier="free",
        subscription={
            "status": "canceled",
            "stripe_customer_id": "cus_1",
            "stripe_subscription_id": "sub_live",
            "revoked_by_admin": True,
        },
    )
    updates = []

    class Users:
        async def find_one(self, *args, **kwargs):
            return user

        async def update_one(self, *args, **kwargs):
            updates.append(args)

    class DB:
        users = Users()

    body = json.dumps({
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": "sub_live", "customer": "cus_victim", "status": "canceled"}},
    }).encode()

    class Request:
        headers = {}

        async def body(self):
            return body

    retrieved = {
        "id": "sub_live",
        "customer": "cus_1",
        "status": "active",
        "items": {"data": [{"current_period_end": 1893456000}]},
    }

    async def run():
        with patch.object(subscription, "db", DB()), patch.object(
            subscription.stripe_sdk.Subscription, "retrieve", return_value=retrieved
        ):
            result = await subscription.stripe_subscription_webhook(Request())
        assert result["ignored"] == "admin_revoke"
        assert updates == []

    asyncio.run(run())


def test_stripe_write_keeps_a_longer_admin_grant():
    now = datetime.now(timezone.utc)
    grant_end = (now + timedelta(days=90)).isoformat()
    stripe_end = (now + timedelta(days=10)).isoformat()
    user = _user(
        tier="pro",
        pro_until=grant_end,
        pro_source="admin_grant",
        subscription={"status": "active", "current_period_end": grant_end},
    )
    merged = preserve_comp_and_reward_pro(user, {
        "tier": "pro",
        "pro_until": stripe_end,
        "pro_source": "stripe_subscription",
        "subscription.status": "active",
        "subscription.current_period_end": stripe_end,
        "subscription.stripe_subscription_id": "sub_live",
    }, now)
    assert merged["pro_until"] == grant_end
    assert merged["tier"] == "pro"
    assert "pro_source" not in merged
    assert merged["subscription.current_period_end"] == stripe_end
    assert merged["subscription.status"] == "active"
    kept = _apply(user, {"$set": merged})
    assert user_record_is_pro(kept, now + timedelta(days=80)) is True


def test_canceled_stripe_write_keeps_a_live_dub_streak_reward():
    now = datetime.now(timezone.utc)
    reward_end = (now + timedelta(days=12)).isoformat()
    user = _user(
        tier="pro",
        pro_until=reward_end,
        pro_source="dub_streak_reward",
        subscription={"status": "active", "stripe_subscription_id": "sub_live"},
    )
    merged = preserve_comp_and_reward_pro(user, {
        "tier": "free",
        "subscription.status": "canceled",
        "subscription.stripe_subscription_id": "sub_live",
        "subscription.current_period_end": (now - timedelta(hours=1)).isoformat(),
    }, now)
    assert merged["tier"] == "pro"
    assert merged["pro_until"] == reward_end
    assert merged["subscription.status"] == "canceled"
    kept = _apply(user, {"$set": merged})
    assert user_record_is_pro(kept, now + timedelta(days=11)) is True
    assert user_record_is_pro(kept, now + timedelta(days=13)) is False


def test_stripe_cancel_still_ends_stripe_sourced_pro():
    now = datetime.now(timezone.utc)
    user = _user(
        tier="pro",
        pro_until=(now + timedelta(days=10)).isoformat(),
        pro_source="stripe_subscription",
        subscription={"status": "active"},
    )
    merged = preserve_comp_and_reward_pro(user, {
        "tier": "free",
        "subscription.status": "canceled",
    }, now)
    assert merged == {"tier": "free", "subscription.status": "canceled"}
    assert user_record_is_pro(_apply(user, {"$set": merged}), now) is False


def test_expired_reward_does_not_block_a_stripe_cancel():
    now = datetime.now(timezone.utc)
    user = _user(
        tier="pro",
        pro_until=(now - timedelta(days=1)).isoformat(),
        pro_source="dub_streak_reward",
    )
    merged = preserve_comp_and_reward_pro(user, {
        "tier": "free",
        "subscription.status": "canceled",
    }, now)
    assert merged["tier"] == "free"


def test_longer_stripe_period_replaces_a_shorter_reward():
    now = datetime.now(timezone.utc)
    stripe_end = (now + timedelta(days=30)).isoformat()
    user = _user(
        tier="pro",
        pro_until=(now + timedelta(days=5)).isoformat(),
        pro_source="dub_streak_reward",
    )
    merged = preserve_comp_and_reward_pro(user, {
        "tier": "pro",
        "pro_until": stripe_end,
        "pro_source": "stripe_subscription",
        "subscription.status": "active",
    }, now)
    assert merged["pro_until"] == stripe_end
    assert merged["pro_source"] == "stripe_subscription"


def test_active_webhook_does_not_shorten_an_admin_grant():
    import routes.subscription as subscription

    now = datetime.now(timezone.utc)
    grant_end = (now + timedelta(days=90)).isoformat()
    user = _user(
        tier="pro",
        pro_until=grant_end,
        pro_source="admin_grant",
        subscription={
            "status": "active",
            "stripe_customer_id": "cus_1",
            "stripe_subscription_id": "sub_live",
            "current_period_end": grant_end,
        },
    )
    updates = []

    class Users:
        async def find_one(self, *args, **kwargs):
            return user

        async def update_one(self, *args, **kwargs):
            updates.append(args)

    class DB:
        users = Users()

    body = json.dumps({
        "type": "customer.subscription.updated",
        "data": {"object": {"id": "sub_live", "customer": "cus_1", "status": "active"}},
    }).encode()

    class Request:
        headers = {}

        async def body(self):
            return body

    stripe_end = int((now + timedelta(days=10)).timestamp())
    retrieved = {
        "id": "sub_live",
        "customer": "cus_1",
        "status": "active",
        "current_period_end": stripe_end,
        "cancel_at_period_end": False,
    }

    async def run():
        with patch.object(subscription, "db", DB()), patch.object(
            subscription.stripe_sdk.Subscription, "retrieve", return_value=retrieved
        ):
            result = await subscription.stripe_subscription_webhook(Request())
        assert result["applied"] is True
        written = updates[0][1]["$set"]
        assert written["pro_until"] == grant_end
        assert written["tier"] == "pro"
        assert "pro_source" not in written
        assert written["subscription.status"] == "active"
        kept = _apply(user, updates[0][1])
        assert user_record_is_pro(kept, now + timedelta(days=80)) is True

    asyncio.run(run())
