"""Unsigned subscription webhooks must not grant Pro from the request body."""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "ripnflip_subscription_webhook_test")
os.environ.setdefault("STRIPE_API_KEY", "sk_test_webhook_guard")
os.environ.setdefault("JWT_SECRET", "webhook-guard-test-secret")
os.environ.setdefault("DISABLE_SCHEDULER", "1")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

import server
from subscription_sync import subscription_write_from_stripe


PERIOD_END = 1_900_000_000
PERIOD_END_ISO = "2030-03-17T17:46:40+00:00"


def test_forged_active_status_does_not_grant_pro_by_itself():
    assert subscription_write_from_stripe({
        "id": "sub_forged",
        "customer": None,
        "status": "active",
        "current_period_end": PERIOD_END,
    }) is None
    assert subscription_write_from_stripe({
        "id": "sub_forged",
        "customer": "not-a-customer",
        "status": "active",
        "current_period_end": PERIOD_END,
    }) is None
    assert subscription_write_from_stripe({
        "id": "not-a-sub",
        "customer": "cus_real",
        "status": "active",
        "current_period_end": PERIOD_END,
    }) is None


def test_retrieved_active_subscription_grants_that_customer():
    decision = subscription_write_from_stripe({
        "id": "sub_real",
        "customer": "cus_real",
        "status": "active",
        "current_period_end": PERIOD_END,
        "cancel_at_period_end": False,
    })
    assert decision["customer_id"] == "cus_real"
    assert decision["set"]["tier"] == "pro"
    assert decision["set"]["pro_until"] == PERIOD_END_ISO
    assert decision["set"]["pro_source"] == "stripe_subscription"
    assert decision["set"]["subscription.status"] == "active"
    assert decision["set"]["subscription.stripe_subscription_id"] == "sub_real"


def test_retrieved_canceled_subscription_clears_pro():
    decision = subscription_write_from_stripe({
        "id": "sub_real",
        "customer": {"id": "cus_real"},
        "status": "canceled",
        "current_period_end": PERIOD_END,
    })
    assert decision["customer_id"] == "cus_real"
    assert decision["set"]["tier"] == "free"
    assert decision["set"]["subscription.status"] == "canceled"
    assert "pro_until" not in decision["set"]


def test_period_end_on_the_subscription_item_still_grants_pro():
    """stripe-python 14 / API 2026-01-28.clover omits subscription.current_period_end."""
    decision = subscription_write_from_stripe({
        "id": "sub_real",
        "customer": "cus_real",
        "status": "active",
        "cancel_at_period_end": False,
        "items": {
            "object": "list",
            "data": [
                {"id": "si_old", "current_period_end": PERIOD_END - 100},
                {"id": "si_current", "current_period_end": PERIOD_END},
            ],
        },
    })
    assert decision["customer_id"] == "cus_real"
    assert decision["set"]["tier"] == "pro"
    assert decision["set"]["pro_until"] == PERIOD_END_ISO
    assert decision["set"]["subscription.current_period_end"] == PERIOD_END_ISO


def test_past_due_does_not_grant_pro():
    decision = subscription_write_from_stripe({
        "id": "sub_real",
        "customer": "cus_real",
        "status": "past_due",
        "current_period_end": PERIOD_END,
    })
    assert decision["set"]["subscription.status"] == "past_due"
    assert "tier" not in decision["set"]


class _MissingSub(Exception):
    http_status = 404
    code = "resource_missing"


class _StripeDown(Exception):
    http_status = None
    code = None


def _mock_db():
    mock_db = MagicMock()
    mock_db.users.find_one = AsyncMock(return_value=None)
    mock_db.users.update_one = AsyncMock()
    mock_db.payment_transactions.update_one = AsyncMock()
    return mock_db


def _forged_active_body(customer="cus_attacker", sub_id="sub_forged"):
    return {
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": sub_id,
                "customer": customer,
                "status": "active",
                "current_period_end": PERIOD_END,
                "cancel_at_period_end": False,
            }
        },
    }


def test_unknown_subscription_does_not_write_user():
    mock_db = _mock_db()
    with patch("routes.subscription.db", mock_db), patch(
        "routes.subscription.stripe_sdk.Subscription.retrieve", side_effect=_MissingSub("missing")
    ), TestClient(server.app) as client:
        resp = client.post("/api/webhook/stripe-subscription", json=_forged_active_body())

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["received"] is True
    assert body["applied"] is False
    mock_db.users.find_one.assert_not_called()
    mock_db.users.update_one.assert_not_called()


def test_body_customer_is_ignored_when_stripe_returns_another():
    """A paid subscription for cus_real must not grant the customer named in the body."""
    mock_db = _mock_db()
    mock_db.users.find_one = AsyncMock(return_value={"user_id": "user_real"})
    retrieved = {
        "id": "sub_real",
        "customer": "cus_real",
        "status": "active",
        "current_period_end": PERIOD_END,
        "cancel_at_period_end": False,
    }
    with patch("routes.subscription.db", mock_db), patch(
        "routes.subscription.stripe_sdk.Subscription.retrieve", return_value=retrieved
    ), TestClient(server.app) as client:
        resp = client.post(
            "/api/webhook/stripe-subscription",
            json=_forged_active_body(customer="cus_victim", sub_id="sub_real"),
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["applied"] is True
    mock_db.users.find_one.assert_awaited_once_with(
        {"subscription.stripe_customer_id": "cus_real"}, {"_id": 0}
    )
    written = mock_db.users.update_one.await_args.args[1]["$set"]
    assert written["tier"] == "pro"
    assert written["pro_until"] == PERIOD_END_ISO
    assert written["subscription.stripe_subscription_id"] == "sub_real"
    assert written["subscription.status"] == "active"


def test_null_customer_in_body_does_not_match_users_without_a_customer():
    mock_db = _mock_db()
    with patch("routes.subscription.db", mock_db), patch(
        "routes.subscription.stripe_sdk.Subscription.retrieve",
        return_value={"id": "sub_real", "customer": None, "status": "active", "current_period_end": PERIOD_END},
    ), TestClient(server.app) as client:
        resp = client.post(
            "/api/webhook/stripe-subscription",
            json=_forged_active_body(customer=None, sub_id="sub_real"),
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["applied"] is False
    mock_db.users.find_one.assert_not_called()
    mock_db.users.update_one.assert_not_called()


def test_stripe_outage_does_not_apply_body_and_asks_for_retry():
    mock_db = _mock_db()
    with patch("routes.subscription.db", mock_db), patch(
        "routes.subscription.stripe_sdk.Subscription.retrieve", side_effect=_StripeDown("down")
    ), TestClient(server.app) as client:
        resp = client.post("/api/webhook/stripe-subscription", json=_forged_active_body())

    assert resp.status_code == 503
    mock_db.users.update_one.assert_not_called()
    mock_db.payment_transactions.update_one.assert_not_called()


def test_forged_invoice_does_not_mark_payment_paid():
    mock_db = _mock_db()
    with patch("routes.subscription.db", mock_db), TestClient(server.app) as client:
        resp = client.post(
            "/api/webhook/stripe-subscription",
            json={
                "type": "invoice.payment_succeeded",
                "data": {"object": {"customer": "cus_victim", "amount_paid": 399}},
            },
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["applied"] is False
    mock_db.payment_transactions.update_one.assert_not_called()
    mock_db.users.update_one.assert_not_called()


def test_bad_json_still_returns_400():
    mock_db = _mock_db()
    with patch("routes.subscription.db", mock_db), TestClient(server.app) as client:
        resp = client.post(
            "/api/webhook/stripe-subscription",
            data="not valid json",
            headers={"Content-Type": "application/json"},
        )

    assert resp.status_code == 400
    assert resp.json()["error"] == "bad_json"
