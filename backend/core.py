"""
Rip N' Flip — shared core dependencies.

This module exposes the singleton DB client, JWT helpers, auth dependencies,
constants, and logger used by both server.py and the modular route packages
under /app/backend/routes/.

Keeping these in one place lets route modules import without circular deps.
"""
from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
from fastapi import HTTPException, Request
from jose import jwt, JWTError
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# ─── MongoDB singleton ──────────────────────────────────────
mongo_url = os.environ["MONGO_URL"]
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[os.environ["DB_NAME"]]

# ─── JWT ────────────────────────────────────────────────────
JWT_SECRET = os.environ.get("JWT_SECRET", "cardfanatic_secret_key")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_DAYS = 7

# ─── Tier limits / business constants ──────────────────────
FREE_TIER_PACKS_PER_WEEK = 2
FREE_TIER_PREDICTOR_PER_DAY = 2
PRO_TIER_PREDICTOR_PER_DAY = 5
TRIAL_DURATION_DAYS = 10
PRO_PRICE_AMOUNT_USD = 3.99
PLATFORM_FEE_PCT = 0.02

# ─── Cold Start Protocol thresholds ────────────────────────
TIER1_MAX = 50
TIER2_MAX = 200

# ─── Stripe ────────────────────────────────────────────────
STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY")

# ─── Logger ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("ripnflip")


# ─── Auth helpers ──────────────────────────────────────────
ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("ADMIN_EMAILS", "").split(",")
    if e.strip()
}


async def get_current_user(request: Request) -> Optional[dict]:
    """Return the user doc if either a valid Emergent OAuth session token
    or a valid JWT bearer/cookie is present. Returns None otherwise.

    Mirrors the helper in server.py so route modules don't double-handle auth.
    """
    token = request.cookies.get("session_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        return None

    # 1) Emergent OAuth session lookup
    try:
        session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
        if session:
            expires_at = session.get("expires_at")
            if isinstance(expires_at, str):
                try:
                    expires_at = datetime.fromisoformat(expires_at)
                except ValueError:
                    expires_at = None
            if expires_at and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at and expires_at < datetime.now(timezone.utc):
                return None
            return await db.users.find_one(
                {"user_id": session["user_id"]}, {"_id": 0, "password_hash": 0}
            )
    except Exception:
        pass

    # 2) JWT fallback
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("user_id")
        if not user_id:
            return None
        return await db.users.find_one(
            {"user_id": user_id}, {"_id": 0, "password_hash": 0}
        )
    except JWTError:
        return None


async def require_auth(request: Request) -> dict:
    """FastAPI dependency — raises 401 if no valid auth."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def is_admin(user: Optional[dict]) -> bool:
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    email = (user.get("email") or "").strip().lower()
    return bool(email and email in ADMIN_EMAILS)


async def require_admin(request: Request) -> dict:
    """FastAPI dependency — raises 401/403 unless caller is admin."""
    user = await require_auth(request)
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Admin only")
    return user


async def user_tier(user_id: str) -> str:
    """Return 'pro' if user is on a paid plan, inside their 10-day trial, OR
    inside a DUB STREAK weekly reward window. Otherwise 'free'.
    """
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not u:
        return "free"

    now = datetime.now(timezone.utc)

    # 1) Explicit Pro (Stripe-active subscription) — only valid if still active.
    #    If pro_until is set, check it hasn't lapsed.
    if u.get("tier") == "pro":
        pro_until = u.get("pro_until")
        if isinstance(pro_until, str):
            try:
                pu = datetime.fromisoformat(pro_until)
                if pu.tzinfo is None:
                    pu = pu.replace(tzinfo=timezone.utc)
                if pu > now:
                    return "pro"
                # Expired reward / lapsed sub — fall through to trial check
            except ValueError:
                return "pro"
        else:
            return "pro"

    # 2) 10-day signup trial
    created = u.get("created_at")
    if isinstance(created, str):
        try:
            created = datetime.fromisoformat(created)
        except ValueError:
            created = None
    if created and getattr(created, "tzinfo", None) is None:
        created = created.replace(tzinfo=timezone.utc)
    if created and (now - created) <= timedelta(days=TRIAL_DURATION_DAYS):
        return "pro"

    return "free"
