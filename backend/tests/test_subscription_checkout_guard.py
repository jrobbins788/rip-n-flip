"""Subscription checkout must not bill twice or attach another account's customer."""
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "ripnflip_subscription_checkout_test")
os.environ.setdefault("STRIPE_API_KEY", "sk_test_checkout_guard")
os.environ.setdefault("JWT_SECRET", "checkout-guard-test-secret")
os.environ.setdefault("DISABLE_SCHEDULER", "1")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

import server
from routes.subscription import checkout_claim_is_in_flight, subscription_blocks_new_checkout


def test_admin_comp_without_a_stripe_subscription_can_still_check_out():
    assert subscription_blocks_new_checkout({
        "subscription": {"status": "active", "granted_by_admin": True},
    }) is False


def test_active_stripe_subscription_blocks_another_checkout():
    assert subscription_blocks_new_checkout({
        "subscription": {"status": "active", "stripe_subscription_id": "sub_live"},
    }) is True
    assert subscription_blocks_new_checkout({
        "subscription": {"status": "canceled", "stripe_subscription_id": "sub_old"},
    }) is False


def test_checkout_claim_expires_so_a_dead_request_cannot_lock_upgrades():
    assert checkout_claim_is_in_flight("creating_1_deadbeef", now=1_800_000_000) is False
    assert checkout_claim_is_in_flight("creating_1799999990_abcdef", now=1_800_000_000) is True
    assert checkout_claim_is_in_flight("creating_no_time") is False


def _user(**subscription):
    return {
        "user_id": "user_payer",
        "email": "payer@example.com",
        "name": "Payer",
        "subscription": subscription,
    }


def _db(user, updates):
    mock_db = MagicMock()

    async def find_one(query, projection=None):
        if query.get("subscription.stripe_customer_id"):
            return None
        if projection and "subscription.stripe_customer_id" in projection:
            return {"subscription": {"stripe_customer_id": "cus_winner"}}
        return user

    async def update_one(query, update, upsert=False):
        updates.append((query, update))
        if "$set" in update and "subscription.stripe_customer_id" in update["$set"]:
            return SimpleNamespace(modified_count=0, matched_count=0)
        return SimpleNamespace(modified_count=1, matched_count=1)

    mock_db.users.find_one = AsyncMock(side_effect=find_one)
    mock_db.users.update_one = AsyncMock(side_effect=update_one)
    mock_db.payment_transactions.insert_one = AsyncMock()
    return mock_db


def _session(customer_holder):
    def create(**kwargs):
        customer_holder["kwargs"] = kwargs
        return SimpleNamespace(id="cs_test_new", url="https://checkout.stripe.test/new")

    return create


def test_second_click_reuses_the_open_checkout_instead_of_billing_again():
    user = _user(pending_checkout_session_id="cs_test_open")
    mock_db = MagicMock()
    mock_db.users.find_one = AsyncMock(return_value=user)
    mock_db.users.update_one = AsyncMock()
    created = {"n": 0}

    def explode(**kwargs):
        created["n"] += 1
        raise AssertionError("a second Checkout Session must not be created")

    with patch("routes.subscription.require_auth", new=AsyncMock(return_value=user)), patch(
        "routes.subscription.db", mock_db
    ), patch(
        "routes.subscription.stripe_sdk.checkout.Session.retrieve",
        return_value={"id": "cs_test_open", "status": "open", "url": "https://checkout.stripe.test/open"},
    ), patch(
        "routes.subscription.stripe_sdk.checkout.Session.create", side_effect=explode
    ), TestClient(server.app) as client:
        resp = client.post(
            "/api/subscription/checkout",
            json={"origin_url": "https://ripnflipapp.com"},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "url": "https://checkout.stripe.test/open",
        "session_id": "cs_test_open",
    }
    assert created["n"] == 0
    mock_db.users.update_one.assert_not_called()


def test_active_subscription_does_not_open_another_checkout():
    user = _user(status="active", stripe_subscription_id="sub_live", stripe_customer_id="cus_live")
    mock_db = MagicMock()
    mock_db.users.find_one = AsyncMock(return_value=user)
    mock_db.users.update_one = AsyncMock()

    with patch("routes.subscription.require_auth", new=AsyncMock(return_value=user)), patch(
        "routes.subscription.db", mock_db
    ), patch(
        "routes.subscription.stripe_sdk.checkout.Session.create",
        side_effect=AssertionError("must not create a session"),
    ), TestClient(server.app) as client:
        resp = client.post(
            "/api/subscription/checkout",
            json={"origin_url": "https://ripnflipapp.com"},
        )

    assert resp.status_code == 409, resp.text
    mock_db.users.update_one.assert_not_called()


def test_parallel_checkout_bills_the_customer_that_won_the_write():
    """The click that lost the customer-id write must not open a session on its own customer."""
    user = _user()
    updates = []
    mock_db = _db(user, updates)
    held = {}

    with patch("routes.subscription.require_auth", new=AsyncMock(return_value=user)), patch(
        "routes.subscription.db", mock_db
    ), patch(
        "routes.subscription._get_or_create_pro_price", new=AsyncMock(return_value="price_pro")
    ), patch(
        "routes.subscription.stripe_sdk.Customer.list",
        return_value=SimpleNamespace(data=[]),
    ), patch(
        "routes.subscription.stripe_sdk.Customer.create",
        return_value=SimpleNamespace(id="cus_loser"),
    ), patch(
        "routes.subscription.stripe_sdk.checkout.Session.create", side_effect=_session(held)
    ), TestClient(server.app) as client:
        resp = client.post(
            "/api/subscription/checkout",
            json={"origin_url": "https://ripnflipapp.com"},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["session_id"] == "cs_test_new"
    assert held["kwargs"]["customer"] == "cus_winner"
    assert held["kwargs"]["subscription_data"]["metadata"]["user_id"] == "user_payer"
    assert held["kwargs"]["metadata"]["user_id"] == "user_payer"


def test_checkout_does_not_reuse_another_accounts_stripe_customer():
    user = _user()
    updates = []
    mock_db = _db(user, updates)

    async def find_one(query, projection=None):
        if query.get("subscription.stripe_customer_id") == "cus_victim":
            return {"user_id": "user_victim"}
        if projection and "subscription.stripe_customer_id" in projection:
            return {"subscription": {"stripe_customer_id": "cus_new"}}
        return user

    mock_db.users.find_one = AsyncMock(side_effect=find_one)
    held = {}

    with patch("routes.subscription.require_auth", new=AsyncMock(return_value=user)), patch(
        "routes.subscription.db", mock_db
    ), patch(
        "routes.subscription._get_or_create_pro_price", new=AsyncMock(return_value="price_pro")
    ), patch(
        "routes.subscription.stripe_sdk.Customer.list",
        return_value=SimpleNamespace(data=[SimpleNamespace(id="cus_victim")]),
    ), patch(
        "routes.subscription.stripe_sdk.Customer.create",
        return_value=SimpleNamespace(id="cus_new"),
    ) as create_customer, patch(
        "routes.subscription.stripe_sdk.checkout.Session.create", side_effect=_session(held)
    ), TestClient(server.app) as client:
        resp = client.post(
            "/api/subscription/checkout",
            json={"origin_url": "https://ripnflipapp.com"},
        )

    assert resp.status_code == 200, resp.text
    assert create_customer.called
    assert held["kwargs"]["customer"] == "cus_new"
    assert held["kwargs"]["customer"] != "cus_victim"


def test_in_flight_checkout_claim_is_not_replaced():
    user = _user(pending_checkout_session_id=f"creating_{int(time.time())}_abcdef")
    mock_db = MagicMock()
    mock_db.users.find_one = AsyncMock(return_value=user)
    mock_db.users.update_one = AsyncMock()

    with patch("routes.subscription.require_auth", new=AsyncMock(return_value=user)), patch(
        "routes.subscription.db", mock_db
    ), patch(
        "routes.subscription.stripe_sdk.checkout.Session.create",
        side_effect=AssertionError("must not create a session"),
    ), TestClient(server.app) as client:
        resp = client.post(
            "/api/subscription/checkout",
            json={"origin_url": "https://ripnflipapp.com"},
        )

    assert resp.status_code == 409, resp.text
    mock_db.users.update_one.assert_not_called()


def test_abandoned_checkout_claim_can_be_replaced():
    user = _user(pending_checkout_session_id="creating_1_deadbeef", stripe_customer_id="cus_live")
    mock_db = MagicMock()
    mock_db.users.find_one = AsyncMock(return_value=user)
    mock_db.users.update_one = AsyncMock(return_value=SimpleNamespace(modified_count=1, matched_count=1))
    mock_db.payment_transactions.insert_one = AsyncMock()
    held = {}

    with patch("routes.subscription.require_auth", new=AsyncMock(return_value=user)), patch(
        "routes.subscription.db", mock_db
    ), patch(
        "routes.subscription._get_or_create_pro_price", new=AsyncMock(return_value="price_pro")
    ), patch(
        "routes.subscription.stripe_sdk.checkout.Session.create", side_effect=_session(held)
    ), TestClient(server.app) as client:
        resp = client.post(
            "/api/subscription/checkout",
            json={"origin_url": "https://ripnflipapp.com"},
        )

    assert resp.status_code == 200, resp.text
    assert held["kwargs"]["customer"] == "cus_live"
    claim_update = mock_db.users.update_one.await_args_list[0].args[1]
    assert claim_update["$set"]["subscription.pending_checkout_session_id"].startswith("creating_")


def test_completed_checkout_does_not_start_another_payment():
    user = _user(pending_checkout_session_id="cs_test_done", stripe_customer_id="cus_live")
    mock_db = MagicMock()
    mock_db.users.find_one = AsyncMock(return_value=user)
    mock_db.users.update_one = AsyncMock()

    with patch("routes.subscription.require_auth", new=AsyncMock(return_value=user)), patch(
        "routes.subscription.db", mock_db
    ), patch(
        "routes.subscription.stripe_sdk.checkout.Session.retrieve",
        return_value={"id": "cs_test_done", "status": "complete", "url": "https://checkout.stripe.test/done"},
    ), patch(
        "routes.subscription.stripe_sdk.checkout.Session.create",
        side_effect=AssertionError("must not create a session"),
    ), TestClient(server.app) as client:
        resp = client.post(
            "/api/subscription/checkout",
            json={"origin_url": "https://ripnflipapp.com"},
        )

    assert resp.status_code == 409, resp.text
    assert "processing" in resp.json()["detail"]
    mock_db.users.update_one.assert_not_called()


def test_canceled_subscription_can_check_out_again_after_the_old_session_completed():
    user = _user(
        status="canceled",
        stripe_subscription_id="sub_old",
        stripe_customer_id="cus_live",
        pending_checkout_session_id="cs_test_done",
    )
    mock_db = MagicMock()
    mock_db.users.find_one = AsyncMock(return_value=user)
    mock_db.users.update_one = AsyncMock(return_value=SimpleNamespace(modified_count=1, matched_count=1))
    mock_db.payment_transactions.insert_one = AsyncMock()
    held = {}

    with patch("routes.subscription.require_auth", new=AsyncMock(return_value=user)), patch(
        "routes.subscription.db", mock_db
    ), patch(
        "routes.subscription._get_or_create_pro_price", new=AsyncMock(return_value="price_pro")
    ), patch(
        "routes.subscription.stripe_sdk.checkout.Session.retrieve",
        return_value={"id": "cs_test_done", "status": "complete"},
    ), patch(
        "routes.subscription.stripe_sdk.checkout.Session.create", side_effect=_session(held)
    ), TestClient(server.app) as client:
        resp = client.post(
            "/api/subscription/checkout",
            json={"origin_url": "https://ripnflipapp.com"},
        )

    assert resp.status_code == 200, resp.text
    assert held["kwargs"]["customer"] == "cus_live"


def test_extra_session_is_expired_when_the_slot_was_lost():
    user = _user(stripe_customer_id="cus_live")
    mock_db = MagicMock()
    mock_db.users.find_one = AsyncMock(return_value=user)
    expired = {}

    async def update_one(query, update, upsert=False):
        if "$set" in update and str(update["$set"].get("subscription.pending_checkout_session_id", "")).startswith("cs_"):
            return SimpleNamespace(modified_count=0, matched_count=0)
        return SimpleNamespace(modified_count=1, matched_count=1)

    mock_db.users.update_one = AsyncMock(side_effect=update_one)
    mock_db.payment_transactions.insert_one = AsyncMock()

    def expire(session_id):
        expired["id"] = session_id

    with patch("routes.subscription.require_auth", new=AsyncMock(return_value=user)), patch(
        "routes.subscription.db", mock_db
    ), patch(
        "routes.subscription._get_or_create_pro_price", new=AsyncMock(return_value="price_pro")
    ), patch(
        "routes.subscription.stripe_sdk.checkout.Session.create",
        return_value=SimpleNamespace(id="cs_test_extra", url="https://checkout.stripe.test/extra"),
    ), patch(
        "routes.subscription.stripe_sdk.checkout.Session.expire", side_effect=expire
    ), TestClient(server.app) as client:
        resp = client.post(
            "/api/subscription/checkout",
            json={"origin_url": "https://ripnflipapp.com"},
        )

    assert resp.status_code == 409, resp.text
    assert expired["id"] == "cs_test_extra"
    mock_db.payment_transactions.insert_one.assert_not_called()
