"""Minimal OIDC/JWT validation for external identity integration."""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx
from jose import jwt

_JWKS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_JWKS_TTL_SECONDS = 3600


def external_identity_enabled() -> bool:
    return bool(os.environ.get("ONTRO_JWKS_URI", "").strip())


def validate_bearer_role(token: str) -> str:
    if not external_identity_enabled():
        raise ValueError("External identity is not configured")

    jwks_uri = os.environ.get("ONTRO_JWKS_URI", "").strip()
    jwks = _get_jwks(jwks_uri)
    unverified_header = jwt.get_unverified_header(token)
    key = _select_jwk(jwks, str(unverified_header.get("kid") or ""))
    algorithms = [str(unverified_header.get("alg") or "RS256")]

    audience = os.environ.get("ONTRO_JWT_AUDIENCE", "").strip() or None
    issuer = os.environ.get("ONTRO_JWT_ISSUER", "").strip() or None
    options = {"verify_aud": audience is not None, "verify_iss": issuer is not None}
    claims = jwt.decode(
        token, key, algorithms=algorithms, audience=audience, issuer=issuer, options=options
    )

    role_claim = os.environ.get("ONTRO_JWT_ROLE_CLAIM", "roles").strip() or "roles"
    role_mapping = _load_role_mapping()
    raw_roles = _extract_claim(claims, role_claim)
    normalized_roles = _normalize_roles(raw_roles)

    for target_role, accepted_roles in role_mapping.items():
        if any(role in accepted_roles for role in normalized_roles):
            return target_role
    raise ValueError("No authorized role claim found in token")


def _get_jwks(jwks_uri: str) -> dict[str, Any]:
    cached = _JWKS_CACHE.get(jwks_uri)
    now_ts = time.time()
    if cached and now_ts - cached[0] < _JWKS_TTL_SECONDS:
        return cached[1]

    response = httpx.get(jwks_uri, timeout=10.0)
    response.raise_for_status()
    payload = response.json()
    _JWKS_CACHE[jwks_uri] = (now_ts, payload)
    return payload


def _select_jwk(jwks: dict[str, Any], kid: str) -> dict[str, Any]:
    keys = jwks.get("keys", []) if isinstance(jwks, dict) else []
    for key in keys:
        if str(key.get("kid") or "") == kid:
            return key
    if len(keys) == 1:
        return keys[0]
    raise ValueError("Matching JWKS key not found")


def _extract_claim(claims: dict[str, Any], claim_path: str) -> Any:
    current: Any = claims
    for part in claim_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _normalize_roles(raw_roles: Any) -> list[str]:
    if raw_roles is None:
        return []
    if isinstance(raw_roles, str):
        return [raw_roles]
    if isinstance(raw_roles, list):
        return [str(item) for item in raw_roles]
    return [str(raw_roles)]


def _load_role_mapping() -> dict[str, list[str]]:
    raw = os.environ.get("ONTRO_JWT_ROLE_MAPPING", "").strip()
    if not raw:
        return {
            "admin": ["admin"],
            "operator": ["operator"],
            "viewer": ["viewer"],
        }
    payload = json.loads(raw)
    return {str(role): [str(item) for item in values] for role, values in payload.items()}
