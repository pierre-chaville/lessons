"""Tasks router — /tasks endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from typing import List, Dict, Any

import crud
from auth import require_roles, _extract_role
from database import get_session
from schemas.task import TaskCreate, TaskResponse
from services.audit import log_event

router = APIRouter(prefix="/tasks", tags=["Tasks"])

VALID_TASK_TYPES = {
    "transcription",
    "correction",
    "edition",
    "extraction",
    "sources",
    "summary",
}


@router.post("", response_model=TaskResponse)
def create_task(
    task: TaskCreate,
    session: Session = Depends(get_session),
    claims: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    """Create and launch a new background task. Editors must be assigned to the lesson."""
    role = _extract_role(claims)
    if role not in ("publisher", "admin"):
        lesson_id = (task.parameters or {}).get("lesson_id")
        if lesson_id:
            user_id = claims.get("sub", "")
            editors = crud.get_lesson_editors(session, lesson_id)
            if not any(e.user_id == user_id for e in editors):
                raise HTTPException(
                    status_code=403,
                    detail="You are not assigned as an editor for this lesson",
                )
    created = crud.create_task(
        session=session, task_type=task.task_type, parameters=task.parameters
    )
    lesson_id = (task.parameters or {}).get("lesson_id")
    if lesson_id and task.task_type in VALID_TASK_TYPES:
        log_event(
            session=session,
            actor={"sub": claims.get("sub"), "role": _extract_role(claims)},
            entity_type="lesson",
            entity_id=str(lesson_id),
            action="pipeline.rerun_requested",
            payload={"task_type": task.task_type, "task_id": created.id},
        )
        session.commit()
    return created


@router.get("", response_model=List[TaskResponse])
def get_tasks(
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    """Get all tasks."""
    return crud.get_all_tasks(session=session)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: int,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["editor", "publisher", "admin"])),
):
    """Get a specific task by ID."""
    task = crud.get_task(session=session, task_id=task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.delete("/{task_id}")
def delete_task(
    task_id: int,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["admin"])),
):
    """Cancel (delete) a task. Admin only."""
    if not crud.delete_task(session=session, task_id=task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task deleted successfully"}


@router.post("/test/{task_type}", response_model=TaskResponse)
def create_test_task(
    task_type: str,
    session: Session = Depends(get_session),
    _: Dict[str, Any] = Depends(require_roles(["admin"])),
):
    """Create a test task for development/testing purposes. Admin only."""
    if task_type not in VALID_TASK_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid task type. Must be: "
                + ", ".join(sorted(VALID_TASK_TYPES))
            ),
        )
    return crud.create_task(
        session=session,
        task_type=task_type,
        parameters={"test": True, "message": f"Test {task_type} task"},
    )
