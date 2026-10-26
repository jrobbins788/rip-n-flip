"""One person, one account, even when the email's case changes.

Register stored the address as typed. Google later returns the same address
in a different case, the lookup missed, and a second empty user was created.
The binder, listings, and Pro grant stayed on the password account.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "ripnflip_email_identity_test")
os.environ.setdefault("JWT_SECRET", "email-identity-test-secret")
os.environ.setdefault("DISABLE_SCHEDULER", "1")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vendor"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server


def _matches(doc: dict, query: dict) -> bool:
    if "$expr" in query:
        raise AssertionError("email lookup should use a case-insensitive regex")
    for key, expected in query.items():
        actual = doc.get(key)
        if isinstance(expected, dict) and "$regex" in expected:
            flags = re.IGNORECASE if "i" in expected.get("$options", "") else 0
            if not isinstance(actual, str) or re.search(expected["$regex"], actual, flags) is None:
                return False
        elif actual != expected:
            return False
    return True


class _Users:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]
        self.updates = []

    async def find_one(self, query, projection=None):
        for doc in self.docs:
            if _matches(doc, query):
                return dict(doc)
        return None

    def find(self, query, projection=None):
        docs = [dict(doc) for doc in self.docs if _matches(doc, query)]

        class _Cursor:
            async def to_list(self, limit):
                return docs[:limit]

        return _Cursor()

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


def _use(users, sessions=None):
    server.db = SimpleNamespace(users=users, user_sessions=sessions or _Sessions())


def _oauth(monkeypatch, payload):
    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None):
            return SimpleNamespace(status_code=200, json=lambda: payload)

    monkeypatch.setattr(server.httpx, "AsyncClient", lambda *args, **kwargs: _Client())


def _request():
    class _Request:
        async def json(self):
            return {"session_id": "sess_google"}

    return _Request()


def test_register_rejects_the_same_address_with_different_case():
    users = _Users([{
        "user_id": "user_first",
        "email": "fan@gmail.com",
        "name": "First",
        "password_hash": "hashed",
    }])
    _use(users)

    with pytest.raises(server.HTTPException) as raised:
        import asyncio
        asyncio.run(server.register(
            server.UserCreate(email="Fan@gmail.com", password="secret-pass", name="Second"),
            _Response(),
        ))

    assert raised.value.status_code == 400
    assert len(users.docs) == 1


def test_login_finds_the_account_when_only_the_case_differs():
    hashed = server.hash_password("secret-pass")
    users = _Users([{
        "user_id": "user_owner",
        "email": "Fan@gmail.com",
        "name": "Owner",
        "password_hash": hashed,
    }])
    _use(users)

    import asyncio
    result = asyncio.run(server.login(
        server.UserLogin(email="fan@gmail.com", password="secret-pass"),
        _Response(),
    ))

    assert result["user_id"] == "user_owner"
    assert result["email"] == "Fan@gmail.com"


def test_password_login_on_a_google_account_is_rejected_not_a_crash():
    users = _Users([{
        "user_id": "user_google",
        "email": "fan@gmail.com",
        "name": "Owner",
    }])
    _use(users)

    with pytest.raises(server.HTTPException) as raised:
        import asyncio
        asyncio.run(server.login(
            server.UserLogin(email="fan@gmail.com", password="secret-pass"),
            _Response(),
        ))

    assert raised.value.status_code == 401


def test_google_sign_in_does_not_open_a_second_account_for_a_different_case(monkeypatch):
    users = _Users([{
        "user_id": "user_owner",
        "email": "Fan@gmail.com",
        "name": "Owner",
        "password_hash": "hashed-password",
        "cash_app_tag": "$owner",
    }])
    sessions = _Sessions()
    _use(users, sessions)
    _oauth(monkeypatch, {
        "email": "fan@gmail.com",
        "name": "Owner via Google",
        "picture": "https://example.com/a.png",
        "session_token": "oauth_session_token",
    })

    with pytest.raises(server.HTTPException) as raised:
        import asyncio
        asyncio.run(server.process_session(_request(), _Response()))

    assert raised.value.status_code == 409
    assert sessions.docs == []
    assert len(users.docs) == 1
    assert users.docs[0]["user_id"] == "user_owner"
    assert users.docs[0]["password_hash"] == "hashed-password"
    assert users.docs[0]["cash_app_tag"] == "$owner"
    assert users.docs[0]["name"] == "Owner"
    assert users.updates == []


def test_google_sign_in_reuses_an_oauth_account_stored_with_different_case(monkeypatch):
    users = _Users([{
        "user_id": "user_owner",
        "email": "Fan@gmail.com",
        "name": "Old Name",
        "picture": None,
    }])
    sessions = _Sessions()
    _use(users, sessions)
    _oauth(monkeypatch, {
        "email": "fan@gmail.com",
        "name": "Owner",
        "picture": "https://example.com/a.png",
        "session_token": "oauth_session_token",
    })

    import asyncio
    result = asyncio.run(server.process_session(_request(), _Response()))

    assert result["user_id"] == "user_owner"
    assert result["email"] == "fan@gmail.com"
    assert len(users.docs) == 1
    assert users.docs[0]["email"] == "fan@gmail.com"
    assert users.docs[0]["name"] == "Owner"
    assert sessions.docs[0]["user_id"] == "user_owner"


def test_google_sign_in_rejects_a_payload_without_an_email(monkeypatch):
    users = _Users([{"user_id": "user_blank", "name": "No email"}])
    sessions = _Sessions()
    _use(users, sessions)
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
    assert users.updates == []
