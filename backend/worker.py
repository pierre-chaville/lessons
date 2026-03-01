"""Background task worker that processes tasks from the database"""

import signal
import sys
import threading
import time
from datetime import datetime
from sqlmodel import Session, select
from database import engine
from models import Task
from models.lesson import Lesson
from services import (
    correct_transcript,
    edit_transcript,
    extract_sources,
    generate_summary,
    transcribe_lesson,
    verify_lesson_sources,
)
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global flag for graceful shutdown — set to True from outside to stop the loop.
should_stop = False

# Map task types to lesson process_status values
TASK_TYPE_TO_PROCESS_STATUS = {
    "transcription": "transcript",
    "correction": "transcript",
    "edition": "edition",
    "extraction": "sources_extraction",
    "sources": "sources_checking",
    "summary": "summary",
}


def set_lesson_process_status(session: Session, lesson_id: int, status: str | None):
    """Set the process_status on a lesson."""
    lesson = session.get(Lesson, lesson_id)
    if lesson:
        lesson.process_status = status
        session.add(lesson)
        session.commit()
        session.refresh(lesson)


def get_pending_task(session: Session) -> Task:
    """Get the oldest pending task"""
    statement = select(Task).where(Task.status == "pending").order_by(Task.created_at)
    result = session.exec(statement).first()
    return result


def update_task_status(session: Session, task: Task, status: str, **kwargs):
    """Update task status and other fields"""
    task.status = status

    if status == "running" and not task.start_date:
        task.start_date = datetime.utcnow()

    if status in ["completed", "failed"] and not task.end_date:
        task.end_date = datetime.utcnow()
        if task.start_date:
            duration = (task.end_date - task.start_date).total_seconds()
            task.duration = duration

    # Update additional fields
    for key, value in kwargs.items():
        setattr(task, key, value)

    session.add(task)
    session.commit()
    session.refresh(task)
    logger.info(f"Task {task.id} status updated to: {status}")


def process_transcription_task(session: Session, task: Task):
    """Process a transcription task"""
    logger.info(f"Processing transcription task {task.id}")

    try:
        # Get parameters from task
        params = task.parameters or {}
        lesson_id = params.get("lesson_id")

        if not lesson_id:
            raise ValueError("lesson_id is required in task parameters")

        # Run transcription
        success = transcribe_lesson(lesson_id=lesson_id, session=session)

        if success:
            update_task_status(
                session,
                task,
                "completed",
                result={
                    "message": "Transcription completed successfully",
                    "lesson_id": lesson_id,
                },
            )
        else:
            update_task_status(session, task, "failed", error="Transcription failed")

    except Exception as e:
        logger.error(f"Error in transcription task: {e}", exc_info=True)
        raise


def process_correction_task(session: Session, task: Task):
    """Process a correction task"""
    logger.info(f"Processing correction task {task.id}")

    try:
        # Get parameters from task
        params = task.parameters or {}
        lesson_id = params.get("lesson_id")
        segments_per_group = params.get("segments_per_group", 10)
        max_concurrency = params.get("max_concurrency", 10)

        if not lesson_id:
            raise ValueError("lesson_id is required in task parameters")

        # Run correction
        success = correct_transcript(
            lesson_id=lesson_id,
            segments_per_group=segments_per_group,
            max_concurrency=max_concurrency,
            session=session,
        )

        if success:
            update_task_status(
                session,
                task,
                "completed",
                result={
                    "message": "Correction completed successfully",
                    "lesson_id": lesson_id,
                    "segments_per_group": segments_per_group,
                    "max_concurrency": max_concurrency,
                },
            )
        else:
            update_task_status(session, task, "failed", error="Correction failed")

    except Exception as e:
        logger.error(f"Error in correction task: {e}", exc_info=True)
        raise


def process_edition_task(session: Session, task: Task):
    """Process an edition task"""
    logger.info(f"Processing edition task {task.id}")

    try:
        # Get parameters from task
        params = task.parameters or {}
        lesson_id = params.get("lesson_id")
        words_per_group = params.get("words_per_group")
        if words_per_group is None:
            words_per_group = params.get("segments_per_group", 1000)
        max_concurrency = params.get("max_concurrency", 10)

        if not lesson_id:
            raise ValueError("lesson_id is required in task parameters")

        # Run edition (rewrite text without sources)
        logger.info(f"Editing transcript for lesson {lesson_id}")
        success = edit_transcript(
            lesson_id=lesson_id,
            words_per_group=words_per_group,
            max_concurrency=max_concurrency,
            session=session,
        )

        if not success:
            update_task_status(session, task, "failed", error="Edition failed")
            return

        update_task_status(
            session,
            task,
            "completed",
            result={
                "message": "Edition completed successfully",
                "lesson_id": lesson_id,
                "words_per_group": words_per_group,
                "max_concurrency": max_concurrency,
            },
        )

    except Exception as e:
        logger.error(f"Error in edition task: {e}", exc_info=True)
        raise


def process_summary_task(session: Session, task: Task):
    """Process a summary generation task"""
    logger.info(f"Processing summary task {task.id}")

    try:
        # Get parameters from task
        params = task.parameters or {}
        lesson_id = params.get("lesson_id")
        prompt_type = params.get("prompt_type")  # Get the prompt type from parameters

        if not lesson_id:
            raise ValueError("lesson_id is required in task parameters")

        # Generate summary
        success = generate_summary(
            lesson_id=lesson_id,
            prompt_type=prompt_type,
            session=session,
        )

        if success:
            update_task_status(
                session,
                task,
                "completed",
                result={
                    "message": "Summary generated successfully",
                    "lesson_id": lesson_id,
                    "prompt_type": prompt_type,
                },
            )
        else:
            update_task_status(
                session, task, "failed", error="Summary generation failed"
            )

    except Exception as e:
        logger.error(f"Error in summary task: {e}", exc_info=True)
        raise


def process_extraction_task(session: Session, task: Task):
    """Process a source extraction task"""
    logger.info(f"Processing extraction task {task.id}")

    try:
        params = task.parameters or {}
        lesson_id = params.get("lesson_id")
        max_concurrency = params.get("max_concurrency", 10)

        if not lesson_id:
            raise ValueError("lesson_id is required in task parameters")

        success = extract_sources(
            lesson_id=lesson_id,
            max_concurrency=max_concurrency,
            session=session,
        )

        if success:
            update_task_status(
                session,
                task,
                "completed",
                result={
                    "message": "Source extraction completed successfully",
                    "lesson_id": lesson_id,
                    "max_concurrency": max_concurrency,
                },
            )
        else:
            update_task_status(
                session, task, "failed", error="Source extraction failed"
            )

    except Exception as e:
        logger.error(f"Error in extraction task: {e}", exc_info=True)
        raise


def process_sources_task(session: Session, task: Task):
    """Process a source verification task"""
    logger.info(f"Processing sources task {task.id}")

    try:
        # Get parameters from task
        params = task.parameters or {}
        lesson_id = params.get("lesson_id")

        if not lesson_id:
            raise ValueError("lesson_id is required in task parameters")

        # Verify sources
        success = verify_lesson_sources(
            lesson_id=lesson_id,
            session=session,
        )

        if success:
            update_task_status(
                session,
                task,
                "completed",
                result={
                    "message": "Source verification completed successfully",
                    "lesson_id": lesson_id,
                },
            )
        else:
            update_task_status(
                session, task, "failed", error="Source verification failed"
            )

    except Exception as e:
        logger.error(f"Error in sources task: {e}", exc_info=True)
        raise


def process_task(session: Session, task: Task):
    """Process a task based on its type"""
    # Resolve lesson_id so we can update process_status on the lesson
    params = task.parameters or {}
    lesson_id = params.get("lesson_id")
    process_status = TASK_TYPE_TO_PROCESS_STATUS.get(task.task_type)

    try:
        # Update status to running
        update_task_status(session, task, "running")

        # Mark lesson as being processed
        if lesson_id and process_status:
            set_lesson_process_status(session, lesson_id, process_status)

        # Process based on task type
        if task.task_type == "transcription":
            process_transcription_task(session, task)
        elif task.task_type == "correction":
            process_correction_task(session, task)
        elif task.task_type == "edition":
            process_edition_task(session, task)
        elif task.task_type == "summary":
            process_summary_task(session, task)
        elif task.task_type == "extraction":
            process_extraction_task(session, task)
        elif task.task_type == "sources":
            process_sources_task(session, task)
        else:
            logger.warning(f"Unknown task type: {task.task_type}")
            update_task_status(
                session, task, "failed", error=f"Unknown task type: {task.task_type}"
            )

    except Exception as e:
        logger.error(f"Error processing task {task.id}: {str(e)}", exc_info=True)
        update_task_status(session, task, "failed", error=str(e))
    finally:
        # Clear process_status on the lesson when done (success or failure)
        if lesson_id:
            set_lesson_process_status(session, lesson_id, None)


def worker_loop():
    """Main worker loop that polls for tasks"""
    logger.info("Worker started, polling for tasks...")

    while not should_stop:
        try:
            with Session(engine) as session:
                # Get the next pending task
                task = get_pending_task(session)

                if task:
                    logger.info(
                        f"Found pending task {task.id} of type '{task.task_type}'"
                    )
                    process_task(session, task)
                else:
                    # No tasks found, sleep for a bit
                    time.sleep(5)

        except Exception as e:
            logger.error(f"Error in worker loop: {str(e)}", exc_info=True)
            time.sleep(5)

    logger.info("Worker stopped")


def start_worker_thread() -> threading.Thread:
    """Start the worker loop in a background daemon thread.

    Called by main.py on application startup so the worker shares the same
    process as the FastAPI server.  Returns the thread so the caller can join
    it during shutdown.
    """
    global should_stop
    should_stop = False
    thread = threading.Thread(target=worker_loop, daemon=True, name="task-worker")
    thread.start()
    logger.info("Worker thread started (embedded in API process)")
    return thread


def main():
    """Main entry point for running the worker as a standalone process."""
    global should_stop

    def _signal_handler(signum, frame):
        global should_stop
        logger.info("Received shutdown signal, stopping worker...")
        should_stop = True

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        worker_loop()
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as e:
        logger.error(f"Worker crashed: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
