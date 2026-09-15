"""
Background scheduler — runs the DUB STREAK weekly award job automatically.

Triggers every Monday 00:05 UTC. The reward logic is idempotent per ISO week
(see /app/backend/routes/rewards.py `_iso_week_key`), so even if the worker
restarts or fires twice, only one award doc is written.

Why Monday 00:05 UTC?
  • The leaderboard's "this week" window is the last rolling 7 days.
  • Sunday end-of-day UTC ≈ Monday 00:00 UTC is a clean cut-off.
  • Adding 5 minutes ensures any late thumbs-up writes from Sunday are
    aggregated before we crown winners.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core import logger


_scheduler: "AsyncIOScheduler | None" = None


async def _run_weekly_award():
    """Idempotent — reuses the rewards module's award logic."""
    # Lazy import so server.py startup order is unaffected.
    from routes.rewards import compute_weekly_winners, _extend_pro_until, _iso_week_key, WEEKLY_REWARD_DAYS
    from core import db

    now = datetime.now(timezone.utc)
    week_key = _iso_week_key(now)

    existing = await db.dub_streak_awards.find_one({"week_key": week_key}, {"_id": 0})
    if existing:
        logger.info(f"[cron] DUB STREAK already awarded for week={week_key} — skipping")
        return

    winners = await compute_weekly_winners(now)
    if not winners:
        await db.dub_streak_awards.insert_one({
            "week_key": week_key,
            "awarded_at": now.isoformat(),
            "winners": [],
            "reward_days": WEEKLY_REWARD_DAYS,
            "trigger": "cron",
        })
        logger.info(f"[cron] DUB STREAK week={week_key} — no qualifying winners")
        return

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

    await db.dub_streak_awards.insert_one({
        "week_key": week_key,
        "awarded_at": now.isoformat(),
        "winners": results,
        "reward_days": WEEKLY_REWARD_DAYS,
        "trigger": "cron",
    })
    logger.info(f"[cron] DUB STREAK awarded {len(results)} winners for week={week_key}")


def start_scheduler() -> None:
    """Idempotently start the in-process APScheduler."""
    global _scheduler
    if _scheduler is not None:
        return
    if os.environ.get("DISABLE_SCHEDULER", "").strip().lower() in ("1", "true", "yes"):
        logger.info("[cron] scheduler disabled by DISABLE_SCHEDULER env")
        return

    sched = AsyncIOScheduler(timezone="UTC")
    sched.add_job(
        _run_weekly_award,
        trigger=CronTrigger(day_of_week="mon", hour=0, minute=5, timezone="UTC"),
        id="dub_streak_weekly_award",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60 * 60,  # if missed by up to 1h, still run
    )
    sched.start()
    _scheduler = sched
    logger.info(
        "[cron] APScheduler started — DUB STREAK weekly award fires Mondays 00:05 UTC"
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("[cron] APScheduler stopped")
