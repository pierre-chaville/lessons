"""Courses router — /courses endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from typing import List, Dict, Any

import crud
from auth import require_roles
from database import get_session
from models import Course
from schemas.course import CourseCreate, CourseUpdate

router = APIRouter(prefix="/courses", tags=["Courses"])


@router.get("", response_model=List[Course])
def get_courses(session: Session = Depends(get_session)):
    """Get all courses."""
    return crud.get_all_courses(session)


@router.get("/{course_id}", response_model=Course)
def get_course(course_id: int, session: Session = Depends(get_session)):
    """Get a specific course by ID."""
    course = crud.get_course(session, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.post("", response_model=Course, status_code=201)
def create_course(
    course_data: CourseCreate,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["admin", "editor"])),
):
    """Create a new course."""
    return crud.create_course(
        session, name=course_data.name, description=course_data.description
    )


@router.patch("/{course_id}", response_model=Course)
def update_course(
    course_id: int,
    course_data: CourseUpdate,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["admin", "editor"])),
):
    """Update an existing course."""
    course = crud.update_course(
        session, course_id, name=course_data.name, description=course_data.description
    )
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.delete("/{course_id}", status_code=204)
def delete_course(
    course_id: int,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["admin", "editor"])),
):
    """Delete a course."""
    if not crud.delete_course(session, course_id):
        raise HTTPException(status_code=404, detail="Course not found")
    return None
