"""API GraphQL (Strawberry). Misma lógica que REST, pero el cliente elige qué campos quiere.

Útil para dashboards o front-ends que necesitan datos a la medida en una sola petición.
"""
from datetime import datetime

import strawberry
from fastapi import Depends
from strawberry.fastapi import GraphQLRouter
from strawberry.types import Info

from app.db import get_db
from app.models import Lead
from app.security import require_api_key
from app.services import leads as service


@strawberry.type(name="Lead")
class LeadType:
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
    status: str
    created_at: datetime

    @staticmethod
    def from_model(lead: Lead) -> "LeadType":
        return LeadType(**{f: getattr(lead, f) for f in LeadType.__annotations__ if f != "from_model"})


VALID_STATUSES = {"new", "contacted", "won", "lost"}


@strawberry.type
class Query:
    @strawberry.field(description="Lista leads con filtros opcionales")
    def leads(
        self,
        info: Info,
        status: str | None = None,
        intent: str | None = None,
        priority: str | None = None,
        limit: int = 50,
    ) -> list[LeadType]:
        db = info.context["db"]
        rows = service.list_leads(db, status, intent, priority, min(limit, 200))
        return [LeadType.from_model(r) for r in rows]

    @strawberry.field
    def lead(self, info: Info, id: int) -> LeadType | None:
        lead = service.get_lead(info.context["db"], id)
        return LeadType.from_model(lead) if lead else None


@strawberry.type
class Mutation:
    @strawberry.mutation(description="Cambia el estatus de un lead en el CRM")
    def update_lead_status(self, info: Info, id: int, status: str) -> LeadType | None:
        if status not in VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}")
        lead = service.update_status(info.context["db"], id, status)
        return LeadType.from_model(lead) if lead else None


async def get_context(_: None = Depends(require_api_key), db=Depends(get_db)):
    # La misma API key protege GraphQL; la sesión de BD se inyecta en el contexto.
    return {"db": db}


schema = strawberry.Schema(query=Query, mutation=Mutation)
graphql_router = GraphQLRouter(schema, context_getter=get_context)
