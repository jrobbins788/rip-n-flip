"""
DUB STREAK weekly reward — top-3 winners each week get a 14-day Pro extension.

This module exposes:
  • compute_weekly_winners() — pure aggregation helper, top-3 by thumbs-up
  • POST /api/leaderboard/award-weekly  — admin-only trigger (idempotent per week)
  • GET  /api/leaderboard/recent-awards — public list of recent reward winners

Reward mechanic: bump users.pro_until = max(now+14d, current pro_until).
The user_tier() helper in core.py already respects pro_until via the
`tier == 'pro'` shortcut (we set that field when awarding).
"""
from __future__ import annotations

from typing import List, Optional
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Request

from core import db, logger
from core import get_current_user


router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard-rewards"])

WEEKLY_REWARD_DAYS = 14
TOP_N_WINNERS = 3


def _iso_week_key(dt: datetime) -> str:
    """ISO week key like '2026-W19' for idempotency."""
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


async def compute_weekly_winners(now: Optional[datetime] = None) -> List[dict]:
    """Aggregate the top-N users by thumbs-up cast in the last 7 days
    on public binders. Pure read — no side effects."""
    now = now or datetime.now(timezone.utc)
    week_ago_iso = (now - timedelta(days=7)).isoformat()
    pipeline = [
        {"$match": {"vote": "up", "created_at": {"$gte": week_ago_iso}}},
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
        {"$limit": TOP_N_WINNERS},
    ]
    rows = await db.pull_thumbs.aggregate(pipeline).to_list(TOP_N_WINNERS)
    winners = [
        {"user_id": r["_id"], "thumbs_total": int(r.get("thumbs_period") or 0), "rank": idx}
        for idx, r in enumerate(rows, start=1)
        if r.get("_id") and (r.get("thumbs_period") or 0) > 0
    ]
    return winners


async def _extend_pro_until(user_id: str, days: int, now: datetime) -> Optional[str]:
    """Idempotent pro_until extension. Sets pro_until = max(now+days, current)."""
    target = now + timedelta(days=days)
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "pro_until": 1, "tier": 1})
    if not user:
        return None
    existing = user.get("pro_until")
    if isinstance(existing, str):
        try:
            existing_dt = datetime.fromisoformat(existing)
            if existing_dt.tzinfo is None:
                existing_dt = existing_dt.replace(tzinfo=timezone.utc)
            if existing_dt > target:
                target = existing_dt
        except ValueError:
            pass
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "tier": "pro",
            "pro_until": target.isoformat(),
            "pro_source": "dub_streak_reward",
            "updated_at": now.isoformat(),
        }},
    )
    return target.isoformat()


@router.post("/award-weekly")
async def award_weekly_winners(request: Request):
    """Admin-only — idempotent. Picks top-3 weekly thumbs-up winners and
    extends pro_until by WEEKLY_REWARD_DAYS for each. Writes an audit doc
    to dub_streak_awards keyed by ISO week so re-running is safe.
    """
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    now = datetime.now(timezone.utc)
    week_key = _iso_week_key(now)

    # Idempotency — if we already ran this week, return prior result
    existing = await db.dub_streak_awards.find_one({"week_key": week_key}, {"_id": 0})
    if existing:
        return {"week_key": week_key, "already_awarded": True, **existing}

    winners = await compute_weekly_winners(now)
    if not winners:
        # No one earned thumbs this week — write empty audit doc
        await db.dub_streak_awards.insert_one({
            "week_key": week_key,
            "awarded_at": now.isoformat(),
            "winners": [],
            "reward_days": WEEKLY_REWARD_DAYS,
        })
        return {"week_key": week_key, "winners": [], "message": "No qualifying winners this week"}

    # Apply the rewards
    results = []
    for w in winners:
        pro_until = await _extend_pro_until(w["user_id"], WEEKLY_REWARD_DAYS, now)
        u = await db.users.find_one(
            {"user_id": w["user_id"]},
            {"_id": 0, "username": 1, "name": 1, "user_id": 1, "picture": 1},
        ) or {}
        results.append({
            "rank": w["rank"],
            "user_id": w["user_id"],
            "username": u.get("username") or u.get("name") or "Anonymous",
            "picture": u.get("picture"),
            "thumbs_total": w["thumbs_total"],
            "pro_until": pro_until,
            "reward_days": WEEKLY_REWARD_DAYS,
        })

    # Audit log
    await db.dub_streak_awards.insert_one({
        "week_key": week_key,
        "awarded_at": now.isoformat(),
        "winners": results,
        "reward_days": WEEKLY_REWARD_DAYS,
    })
    logger.info(f"DUB STREAK awarded {len(results)} winners for week {week_key}")

    return {
        "week_key": week_key,
        "winners": results,
        "reward_days": WEEKLY_REWARD_DAYS,
        "already_awarded": False,
    }


@router.get("/recent-awards")
async def recent_awards(limit: int = 8):
    """Public — last N weeks of DUB STREAK winners. UI uses this to show
    the 'Past Champions' strip beneath the live leaderboard."""
    cap = max(1, min(int(limit), 26))
    cursor = db.dub_streak_awards.find({}, {"_id": 0}).sort("awarded_at", -1).limit(cap)
    docs = await cursor.to_list(cap)
    return {"awards": docs, "count": len(docs)}
