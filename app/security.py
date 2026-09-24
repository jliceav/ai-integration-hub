"""Seguridad: API key para clientes internos y firma HMAC para webhooks externos."""
import base64
import hashlib
import hmac

from fastapi import Depends, Header, HTTPException, status

from app.config import Settings, get_settings


def require_api_key(
    x_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Protege los endpoints internos. El cliente debe enviar el header X-API-Key."""
    # compare_digest evita ataques de tiempo (timing attacks) al comparar secretos.
    if not x_api_key or not hmac.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key")


def woocommerce_signature(body: bytes, secret: str) -> str:
    """WooCommerce firma cada webhook con HMAC-SHA256 del cuerpo, codificado en base64."""
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def verify_woocommerce_signature(body: bytes, received: str | None, secret: str) -> bool:
    if not received:
        return False
    return hmac.compare_digest(woocommerce_signature(body, secret), received)
