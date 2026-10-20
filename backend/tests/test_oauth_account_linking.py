"""Google sign-in must not attach to an unverified password account.

Register does not confirm the address. Linking OAuth onto that row used to
issue a session for the pre-registrant's user id and leave password_hash in
place, so the registrant could still log in after the real owner added a
Cash App tag, listings, and trades.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "ripnflip_oauth_link_test")
os.environ.setdefault("JWT_SECRET", "oauth-link-test-secret")
os.environ.setdefault("DISABLE_SCHEDULER", "1")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vendor"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server


class _Users:
    def __init__(self, docs):
        self.docs = [dict(doc) for doc in docs]
        self.updates = []

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if all(doc.get(key) == expected for key, expected in query.items()):
                return dict(doc)
        return None

    async def update_one(self, query, update):
        self.updates.append((query, update))
        for doc in self.docs:
            if doc.get("user_id") == query.get("user_id"):
                doc.update(update.get("$set") or {})
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=1)


class _Sessions:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id=1)


class _Response:
    def __init__(self):
        self.cookies = []

    def set_cookie(self, **kwargs):
        self.cookies.append(kwargs)


def _oauth(monkeypatch, payload):
    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            assert headers["X-Session-ID"] == "sess_google"
            return SimpleNamespace(status_code=200, json=lambda: payload)

    monkeypatch.setattr(server.httpx, "AsyncClient", lambda *args, **kwargs: _Client())


def _request():
    class _Request:
        async def json(self):
            return {"session_id": "sess_google"}

    return _Request()


def test_google_sign_in_does_not_enter_a_password_account(monkeypatch):
    users = _Users([{
        "user_id": "user_attacker",
        "email": "owner@example.com",
        "name": "Pre registrant",
        "password_hash": "hashed-password",
        "cash_app_tag": "$attacker",
    }])
    sessions = _Sessions()
    server.db = SimpleNamespace(users=users, user_sessions=sessions)
    _oauth(monkeypatch, {
        "email": "owner@example.com",
        "name": "Real Owner",
        "picture": "https://example.com/owner.png",
        "session_token": "oauth_session_token",
    })

    with pytest.raises(server.HTTPException) as raised:
        import asyncio
        asyncio.run(server.process_session(_request(), _Response()))

    assert raised.value.status_code == 409
    assert sessions.docs == []
    assert users.updates == []
    assert users.docs[0]["password_hash"] == "hashed-password"
    assert users.docs[0]["cash_app_tag"] == "$attacker"
    assert users.docs[0]["name"] == "Pre registrant"


def test_google_sign_in_still_links_an_existing_oauth_account(monkeypatch):
    users = _Users([{
        "user_id": "user_owner",
        "email": "owner@example.com",
        "name": "Old Name",
        "picture": None,
    }])
    sessions = _Sessions()
    server.db = SimpleNamespace(users=users, user_sessions=sessions)
    response = _Response()
    _oauth(monkeypatch, {
        "email": "  owner@example.com  ",
        "name": "Real Owner",
        "picture": "https://example.com/owner.png",
        "session_token": "oauth_session_token",
    })

    import asyncio
    result = asyncio.run(server.process_session(_request(), response))

    assert result["user_id"] == "user_owner"
    assert result["email"] == "owner@example.com"
    assert users.docs[0]["name"] == "Real Owner"
    assert sessions.docs[0]["user_id"] == "user_owner"
    assert sessions.docs[0]["session_token"] == "oauth_session_token"
    assert response.cookies[0]["value"] == "oauth_session_token"


def test_google_sign_in_rejects_a_payload_without_an_email(monkeypatch):
    users = _Users([{"user_id": "user_blank", "name": "No email"}])
    sessions = _Sessions()
    server.db = SimpleNamespace(users=users, user_sessions=sessions)
    _oauth(monkeypatch, {
        "email": None,
        "name": "Nobody",
        "session_token": "oauth_session_token",
    })

    with pytest.raises(server.HTTPException) as raised:
        import asyncio
        asyncio.run(server.process_session(_request(), _Response()))

    assert raised.value.status_code == 401
    assert sessions.docs == []
    assert len(users.docs) == 1
