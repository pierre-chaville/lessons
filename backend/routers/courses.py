"""Courses router — /courses endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from typing import List, Dict, Any

import crud
from auth import require_roles
from database import get_session
from schemas.course import CourseCreate, CourseUpdate, CourseResponse
from hashid_utils import encode_id, decode_id

router = APIRouter(prefix="/courses", tags=["Courses"])


def _build_course_response(course) -> CourseResponse:
    """Build a CourseResponse with hashid from a Course DB model."""
    return CourseResponse(
        id=course.id,
        hashid=encode_id(course.id),
        name=course.name,
        description=course.description,
    )


@router.get("", response_model=List[CourseResponse])
def get_courses(session: Session = Depends(get_session)):
    """Get all courses."""
    courses = crud.get_all_courses(session)
    return [_build_course_response(c) for c in courses]


@router.get("/{course_hashid}", response_model=CourseResponse)
def get_course(course_hashid: str, session: Session = Depends(get_session)):
    """Get a specific course by hashid."""
    course_id = decode_id(course_hashid)
    course = crud.get_course(session, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return _build_course_response(course)


@router.post("", response_model=CourseResponse, status_code=201)
def create_course(
    course_data: CourseCreate,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    """Create a new course."""
    course = crud.create_course(
        session, name=course_data.name, description=course_data.description
    )
    return _build_course_response(course)


@router.patch("/{course_hashid}", response_model=CourseResponse)
def update_course(
    course_hashid: str,
    course_data: CourseUpdate,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    """Update an existing course."""
    course_id = decode_id(course_hashid)
    course = crud.update_course(
        session, course_id, name=course_data.name, description=course_data.description
    )
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return _build_course_response(course)


@router.delete("/{course_hashid}", status_code=204)
def delete_course(
    course_hashid: str,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["publisher", "admin"])),
):
    """Delete a course."""
    course_id = decode_id(course_hashid)
    if not crud.delete_course(session, course_id):
        raise HTTPException(status_code=404, detail="Course not found")
    return None
