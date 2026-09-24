"""Dependencias compartidas (inyección de dependencias de FastAPI)."""
from fastapi import Depends

from app.ai.client import AIClient, build_ai_client
from app.config import Settings, get_settings

_ai_client: AIClient | None = None


def get_ai_client(settings: Settings = Depends(get_settings)) -> AIClient:
    """Un solo cliente de IA para toda la app (reutiliza conexiones HTTP)."""
    global _ai_client
    if _ai_client is None:
        _ai_client = build_ai_client(settings)
    return _ai_client
