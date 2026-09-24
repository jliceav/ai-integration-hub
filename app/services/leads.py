"""Lógica de negocio. Los routers REST, GraphQL y webhooks la reutilizan (una sola fuente de verdad)."""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.client import AIClient
from app.models import Lead
from app.schemas import LeadIn

logger = logging.getLogger(__name__)


def ingest_lead(db: Session, ai: AIClient, data: LeadIn) -> tuple[Lead, bool]:
    """Guarda un lead enriquecido con IA. Regresa (lead, creado).

    Es idempotente: si el mismo evento llega dos veces, no se duplica ni se vuelve a pagar la IA.
    """
    existing = db.scalar(select(Lead).where(Lead.source == data.source, Lead.external_id == data.external_id))
    if existing:
        return existing, False

    analysis = ai.analyze(data.message)
    lead = Lead(**data.model_dump(), **analysis.model_dump(), ai_provider=ai.name)
    db.add(lead)
    db.commit()
    db.refresh(lead)
    logger.info("Lead %s ingested from %s (intent=%s, priority=%s)", lead.id, lead.source, lead.intent, lead.priority)
    return lead, True


def list_leads(
    db: Session,
    status: str | None = None,
    intent: str | None = None,
    priority: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Lead]:
    stmt = select(Lead).order_by(Lead.created_at.desc(), Lead.id.desc())
    if status:
        stmt = stmt.where(Lead.status == status)
    if intent:
        stmt = stmt.where(Lead.intent == intent)
    if priority:
        stmt = stmt.where(Lead.priority == priority)
    return list(db.scalars(stmt.limit(limit).offset(offset)))


def get_lead(db: Session, lead_id: int) -> Lead | None:
    return db.get(Lead, lead_id)


def update_status(db: Session, lead_id: int, status: str) -> Lead | None:
    lead = db.get(Lead, lead_id)
    if lead is None:
        return None
    lead.status = status
    db.commit()
    db.refresh(lead)
    return lead
