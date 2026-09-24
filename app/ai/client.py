"""Integración con APIs de IA.

Patrón "adaptador": el resto del sistema solo conoce `AIClient.analyze()`.
Cambiar de proveedor (Anthropic, OpenAI o un mock para pruebas) es cambiar
una variable de entorno, sin tocar la lógica de negocio.
"""
from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.schemas import AIAnalysis

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres un asistente que clasifica mensajes de clientes de una empresa de turismo.
Responde SOLO con un objeto JSON válido, sin texto adicional, con estas llaves:
- "intent": una de "booking", "pricing", "complaint", "support", "other"
- "priority": una de "high", "medium", "low" (quejas y reservas con fecha cercana = high)
- "language": código ISO de 2 letras del idioma del mensaje (ej. "es", "en")
- "summary": resumen de máximo 25 palabras en español
"""


class AIError(Exception):
    """Error al hablar con el proveedor de IA."""


class RetryableAIError(AIError):
    """Error temporal (límite de uso, caída del proveedor): vale la pena reintentar."""


class AIClient(ABC):
    name: str

    @abstractmethod
    def _complete(self, message: str) -> str:
        """Envía el mensaje al modelo y regresa el texto crudo de la respuesta."""

    def analyze(self, message: str) -> AIAnalysis:
        """Analiza el mensaje. Nunca rompe el flujo: si la IA falla, regresa un análisis neutro."""
        try:
            raw = self._complete(message)
            return parse_analysis(raw)
        except (AIError, ValidationError, ValueError) as exc:
            logger.warning("AI analysis failed, using fallback: %s", exc)
            return AIAnalysis(summary=message[:200])


def parse_analysis(raw: str) -> AIAnalysis:
    """Extrae el JSON de la respuesta del modelo y lo valida contra el esquema."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)  # tolera texto extra alrededor del JSON
    if not match:
        raise ValueError("No JSON object in AI response")
    return AIAnalysis.model_validate(json.loads(match.group(0)))


class HTTPAIClient(AIClient):
    """Lógica común para proveedores HTTP: timeout y reintentos con backoff exponencial."""

    def __init__(self, settings: Settings, http: httpx.Client | None = None):
        self.settings = settings
        self.http = http or httpx.Client(timeout=settings.ai_timeout_seconds)

    def _post(self, url: str, headers: dict, payload: dict) -> dict:
        last_exc: Exception | None = None
        for attempt in range(self.settings.ai_max_retries + 1):
            try:
                resp = self.http.post(url, headers=headers, json=payload)
                # 429 (límite de uso) y 5xx son temporales: vale la pena reintentar.
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise RetryableAIError(f"Retryable status {resp.status_code}")
                if resp.status_code >= 400:
                    # 4xx (llave inválida, petición mal formada): reintentar no lo arregla.
                    raise AIError(f"Provider error {resp.status_code}: {resp.text[:200]}")
                return resp.json()
            except (httpx.HTTPError, RetryableAIError) as exc:
                last_exc = exc
                if attempt < self.settings.ai_max_retries:
                    time.sleep(0.5 * 2**attempt)
        raise AIError(str(last_exc))


class AnthropicClient(HTTPAIClient):
    name = "anthropic"
    url = "https://api.anthropic.com/v1/messages"

    def _complete(self, message: str) -> str:
        data = self._post(
            self.url,
            headers={
                "x-api-key": self.settings.ai_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            payload={
                "model": self.settings.ai_model or "claude-haiku-4-5",
                "max_tokens": 300,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": message}],
            },
        )
        return "".join(block.get("text", "") for block in data.get("content", []))


class OpenAIClient(HTTPAIClient):
    name = "openai"
    url = "https://api.openai.com/v1/chat/completions"

    def _complete(self, message: str) -> str:
        data = self._post(
            self.url,
            headers={"Authorization": f"Bearer {self.settings.ai_api_key}"},
            payload={
                "model": self.settings.ai_model or "gpt-4o-mini",
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": message},
                ],
            },
        )
        return data["choices"][0]["message"]["content"]


class MockAIClient(AIClient):
    """Clasificador por reglas: permite desarrollar y probar sin gastar en la API."""

    name = "mock"
    RULES = [
        ("complaint", "high", ("queja", "molest", "pésimo", "reembolso", "complaint", "refund")),
        ("booking", "high", ("reserv", "book", "apartar", "disponibilidad")),
        ("pricing", "medium", ("precio", "costo", "cuánto", "cuanto", "price", "cost")),
        ("support", "medium", ("ayuda", "problema", "no puedo", "help", "issue")),
    ]
    ENGLISH_HINTS = (" the ", " i ", " want", " please", "hello", " how ")

    def _complete(self, message: str) -> str:
        text = f" {message.lower()} "
        intent, priority = "other", "low"
        for rule_intent, rule_priority, words in self.RULES:
            if any(w in text for w in words):
                intent, priority = rule_intent, rule_priority
                break
        language = "en" if any(h in text for h in self.ENGLISH_HINTS) else "es"
        summary = " ".join(message.split()[:25])
        return json.dumps({"intent": intent, "priority": priority, "language": language, "summary": summary})


def build_ai_client(settings: Settings) -> AIClient:
    providers = {"anthropic": AnthropicClient, "openai": OpenAIClient}
    if settings.ai_provider in providers:
        if not settings.ai_api_key:
            logger.warning("AI_PROVIDER=%s but AI_API_KEY is empty; using mock", settings.ai_provider)
            return MockAIClient()
        return providers[settings.ai_provider](settings)
    return MockAIClient()
