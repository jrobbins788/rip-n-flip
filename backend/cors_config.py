"""Browser CORS for the Rip N' Flip API.

Credentialed requests (cookies with SameSite=None) cannot use
``Access-Control-Allow-Origin: *``. Starlette still emits that wildcard on
simple responses when ``allow_origins`` contains ``*`` and the request has no
Cookie header, which is exactly the anonymous-visitor case. Browsers then
block ``/api/auth/me`` and ``/api/predictor/rip``.

Unhandled exceptions are turned into a plain 500 by Starlette's
``ServerErrorMiddleware``, which sits outside user middleware, so those
responses never receive CORS headers either (``/api/packs/price``,
``/api/binders/public``).

``CORS_ORIGINS`` is an optional comma-separated list of extra origins
(preview deploys, another local port). A value of ``*`` is ignored.

These origins are always allowed, so production keeps working even when
``CORS_ORIGINS`` is unset, ``*``, or a partial list:

    https://www.ripnflipapp.com
    https://ripnflipapp.com

When ``CORS_ORIGINS`` is unset or only ``*``, local dev is allowed too:

    http://localhost:3000
    http://127.0.0.1:3000

No Railway change is required for the production site. To allow an extra
origin, set for example::

    CORS_ORIGINS=https://sports-card-bot.preview.emergentagent.com
"""
from __future__ import annotations

import logging
import os
from typing import Any, Sequence
from urllib.parse import urlsplit

from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("ripnflip.cors")

# Cookie session is SameSite=None so the site on another host can call the API.
# A cross-site form POST is a "simple" request: the browser sends the cookie and
# does not preflight. Routes with no JSON body (Cash App confirm / cancel /
# mark-paid, subscription cancel, admin grant and revoke) still run.
# Browsers attach Origin on those posts. Stripe webhooks and non-browser
# clients omit it and must keep working.
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Always echoed for credentialed browser calls. Do not drop these when
# CORS_ORIGINS is missing or still set to the old wildcard.
PRODUCTION_ORIGINS: tuple[str, ...] = (
    "https://www.ripnflipapp.com",
    "https://ripnflipapp.com",
)

LOCAL_DEV_ORIGINS: tuple[str, ...] = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)


def _normalize_origin(value: str) -> str | None:
    origin = value.strip().rstrip("/")
    if not origin or origin == "*":
        return None
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        logger.warning("Ignoring CORS origin %r — expected an http(s) origin", value)
        return None
    if parsed.path or parsed.query or parsed.fragment:
        logger.warning("Ignoring CORS origin %r — origins cannot include a path", value)
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def resolve_allowed_origins(raw: str | None = None) -> list[str]:
    """Build the explicit allowlist. Never returns ``*``."""
    if raw is None:
        raw = os.environ.get("CORS_ORIGINS", "")

    configured: list[str] = []
    saw_wildcard = False
    for part in raw.split(","):
        if part.strip() == "*":
            saw_wildcard = True
            continue
        origin = _normalize_origin(part)
        if origin:
            configured.append(origin)
    if saw_wildcard:
        logger.warning(
            "CORS_ORIGINS includes '*', which browsers reject on credentialed "
            "requests. The wildcard is ignored; set an explicit comma-separated "
            "list to allow extra origins."
        )

    # Wildcard-only or empty → production plus local dev.
    # An explicit list is added on top of production so a stale env var
    # cannot lock https://www.ripnflipapp.com out.
    base: Sequence[str]
    if configured:
        base = (*PRODUCTION_ORIGINS, *configured)
    else:
        base = (*PRODUCTION_ORIGINS, *LOCAL_DEV_ORIGINS)

    allowed: list[str] = []
    seen: set[str] = set()
    for origin in base:
        if origin not in seen:
            seen.add(origin)
            allowed.append(origin)
    return allowed


def _origin_header(scope: Scope) -> str | None:
    for key, value in scope.get("headers") or []:
        if key.lower() == b"origin":
            try:
                return value.decode("latin-1").strip()
            except UnicodeError:
                return ""
    return None


class CrossSiteWriteGuard:
    """Reject unsafe requests whose Origin is not the site that owns the cookie.

    Missing Origin is allowed. A browser form POST always sends one, including
    the literal ``null`` origin from a sandboxed frame.
    """

    def __init__(self, app: ASGIApp, allowed_origins: Sequence[str]) -> None:
        self.app = app
        self.allowed_origins = set(allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") not in _UNSAFE_METHODS:
            await self.app(scope, receive, send)
            return
        origin = _origin_header(scope)
        if origin is not None and origin not in self.allowed_origins:
            logger.info("Blocked cross-site %s from origin %r", scope.get("method"), origin)
            response = JSONResponse(
                status_code=403,
                content={"detail": "Cross-site request blocked"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


class UnhandledServerErrorMiddleware:
    """Turn unhandled errors into responses while still inside CORSMiddleware.

    Starlette builds the stack as ServerErrorMiddleware → user middleware →
    ExceptionMiddleware. A crash that ExceptionMiddleware does not handle
    becomes a text/plain 500 *outside* CORS, so the browser reports a missing
    Access-Control-Allow-Origin header instead of the 500.

    This middleware is registered inside CORSMiddleware. It converts that
    crash into a normal response, and CORSMiddleware then tags it.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def track_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, track_send)
        except Exception:
            if started:
                raise
            logger.exception("Unhandled server error")
            response = JSONResponse(
                status_code=500,
                content={"detail": "Internal Server Error"},
            )
            await response(scope, receive, send)


def install_cors(app: Any, *, allowed_origins: list[str] | None = None) -> list[str]:
    """Attach credentialed CORS. Returns the origins that were registered.

    Must stay the last middleware installed on the app so it remains the
    outermost user middleware. ``UnhandledServerErrorMiddleware`` is added
    first so it stays *inside* CORS and error responses still get headers.
    """
    origins = list(allowed_origins) if allowed_origins is not None else resolve_allowed_origins()
    if not origins or "*" in origins:
        raise ValueError(
            "CORS allow_origins must be an explicit list when credentials are enabled"
        )

    # add_middleware inserts at the front, so the last call is outermost.
    # Guard sits inside CORS so a rejected browser call still gets ACAO when
    # the origin is allowed, and outside the app so the route never runs.
    app.add_middleware(UnhandledServerErrorMiddleware)
    app.add_middleware(CrossSiteWriteGuard, allowed_origins=origins)
    app.add_middleware(
        CORSMiddleware,
        allow_credentials=True,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info("CORS allow_origins=%s", origins)
    return origins
