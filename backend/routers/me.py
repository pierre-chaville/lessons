"""Signed-in user's own resources — /me endpoints.

Every endpoint works on the user identified by the token (JWT ``sub``); none
takes a user id (see AGENTS.md › Access Control › My preferences).
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlmodel import Session

import crud
from auth import require_roles
from database import get_session
from schemas.user_preference import HebrewDisplaySettings, UserPreferencesResponse

router = APIRouter(prefix="/me", tags=["Me"])

PREFERENCES_ROLES = ["reader", "editor", "publisher", "admin"]


def _user_id(claims: Dict[str, Any]) -> str:
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return str(user_id)


def _stored_hebrew_display(value: Dict[str, Any] | None) -> HebrewDisplaySettings | None:
    """Stored settings, or None if absent or no longer valid (the client then uses its defaults)."""
    if not value:
        return None
    try:
        return HebrewDisplaySettings.model_validate(value)
    except ValidationError:
        return None


@router.get("/preferences", response_model=UserPreferencesResponse)
def get_my_preferences(
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(PREFERENCES_ROLES)),
):
    preference = crud.get_user_preference(session, _user_id(claims))
    return UserPreferencesResponse(
        hebrew_display=_stored_hebrew_display(preference.hebrew_display if preference else None)
    )


@router.put("/preferences/hebrew-display", response_model=HebrewDisplaySettings)
def update_my_hebrew_display(
    body: HebrewDisplaySettings,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(PREFERENCES_ROLES)),
):
    preference = crud.set_user_hebrew_display(session, _user_id(claims), body.model_dump())
    return HebrewDisplaySettings.model_validate(preference.hebrew_display)
