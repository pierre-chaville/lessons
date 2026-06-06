"""Background task worker that processes tasks from the database"""

import gc
import signal
import sys
import threading
import time
from datetime import datetime
from sqlmodel import Session, select
from database import engine
from models import ModelPreset, Task
from models.lesson import Lesson
from services import (
    correct_transcript,
    edit_transcript,
    extract_sources,
    generate_brief,
    generate_summary,
    transcribe_lesson,
    verify_lesson_sources,
)
from services import lessons as lesson_service
from services.llm_utils import get_token_usage_tracker, reset_token_usage_tracker
from services.rag_embeddings import rebuild_stale_rag_embeddings
from memory_usage import format_memory_mb, get_rss_memory_mb
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
    "brief": "summary",
}
TASK_TYPE_TO_WORKFLOW_STEP = {
    "transcription": "transcription",
    "correction": "edited",
    "edition": "edited",
    "extraction": "sources",
    "sources": "sources",
    "summary": "summary",
    "brief": "brief",
}
LLM_TASK_TYPES = {"correction", "edition", "summary", "brief", "extraction", "sources"}
TASK_POLL_SLEEP_SECONDS = 5
RAG_EMBEDDING_REFRESH_INTERVAL_SECONDS = 15 * 60
RAG_EMBEDDING_REFRESH_SLEEP_SECONDS = 5
RAG_EMBEDDING_REFRESH_STALE_LESSON_LIMIT = 10


def _build_pricing_map(session: Session) -> dict[tuple[str, str], ModelPreset]:
    presets = list(session.exec(select(ModelPreset)).all())
    pricing_map: dict[tuple[str, str], ModelPreset] = {}
    for preset in presets:
        provider_key = (preset.provider or "").strip().lower()
        model_key = (preset.model_id or "").strip()
        if provider_key and model_key:
            pricing_map[(provider_key, model_key)] = preset
    return pricing_map


def _calculate_estimated_cost(
    session: Session,
    token_usage: dict | None,
) -> dict:
    token_usage = token_usage or {}
    model_usage = token_usage.get("model_usage")
    if not isinstance(model_usage, dict) or not model_usage:
        return {
            "estimated_cost_usd": 0.0,
            "estimated_cost_breakdown": [],
            "unpriced_models": [],
        }

    pricing_map = _build_pricing_map(session)
    total_cost = 0.0
    breakdown = []
    unpriced_models = []

    for usage in model_usage.values():
        if not isinstance(usage, dict):
            continue

        provider = (usage.get("provider") or "").strip()
        model = (usage.get("model") or "").strip()
        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or output_tokens)
        total_tokens = int(usage.get("total_tokens") or (input_tokens + output_tokens))
        service_tier = (usage.get("service_tier") or "").strip().lower() or None
        service_tier_source = (usage.get("service_tier_source") or "").strip().lower() or None
        flex_used = service_tier == "flex" or bool(usage.get("flex_used", False))

        if not provider or not model:
            continue

        preset = pricing_map.get((provider.lower(), model))
        if not preset:
            unpriced_models.append({"provider": provider, "model": model})
            continue

        input_cost = (input_tokens / 1_000_000) * float(preset.cost_input_per_m_tokens or 0.0)
        output_cost = (output_tokens / 1_000_000) * float(preset.cost_output_per_m_tokens or 0.0)
        base_model_cost = input_cost + output_cost
        flex_cost_ratio = (
            float(preset.flex_cost_ratio)
            if getattr(preset, "flex_cost_ratio", None) is not None
            else 0.5
        )
        applied_cost_ratio = flex_cost_ratio if flex_used else 1.0
        model_cost = base_model_cost * applied_cost_ratio
        total_cost += model_cost

        breakdown.append(
            {
                "provider": provider,
                "model": model,
                "service_tier": service_tier,
                "service_tier_source": service_tier_source,
                "flex_used": flex_used,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cost_input_per_m_tokens": float(preset.cost_input_per_m_tokens or 0.0),
                "cost_output_per_m_tokens": float(preset.cost_output_per_m_tokens or 0.0),
                "flex_cost_ratio": flex_cost_ratio,
                "applied_cost_ratio": applied_cost_ratio,
                "base_estimated_cost_usd": round(base_model_cost, 8),
                "estimated_cost_usd": round(model_cost, 8),
            }
        )

    return {
        "estimated_cost_usd": round(total_cost, 8),
        "estimated_cost_breakdown": breakdown,
        "unpriced_models": unpriced_models,
    }


def _build_llm_result(session: Session, payload: dict, token_usage: dict | None) -> dict:
    usage = token_usage or {}
    pricing = _calculate_estimated_cost(session, usage)
    payload["token_usage"] = usage
    payload["estimated_cost_usd"] = pricing["estimated_cost_usd"]
    payload["estimated_cost_breakdown"] = pricing["estimated_cost_breakdown"]
    if pricing["unpriced_models"]:
        payload["unpriced_models"] = pricing["unpriced_models"]
    return payload


def set_lesson_process_status(session: Session, lesson_id: int, status: str | None):
    """Set the process_status on a lesson."""
    lesson = session.get(Lesson, lesson_id)
    if lesson:
        lesson.process_status = status
        session.add(lesson)
        session.commit()
        session.refresh(lesson)


def task_uses_flex(task: Task) -> bool:
    """Return whether a task was requested with OpenRouter flex mode."""
    params = task.parameters or {}
    if not isinstance(params, dict):
        return False
    return bool(params.get("use_flex", False))


def get_pending_task(session: Session, use_flex: bool | None = None) -> Task | None:
    """Get the oldest pending task, optionally scoped to flex/non-flex mode."""
    statement = select(Task).where(Task.status == "pending").order_by(Task.created_at)
    pending_tasks = session.exec(statement)
    for task in pending_tasks:
        if use_flex is None or task_uses_flex(task) == use_flex:
            return task
    return None


def fail_stale_running_tasks(session: Session):
    """Fail tasks left as running from a previous crashed/stopped worker."""
    statement = select(Task).where(Task.status == "running").order_by(Task.created_at)
    stale_tasks = list(session.exec(statement).all())

    if not stale_tasks:
        return

    logger.warning(
        "Found %s stale running task(s) on startup; marking them as failed",
        len(stale_tasks),
    )

    for task in stale_tasks:
        update_task_status(
            session,
            task,
            "failed",
            error=(
                "Task was left in running state after worker restart. "
                "It likely failed unexpectedly (e.g., process crash/OOM)."
            ),
        )

        params = task.parameters or {}
        lesson_id = params.get("lesson_id")
        if lesson_id:
            set_lesson_process_status(session, lesson_id, None)


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
        prompt_type = params.get("prompt_type")
        use_flex = bool(params.get("use_flex", False))

        if not lesson_id:
            raise ValueError("lesson_id is required in task parameters")

        reset_token_usage_tracker()
        # Run correction
        success = correct_transcript(
            lesson_id=lesson_id,
            segments_per_group=segments_per_group,
            max_concurrency=max_concurrency,
            prompt_type=prompt_type,
            use_flex=use_flex,
            session=session,
        )

        if success:
            token_usage = get_token_usage_tracker()
            update_task_status(
                session,
                task,
                "completed",
                result=_build_llm_result(
                    session,
                    {
                        "message": "Correction completed successfully",
                        "lesson_id": lesson_id,
                        "segments_per_group": segments_per_group,
                        "max_concurrency": max_concurrency,
                        "use_flex": use_flex,
                    },
                    token_usage,
                ),
            )
        else:
            update_task_status(
                session,
                task,
                "failed",
                error="Correction failed",
                result=_build_llm_result(session, {}, get_token_usage_tracker()),
            )

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
        prompt_type = params.get("prompt_type")
        use_flex = bool(params.get("use_flex", False))

        if not lesson_id:
            raise ValueError("lesson_id is required in task parameters")

        reset_token_usage_tracker()
        # Run edition (rewrite text without sources)
        logger.info(f"Editing transcript for lesson {lesson_id}")
        success = edit_transcript(
            lesson_id=lesson_id,
            words_per_group=words_per_group,
            max_concurrency=max_concurrency,
            prompt_type=prompt_type,
            use_flex=use_flex,
            session=session,
        )

        if not success:
            update_task_status(
                session,
                task,
                "failed",
                error="Edition failed",
                result=_build_llm_result(session, {}, get_token_usage_tracker()),
            )
            return

        update_task_status(
            session,
            task,
            "completed",
            result=_build_llm_result(
                session,
                {
                    "message": "Edition completed successfully",
                    "lesson_id": lesson_id,
                    "words_per_group": words_per_group,
                    "max_concurrency": max_concurrency,
                    "use_flex": use_flex,
                },
                get_token_usage_tracker(),
            ),
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
        use_flex = bool(params.get("use_flex", False))

        if not lesson_id:
            raise ValueError("lesson_id is required in task parameters")

        reset_token_usage_tracker()
        # Generate summary
        success = generate_summary(
            lesson_id=lesson_id,
            prompt_type=prompt_type,
            use_flex=use_flex,
            session=session,
        )

        if success:
            update_task_status(
                session,
                task,
                "completed",
                result=_build_llm_result(
                    session,
                    {
                        "message": "Summary generated successfully",
                        "lesson_id": lesson_id,
                        "prompt_type": prompt_type,
                        "use_flex": use_flex,
                    },
                    get_token_usage_tracker(),
                ),
            )
        else:
            update_task_status(
                session,
                task,
                "failed",
                error="Summary generation failed",
                result=_build_llm_result(session, {}, get_token_usage_tracker()),
            )

    except Exception as e:
        logger.error(f"Error in summary task: {e}", exc_info=True)
        raise


def process_brief_task(session: Session, task: Task):
    """Process a brief generation task"""
    logger.info(f"Processing brief task {task.id}")

    try:
        params = task.parameters or {}
        lesson_id = params.get("lesson_id")
        use_flex = bool(params.get("use_flex", False))

        if not lesson_id:
            raise ValueError("lesson_id is required in task parameters")

        reset_token_usage_tracker()
        success = generate_brief(
            lesson_id=lesson_id,
            use_flex=use_flex,
            session=session,
        )

        if success:
            update_task_status(
                session,
                task,
                "completed",
                result=_build_llm_result(
                    session,
                    {
                        "message": "Brief generated successfully",
                        "lesson_id": lesson_id,
                        "use_flex": use_flex,
                    },
                    get_token_usage_tracker(),
                ),
            )
        else:
            update_task_status(
                session,
                task,
                "failed",
                error="Brief generation failed",
                result=_build_llm_result(session, {}, get_token_usage_tracker()),
            )

    except Exception as e:
        logger.error(f"Error in brief task: {e}", exc_info=True)
        raise


def process_extraction_task(session: Session, task: Task):
    """Process a source extraction task"""
    logger.info(f"Processing extraction task {task.id}")

    try:
        params = task.parameters or {}
        lesson_id = params.get("lesson_id")
        max_concurrency = params.get("max_concurrency", 10)
        prompt_type = params.get("prompt_type")
        use_flex = bool(params.get("use_flex", False))

        if not lesson_id:
            raise ValueError("lesson_id is required in task parameters")

        reset_token_usage_tracker()
        success = extract_sources(
            lesson_id=lesson_id,
            max_concurrency=max_concurrency,
            prompt_type=prompt_type,
            use_flex=use_flex,
            session=session,
        )

        if success:
            update_task_status(
                session,
                task,
                "completed",
                result=_build_llm_result(
                    session,
                    {
                        "message": "Source extraction completed successfully",
                        "lesson_id": lesson_id,
                        "max_concurrency": max_concurrency,
                        "use_flex": use_flex,
                    },
                    get_token_usage_tracker(),
                ),
            )
        else:
            update_task_status(
                session,
                task,
                "failed",
                error="Source extraction failed",
                result=_build_llm_result(session, {}, get_token_usage_tracker()),
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
        prompt_type = params.get("prompt_type")
        use_flex = bool(params.get("use_flex", False))

        if not lesson_id:
            raise ValueError("lesson_id is required in task parameters")

        reset_token_usage_tracker()
        # Verify sources
        success = verify_lesson_sources(
            lesson_id=lesson_id,
            prompt_type=prompt_type,
            use_flex=use_flex,
            session=session,
        )

        if success:
            update_task_status(
                session,
                task,
                "completed",
                result=_build_llm_result(
                    session,
                    {
                        "message": "Source verification completed successfully",
                        "lesson_id": lesson_id,
                        "use_flex": use_flex,
                    },
                    get_token_usage_tracker(),
                ),
            )
        else:
            update_task_status(
                session,
                task,
                "failed",
                error="Source verification failed",
                result=_build_llm_result(session, {}, get_token_usage_tracker()),
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
    mem_before_task = get_rss_memory_mb()
    logger.info(
        "Memory before task %s (%s): %s",
        task.id,
        task.task_type,
        format_memory_mb(mem_before_task),
    )

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
        elif task.task_type == "brief":
            process_brief_task(session, task)
        elif task.task_type == "extraction":
            process_extraction_task(session, task)
        elif task.task_type == "sources":
            process_sources_task(session, task)
        else:
            logger.warning(f"Unknown task type: {task.task_type}")
            update_task_status(
                session, task, "failed", error=f"Unknown task type: {task.task_type}"
            )

        step = TASK_TYPE_TO_WORKFLOW_STEP.get(task.task_type)
        task_status = getattr(task, "status", None)
        if lesson_id and step and task_status in {"completed", "failed"}:
            next_status = "to_review" if task_status == "completed" else "failed"
            try:
                lesson_service.set_lesson_step_status(
                    session=session,
                    lesson_id=lesson_id,
                    step=step,
                    status=next_status,
                    updated_by="worker",
                )
            except Exception as step_error:
                logger.warning(
                    "Failed to set step status to %s for lesson %s step %s: %s",
                    next_status,
                    lesson_id,
                    step,
                    step_error,
                )
    except Exception as e:
        logger.error(f"Error processing task {task.id}: {str(e)}", exc_info=True)
        step = TASK_TYPE_TO_WORKFLOW_STEP.get(task.task_type)
        if lesson_id and step:
            try:
                lesson_service.set_lesson_step_status(
                    session=session,
                    lesson_id=lesson_id,
                    step=step,
                    status="failed",
                    updated_by="worker",
                )
            except Exception as step_error:
                logger.warning(
                    "Failed to set step status to failed for lesson %s step %s: %s",
                    lesson_id,
                    step,
                    step_error,
                )
        extra_kwargs = {}
        if task.task_type in LLM_TASK_TYPES:
            extra_kwargs["result"] = _build_llm_result(
                session, {}, get_token_usage_tracker()
            )
        update_task_status(session, task, "failed", error=str(e), **extra_kwargs)
    finally:
        # Clear process_status on the lesson when done (success or failure)
        if lesson_id:
            set_lesson_process_status(session, lesson_id, None)
        gc.collect()
        mem_after_task = get_rss_memory_mb()
        delta_str = "n/a"
        if mem_before_task is not None and mem_after_task is not None:
            delta_str = f"{mem_after_task - mem_before_task:+.2f} MB"
        logger.info(
            "Memory after task %s (%s): %s (delta=%s)",
            task.id,
            task.task_type,
            format_memory_mb(mem_after_task),
            delta_str,
        )


def rag_embedding_refresh_loop():
    """Periodically refresh stale RAG embeddings in the worker process."""
    logger.info("RAG embedding refresh loop started")
    while not should_stop:
        mem_before_refresh = get_rss_memory_mb()
        try:
            with Session(engine) as session:
                logger.info(
                    "Starting periodic RAG embedding refresh (memory=%s)",
                    format_memory_mb(mem_before_refresh),
                )
                stats = rebuild_stale_rag_embeddings(
                    session,
                    limit=RAG_EMBEDDING_REFRESH_STALE_LESSON_LIMIT,
                )
                logger.info("RAG embedding refresh finished: %s", stats)
        except Exception as e:
            logger.error("Error in RAG embedding refresh loop: %s", str(e), exc_info=True)
        finally:
            gc.collect()
            mem_after_refresh = get_rss_memory_mb()
            delta_str = "n/a"
            if mem_before_refresh is not None and mem_after_refresh is not None:
                delta_str = f"{mem_after_refresh - mem_before_refresh:+.2f} MB"
            logger.info(
                "Memory after RAG embedding refresh: %s (delta=%s)",
                format_memory_mb(mem_after_refresh),
                delta_str,
            )

        slept = 0
        while slept < RAG_EMBEDDING_REFRESH_INTERVAL_SECONDS and not should_stop:
            time.sleep(RAG_EMBEDDING_REFRESH_SLEEP_SECONDS)
            slept += RAG_EMBEDDING_REFRESH_SLEEP_SECONDS

    logger.info("RAG embedding refresh loop stopped")


def task_worker_loop(worker_name: str, use_flex: bool):
    """Poll and process one task queue serially."""
    mode_label = "flex" if use_flex else "non-flex"
    logger.info("%s task worker started, polling for %s tasks...", worker_name, mode_label)
    while not should_stop:
        try:
            found_task = False
            with Session(engine) as session:
                task = get_pending_task(session, use_flex=use_flex)

                if task:
                    found_task = True
                    logger.info(
                        "%s found pending %s task %s of type '%s'",
                        worker_name,
                        mode_label,
                        task.id,
                        task.task_type,
                    )
                    process_task(session, task)

            if not found_task:
                time.sleep(TASK_POLL_SLEEP_SECONDS)

        except Exception as e:
            logger.error(
                "Error in %s task worker loop: %s",
                worker_name,
                str(e),
                exc_info=True,
            )
            time.sleep(TASK_POLL_SLEEP_SECONDS)

    logger.info("%s task worker stopped", worker_name)


def worker_loop():
    """Main worker supervisor that runs flex and non-flex task loops."""
    logger.info("Worker started, polling for flex and non-flex tasks...")

    try:
        with Session(engine) as session:
            fail_stale_running_tasks(session)
    except Exception as e:
        logger.error(
            "Failed to reconcile stale running tasks on startup: %s",
            str(e),
            exc_info=True,
        )

    rag_thread = threading.Thread(
        target=rag_embedding_refresh_loop,
        name="rag-embedding-refresh",
        daemon=True,
    )
    task_threads = [
        threading.Thread(
            target=task_worker_loop,
            args=("non-flex", False),
            name="task-worker-non-flex",
            daemon=True,
        ),
        threading.Thread(
            target=task_worker_loop,
            args=("flex", True),
            name="task-worker-flex",
            daemon=True,
        ),
    ]

    rag_thread.start()
    for task_thread in task_threads:
        task_thread.start()

    while not should_stop:
        time.sleep(1)

    logger.info("Worker stopped")
    for task_thread in task_threads:
        task_thread.join(timeout=2)
    rag_thread.join(timeout=2)


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
