"""
DUB STREAK Leaderboard — community thumbs-up ranking.

Endpoint:
    GET /api/leaderboard/dub-streak?period=week|all&limit=20

Privacy rule preserved: aggregates only count entries from binders where
case_packs.is_public = True. No source-pack info is exposed.
"""
from __future__ import annotations

from typing import List
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException

from core import db


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

    if period == "week":
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        pipeline = [
            {"$match": {"vote": "up", "created_at": {"$gte": week_ago}}},
            {"$lookup": {
                "from": "case_pulls", "localField": "pull_id",
                "foreignField": "pull_id", "as": "pull",
            }},
            {"$unwind": "$pull"},
            {"$lookup": {
                "from": "case_packs",
                "localField": "pull.case_pack_id",
                "foreignField": "case_pack_id",
                "as": "pack",
            }},
            {"$unwind": "$pack"},
            {"$match": {"pack.is_public": True}},
            {"$group": {"_id": "$pull.user_id", "thumbs_period": {"$sum": 1}}},
            {"$sort": {"thumbs_period": -1}},
            {"$limit": cap},
        ]
        rows = await db.pull_thumbs.aggregate(pipeline).to_list(cap)
    else:
        pipeline = [
            {"$lookup": {
                "from": "case_packs", "localField": "case_pack_id",
                "foreignField": "case_pack_id", "as": "pack",
            }},
            {"$unwind": "$pack"},
            {"$match": {"pack.is_public": True}},
            {"$group": {
                "_id": "$user_id",
                "thumbs_period": {"$sum": "$thumbs_up_count"},
                "public_pulls": {"$sum": 1},
            }},
            {"$sort": {"thumbs_period": -1}},
            {"$limit": cap},
        ]
        rows = await db.case_pulls.aggregate(pipeline).to_list(cap)

    entries: List[dict] = []
    for idx, r in enumerate(rows, start=1):
        user_id = r.get("_id")
        if not user_id:
            continue
        u = await db.users.find_one(
            {"user_id": user_id},
            {"_id": 0, "user_id": 1, "username": 1, "name": 1, "picture": 1},
        )
        if not u:
            continue
        entry = {
            "rank": idx,
            "user_id": u["user_id"],
            "username": u.get("username") or u.get("name") or "Anonymous",
            "picture": u.get("picture"),
            "thumbs_total": int(r.get("thumbs_period") or 0),
            "is_flame": idx == 1 and (r.get("thumbs_period") or 0) > 0,
        }
        if period == "all":
            entry["public_pulls"] = int(r.get("public_pulls") or 0)
        entries.append(entry)

    return {"period": period, "entries": entries, "count": len(entries)}
