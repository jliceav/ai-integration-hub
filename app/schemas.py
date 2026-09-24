"""Contratos de entrada/salida de la API (validación automática con Pydantic)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Intent = Literal["booking", "pricing", "complaint", "support", "other"]
Priority = Literal["high", "medium", "low"]
Status = Literal["new", "contacted", "won", "lost"]


class LeadIn(BaseModel):
    """Lo que envía cualquier sistema externo (formulario web, WhatsApp, otro CRM)."""

    source: str = Field(min_length=2, max_length=50, examples=["web_form"])
    external_id: str = Field(min_length=1, max_length=100, examples=["form-1001"])
    customer_name: str = Field(min_length=1, max_length=200, examples=["María López"])
    customer_email: EmailStr | None = None
    message: str = Field(min_length=1, max_length=5000, examples=["Hola, quiero reservar el Day Pass para 4 personas el sábado"])


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    external_id: str
    customer_name: str
    customer_email: str | None
    message: str
    intent: str
    priority: str
    language: str
    summary: str
    ai_provider: str
    status: str
    created_at: datetime
    updated_at: datetime


class LeadStatusUpdate(BaseModel):
    status: Status


class AIAnalysis(BaseModel):
    """Respuesta estructurada que exigimos a la IA. Si no cumple, se descarta."""

    intent: Intent = "other"
    priority: Priority = "medium"
    language: str = Field(default="es", max_length=5)
    summary: str = Field(default="", max_length=500)
