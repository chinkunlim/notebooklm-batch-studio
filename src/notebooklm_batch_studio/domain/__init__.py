"""Domain package: entities, value objects, and domain exceptions."""

from __future__ import annotations

from notebooklm_batch_studio.domain.exceptions import (
    AuthExpiredError,
    CourseNotFoundError,
    DuplicateCourseError,
    IncompleteArtifactError,
    QuotaExceededError,
    StudioError,
)
from notebooklm_batch_studio.domain.models import (
    ArtifactJob,
    ArtifactType,
    Choice,
    Course,
    Flashcard,
    GreetingRequest,
    GreetingResult,
    JobStatus,
    Lecture,
    MindMapNode,
    ProfileName,
    Question,
    Quiz,
)

__all__ = [
    "ArtifactJob",
    "ArtifactType",
    "AuthExpiredError",
    "Choice",
    "Course",
    "CourseNotFoundError",
    "DuplicateCourseError",
    "Flashcard",
    "GreetingRequest",
    "GreetingResult",
    "IncompleteArtifactError",
    "JobStatus",
    "Lecture",
    "MindMapNode",
    "ProfileName",
    "Question",
    "Quiz",
    "QuotaExceededError",
    "StudioError",
]
