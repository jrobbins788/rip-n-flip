"""Read paths for the three public pages that were returning 500s.

GET /api/packs/price only uses Mongo as a 60-minute cache. A down database
must not block the eBay lookup.

GET /api/binders/public and GET /api/leaderboard/dub-streak have no source
other than Mongo. When the database is unreachable they return the same
empty shapes the UI already renders, plus ``unavailable: true``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

from services.db_guard import DatabaseUnavailable, await_db

logger = logging.getLogger("ripnflip.public_reads")

Scrape = Callable[[str, bool], Awaitable[dict]]


def _as_utc(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _json_time(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _fresh_cache(cached: Any, now: datetime, ttl: timedelta) -> Optional[dict]:
    if not isinstance(cached, dict):
        return None
    data = cached.get("data")
    if not isinstance(data, dict):
        return None
    fetched_at = _as_utc(cached.get("fetched_at"))
    if fetched_at is None or now - fetched_at >= ttl:
        return None
    hit = dict(data)
    hit["cached"] = True
    hit["fetched_at"] = fetched_at.isoformat()
    return hit


def _price_unavailable(query: str, sold: bool, now: datetime, reason: str) -> dict:
    return {
        "query": query.strip(),
        "sold_only": bool(sold),
        "count": 0,
        "avg": None,
        "min": None,
        "max": None,
        "median": None,
        "listings": [],
        "blocked": True,
        "cached": False,
        "fetched_at": now.isoformat(),
        "reason": reason,
    }


async def resolve_pack_price(
    *,
    db,
    query: str,
    sold: bool,
    refresh: bool,
    scrape: Scrape,
    now: datetime,
    ttl: timedelta,
) -> dict:
    """Return a price payload. Cache misses and cache outages still scrape."""
    cache_key = f"{query.strip().lower()}|sold={sold}"

    if not refresh:
        try:
            cached = await await_db(
                db.price_cache.find_one({"cache_key": cache_key}, {"_id": 0})
            )
        except DatabaseUnavailable as exc:
            logger.warning("Price cache read skipped; MongoDB unavailable: %s", exc)
            cached = None
        hit = _fresh_cache(cached, now, ttl)
        if hit is not None:
            return hit

    try:
        data = await scrape(query.strip(), sold)
    except Exception as exc:
        logger.exception("Price scrape failed for %r", query)
        return _price_unavailable(
            query,
            sold,
            now,
            f"Live eBay prices are temporarily unavailable ({type(exc).__name__}).",
        )

    if not isinstance(data, dict):
        return _price_unavailable(query, sold, now, "Live eBay prices are temporarily unavailable.")

    data = dict(data)
    data.setdefault("query", query.strip())
    data.setdefault("sold_only", bool(sold))
    data.setdefault("count", 0)
    data.setdefault("listings", [])
    data.setdefault("blocked", False)
    data["cached"] = False
    data["fetched_at"] = now.isoformat()

    try:
        await await_db(
            db.price_cache.update_one(
                {"cache_key": cache_key},
                {"$set": {
                    "cache_key": cache_key,
                    "query": query.strip(),
                    "sold_only": bool(sold),
                    "data": data,
                    "fetched_at": now.isoformat(),
                }},
                upsert=True,
            )
        )
    except DatabaseUnavailable as exc:
        logger.warning("Price cache write skipped; MongoDB unavailable: %s", exc)

    return data


async def fetch_public_binders(db, *, limit: int, sport: Optional[str]) -> dict:
    """Gallery list. Empty + unavailable when MongoDB cannot answer."""
    cap = max(1, min(int(limit), 100))
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
        {"$limit": cap},
    ]
    try:
        rows = await await_db(db.case_packs.aggregate(pipeline).to_list(cap))
        out = []
        for row in rows:
            user = await await_db(
                db.users.find_one(
                    {"user_id": row["_id"]},
                    {"_id": 0, "username": 1, "name": 1, "user_id": 1, "picture": 1},
                )
            )
            if not user:
                continue
            out.append({
                "user_id": user["user_id"],
                "username": user.get("username") or user.get("name") or "Anonymous",
                "picture": user.get("picture"),
                "binder_count": row.get("binder_count", 0),
                "pulls_total": row.get("pulls_total", 0),
                "sports": [s for s in (row.get("sports") or []) if s],
                "latest": _json_time(row.get("latest")),
            })
    except DatabaseUnavailable as exc:
        logger.warning("Public binder gallery unavailable: %s", exc)
        return {
            "binders": [],
            "count": 0,
            "unavailable": True,
            "reason": "Public binders are temporarily unavailable.",
        }
    return {"binders": out, "count": len(out)}


async def fetch_dub_streak(db, *, period: str, limit: int) -> dict:
    """DUB STREAK ranks. Empty + unavailable when MongoDB cannot answer."""
    cap = max(1, min(int(limit), 100))
    try:
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
            rows = await await_db(db.pull_thumbs.aggregate(pipeline).to_list(cap))
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
            rows = await await_db(db.case_pulls.aggregate(pipeline).to_list(cap))

        entries = []
        for idx, row in enumerate(rows, start=1):
            user_id = row.get("_id")
            if not user_id:
                continue
            user = await await_db(
                db.users.find_one(
                    {"user_id": user_id},
                    {"_id": 0, "user_id": 1, "username": 1, "name": 1, "picture": 1},
                )
            )
            if not user:
                continue
            entry = {
                "rank": idx,
                "user_id": user["user_id"],
                "username": user.get("username") or user.get("name") or "Anonymous",
                "picture": user.get("picture"),
                "thumbs_total": int(row.get("thumbs_period") or 0),
                "is_flame": idx == 1 and (row.get("thumbs_period") or 0) > 0,
            }
            if period == "all":
                entry["public_pulls"] = int(row.get("public_pulls") or 0)
            entries.append(entry)
    except DatabaseUnavailable as exc:
        logger.warning("DUB STREAK leaderboard unavailable: %s", exc)
        return {
            "period": period,
            "entries": [],
            "count": 0,
            "unavailable": True,
            "reason": "The leaderboard is temporarily unavailable.",
        }
    return {"period": period, "entries": entries, "count": len(entries)}
