"""Logout must expire the cross-site session cookie.

Password and admin login store a JWT in a Secure SameSite=None cookie.
The API is a different origin from the site, so logout is a cross-site
response. Starlette's delete_cookie() defaults (SameSite=Lax, not Secure)
are ignored by browsers in that case, and the JWT is not saved in
user_sessions, so a refresh signs the user back in.
"""
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

from starlette.responses import Response

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_logout_cookie")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vendor"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server


class _Sessions:
    def __init__(self):
        self.queries = []

    async def delete_many(self, query):
        self.queries.append(query)
        return SimpleNamespace(deleted_count=1)


def _cookie_headers(response: Response) -> list[str]:
    return response.headers.getlist("set-cookie")


def test_logout_expires_the_cross_site_session_cookie(monkeypatch):
    sessions = _Sessions()
    monkeypatch.setattr(server, "db", SimpleNamespace(user_sessions=sessions))
    response = Response()

    result = asyncio.run(
        server.logout(
            SimpleNamespace(cookies={"session_token": "jwt-still-valid"}),
            response,
        )
    )

    assert result == {"message": "Logged out"}
    assert sessions.queries == [{"session_token": "jwt-still-valid"}]
    session_cookie = next(
        header for header in _cookie_headers(response) if header.startswith("session_token=")
    )
    lowered = session_cookie.lower()
    assert "max-age=0" in lowered
    assert "samesite=none" in lowered
    assert "secure" in lowered
    # SameSite=None without Secure is rejected, which is the bug this guards.
    assert "samesite=lax" not in lowered
