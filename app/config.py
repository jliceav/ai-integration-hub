"""Configuración central. Todo se lee de variables de entorno (o de un archivo .env).

Así el mismo código corre en local, en Docker y en Azure sin cambios:
solo cambian las variables.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AI Integration Hub"
    environment: str = "local"

    # Base de datos: SQLite en local, PostgreSQL en Docker/Azure.
    database_url: str = "sqlite:///./hub.db"

    # Seguridad
    api_key: str = "change-me"  # llave para consumir la API (header X-API-Key)
    woocommerce_webhook_secret: str = "change-me-too"  # secreto que configura WooCommerce

    # Proveedor de IA: "mock" (sin costo, para pruebas), "anthropic" u "openai"
    ai_provider: str = "mock"
    ai_api_key: str = ""
    ai_model: str = ""  # si se deja vacío se usa el default del proveedor
    ai_timeout_seconds: float = 20.0
    ai_max_retries: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
