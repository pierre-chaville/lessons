"""Background task worker that processes tasks from the database"""

import time
import signal
import sys
from datetime import datetime
from sqlmodel import Session, select
from database import engine
from models import Task
from tasks import (
    correct_transcript,
    edit_transcript,
    generate_summary,
    transcribe_lesson,
)
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
should_stop = False


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global should_stop
    logger.info("Received shutdown signal, stopping worker...")
    should_stop = True


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


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
        segments_per_group = params.get("segments_per_group", 100)
        max_concurrency = params.get("max_concurrency", 10)

        if not lesson_id:
            raise ValueError("lesson_id is required in task parameters")

        # Run edition
        success = edit_transcript(
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
                    "message": "Edition completed successfully",
                    "lesson_id": lesson_id,
                    "segments_per_group": segments_per_group,
                    "max_concurrency": max_concurrency,
                },
            )
        else:
            update_task_status(session, task, "failed", error="Edition failed")

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
        use_corrected = params.get("use_corrected", True)
        prompt_type = params.get("prompt_type")  # Get the prompt type from parameters

        if not lesson_id:
            raise ValueError("lesson_id is required in task parameters")

        # Generate summary
        success = generate_summary(
            lesson_id=lesson_id,
            use_corrected=use_corrected,
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
                    "use_corrected": use_corrected,
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


def process_task(session: Session, task: Task):
    """Process a task based on its type"""
    try:
        # Update status to running
        update_task_status(session, task, "running")

        # Process based on task type
        if task.task_type == "transcription":
            process_transcription_task(session, task)
        elif task.task_type == "correction":
            process_correction_task(session, task)
        elif task.task_type == "edition":
            process_edition_task(session, task)
        elif task.task_type == "summary":
            process_summary_task(session, task)
        else:
            logger.warning(f"Unknown task type: {task.task_type}")
            update_task_status(
                session, task, "failed", error=f"Unknown task type: {task.task_type}"
            )

    except Exception as e:
        logger.error(f"Error processing task {task.id}: {str(e)}", exc_info=True)
        update_task_status(session, task, "failed", error=str(e))


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


def main():
    """Main entry point"""
    try:
        worker_loop()
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as e:
        logger.error(f"Worker crashed: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
