"""
Web Push notifications + in-app notification queue.

Endpoints (all under /api):
    GET  /api/push/vapid-public-key            — public; frontend uses to subscribe
    POST /api/push/subscribe                   — auth; register PushSubscription JSON
    POST /api/push/unsubscribe                 — auth; remove a registered endpoint
    GET  /api/notifications                    — auth; list current user's notifications
    POST /api/notifications/{id}/read          — auth; mark single notification read
    POST /api/notifications/read-all           — auth; mark all read

The dethrone trigger lives in `services/dethrone.py` and is called from
`routes/social.py` immediately after a successful upvote that increments a
thumbs_up_count. That keeps the hot path lean.
"""
from __future__ import annotations

import os
import uuid
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core import db, require_auth, logger

router = APIRouter(prefix="/api", tags=["push"])

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "").strip()
VAPID_PRIVATE_KEY_PEM = os.environ.get("VAPID_PRIVATE_KEY_PEM", "").strip()
VAPID_CONTACT = os.environ.get("VAPID_CONTACT", "mailto:admin@flipnrip.com").strip()

if VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY_PEM:
    logger.info(f"[push] VAPID keys loaded — public={VAPID_PUBLIC_KEY[:16]}…")
else:
    logger.warning("[push] VAPID keys missing — push notifications disabled")


class PushSubscribePayload(BaseModel):
    endpoint: str
    keys: dict  # {p256dh: str, auth: str}
    user_agent: Optional[str] = None


class PushUnsubscribePayload(BaseModel):
    endpoint: str


@router.get("/push/vapid-public-key")
async def get_vapid_public_key():
    """Public — browser uses this to call PushManager.subscribe()."""
    return {
        "vapid_public_key": VAPID_PUBLIC_KEY or None,
        "enabled": bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY_PEM),
    }


@router.post("/push/subscribe")
async def push_subscribe(payload: PushSubscribePayload, request: Request):
    """Persist a PushSubscription for the logged-in user.
    Upsert by (user_id, endpoint) so re-subscribing is idempotent.
    """
    user = await require_auth(request)
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.push_subscriptions.update_one(
        {"user_id": user["user_id"], "endpoint": payload.endpoint},
        {"$set": {
            "user_id": user["user_id"],
            "endpoint": payload.endpoint,
            "keys": payload.keys,
            "user_agent": payload.user_agent,
            "updated_at": now_iso,
        }, "$setOnInsert": {"created_at": now_iso}},
        upsert=True,
    )
    return {"subscribed": True}


@router.post("/push/unsubscribe")
async def push_unsubscribe(payload: PushUnsubscribePayload, request: Request):
    user = await require_auth(request)
    result = await db.push_subscriptions.delete_one({
        "user_id": user["user_id"],
        "endpoint": payload.endpoint,
    })
    return {"unsubscribed": result.deleted_count > 0}


@router.get("/notifications")
async def list_notifications(request: Request, limit: int = 20, only_unread: bool = False):
    """In-app notification feed for the logged-in user."""
    user = await require_auth(request)
    q: dict = {"user_id": user["user_id"]}
    if only_unread:
        q["read"] = False
    cursor = db.notifications.find(q, {"_id": 0}).sort("created_at", -1).limit(int(limit))
    rows = await cursor.to_list(int(limit))
    unread_count = await db.notifications.count_documents(
        {"user_id": user["user_id"], "read": False}
    )
    return {"notifications": rows, "unread_count": unread_count}


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, request: Request):
    user = await require_auth(request)
    result = await db.notifications.update_one(
        {"notification_id": notification_id, "user_id": user["user_id"]},
        {"$set": {"read": True, "read_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"read": True}


@router.post("/notifications/read-all")
async def mark_all_notifications_read(request: Request):
    user = await require_auth(request)
    result = await db.notifications.update_many(
        {"user_id": user["user_id"], "read": False},
        {"$set": {"read": True, "read_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"updated": result.modified_count}


# ─── Internal: send a web push + persist in-app notification ───
async def send_notification(
    user_id: str,
    title: str,
    body: str,
    payload: Optional[dict] = None,
    notification_type: str = "generic",
    url: Optional[str] = None,
) -> dict:
    """Fan-out a notification:
      1. Insert an in-app notification doc (always)
      2. For each registered push subscription, send web push (best-effort)

    Returns: {notification_id, push_sent, push_failed}
    """
    notification_id = f"notif_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    doc = {
        "notification_id": notification_id,
        "user_id": user_id,
        "type": notification_type,
        "title": title,
        "body": body,
        "payload": payload or {},
        "url": url,
        "read": False,
        "created_at": now_iso,
    }
    await db.notifications.insert_one(doc)

    push_sent, push_failed = 0, 0
    if VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY_PEM:
        try:
            from pywebpush import webpush, WebPushException  # noqa
            cursor = db.push_subscriptions.find(
                {"user_id": user_id}, {"_id": 0, "endpoint": 1, "keys": 1}
            )
            subs = await cursor.to_list(50)
            push_payload = json.dumps({
                "title": title,
                "body": body,
                "url": url or "/binders",
                "notification_id": notification_id,
                "type": notification_type,
            })
            for s in subs:
                try:
                    webpush(
                        subscription_info={"endpoint": s["endpoint"], "keys": s["keys"]},
                        data=push_payload,
                        vapid_private_key=VAPID_PRIVATE_KEY_PEM,
                        vapid_claims={"sub": VAPID_CONTACT},
                    )
                    push_sent += 1
                except WebPushException as e:
                    push_failed += 1
                    code = getattr(e.response, "status_code", None) if hasattr(e, "response") and e.response else None
                    # 404 / 410 → endpoint gone, remove it
                    if code in (404, 410):
                        await db.push_subscriptions.delete_one(
                            {"user_id": user_id, "endpoint": s["endpoint"]}
                        )
                    logger.warning(f"[push] webpush failed user={user_id} code={code}: {e}")
                except Exception as e:
                    push_failed += 1
                    logger.warning(f"[push] webpush unexpected user={user_id}: {e}")
        except Exception as e:
            logger.error(f"[push] notification fanout error: {e}")

    return {"notification_id": notification_id, "push_sent": push_sent, "push_failed": push_failed}
