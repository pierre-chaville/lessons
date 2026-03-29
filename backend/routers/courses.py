"""Courses router — /courses endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, func
from typing import Dict, Any, List

import crud
from auth import require_roles
from database import get_session
from models import Lesson
from schemas.course import CourseCreate, CourseUpdate, CourseResponse, CourseTreeNode
from hashid_utils import encode_id, decode_id

router = APIRouter(prefix="/courses", tags=["Courses"])


def _build_course_response(course) -> CourseResponse:
    """Build a CourseResponse with hashid from a Course DB model."""
    return CourseResponse(
        id=course.id,
        hashid=encode_id(course.id),
        name=course.name,
        description=course.description,
        parent_id=course.parent_id,
    )


def _get_lesson_counts(session: Session) -> Dict[int, int]:
    """Return {course_id: direct_lesson_count} for all courses."""
    rows = session.exec(
        select(Lesson.course_id, func.count(Lesson.id))
        .where(Lesson.course_id.is_not(None))
        .group_by(Lesson.course_id)
    ).all()
    return {course_id: count for course_id, count in rows}


def _propagate_counts(node: CourseTreeNode) -> int:
    """Recursively sum lesson counts from children into each node. Returns subtree total."""
    child_total = sum(_propagate_counts(c) for c in node.children)
    node.lesson_count += child_total
    return node.lesson_count


def _build_tree(courses, lesson_counts: Dict[int, int]) -> List[CourseTreeNode]:
    """Build a list of root-level CourseTreeNode from a flat list of courses."""
    nodes: Dict[int, CourseTreeNode] = {}
    for c in courses:
        nodes[c.id] = CourseTreeNode(
            id=c.id,
            hashid=encode_id(c.id),
            name=c.name,
            description=c.description,
            parent_id=c.parent_id,
            lesson_count=lesson_counts.get(c.id, 0),
            children=[],
        )
    roots: List[CourseTreeNode] = []
    for node in nodes.values():
        if node.parent_id and node.parent_id in nodes:
            nodes[node.parent_id].children.append(node)
        else:
            roots.append(node)
    def _sort_children(node: CourseTreeNode):
        node.children.sort(key=lambda c: c.name)
        for child in node.children:
            _sort_children(child)

    for root in roots:
        _propagate_counts(root)
        _sort_children(root)
    roots.sort(key=lambda c: c.name)
    return roots


def _would_create_cycle(
    session: Session, course_id: int, new_parent_id: int
) -> bool:
    """Return True if setting course_id.parent_id = new_parent_id creates a cycle."""
    visited = {course_id}
    current = new_parent_id
    while current is not None:
        if current in visited:
            return True
        visited.add(current)
        parent = crud.get_course(session, current)
        current = parent.parent_id if parent else None
    return False


@router.get("", response_model=List[CourseResponse])
def get_courses(session: Session = Depends(get_session)):
    """Get all courses (flat list)."""
    courses = crud.get_all_courses(session)
    return [_build_course_response(c) for c in courses]


@router.get("/tree", response_model=List[CourseTreeNode])
def get_courses_tree(session: Session = Depends(get_session)):
    """Get courses as a hierarchical tree with aggregated lesson counts."""
    courses = crud.get_all_courses(session)
    lesson_counts = _get_lesson_counts(session)
    return _build_tree(courses, lesson_counts)


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
    if course_data.parent_id is not None:
        if not crud.get_course(session, course_data.parent_id):
            raise HTTPException(status_code=404, detail="Parent course not found")

    course = crud.create_course(
        session,
        name=course_data.name,
        description=course_data.description,
        parent_id=course_data.parent_id,
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

    if course_data.parent_id is not None:
        if course_data.parent_id == course_id:
            raise HTTPException(status_code=400, detail="A course cannot be its own parent")
        if course_data.parent_id != 0:
            if not crud.get_course(session, course_data.parent_id):
                raise HTTPException(status_code=404, detail="Parent course not found")
            if _would_create_cycle(session, course_id, course_data.parent_id):
                raise HTTPException(status_code=400, detail="This parent would create a cycle")

    course = crud.update_course(
        session,
        course_id,
        name=course_data.name,
        description=course_data.description,
        parent_id=course_data.parent_id,
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
    """Delete a course. Children are re-parented to the deleted course's parent."""
    course_id = decode_id(course_hashid)
    if not crud.delete_course(session, course_id):
        raise HTTPException(status_code=404, detail="Course not found")
    return None
