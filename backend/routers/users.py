"""Users router — /users endpoints that proxy Clerk Backend API."""

import os
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import require_roles
from config import load_config

router = APIRouter(prefix="/users", tags=["Users"])

CLERK_API_BASE = "https://api.clerk.com/v1"


def _get_clerk_secret_key() -> str:
    """Return the Clerk secret key from environment variables."""
    load_config()  # ensures .env is loaded
    key = os.getenv("CLERK_SECRET_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=500, detail="CLERK_SECRET_KEY is not configured")
    return key


def _clerk_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_clerk_secret_key()}",
        "Content-Type": "application/json",
    }


# ── Schemas ────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    first_name: str
    last_name: str
    email: str
    password: str
    role: str = "reader"


class UserInvite(BaseModel):
    first_name: str = ""
    last_name: str = ""
    email: str
    role: str = "reader"


class UserUpdateRole(BaseModel):
    role: str


class InvitationResponse(BaseModel):
    id: str
    email_address: str
    status: str
    role: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    created_at: Optional[int] = None


class ClerkUser(BaseModel):
    id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    image_url: Optional[str] = None
    created_at: Optional[int] = None
    last_sign_in_at: Optional[int] = None


def _parse_clerk_user(user: Dict[str, Any]) -> ClerkUser:
    """Extract relevant fields from a Clerk user object."""
    emails = user.get("email_addresses", [])
    primary_email = None
    primary_id = user.get("primary_email_address_id")
    for em in emails:
        if em.get("id") == primary_id:
            primary_email = em.get("email_address")
            break
    if not primary_email and emails:
        primary_email = emails[0].get("email_address")

    public_metadata = user.get("public_metadata", {}) or {}

    return ClerkUser(
        id=user["id"],
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
        email=primary_email,
        role=public_metadata.get("role"),
        image_url=user.get("image_url"),
        created_at=user.get("created_at"),
        last_sign_in_at=user.get("last_sign_in_at"),
    )


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[ClerkUser])
def list_users(
    _: Dict[str, Any] = Depends(require_roles(["admin"])),
):
    """List all Clerk users."""
    headers = _clerk_headers()
    users: List[Dict[str, Any]] = []
    offset = 0
    limit = 100

    # Paginate through all users
    while True:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{CLERK_API_BASE}/users",
                headers=headers,
                params={"limit": limit, "offset": offset, "order_by": "-created_at"},
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        batch = resp.json()
        if not batch:
            break
        users.extend(batch)
        if len(batch) < limit:
            break
        offset += limit

    return [_parse_clerk_user(u) for u in users]


@router.post("", response_model=ClerkUser, status_code=201)
def create_user(
    data: UserCreate,
    _: Dict[str, Any] = Depends(require_roles(["admin"])),
):
    """Create a new Clerk user with a role in public_metadata."""
    headers = _clerk_headers()
    payload = {
        "first_name": data.first_name,
        "last_name": data.last_name,
        "email_address": [data.email],
        "password": data.password,
        "public_metadata": {"role": data.role},
    }

    with httpx.Client(timeout=15) as client:
        resp = client.post(f"{CLERK_API_BASE}/users", headers=headers, json=payload)

    if resp.status_code not in (200, 201):
        detail = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)

    return _parse_clerk_user(resp.json())


@router.post("/invite", response_model=InvitationResponse, status_code=201)
def invite_user(
    data: UserInvite,
    _: Dict[str, Any] = Depends(require_roles(["admin"])),
):
    """Send a Clerk invitation email with a role in public_metadata."""
    headers = _clerk_headers()
    public_metadata: Dict[str, Any] = {"role": data.role}
    if data.first_name:
        public_metadata["first_name"] = data.first_name
    if data.last_name:
        public_metadata["last_name"] = data.last_name
    payload: Dict[str, Any] = {
        "email_address": data.email,
        "public_metadata": public_metadata,
        "notify": True,
        "ignore_existing": False,
    }

    with httpx.Client(timeout=15) as client:
        resp = client.post(f"{CLERK_API_BASE}/invitations", headers=headers, json=payload)

    if resp.status_code not in (200, 201):
        detail = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)

    body = resp.json()
    public_metadata = body.get("public_metadata", {}) or {}
    return InvitationResponse(
        id=body["id"],
        email_address=body.get("email_address", data.email),
        status=body.get("status", "pending"),
        role=public_metadata.get("role"),
        first_name=public_metadata.get("first_name"),
        last_name=public_metadata.get("last_name"),
        created_at=body.get("created_at"),
    )


@router.get("/invitations", response_model=List[InvitationResponse])
def list_invitations(
    _: Dict[str, Any] = Depends(require_roles(["admin"])),
):
    """List pending Clerk invitations."""
    headers = _clerk_headers()

    with httpx.Client(timeout=15) as client:
        resp = client.get(
            f"{CLERK_API_BASE}/invitations",
            headers=headers,
            params={"status": "pending", "limit": 100},
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    raw = resp.json()
    # Clerk may return a plain array or a dict with a "data" key
    invitations = raw.get("data", raw) if isinstance(raw, dict) else raw
    results: List[InvitationResponse] = []
    for inv in invitations:
        public_metadata = inv.get("public_metadata", {}) or {}
        results.append(InvitationResponse(
            id=inv["id"],
            email_address=inv.get("email_address", ""),
            status=inv.get("status", "pending"),
            role=public_metadata.get("role"),
            first_name=public_metadata.get("first_name"),
            last_name=public_metadata.get("last_name"),
            created_at=inv.get("created_at"),
        ))
    return results


@router.delete("/invitations/{invitation_id}", status_code=204)
def revoke_invitation(
    invitation_id: str,
    _: Dict[str, Any] = Depends(require_roles(["admin"])),
):
    """Revoke a pending Clerk invitation."""
    headers = _clerk_headers()

    with httpx.Client(timeout=15) as client:
        resp = client.post(f"{CLERK_API_BASE}/invitations/{invitation_id}/revoke", headers=headers)

    if resp.status_code not in (200, 204):
        detail = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)

    return None


@router.patch("/{user_id}/role", response_model=ClerkUser)
def update_user_role(
    user_id: str,
    data: UserUpdateRole,
    _: Dict[str, Any] = Depends(require_roles(["admin"])),
):
    """Update a Clerk user's public_metadata role."""
    headers = _clerk_headers()
    payload = {"public_metadata": {"role": data.role}}

    with httpx.Client(timeout=15) as client:
        resp = client.patch(f"{CLERK_API_BASE}/users/{user_id}", headers=headers, json=payload)

    if resp.status_code != 200:
        detail = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)

    return _parse_clerk_user(resp.json())


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: str,
    _: Dict[str, Any] = Depends(require_roles(["admin"])),
):
    """Delete a Clerk user."""
    headers = _clerk_headers()

    with httpx.Client(timeout=15) as client:
        resp = client.delete(f"{CLERK_API_BASE}/users/{user_id}", headers=headers)

    if resp.status_code not in (200, 204):
        detail = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)

    return None
