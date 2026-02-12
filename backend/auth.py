"""Clerk JWT authentication for FastAPI."""
from __future__ import annotations

import time
from typing import Any, Dict, Optional, List

import httpx
from fastapi import Depends, Header, HTTPException, Request
from jose import jwt

from config import load_config

ALLOWED_ROLES = {"admin", "reader", "editor"}
JWKS_CACHE_TTL_SECONDS = 600

_jwks_cache: Dict[str, Any] = {"data": None, "fetched_at": 0.0}


def _get_jwks_url() -> str:
    load_config()  # ensures .env is loaded
    # Use env variable for Clerk JWKS
    from os import getenv

    jwks = getenv("CLERK_JWKS_URL", "").strip()
    if not jwks:
        raise HTTPException(
            status_code=500,
            detail="CLERK_JWKS_URL is not configured",
        )
    return jwks


def _get_jwks() -> Dict[str, Any]:
    now = time.time()
    if _jwks_cache["data"] and now - _jwks_cache["fetched_at"] < JWKS_CACHE_TTL_SECONDS:
        return _jwks_cache["data"]

    jwks_url = _get_jwks_url()
    with httpx.Client(timeout=10) as client:
        response = client.get(jwks_url)
        response.raise_for_status()
        jwks = response.json()
        _jwks_cache["data"] = jwks
        _jwks_cache["fetched_at"] = now
        return jwks


def _get_public_key(token: str) -> Optional[Dict[str, Any]]:
    jwks = _get_jwks()
    headers = jwt.get_unverified_header(token)
    kid = headers.get("kid")
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    return None


def _extract_role(claims: Dict[str, Any]) -> str:
    for metadata_key in ("public_metadata", "unsafe_metadata", "metadata"):
        metadata = claims.get(metadata_key)
        if isinstance(metadata, dict) and metadata.get("role"):
            return str(metadata.get("role")).lower()
    role = claims.get("role")
    if role:
        return str(role).lower()
    org_role = claims.get("org_role")
    if org_role:
        return str(org_role).lower()
    org_membership = claims.get("org_membership")
    if isinstance(org_membership, dict) and org_membership.get("role"):
        return str(org_membership.get("role")).lower()
    return ""


def _extract_roles(claims: Dict[str, Any]) -> List[str]:
    roles: List[str] = []
    role = _extract_role(claims)
    if role:
        roles.append(role)
    for list_key in ("roles", "org_roles", "permissions"):
        value = claims.get(list_key)
        if isinstance(value, list):
            roles.extend([str(item).lower() for item in value])
    return roles


def require_auth(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    if request.method == "OPTIONS":
        return {}
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not token:
        token = request.query_params.get("token", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    if not token:
        raise HTTPException(status_code=401, detail="Empty Bearer token")

    public_key = _get_public_key(token)
    if not public_key:
        raise HTTPException(status_code=401, detail="Invalid token key")

    try:
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    roles = _extract_roles(claims)
    if not roles or not any(role in ALLOWED_ROLES for role in roles):
        raise HTTPException(status_code=403, detail="Insufficient role")

    return claims


def require_roles(allowed_roles: List[str]):
    allowed_set = {role.lower() for role in allowed_roles}

    def _require_roles(claims: Dict[str, Any] = Depends(require_auth)) -> Dict[str, Any]:
        roles = _extract_roles(claims)
        if not roles or not any(role in allowed_set for role in roles):
            raise HTTPException(status_code=403, detail="Insufficient role")
        return claims

    return _require_roles

