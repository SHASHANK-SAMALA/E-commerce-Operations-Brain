"""API authentication dependency — single API key, checked on every request."""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader

from ecommerce_brain.config.settings import settings

_api_key_header = APIKeyHeader(name=settings.api_key_header, auto_error=False)


def require_api_key(api_key: str | None = Security(_api_key_header)) -> str:
    """FastAPI dependency — raises 401 if API key is missing or wrong."""
    if api_key is None or not secrets.compare_digest(api_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key
