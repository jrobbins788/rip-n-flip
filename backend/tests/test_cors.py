"""CORS allowlist, credentialed preflight, and error responses.

Production was serving Access-Control-Allow-Origin: * together with
Access-Control-Allow-Credentials: true. Anonymous visitors (no Cookie)
are rejected by the browser for that combination, and unhandled 500s
omitted CORS headers entirely because they are generated outside the
CORS middleware.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cors_config import install_cors, resolve_allowed_origins  # noqa: E402

WWW = "https://www.ripnflipapp.com"
APEX = "https://ripnflipapp.com"
EVIL = "https://evil.example"


def _app(origins_env: str | None = None) -> FastAPI:
    app = FastAPI()

    @app.get("/api/health")
    def health():
        return {"status": "healthy"}

    @app.get("/api/auth/me")
    def me():
        raise HTTPException(status_code=401, detail="Not authenticated")

    @app.post("/api/predictor/rip")
    def rip():
        return {"ok": True}

    @app.get("/api/packs/price")
    def price():
        raise RuntimeError("price backend unavailable")

    if origins_env is None:
        install_cors(app, allowed_origins=resolve_allowed_origins(""))
    else:
        install_cors(app, allowed_origins=resolve_allowed_origins(origins_env))
    return app


def _client(origins_env: str | None = None) -> TestClient:
    return TestClient(_app(origins_env))


def test_wildcard_env_never_becomes_star_allowlist():
    origins = resolve_allowed_origins("*")
    assert "*" not in origins
    assert origins[0] == WWW
    assert APEX in origins
    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3000" in origins


def test_explicit_list_keeps_production_and_extra_origins():
    origins = resolve_allowed_origins(
        " https://preview.example.com/ , *, https://www.ripnflipapp.com "
    )
    assert origins == [
        WWW,
        APEX,
        "https://preview.example.com",
    ]


def test_invalid_origin_tokens_are_dropped():
    origins = resolve_allowed_origins("not a url, https://ok.example.com/path, ftp://nope.com")
    assert "https://ok.example.com" not in origins
    assert WWW in origins
    assert APEX in origins


def test_credentialed_get_echoes_origin_without_a_cookie():
    """Anonymous /api/auth/me: no Cookie, credentials mode include."""
    response = _client().get("/api/auth/me", headers={"Origin": WWW})
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == WWW
    assert response.headers["access-control-allow-credentials"] == "true"
    assert response.headers["access-control-allow-origin"] != "*"


def test_credentialed_get_echoes_apex_origin():
    response = _client().get("/api/health", headers={"Origin": APEX})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == APEX
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "origin" in response.headers["vary"].lower()


def test_predictor_preflight_allows_www_with_credentials():
    response = _client().options(
        "/api/predictor/rip",
        headers={
            "Origin": WWW,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == WWW
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "content-type" in response.headers["access-control-allow-headers"].lower()
    assert response.headers["access-control-allow-origin"] != "*"


def test_predictor_preflight_allows_apex():
    response = _client().options(
        "/api/predictor/rip",
        headers={
            "Origin": APEX,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == APEX
    assert response.headers["access-control-allow-credentials"] == "true"


def test_actual_post_after_preflight_echoes_origin():
    response = _client().post(
        "/api/predictor/rip",
        headers={"Origin": WWW, "Content-Type": "application/json"},
        json={"pack_id": "prizm-bball-hobby"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == WWW
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cross_site_form_post_does_not_run_the_handler():
    """SameSite=None cookies ride along on a foreign form POST.

    Cash App confirm, cancel, and mark-paid have no JSON body, so the browser
    does not preflight and the write used to land. Origin is always present on
    that post; Stripe webhooks omit it.
    """
    calls = {"n": 0}
    app = FastAPI()

    @app.post("/api/trades/{trade_id}/confirm")
    def confirm(trade_id: str):
        calls["n"] += 1
        return {"trade_id": trade_id, "status": "completed"}

    install_cors(app, allowed_origins=resolve_allowed_origins(""))
    client = TestClient(app)

    blocked = client.post(
        "/api/trades/trade_victim/confirm",
        headers={"Origin": EVIL, "Cookie": "session_token=seller"},
    )
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "Cross-site request blocked"
    assert calls["n"] == 0

    sandboxed = client.post(
        "/api/trades/trade_victim/confirm",
        headers={"Origin": "null", "Cookie": "session_token=seller"},
    )
    assert sandboxed.status_code == 403
    assert calls["n"] == 0

    allowed = client.post(
        "/api/trades/trade_victim/confirm",
        headers={"Origin": WWW, "Cookie": "session_token=seller"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "completed"
    assert calls["n"] == 1

    webhook = client.post("/api/trades/trade_victim/confirm")
    assert webhook.status_code == 200
    assert calls["n"] == 2


def test_unhandled_500_still_carries_cors_headers():
    response = _client().get("/api/packs/price", headers={"Origin": WWW})
    assert response.status_code == 500
    assert response.json()["detail"] == "Internal Server Error"
    assert response.headers["access-control-allow-origin"] == WWW
    assert response.headers["access-control-allow-credentials"] == "true"


def test_unhandled_500_for_apex_carries_cors_headers():
    response = _client().get("/api/packs/price", headers={"Origin": APEX})
    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == APEX


def test_disallowed_origin_is_not_reflected():
    client = _client()
    simple = client.get("/api/health", headers={"Origin": EVIL})
    assert "access-control-allow-origin" not in simple.headers

    preflight = client.options(
        "/api/predictor/rip",
        headers={
            "Origin": EVIL,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight.status_code == 400
    assert "access-control-allow-origin" not in preflight.headers

    crashed = client.get("/api/packs/price", headers={"Origin": EVIL})
    assert crashed.status_code == 500
    assert "access-control-allow-origin" not in crashed.headers


def test_star_env_still_echoes_production_origin_on_preflight(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "*")
    response = _client("*").options(
        "/api/predictor/rip",
        headers={
            "Origin": WWW,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == WWW
    assert response.headers["access-control-allow-origin"] != "*"


def test_install_cors_rejects_wildcard_list():
    app = FastAPI()
    with pytest.raises(ValueError):
        install_cors(app, allowed_origins=["*"])


def test_legacy_wildcard_middleware_is_the_production_bug():
    """Starlette 0.37 emits '*' on credentialed calls that have no cookie.

    This is what rip-n-flip-production.up.railway.app returned for
    GET /api/auth/me from https://www.ripnflipapp.com.
    """
    app = FastAPI()

    @app.get("/api/auth/me")
    def me():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.add_middleware(
        CORSMiddleware,
        allow_credentials=True,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    response = TestClient(app).get("/api/auth/me", headers={"Origin": WWW})
    assert response.headers["access-control-allow-origin"] == "*"
    assert response.headers["access-control-allow-credentials"] == "true"
