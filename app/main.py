"""Punto de entrada de la aplicación."""
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from sqlalchemy import text

from app.config import get_settings
from app.db import engine, init_db
from app.graphql_api import graphql_router
from app.routers import leads, webhooks

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("hub")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    logger.info("Started %s (env=%s, ai=%s)", get_settings().app_name, get_settings().environment, get_settings().ai_provider)
    yield


app = FastAPI(
    title="AI Integration Hub",
    version="1.0.0",
    description="Recibe leads y pedidos de sistemas externos, los enriquece con IA y los expone vía REST y GraphQL.",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_id_and_timing(request: Request, call_next):
    """Cada petición recibe un ID único para rastrearla en los logs (clave al depurar integraciones)."""
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    response.headers["x-request-id"] = request_id
    logger.info("%s %s -> %s (%.1f ms) rid=%s", request.method, request.url.path, response.status_code, elapsed_ms, request_id)
    return response


@app.get("/health", tags=["ops"])
def health():
    """Liveness/readiness: lo usan Docker y Azure para saber si el servicio está sano."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": db_ok, "ai_provider": get_settings().ai_provider}


app.include_router(leads.router)
app.include_router(webhooks.router)
app.include_router(graphql_router, prefix="/graphql", tags=["graphql"])
