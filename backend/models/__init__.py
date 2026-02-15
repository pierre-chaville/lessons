"""SQLModel table models."""

from models.app_config import AppConfig
from models.course import Course
from models.theme import Theme
from models.lesson import Lesson
from models.task import Task

__all__ = [
    "AppConfig",
    "Course",
    "Theme",
    "Lesson",
    "Task",
]
