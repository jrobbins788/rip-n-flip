"""
Social binders — public visibility, gallery, and thumbs-up voting.

Endpoints:
    PATCH /api/case/packs/{case_pack_id}/visibility   — owner-only toggle is_public
    GET   /api/binders/public                          — aggregated public gallery
    GET   /api/binders/public/{user_id}                — single user's public binder (privacy enforced)
    POST  /api/case/pulls/{pull_id}/thumbs             — cast / toggle thumbs vote
    GET   /api/case/pulls/{pull_id}/thumbs             — public count + caller's own vote
    GET   /api/binders/public/{user_id}/battle-cta     — "Battle a Champion" payload

Privacy rule:
    Public pulls are returned WITHOUT `case_pack_id` or `pack_type_id` — that
    mapping stays owner-private. Only the owner can see which pack each pull
    came from.
"""
from __future__ import annotations

from typing import List, Optional
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core import db, get_current_user, require_auth


router = APIRouter(prefix="/api", tags=["social"])


# ─── Visibility toggle ─────────────────────────────────────
class BinderVisibilityUpdate(BaseModel):
    is_public: bool


@router.patch("/case/packs/{case_pack_id}/visibility")
async def case_set_visibility(case_pack_id: str, payload: BinderVisibilityUpdate, request: Request):
    """Owner toggles whether a binder is publicly visible."""
    user = await require_auth(request)
    pack = await db.case_packs.find_one({"case_pack_id": case_pack_id}, {"_id": 0})
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")
    if pack["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Not your pack")
    await db.case_packs.update_one(
        {"case_pack_id": case_pack_id},
        {"$set": {
            "is_public": bool(payload.is_public),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {"case_pack_id": case_pack_id, "is_public": bool(payload.is_public)}


# ─── Public gallery list ───────────────────────────────────
@router.get("/binders/public")
async def list_public_binders(limit: int = 24, sport: Optional[str] = None):
    """Aggregated public gallery — users with public binders + counts."""
    match: dict = {"is_public": True}
    if sport:
        match["sport"] = sport
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$user_id",
            "binder_count": {"$sum": 1},
            "pulls_total": {"$sum": "$pulls_count"},
            "sports": {"$addToSet": "$sport"},
            "latest": {"$max": "$updated_at"},
        }},
        {"$sort": {"latest": -1}},
        {"$limit": int(limit)},
    ]
    rows = await db.case_packs.aggregate(pipeline).to_list(int(limit))
    out = []
    for r in rows:
        u = await db.users.find_one(
            {"user_id": r["_id"]},
            {"_id": 0, "username": 1, "name": 1, "user_id": 1, "picture": 1},
        )
        if not u:
            continue
        out.append({
            "user_id": u["user_id"],
            "username": u.get("username") or u.get("name") or "Anonymous",
            "picture": u.get("picture"),
            "binder_count": r.get("binder_count", 0),
            "pulls_total": r.get("pulls_total", 0),
            "sports": [s for s in (r.get("sports") or []) if s],
            "latest": r.get("latest"),
        })
    return {"binders": out, "count": len(out)}


# ─── Single user's public binder ───────────────────────────
@router.get("/binders/public/{user_id}")
async def public_binder(user_id: str):
    """Single user's public binder.
    PRIVACY RULE: pulls returned WITHOUT case_pack_id, pack_type_id, or any
    info tying a card to its source pack.
    """
    u = await db.users.find_one(
        {"user_id": user_id},
        {"_id": 0, "username": 1, "name": 1, "user_id": 1, "picture": 1, "created_at": 1},
    )
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    public_pack_ids: List[str] = []
    sports = set()
    async for p in db.case_packs.find(
        {"user_id": user_id, "is_public": True},
        {"_id": 0, "case_pack_id": 1, "sport": 1},
    ):
        public_pack_ids.append(p["case_pack_id"])
        if p.get("sport"):
            sports.add(p["sport"])

    pulls = []
    if public_pack_ids:
        cursor = db.case_pulls.find(
            {"case_pack_id": {"$in": public_pack_ids}},
            {"_id": 0, "pull_id": 1, "card": 1, "card_number": 1, "parallel": 1,
             "rarity_tier": 1, "thumbs_up_count": 1, "timestamp": 1, "image_url": 1},
        ).sort("timestamp", -1).limit(500)
        pulls_raw = await cursor.to_list(500)
        for pull in pulls_raw:
            pull["source_pack"] = "—"  # privacy mask
            pull.setdefault("thumbs_up_count", 0)
            pulls.append(pull)

    return {
        "user": {
            "user_id": u["user_id"],
            "username": u.get("username") or u.get("name") or "Anonymous",
            "picture": u.get("picture"),
            "joined": u.get("created_at"),
        },
        "stats": {
            "public_binders": len(public_pack_ids),
            "pulls_total": len(pulls),
            "sports": sorted(sports),
        },
        "pulls": pulls,
    }


# ─── Battle a Champion CTA ─────────────────────────────────
# Drives competitive engagement: when viewing a top-3 weekly winner's binder,
# expose "Beat their X thumbs this week to take the crown" copy.
@router.get("/binders/public/{user_id}/battle-cta")
async def battle_cta(user_id: str):
    """Return rank info for `user_id` on this week's DUB STREAK leaderboard.

    Response keys:
      - is_champion (bool): user is in current top-3 weekly winners
      - rank (int | None): 1-based rank if in top-N (limit=10)
      - thumbs_week (int): user's thumbs-up count over last 7 days
      - top_thumbs (int): #1 weekly leader's thumbs (helps frontend show "beat the king")
      - crown_holder (str | None): username of #1 leader
    """
    target_user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "user_id": 1})
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    week_ago_iso = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    pipeline = [
        {"$match": {"vote": "up", "created_at": {"$gte": week_ago_iso}}},
        {"$lookup": {
            "from": "case_pulls", "localField": "pull_id",
            "foreignField": "pull_id", "as": "pull",
        }},
        {"$unwind": "$pull"},
        {"$lookup": {
            "from": "case_packs", "localField": "pull.case_pack_id",
            "foreignField": "case_pack_id", "as": "pack",
        }},
        {"$unwind": "$pack"},
        {"$match": {"pack.is_public": True}},
        {"$group": {"_id": "$pull.user_id", "thumbs_week": {"$sum": 1}}},
        {"$sort": {"thumbs_week": -1}},
        {"$limit": 10},
    ]
    rows = await db.pull_thumbs.aggregate(pipeline).to_list(10)

    rank = None
    thumbs_week = 0
    for idx, r in enumerate(rows, start=1):
        if r.get("_id") == user_id:
            rank = idx
            thumbs_week = int(r.get("thumbs_week") or 0)
            break

    top_thumbs = int(rows[0].get("thumbs_week") or 0) if rows else 0
    crown_holder = None
    if rows:
        cu = await db.users.find_one(
            {"user_id": rows[0]["_id"]},
            {"_id": 0, "username": 1, "name": 1},
        )
        if cu:
            crown_holder = cu.get("username") or cu.get("name") or "Anonymous"

    return {
        "user_id": user_id,
        "is_champion": rank is not None and rank <= 3 and thumbs_week > 0,
        "rank": rank,
        "thumbs_week": thumbs_week,
        "top_thumbs": top_thumbs,
        "crown_holder": crown_holder,
    }


# ─── Thumbs vote ───────────────────────────────────────────
class PullThumbVote(BaseModel):
    vote: str  # 'up' | 'down'


@router.post("/case/pulls/{pull_id}/thumbs")
async def case_thumb_pull(pull_id: str, payload: PullThumbVote, request: Request):
    """One vote per user per pull. Toggling same vote removes it.
    Public response only ever exposes thumbs_up count.
    """
    user = await require_auth(request)
    if payload.vote not in ("up", "down"):
        raise HTTPException(status_code=400, detail="vote must be 'up' or 'down'")

    pull = await db.case_pulls.find_one(
        {"pull_id": pull_id}, {"_id": 0, "user_id": 1, "case_pack_id": 1},
    )
    if not pull:
        raise HTTPException(status_code=404, detail="Pull not found")

    parent = await db.case_packs.find_one(
        {"case_pack_id": pull["case_pack_id"]}, {"_id": 0, "is_public": 1},
    )
    if not parent or not parent.get("is_public"):
        raise HTTPException(status_code=403, detail="Voting is only allowed on public binders")

    if pull["user_id"] == user["user_id"]:
        raise HTTPException(status_code=400, detail="Can't vote on your own pulls")

    existing = await db.pull_thumbs.find_one(
        {"pull_id": pull_id, "user_id": user["user_id"]}, {"_id": 0},
    )
    now_iso = datetime.now(timezone.utc).isoformat()

    if existing and existing.get("vote") == payload.vote:
        await db.pull_thumbs.delete_one({"pull_id": pull_id, "user_id": user["user_id"]})
        if payload.vote == "up":
            await db.case_pulls.update_one(
                {"pull_id": pull_id}, {"$inc": {"thumbs_up_count": -1}},
            )
        result_vote = None
    elif existing:
        await db.pull_thumbs.update_one(
            {"pull_id": pull_id, "user_id": user["user_id"]},
            {"$set": {"vote": payload.vote, "updated_at": now_iso}},
        )
        delta = 1 if payload.vote == "up" else -1
        await db.case_pulls.update_one(
            {"pull_id": pull_id}, {"$inc": {"thumbs_up_count": delta}},
        )
        result_vote = payload.vote
    else:
        await db.pull_thumbs.insert_one({
            "pull_id": pull_id,
            "user_id": user["user_id"],
            "vote": payload.vote,
            "created_at": now_iso,
            "updated_at": now_iso,
        })
        if payload.vote == "up":
            await db.case_pulls.update_one(
                {"pull_id": pull_id}, {"$inc": {"thumbs_up_count": 1}},
            )
        result_vote = payload.vote

    fresh = await db.case_pulls.find_one(
        {"pull_id": pull_id}, {"_id": 0, "thumbs_up_count": 1},
    )

    # 👑 Dethrone check — fires when an upvote may have flipped the weekly #1.
    # Best-effort; never break the vote response if this fails.
    if payload.vote == "up" and result_vote == "up":
        try:
            from services.dethrone import check_for_dethrone
            await check_for_dethrone()
        except Exception:
            pass

    return {
        "pull_id": pull_id,
        "your_vote": result_vote,
        "thumbs_up_count": (fresh or {}).get("thumbs_up_count", 0),
    }


@router.get("/case/pulls/{pull_id}/thumbs")
async def case_get_pull_thumbs(pull_id: str, request: Request):
    """Public thumbs_up count + caller's own vote (if logged in)."""
    pull = await db.case_pulls.find_one(
        {"pull_id": pull_id}, {"_id": 0, "thumbs_up_count": 1},
    )
    if not pull:
        raise HTTPException(status_code=404, detail="Pull not found")
    your_vote = None
    user = await get_current_user(request)
    if user:
        v = await db.pull_thumbs.find_one(
            {"pull_id": pull_id, "user_id": user["user_id"]}, {"_id": 0, "vote": 1},
        )
        your_vote = (v or {}).get("vote")
    return {
        "pull_id": pull_id,
        "thumbs_up_count": pull.get("thumbs_up_count", 0),
        "your_vote": your_vote,
    }
