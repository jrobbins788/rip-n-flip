"""
Dethrone detection — "Heart Attack" push nudge.

Strategy:
    Each successful upvote on a public-binder pull triggers a re-check of the
    weekly #1 ranker. We persist the current crown holder in a `crown_state`
    doc keyed by ISO week. If the holder changes mid-week:
       • Old holder gets a push notification + in-app banner:
         "You just lost the crown to @new_holder. Beat them by Sunday or it's their Pro extension! 👑"
       • crown_state is updated to the new holder.

    The 7-day rolling window matches `/api/leaderboard/dub-streak?period=week`
    and the cron reward in `routes/rewards.py` — so the experience is consistent.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from core import db, logger
from routes.push import send_notification


WEEK_KEY_FMT = "%G-W%V"  # ISO year-week (matches rewards._iso_week_key shape)


def _iso_week_key(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    iy, iw, _ = now.isocalendar()
    return f"{iy}-W{iw:02d}"


async def _compute_current_top() -> Optional[dict]:
    """Return {user_id, username, thumbs_week} for the current week's #1, or None."""
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
        {"$limit": 1},
    ]
    rows = await db.pull_thumbs.aggregate(pipeline).to_list(1)
    if not rows:
        return None
    top = rows[0]
    u = await db.users.find_one(
        {"user_id": top["_id"]},
        {"_id": 0, "user_id": 1, "username": 1, "name": 1, "picture": 1},
    )
    if not u:
        return None
    return {
        "user_id": top["_id"],
        "username": u.get("username") or u.get("name") or "Anonymous",
        "thumbs_week": int(top.get("thumbs_week") or 0),
        "picture": u.get("picture"),
    }


async def check_for_dethrone() -> Optional[dict]:
    """Called after a successful thumbs-up. If the weekly #1 changed since the
    last check, notify the dethroned user. Idempotent within the same crown
    holder — re-running won't double-notify.

    Returns: {dethroned_user_id, new_holder_id} on successful dethrone, else None.
    """
    week_key = _iso_week_key()
    new_top = await _compute_current_top()
    if not new_top or new_top["thumbs_week"] <= 0:
        return None

    state = await db.crown_state.find_one({"state_key": "weekly"}, {"_id": 0})

    # First time in this week — just bootstrap state, no dethrone fired
    if not state or state.get("week_key") != week_key:
        await db.crown_state.update_one(
            {"state_key": "weekly"},
            {"$set": {
                "state_key": "weekly",
                "week_key": week_key,
                "current_top_user_id": new_top["user_id"],
                "current_top_username": new_top["username"],
                "current_top_thumbs": new_top["thumbs_week"],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )
        return None

    prev_top_id = state.get("current_top_user_id")
    if prev_top_id and prev_top_id != new_top["user_id"]:
        # 👑 DETHRONE EVENT — notify the prior #1
        await db.crown_state.update_one(
            {"state_key": "weekly"},
            {"$set": {
                "current_top_user_id": new_top["user_id"],
                "current_top_username": new_top["username"],
                "current_top_thumbs": new_top["thumbs_week"],
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "last_dethrone_at": datetime.now(timezone.utc).isoformat(),
                "last_dethroned_user_id": prev_top_id,
            }},
        )
        try:
            await send_notification(
                user_id=prev_top_id,
                title="👑 You lost the crown",
                body=f"You just lost the crown to @{new_top['username']}. Beat them by Sunday or it's their Pro extension! 👑",
                payload={
                    "new_holder_user_id": new_top["user_id"],
                    "new_holder_username": new_top["username"],
                    "new_holder_thumbs": new_top["thumbs_week"],
                    "week_key": week_key,
                },
                notification_type="dethrone",
                url=f"/binders/{new_top['user_id']}",
            )
            logger.info(
                f"[dethrone] {prev_top_id} dethroned by {new_top['user_id']} "
                f"({new_top['thumbs_week']} thumbs, week={week_key})"
            )
        except Exception as e:
            logger.error(f"[dethrone] notification send failed: {e}")
        return {"dethroned_user_id": prev_top_id, "new_holder_id": new_top["user_id"]}

    # Same holder gained more thumbs — keep state fresh, no notification
    if new_top["thumbs_week"] != state.get("current_top_thumbs"):
        await db.crown_state.update_one(
            {"state_key": "weekly"},
            {"$set": {
                "current_top_thumbs": new_top["thumbs_week"],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
    return None
