"""POST /api/webhook/stripe must not fulfill from the request body."""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "ripnflip_webhook_test")
os.environ.setdefault("STRIPE_API_KEY", "sk_test_webhook_guard")
os.environ.setdefault("JWT_SECRET", "webhook-guard-test-secret")
os.environ.setdefault("DISABLE_SCHEDULER", "1")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

import server


def _mock_db():
    mock_db = MagicMock()
    mock_db.payment_transactions.find_one = AsyncMock(return_value=None)
    mock_db.payment_transactions.update_one = AsyncMock()
    mock_db.listings.update_one = AsyncMock()
    mock_db.user_sessions.find_one = AsyncMock(return_value=None)
    mock_db.users.find_one = AsyncMock(return_value=None)
    return mock_db


def test_forged_paid_metadata_does_not_mark_victim_listing_sold():
    mock_db = _mock_db()
    mock_db.payment_transactions.find_one = AsyncMock(return_value={
        "session_id": "cs_test_real",
        "listing_id": "listing_real",
        "payment_status": "pending",
    })
    unpaid = {"payment_status": "unpaid", "metadata": {"listing_id": "listing_real"}}

    with patch("server.db", mock_db), patch.object(
        server.stripe_sdk.checkout.Session, "retrieve", return_value=unpaid
    ), TestClient(server.app) as client:
        resp = client.post(
            "/api/webhook/stripe",
            json={
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": "cs_test_real",
                        "payment_status": "paid",
                        "metadata": {"listing_id": "listing_victim"},
                    }
                },
            },
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    mock_db.listings.update_one.assert_not_called()
    mock_db.payment_transactions.update_one.assert_not_called()


def test_paid_stripe_session_marks_only_the_stored_listing():
    mock_db = _mock_db()
    mock_db.payment_transactions.find_one = AsyncMock(return_value={
        "session_id": "cs_test_paid",
        "listing_id": "listing_real",
        "payment_status": "pending",
    })
    paid = {"payment_status": "paid", "metadata": {"listing_id": "listing_real"}}

    with patch("server.db", mock_db), patch.object(
        server.stripe_sdk.checkout.Session, "retrieve", return_value=paid
    ), TestClient(server.app) as client:
        resp = client.post(
            "/api/webhook/stripe",
            json={
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": "cs_test_paid",
                        "payment_status": "paid",
                        "metadata": {"listing_id": "listing_victim"},
                    }
                },
            },
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    mock_db.listings.update_one.assert_awaited_once_with(
        {"listing_id": "listing_real"},
        {"$set": {"status": "sold"}},
    )


class _MissingSession(Exception):
    http_status = 404
    code = "resource_missing"


class _StripeDown(Exception):
    http_status = None
    code = None


def test_unknown_session_does_not_update_listings():
    mock_db = _mock_db()

    def _boom(session_id, **_kwargs):
        raise _MissingSession(f"no such session {session_id}")

    with patch("server.db", mock_db), patch.object(
        server.stripe_sdk.checkout.Session, "retrieve", side_effect=_boom
    ), TestClient(server.app) as client:
        resp = client.post(
            "/api/webhook/stripe",
            json={
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": "cs_test_missing",
                        "payment_status": "paid",
                        "metadata": {"listing_id": "listing_victim"},
                    }
                },
            },
        )

    assert resp.status_code == 400
    mock_db.listings.update_one.assert_not_called()


def test_stripe_outage_does_not_mark_sold_and_asks_for_retry():
    mock_db = _mock_db()

    with patch("server.db", mock_db), patch.object(
        server.stripe_sdk.checkout.Session, "retrieve", side_effect=_StripeDown("down")
    ), TestClient(server.app) as client:
        resp = client.post(
            "/api/webhook/stripe",
            json={
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": "cs_test_paid",
                        "payment_status": "paid",
                        "metadata": {"listing_id": "listing_victim"},
                    }
                },
            },
        )

    assert resp.status_code == 503
    mock_db.listings.update_one.assert_not_called()
    mock_db.payment_transactions.update_one.assert_not_called()


def _txn_lookup(transaction):
    async def find_txn(query, projection=None):
        session_id = query.get("session_id")
        if session_id == transaction["session_id"]:
            return transaction
        return None

    return find_txn


def test_failed_delayed_payment_puts_the_listing_back_on_sale():
    mock_db = _mock_db()
    transaction = {
        "session_id": "cs_test_klarna",
        "listing_id": "listing_real",
        "payment_status": "pending",
        "created_at": "2026-11-01T00:00:00+00:00",
    }
    mock_db.payment_transactions.find_one = _txn_lookup(transaction)
    mock_db.trades.find_one = AsyncMock(return_value=None)
    failed = {
        "status": "complete",
        "payment_status": "unpaid",
        "payment_intent": {"id": "pi_failed", "status": "canceled"},
        "metadata": {"listing_id": "listing_real"},
    }

    with patch("server.db", mock_db), patch.object(
        server.stripe_sdk.checkout.Session, "retrieve", return_value=failed
    ), patch.object(
        server.stripe_sdk.PaymentIntent, "retrieve", side_effect=AssertionError("intent is already expanded")
    ), TestClient(server.app) as client:
        resp = client.post(
            "/api/webhook/stripe",
            json={
                "type": "checkout.session.async_payment_failed",
                "data": {
                    "object": {
                        "id": "cs_test_klarna",
                        "payment_status": "paid",
                        "metadata": {"listing_id": "listing_victim"},
                    }
                },
            },
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "released"
    mock_db.listings.update_one.assert_awaited_once_with(
        {"listing_id": "listing_real", "status": "pending"},
        {"$set": {"status": "active"}, "$unset": {"pending_since": ""}},
    )
    mock_db.payment_transactions.update_one.assert_awaited_once_with(
        {"session_id": "cs_test_klarna", "payment_status": {"$nin": ["paid"]}},
        {"$set": {"payment_status": "failed", "status": "complete"}},
    )


def test_processing_delayed_payment_does_not_relist():
    mock_db = _mock_db()
    mock_db.payment_transactions.find_one = _txn_lookup({
        "session_id": "cs_test_klarna",
        "listing_id": "listing_real",
        "payment_status": "pending",
        "created_at": "2026-11-01T00:00:00+00:00",
    })
    processing = {
        "status": "complete",
        "payment_status": "unpaid",
        "payment_intent": {"id": "pi_open", "status": "processing"},
        "metadata": {"listing_id": "listing_real"},
    }

    with patch("server.db", mock_db), patch.object(
        server.stripe_sdk.checkout.Session, "retrieve", return_value=processing
    ), TestClient(server.app) as client:
        resp = client.post(
            "/api/webhook/stripe",
            json={
                "type": "checkout.session.async_payment_failed",
                "data": {"object": {"id": "cs_test_klarna", "payment_status": "unpaid"}},
            },
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    mock_db.listings.update_one.assert_not_called()


def test_failed_delayed_payment_does_not_release_a_newer_checkout():
    mock_db = _mock_db()
    transaction = {
        "session_id": "cs_test_klarna",
        "listing_id": "listing_real",
        "payment_status": "pending",
        "created_at": "2026-11-01T00:00:00+00:00",
    }

    async def find_txn(query, projection=None):
        if query.get("session_id") == transaction["session_id"]:
            return transaction
        return {"session_id": "cs_test_newer", "payment_status": "pending"}

    mock_db.payment_transactions.find_one = find_txn
    mock_db.trades.find_one = AsyncMock(return_value=None)
    failed = {
        "status": "complete",
        "payment_status": "unpaid",
        "payment_intent": {"id": "pi_failed", "status": "canceled"},
    }

    with patch("server.db", mock_db), patch.object(
        server.stripe_sdk.checkout.Session, "retrieve", return_value=failed
    ), TestClient(server.app) as client:
        resp = client.post(
            "/api/webhook/stripe",
            json={
                "type": "checkout.session.async_payment_failed",
                "data": {"object": {"id": "cs_test_klarna"}},
            },
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "released"
    mock_db.listings.update_one.assert_not_called()


def test_non_checkout_event_is_ignored():
    mock_db = _mock_db()
    with patch("server.db", mock_db), patch.object(
        server.stripe_sdk.checkout.Session, "retrieve"
    ) as retrieve, TestClient(server.app) as client:
        resp = client.post(
            "/api/webhook/stripe",
            json={
                "type": "customer.subscription.updated",
                "data": {
                    "object": {
                        "id": "sub_123",
                        "payment_status": "paid",
                        "metadata": {"listing_id": "listing_victim"},
                    }
                },
            },
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    retrieve.assert_not_called()
    mock_db.listings.update_one.assert_not_called()


def test_admin_login_sets_session_token_cookie():
    hashed = server.bcrypt.hashpw(b"secret-pass", server.bcrypt.gensalt()).decode()
    user = {
        "user_id": "user_admin",
        "email": "Admin@example.com",
        "name": "Ada Admin",
        "password_hash": hashed,
    }
    mock_db = _mock_db()
    # Exact email misses; case-insensitive lookup finds the account.
    # /auth/me then loads the same user from the JWT in the session cookie.
    lookups = {"n": 0}

    async def find_user(*_args, **_kwargs):
        lookups["n"] += 1
        if lookups["n"] == 1:
            return None
        return user

    mock_db.users.find_one = find_user

    original_admins = set(server.ADMIN_EMAILS)
    server.ADMIN_EMAILS.add("admin@example.com")
    try:
        with patch("server.db", mock_db), TestClient(server.app) as client:
            resp = client.post(
                "/api/admin/login",
                json={"email": "Admin@example.com", "password": "secret-pass"},
            )
            assert resp.status_code == 200, resp.text
            set_cookies = resp.headers.get_list("set-cookie")
            session_cookie = next(c for c in set_cookies if c.startswith("session_token="))
            token = session_cookie.split(";", 1)[0].split("=", 1)[1]
            assert token
            assert not any(
                c.startswith("auth_token=") and not c.startswith("auth_token=;") and "Max-Age=0" not in c
                for c in set_cookies
            )

            me = client.get("/api/auth/me", headers={"Cookie": f"session_token={token}"})
            assert me.status_code == 200, me.text
            assert me.json()["user_id"] == "user_admin"
    finally:
        server.ADMIN_EMAILS.clear()
        server.ADMIN_EMAILS.update(original_admins)
