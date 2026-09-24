"""Tablas de la base de datos (el "CRM" interno)."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Lead(Base):
    """Un prospecto o pedido que llegó de un sistema externo y fue enriquecido con IA."""

    __tablename__ = "leads"
    # Evita duplicados si el sistema externo reenvía el mismo evento (idempotencia).
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_source_external_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50))  # woocommerce, whatsapp, web_form...
    external_id: Mapped[str] = mapped_column(String(100))
    customer_name: Mapped[str] = mapped_column(String(200))
    customer_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    message: Mapped[str] = mapped_column(Text)

    # Campos que llena la IA
    intent: Mapped[str] = mapped_column(String(50), default="other")
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    language: Mapped[str] = mapped_column(String(5), default="es")
    summary: Mapped[str] = mapped_column(Text, default="")
    ai_provider: Mapped[str] = mapped_column(String(20), default="mock")

    status: Mapped[str] = mapped_column(String(20), default="new")  # new, contacted, won, lost
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
