"""Webhook router — receives Clerk webhook events.

Configure in Clerk Dashboard → Webhooks:
  - URL: https://<your-backend>/webhooks/clerk
  - Events: user.created
  - Copy the Signing Secret into env var CLERK_WEBHOOK_SIGNING_SECRET
"""

import base64
import hashlib
import hmac
import logging
import os
from typing import Any, Dict

import httpx
from fastapi import APIRouter, HTTPException, Request

from config import load_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

CLERK_API_BASE = "https://api.clerk.com/v1"


def _get_clerk_secret_key() -> str:
    load_config()
    key = os.getenv("CLERK_SECRET_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=500, detail="CLERK_SECRET_KEY is not configured")
    return key


def _get_webhook_secret() -> str | None:
    """Return the Svix signing secret (optional – skips verification if unset)."""
    load_config()
    return os.getenv("CLERK_WEBHOOK_SIGNING_SECRET", "").strip() or None


def _verify_svix_signature(payload: bytes, headers: Dict[str, str], secret: str) -> bool:
    """Verify the Svix webhook signature without requiring the svix package.

    Svix sends three headers:
      - svix-id
      - svix-timestamp
      - svix-signature  (comma-separated list of "v1,<base64>" signatures)

    The signing secret is prefixed with "whsec_" and base64-encoded.
    """
    svix_id = headers.get("svix-id", "")
    svix_timestamp = headers.get("svix-timestamp", "")
    svix_signature = headers.get("svix-signature", "")

    if not svix_id or not svix_timestamp or not svix_signature:
        return False

    # Decode the signing secret (strip "whsec_" prefix)
    raw_secret = secret
    if raw_secret.startswith("whsec_"):
        raw_secret = raw_secret[len("whsec_"):]
    try:
        decoded_secret = base64.b64decode(raw_secret)
    except Exception:
        logger.error("Failed to decode webhook signing secret")
        return False

    # Build the signed content
    signed_content = f"{svix_id}.{svix_timestamp}.{payload.decode('utf-8')}"

    # Compute expected signature
    expected = hmac.new(
        decoded_secret,
        signed_content.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    expected_b64 = base64.b64encode(expected).decode("utf-8")

    # Compare against each provided signature
    for sig in svix_signature.split(" "):
        parts = sig.split(",", 1)
        if len(parts) == 2 and parts[0] == "v1":
            if hmac.compare_digest(expected_b64, parts[1]):
                return True

    return False


@router.post("/clerk")
async def clerk_webhook(request: Request):
    """Handle Clerk webhook events.

    Currently handles:
      - user.created: copies first_name / last_name from public_metadata
        (set during invitation) to the actual user profile fields, then removes
        them from public_metadata to keep it clean.
    """
    body = await request.body()

    # Verify signature if a signing secret is configured
    webhook_secret = _get_webhook_secret()
    if webhook_secret:
        headers = {
            "svix-id": request.headers.get("svix-id", ""),
            "svix-timestamp": request.headers.get("svix-timestamp", ""),
            "svix-signature": request.headers.get("svix-signature", ""),
        }
        if not _verify_svix_signature(body, headers, webhook_secret):
            logger.warning("Webhook signature verification failed")
            raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        event = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type = event.get("type")
    logger.info("Received Clerk webhook event: %s", event_type)

    if event_type == "user.created":
        await _handle_user_created(event.get("data", {}))

    return {"status": "ok"}


async def _handle_user_created(user_data: Dict[str, Any]) -> None:
    """When a user is created (typically after accepting an invitation),
    copy first_name and last_name from public_metadata to the user profile
    and clean up public_metadata."""
    user_id = user_data.get("id")
    if not user_id:
        logger.warning("user.created event with no user id")
        return

    public_metadata = user_data.get("public_metadata") or {}
    first_name = public_metadata.get("first_name", "")
    last_name = public_metadata.get("last_name", "")

    if not first_name and not last_name:
        logger.info("User %s: no first_name/last_name in public_metadata, skipping", user_id)
        return

    logger.info(
        "User %s: updating first_name=%s, last_name=%s from public_metadata",
        user_id, first_name, last_name,
    )

    # Build updated public_metadata without first_name / last_name
    cleaned_metadata = {k: v for k, v in public_metadata.items() if k not in ("first_name", "last_name")}

    # Update the user via Clerk API
    clerk_secret = _get_clerk_secret_key()
    headers = {
        "Authorization": f"Bearer {clerk_secret}",
        "Content-Type": "application/json",
    }

    payload: Dict[str, Any] = {
        "public_metadata": cleaned_metadata,
    }
    if first_name:
        payload["first_name"] = first_name
    if last_name:
        payload["last_name"] = last_name

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.patch(
            f"{CLERK_API_BASE}/users/{user_id}",
            headers=headers,
            json=payload,
        )

    if resp.status_code == 200:
        logger.info("User %s: successfully updated first_name/last_name", user_id)
    else:
        logger.error(
            "User %s: failed to update — status=%s body=%s",
            user_id, resp.status_code, resp.text,
        )
