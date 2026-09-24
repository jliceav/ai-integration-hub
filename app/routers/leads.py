"""API REST para sistemas internos (CRM, dashboards, ERP)."""
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.ai.client import AIClient
from app.db import get_db
from app.deps import get_ai_client
from app.schemas import Intent, LeadIn, LeadOut, LeadStatusUpdate, Priority, Status
from app.security import require_api_key
from app.services import leads as service

router = APIRouter(prefix="/api/v1/leads", tags=["leads"], dependencies=[Depends(require_api_key)])


@router.post("", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
def create_lead(
    data: LeadIn,
    response: Response,
    db: Session = Depends(get_db),
    ai: AIClient = Depends(get_ai_client),
):
    """Recibe un lead de cualquier sistema, lo analiza con IA y lo guarda."""
    lead, created = service.ingest_lead(db, ai, data)
    if not created:
        response.status_code = status.HTTP_200_OK  # ya existía: respuesta idempotente
    return lead


@router.get("", response_model=list[LeadOut])
def list_leads(
    status_: Status | None = Query(default=None, alias="status"),
    intent: Intent | None = None,
    priority: Priority | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return service.list_leads(db, status_, intent, priority, limit, offset)


@router.get("/{lead_id}", response_model=LeadOut)
def get_lead(lead_id: int, db: Session = Depends(get_db)):
    lead = service.get_lead(db, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.patch("/{lead_id}", response_model=LeadOut)
def update_lead_status(lead_id: int, body: LeadStatusUpdate, db: Session = Depends(get_db)):
    lead = service.update_status(db, lead_id, body.status)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead
