"""CRUD operations for database models"""

from sqlalchemy import delete
from sqlmodel import Session, select, func
from typing import List, Optional
from datetime import datetime
from models import (
    Lesson,
    LessonEditor,
    LessonSource,
    Course,
    Theme,
    Task,
    SefariaCache,
    ContentVersion,
    ModelPreset,
)


# Course CRUD
def create_course(
    session: Session,
    name: str,
    description: Optional[str] = None,
    parent_id: Optional[int] = None,
    sort_order: Optional[int] = None,
) -> Course:
    """Create a new course. Auto-assigns sort_order at end of siblings if not provided."""
    if sort_order is None:
        max_order = session.exec(
            select(func.coalesce(func.max(Course.sort_order), -1))
            .where(Course.parent_id == parent_id)
        ).one()
        sort_order = max_order + 1
    course = Course(name=name, description=description, parent_id=parent_id, sort_order=sort_order)
    session.add(course)
    session.commit()
    session.refresh(course)
    return course


def get_course(session: Session, course_id: int) -> Optional[Course]:
    """Get course by ID"""
    return session.get(Course, course_id)


def get_all_courses(session: Session) -> List[Course]:
    """Get all courses ordered by sort_order, then name"""
    statement = select(Course).order_by(Course.sort_order, Course.name)
    return list(session.exec(statement).all())


def update_course(
    session: Session,
    course_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    parent_id: object = None,
    sort_order: Optional[int] = None,
) -> Optional[Course]:
    """Update a course. Pass parent_id=0 to clear the parent."""
    course = session.get(Course, course_id)
    if course:
        if name is not None:
            course.name = name
        if description is not None:
            course.description = description
        if parent_id is not None:
            course.parent_id = parent_id if parent_id != 0 else None
        if sort_order is not None:
            course.sort_order = sort_order
        session.add(course)
        session.commit()
        session.refresh(course)
    return course


def delete_course(session: Session, course_id: int) -> bool:
    """Delete a course (re-parents children to this course's parent)."""
    course = session.get(Course, course_id)
    if course:
        children = list(
            session.exec(select(Course).where(Course.parent_id == course_id)).all()
        )
        for child in children:
            child.parent_id = course.parent_id
            session.add(child)
        session.delete(course)
        session.commit()
        return True
    return False


# Theme CRUD
def create_theme(session: Session, name: str) -> Theme:
    """Create a new theme"""
    theme = Theme(name=name)
    session.add(theme)
    session.commit()
    session.refresh(theme)
    return theme


def get_theme(session: Session, theme_id: int) -> Optional[Theme]:
    """Get theme by ID"""
    return session.get(Theme, theme_id)


def get_all_themes(session: Session) -> List[Theme]:
    """Get all themes"""
    statement = select(Theme)
    return list(session.exec(statement).all())


def get_themes_by_ids(session: Session, theme_ids: List[int]) -> List[Theme]:
    """Get themes by list of IDs"""
    if not theme_ids:
        return []
    statement = select(Theme).where(Theme.id.in_(theme_ids))
    return list(session.exec(statement).all())


def update_theme(session: Session, theme_id: int, name: str) -> Optional[Theme]:
    """Update a theme"""
    theme = session.get(Theme, theme_id)
    if theme:
        theme.name = name
        session.add(theme)
        session.commit()
        session.refresh(theme)
    return theme


def delete_theme(session: Session, theme_id: int) -> bool:
    """Delete a theme"""
    theme = session.get(Theme, theme_id)
    if theme:
        session.delete(theme)
        session.commit()
        return True
    return False


# ModelPreset CRUD
def create_model_preset(
    session: Session,
    name: str,
    provider: str,
    model_id: str,
    temperature: float = 0.7,
    cost_input_per_m_tokens: float = 0.0,
    cost_output_per_m_tokens: float = 0.0,
    thinking_mode: Optional[dict] = None,
) -> ModelPreset:
    """Create a new model preset."""
    preset = ModelPreset(
        name=name,
        provider=provider,
        model_id=model_id,
        temperature=temperature,
        cost_input_per_m_tokens=cost_input_per_m_tokens,
        cost_output_per_m_tokens=cost_output_per_m_tokens,
        thinking_mode=thinking_mode or {},
    )
    session.add(preset)
    session.commit()
    session.refresh(preset)
    return preset


def get_model_preset(session: Session, preset_id: int) -> Optional[ModelPreset]:
    """Get a model preset by ID."""
    return session.get(ModelPreset, preset_id)


def get_all_model_presets(session: Session) -> List[ModelPreset]:
    """Get all model presets."""
    statement = select(ModelPreset).order_by(ModelPreset.name)
    return list(session.exec(statement).all())


def update_model_preset(
    session: Session,
    preset_id: int,
    name: Optional[str] = None,
    provider: Optional[str] = None,
    model_id: Optional[str] = None,
    temperature: Optional[float] = None,
    cost_input_per_m_tokens: Optional[float] = None,
    cost_output_per_m_tokens: Optional[float] = None,
    thinking_mode: Optional[dict] = None,
) -> Optional[ModelPreset]:
    """Update an existing model preset."""
    preset = session.get(ModelPreset, preset_id)
    if not preset:
        return None

    if name is not None:
        preset.name = name
    if provider is not None:
        preset.provider = provider
    if model_id is not None:
        preset.model_id = model_id
    if temperature is not None:
        preset.temperature = temperature
    if cost_input_per_m_tokens is not None:
        preset.cost_input_per_m_tokens = cost_input_per_m_tokens
    if cost_output_per_m_tokens is not None:
        preset.cost_output_per_m_tokens = cost_output_per_m_tokens
    if thinking_mode is not None:
        preset.thinking_mode = thinking_mode
    preset.updated_at = datetime.utcnow()

    session.add(preset)
    session.commit()
    session.refresh(preset)
    return preset


def delete_model_preset(session: Session, preset_id: int) -> bool:
    """Delete a model preset."""
    preset = session.get(ModelPreset, preset_id)
    if not preset:
        return False
    session.delete(preset)
    session.commit()
    return True


# Lesson CRUD
def create_lesson(
    session: Session,
    title: str,
    filename: str,
    course_id: Optional[int] = None,
    date: Optional[datetime] = None,
    duration: Optional[float] = None,
    transcript: Optional[str] = None,
    corrected_transcript: Optional[str] = None,
    summary: Optional[str] = None,
    theme_ids: Optional[List[int]] = None,
) -> Lesson:
    """Create a new lesson"""
    lesson = Lesson(
        title=title,
        filename=filename,
        course_id=course_id,
        date=date or datetime.now(),
        duration=duration,
        transcript=transcript,
        corrected_transcript=corrected_transcript,
        summary=summary,
    )
    if theme_ids:
        lesson.set_themes(theme_ids)
    session.add(lesson)
    session.commit()
    session.refresh(lesson)
    return lesson


def get_lesson(session: Session, lesson_id: int) -> Optional[Lesson]:
    """Get lesson by ID"""
    return session.get(Lesson, lesson_id)


def get_all_lessons(
    session: Session,
    course_id: Optional[int] = None,
    course_ids: Optional[List[int]] = None,
) -> List[Lesson]:
    """Get all lessons, optionally filtered by course(s), sorted by date (latest first)."""
    if course_ids:
        statement = select(Lesson).where(Lesson.course_id.in_(course_ids)).order_by(Lesson.date.desc())
    elif course_id:
        statement = select(Lesson).where(Lesson.course_id == course_id).order_by(Lesson.date.desc())
    else:
        statement = select(Lesson).order_by(Lesson.date.desc())
    return list(session.exec(statement).all())


def update_lesson(
    session: Session,
    lesson_id: int,
    title: Optional[str] = None,
    filename: Optional[str] = None,
    course_id: Optional[int] = None,
    date: Optional[datetime] = None,
    duration: Optional[float] = None,
    transcript: Optional[List[dict]] = None,
    corrected_transcript: Optional[List[dict]] = None,
    edited_transcript: Optional[List[dict]] = None,
    brief: Optional[str] = None,
    summary: Optional[str] = None,
    process_status: Optional[str] = None,
    theme_ids: Optional[List[int]] = None,
    transcript_metadata: Optional[dict] = None,
    correction_metadata: Optional[dict] = None,
    summary_metadata: Optional[dict] = None,
    edited_metadata: Optional[dict] = None,
) -> Optional[Lesson]:
    """Update a lesson"""
    lesson = session.get(Lesson, lesson_id)
    if lesson:
        # title/corrected_transcript/edited_transcript/brief/summary are versioned.
        # They must be changed via services.versioning.update_content.
        if filename is not None:
            lesson.filename = filename
        if course_id is not None:
            lesson.course_id = course_id
        if date is not None:
            lesson.date = date
        if duration is not None:
            lesson.duration = duration
        if transcript is not None:
            lesson.transcript = transcript
        if process_status is not None:
            lesson.process_status = process_status
        if theme_ids is not None:
            lesson.set_themes(theme_ids)
        if transcript_metadata is not None:
            lesson.transcript_metadata = transcript_metadata
        if correction_metadata is not None:
            lesson.correction_metadata = correction_metadata
        if summary_metadata is not None:
            lesson.summary_metadata = summary_metadata
        if edited_metadata is not None:
            lesson.edited_metadata = edited_metadata

        session.add(lesson)
        session.commit()
        session.refresh(lesson)
    return lesson


def delete_lesson(session: Session, lesson_id: int) -> bool:
    """Delete a lesson and its associated sources and editors"""
    lesson = session.get(Lesson, lesson_id)
    if lesson:
        delete_lesson_editors(session, lesson_id)
        delete_lesson_sources(session, lesson_id)
        delete_content_versions(session, lesson_id)
        session.delete(lesson)
        session.commit()
        return True
    return False


def delete_content_versions(session: Session, lesson_id: int) -> int:
    """Delete all content versions for a lesson. Returns count deleted."""
    count_statement = select(func.count()).select_from(ContentVersion).where(ContentVersion.lesson_id == lesson_id)
    deleted_count = int(session.exec(count_statement).one() or 0)
    if deleted_count == 0:
        return 0
    session.exec(delete(ContentVersion).where(ContentVersion.lesson_id == lesson_id))
    # Ensure dependent rows are deleted before the lesson row is flushed.
    session.flush()
    return deleted_count


# LessonEditor CRUD
def get_lesson_editors(session: Session, lesson_id: int) -> List[LessonEditor]:
    """Get all editor assignments for a lesson."""
    statement = (
        select(LessonEditor)
        .where(LessonEditor.lesson_id == lesson_id)
        .order_by(LessonEditor.assigned_at)
    )
    return list(session.exec(statement).all())


def set_lesson_editors(
    session: Session,
    lesson_id: int,
    user_ids: List[str],
    assigned_by: Optional[str] = None,
) -> List[LessonEditor]:
    """Replace the full set of editors for a lesson (diff-based)."""
    existing = {e.user_id: e for e in get_lesson_editors(session, lesson_id)}
    target = set(user_ids)

    for uid in existing:
        if uid not in target:
            session.delete(existing[uid])

    for uid in target:
        if uid not in existing:
            session.add(LessonEditor(
                lesson_id=lesson_id,
                user_id=uid,
                assigned_by=assigned_by,
            ))

    session.flush()
    return get_lesson_editors(session, lesson_id)


def delete_lesson_editors(session: Session, lesson_id: int) -> int:
    """Delete all editor assignments for a lesson. Returns count deleted."""
    editors = get_lesson_editors(session, lesson_id)
    for e in editors:
        session.delete(e)
    return len(editors)


# LessonSource CRUD
def get_lesson_sources(session: Session, lesson_id: int) -> List[LessonSource]:
    """Get all sources for a lesson, ordered by paragraph_index then id."""
    statement = (
        select(LessonSource)
        .where(LessonSource.lesson_id == lesson_id)
        .order_by(LessonSource.paragraph_index, LessonSource.id)
    )
    return list(session.exec(statement).all())


def get_lesson_sources_by_paragraph(
    session: Session, lesson_id: int, paragraph_index: int
) -> List[LessonSource]:
    """Get all sources for a specific paragraph of a lesson."""
    statement = (
        select(LessonSource)
        .where(
            LessonSource.lesson_id == lesson_id,
            LessonSource.paragraph_index == paragraph_index,
        )
        .order_by(LessonSource.id)
    )
    return list(session.exec(statement).all())


def create_lesson_source(session: Session, **kwargs) -> LessonSource:
    """Create a single lesson source row."""
    source = LessonSource(**kwargs)
    session.add(source)
    return source


def bulk_create_lesson_sources(
    session: Session, sources: List[dict]
) -> List[LessonSource]:
    """Bulk-insert lesson sources. Caller must commit."""
    objs = [LessonSource(**s) for s in sources]
    session.add_all(objs)
    return objs


def delete_lesson_sources(session: Session, lesson_id: int) -> int:
    """Delete all sources for a lesson. Returns count deleted."""
    sources = get_lesson_sources(session, lesson_id)
    count = len(sources)
    for s in sources:
        session.delete(s)
    return count


def delete_lesson_sources_by_paragraph(
    session: Session, lesson_id: int, paragraph_index: int
) -> int:
    """Delete sources for a specific paragraph. Returns count deleted."""
    sources = get_lesson_sources_by_paragraph(session, lesson_id, paragraph_index)
    count = len(sources)
    for s in sources:
        session.delete(s)
    return count


def update_lesson_source(
    session: Session, source_id: int, **kwargs
) -> Optional[LessonSource]:
    """Update specific fields of a lesson source."""
    source = session.get(LessonSource, source_id)
    if not source:
        return None
    for key, value in kwargs.items():
        if value is not None:
            setattr(source, key, value)
    session.add(source)
    return source


# Task CRUD
def create_task(
    session: Session,
    task_type: str,
    parameters: Optional[dict] = None,
    status: str = "pending",
    created_by_id: Optional[str] = None,
) -> Task:
    """Create a new task"""
    from datetime import datetime

    task = Task(
        task_type=task_type,
        status=status,
        parameters=parameters,
        created_by_id=created_by_id,
        created_at=datetime.utcnow(),
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def get_task(session: Session, task_id: int) -> Optional[Task]:
    """Get task by ID"""
    return session.get(Task, task_id)


def get_all_tasks(session: Session) -> List[Task]:
    """Get all tasks"""
    statement = select(Task).order_by(Task.created_at.desc())
    return list(session.exec(statement).all())


def update_task(
    session: Session,
    task_id: int,
    status: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    duration: Optional[float] = None,
    result: Optional[dict] = None,
    error: Optional[str] = None,
) -> Optional[Task]:
    """Update task details"""
    task = session.get(Task, task_id)
    if not task:
        return None

    if status is not None:
        task.status = status
    if start_date is not None:
        task.start_date = start_date
    if end_date is not None:
        task.end_date = end_date
    if duration is not None:
        task.duration = duration
    if result is not None:
        task.result = result
    if error is not None:
        task.error = error

    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def delete_task(session: Session, task_id: int) -> bool:
    """Delete a task"""
    task = session.get(Task, task_id)
    if task:
        session.delete(task)
        session.commit()
        return True
    return False


# SefariaCache CRUD
def get_sefaria_cache_by_slugs(session: Session, slugs: List[str]) -> List[SefariaCache]:
    """Get cached Sefaria entries for a list of standard slugs (batch lookup)."""
    if not slugs:
        return []
    statement = select(SefariaCache).where(SefariaCache.standard_slug.in_(slugs))
    return list(session.exec(statement).all())


def get_sefaria_cache_by_slug(session: Session, standard_slug: str) -> Optional[SefariaCache]:
    """Get a cached Sefaria entry by its standard slug."""
    statement = select(SefariaCache).where(SefariaCache.standard_slug == standard_slug)
    return session.exec(statement).first()


def get_all_sefaria_cache(session: Session) -> List[SefariaCache]:
    """Get all cached Sefaria entries."""
    statement = select(SefariaCache).order_by(SefariaCache.fetched_at.desc())
    return list(session.exec(statement).all())


def create_sefaria_cache(
    session: Session,
    standard_slug: str,
    type: Optional[str] = None,
    work: Optional[str] = None,
    ref: Optional[str] = None,
    he_ref: Optional[str] = None,
    text_english: Optional[str] = None,
    text_hebrew: Optional[str] = None,
) -> SefariaCache:
    """Create a new Sefaria cache entry."""
    entry = SefariaCache(
        standard_slug=standard_slug,
        type=type,
        work=work,
        ref=ref,
        he_ref=he_ref,
        text_english=text_english,
        text_hebrew=text_hebrew,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def upsert_sefaria_cache(
    session: Session,
    standard_slug: str,
    type: Optional[str] = None,
    work: Optional[str] = None,
    ref: Optional[str] = None,
    he_ref: Optional[str] = None,
    text_english: Optional[str] = None,
    text_hebrew: Optional[str] = None,
) -> SefariaCache:
    """Create or update a Sefaria cache entry by standard_slug."""
    existing = get_sefaria_cache_by_slug(session, standard_slug)
    if existing:
        if type is not None:
            existing.type = type
        if work is not None:
            existing.work = work
        if ref is not None:
            existing.ref = ref
        if he_ref is not None:
            existing.he_ref = he_ref
        if text_english is not None:
            existing.text_english = text_english
        if text_hebrew is not None:
            existing.text_hebrew = text_hebrew
        existing.fetched_at = datetime.utcnow()
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing
    return create_sefaria_cache(
        session, standard_slug=standard_slug, type=type, work=work,
        ref=ref, he_ref=he_ref, text_english=text_english, text_hebrew=text_hebrew,
    )


def delete_sefaria_cache(session: Session, cache_id: int) -> bool:
    """Delete a Sefaria cache entry."""
    entry = session.get(SefariaCache, cache_id)
    if entry:
        session.delete(entry)
        session.commit()
        return True
    return False
