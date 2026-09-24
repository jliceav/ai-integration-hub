"""Webhooks: puntos de entrada para sistemas EXTERNOS (aquí, WooCommerce).

WooCommerce no manda nuestra API key; en su lugar firma cada envío con un secreto
compartido. Verificamos esa firma antes de confiar en el contenido.
"""
import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.ai.client import AIClient
from app.config import Settings, get_settings
from app.db import get_db
from app.deps import get_ai_client
from app.schemas import LeadIn
from app.security import verify_woocommerce_signature
from app.services.leads import ingest_lead

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def woocommerce_order_to_lead(order: dict) -> LeadIn:
    """Traduce el formato de pedido de WooCommerce a nuestro formato interno (mapeo de datos)."""
    billing = order.get("billing") or {}
    name = f"{billing.get('first_name', '')} {billing.get('last_name', '')}".strip() or "Sin nombre"
    items = ", ".join(f"{i.get('quantity', 1)}x {i.get('name', '')}" for i in order.get("line_items", []))
    note = order.get("customer_note") or ""
    message = f"Pedido WooCommerce #{order.get('number', order.get('id'))}: {items}. Nota del cliente: {note}".strip()
    return LeadIn(
        source="woocommerce",
        external_id=str(order["id"]),
        customer_name=name,
        customer_email=billing.get("email") or None,
        message=message,
    )


@router.post("/woocommerce", status_code=status.HTTP_202_ACCEPTED)
async def woocommerce_webhook(
    request: Request,
    x_wc_webhook_signature: str | None = Header(default=None),
    x_wc_webhook_topic: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
    ai: AIClient = Depends(get_ai_client),
):
    body = await request.body()  # se usa el cuerpo CRUDO: la firma se calcula sobre los bytes exactos

    # WooCommerce hace un "ping" al crear el webhook (form-urlencoded, sin firma). Respondemos OK.
    if body.startswith(b"webhook_id="):
        return {"status": "ping_ok"}

    if not verify_woocommerce_signature(body, x_wc_webhook_signature, settings.woocommerce_webhook_secret):
        logger.warning("Rejected WooCommerce webhook: invalid signature")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    try:
        order = json.loads(body)
        lead_in = woocommerce_order_to_lead(order)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=f"Unexpected payload: {exc}") from exc

    lead, created = ingest_lead(db, ai, lead_in)
    return {"status": "created" if created else "duplicate", "lead_id": lead.id, "topic": x_wc_webhook_topic}
