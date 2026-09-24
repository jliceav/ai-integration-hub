import os

# Configuración de pruebas ANTES de importar la app: BD en archivo temporal y IA simulada.
os.environ.update(
    {
        "DATABASE_URL": "sqlite:///./test_hub.db",
        "API_KEY": "test-key",
        "WOOCOMMERCE_WEBHOOK_SECRET": "wc-secret",
        "AI_PROVIDER": "mock",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    with TestClient(app) as c:  # "with" ejecuta el arranque (crea tablas)
        yield c
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def auth():
    return {"X-API-Key": "test-key"}
