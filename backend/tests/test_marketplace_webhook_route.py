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


def test_unknown_session_does_not_update_listings():
    mock_db = _mock_db()

    def _boom(session_id):
        raise RuntimeError(f"no such session {session_id}")

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
