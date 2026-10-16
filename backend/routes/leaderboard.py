"""
DUB STREAK Leaderboard — community thumbs-up ranking.

Endpoint:
    GET /api/leaderboard/dub-streak?period=week|all&limit=20

Privacy rule preserved: aggregates only count entries from binders where
case_packs.is_public = True. No source-pack info is exposed.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from core import db
from services.public_reads import fetch_dub_streak


router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])


@router.get("/dub-streak")
async def dub_streak_leaderboard(period: str = "week", limit: int = 20):
    """Ranks users by total thumbs-up across their public binders.

    Periods:
      - 'week' → thumbs-up cast in the last 7 days (drives recurring engagement)
      - 'all'  → cumulative thumbs_up_count across public pulls

    Top entry is flagged with `is_flame: true` so the UI can render the
    flame icon on #1 only.
    """
    if period not in ("week", "all"):
        raise HTTPException(status_code=400, detail="period must be 'week' or 'all'")
    cap = max(1, min(int(limit), 100))
    return await fetch_dub_streak(db, period=period, limit=cap)
