"""
OIDC authentication via Authentik.
Config via env vars: OIDC_DISABLE, OIDC_ISSUER, OIDC_CLIENT_ID, OIDC_AUDIENCE, MASTER_TOKEN
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

logger = logging.getLogger(__name__)

OIDC_DISABLE = os.getenv("OIDC_DISABLE", "false").lower() in ("true", "1", "yes")
OIDC_ISSUER = os.getenv("OIDC_ISSUER", "")
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "")
OIDC_AUDIENCE = os.getenv("OIDC_AUDIENCE", "")
MASTER_TOKEN = os.getenv("MASTER_TOKEN", "")

_jwks_client: PyJWKClient | None = None
_discovery: dict[str, Any] = {}
_discovery_fetched_at: float = 0
_DISCOVERY_TTL = 3600


def _get_discovery() -> dict[str, Any]:
    global _discovery, _discovery_fetched_at
    if _discovery and (time.time() - _discovery_fetched_at) < _DISCOVERY_TTL:
        return _discovery
    url = OIDC_ISSUER.rstrip("/") + "/.well-known/openid-configuration"
    resp = httpx.get(url, timeout=10)
    resp.raise_for_status()
    _discovery = resp.json()
    _discovery_fetched_at = time.time()
    return _discovery


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is not None:
        return _jwks_client
    discovery = _get_discovery()
    _jwks_client = PyJWKClient(discovery["jwks_uri"], cache_keys=True)
    return _jwks_client


def is_auth_enabled() -> bool:
    return not OIDC_DISABLE


def validate_token(token: str) -> dict[str, Any]:
    """Validate a Bearer token. Returns decoded claims dict."""
    if MASTER_TOKEN and token == MASTER_TOKEN:
        return {"sub": "master", "master": True}

    if not OIDC_ISSUER:
        raise ValueError("OIDC_ISSUER not configured")

    jwks_client = _get_jwks_client()
    signing_key = jwks_client.get_signing_key_from_jwt(token)

    issuer = OIDC_ISSUER.rstrip("/") + "/"
    audience = OIDC_AUDIENCE or OIDC_CLIENT_ID

    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256", "ES256"],
        issuer=issuer,
        audience=audience,
        options={
            "verify_exp": True,
            "verify_iss": True,
            "verify_aud": bool(audience),
        },
    )
