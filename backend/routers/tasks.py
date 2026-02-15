"""Tasks router — /tasks endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from typing import List

import crud
from database import get_session
from schemas.task import TaskCreate, TaskResponse

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
def create_task(task: TaskCreate, session: Session = Depends(get_session)):
    """Create and launch a new background task."""
    return crud.create_task(
        session=session, task_type=task.task_type, parameters=task.parameters
    )


@router.get("", response_model=List[TaskResponse])
def get_tasks(session: Session = Depends(get_session)):
    """Get all tasks."""
    return crud.get_all_tasks(session=session)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, session: Session = Depends(get_session)):
    """Get a specific task by ID."""
    task = crud.get_task(session=session, task_id=task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.delete("/{task_id}")
def delete_task(task_id: int, session: Session = Depends(get_session)):
    """Delete a task."""
    if not crud.delete_task(session=session, task_id=task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task deleted successfully"}


@router.post("/test/{task_type}", response_model=TaskResponse)
def create_test_task(task_type: str, session: Session = Depends(get_session)):
    """Create a test task for development/testing purposes."""
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
