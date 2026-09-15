"""Minimal Stripe Checkout wrapper matching Emergent's emergentintegrations API surface."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import stripe
from pydantic import BaseModel, Field


class CheckoutSessionRequest(BaseModel):
    amount: float
    currency: str = "usd"
    success_url: str
    cancel_url: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    payment_methods: Optional[List[str]] = None


class CheckoutSessionResponse(BaseModel):
    session_id: str
    url: str


class CheckoutStatusResponse(BaseModel):
    status: str
    payment_status: str
    amount_total: Optional[float] = None
    currency: Optional[str] = None


class WebhookResponse(BaseModel):
    session_id: Optional[str] = None
    payment_status: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StripeCheckout:
    def __init__(self, api_key: str, webhook_url: Optional[str] = None):
        self.api_key = api_key
        self.webhook_url = webhook_url
        stripe.api_key = api_key

    async def create_checkout_session(self, request: CheckoutSessionRequest) -> CheckoutSessionResponse:
        params: Dict[str, Any] = {
            "mode": "payment",
            "success_url": request.success_url,
            "cancel_url": request.cancel_url,
            "line_items": [
                {
                    "price_data": {
                        "currency": request.currency,
                        "unit_amount": int(round(request.amount * 100)),
                        "product_data": {"name": "Marketplace purchase"},
                    },
                    "quantity": 1,
                }
            ],
            "metadata": request.metadata or {},
        }
        if request.payment_methods:
            params["payment_method_types"] = request.payment_methods
        session = stripe.checkout.Session.create(**params)
        return CheckoutSessionResponse(session_id=session.id, url=session.url or "")

    async def get_checkout_status(self, session_id: str) -> CheckoutStatusResponse:
        session = stripe.checkout.Session.retrieve(session_id)
        amount_total = session.amount_total
        return CheckoutStatusResponse(
            status=session.status or "unknown",
            payment_status=session.payment_status or "unpaid",
            amount_total=(amount_total / 100.0) if amount_total is not None else None,
            currency=session.currency,
        )

    async def handle_webhook(self, body: bytes, sig: Optional[str]) -> WebhookResponse:
        # Dev-friendly: parse JSON event without requiring webhook secret.
        import json

        event = json.loads(body.decode("utf-8"))
        data_object = (event.get("data") or {}).get("object") or {}
        return WebhookResponse(
            session_id=data_object.get("id"),
            payment_status=data_object.get("payment_status"),
            metadata=data_object.get("metadata") or {},
        )
