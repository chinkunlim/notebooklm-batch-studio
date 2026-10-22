"""Pydantic request and response schemas for FastAPI and OpenAPI interfaces.

Validates incoming payloads at boundary layers before passing sanitized domain
data to underlying services.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PreviewCoursesRequest(BaseModel):
    """Payload to preview course materials from local folder paths.

    Attributes:
        folders: List of filesystem directory paths containing course PDFs.
    """

    folders: list[str] = Field(..., description="List of filesystem folder paths to scan for course PDFs")


class AddCoursesRequest(BaseModel):
    """Payload to register course folders and enqueue artifact processing.

    Attributes:
        folders: List of folder paths to register.
        profile: Generation profile ('full', 'quiz-only', 'exam-prep').
    """

    folders: list[str] = Field(..., description="List of course folder paths to register")
    profile: str = Field(
        default="full",
        description="Artifact generation profile ('full', 'quiz-only', 'exam-prep')",
    )


class UpdateProfileRequest(BaseModel):
    """Payload to update the artifact generation profile for an existing course.

    Attributes:
        profile: Target profile name ('full', 'quiz-only', 'exam-prep').
    """

    profile: str = Field(..., description="Target generation profile ('full', 'quiz-only', 'exam-prep')")


class QueueActionRequest(BaseModel):
    """Payload for mutating queue actions requiring confirmation.

    Attributes:
        confirm: Confirmation flag to guard against accidental execution.
    """

    confirm: bool = Field(default=False, description="Confirmation flag to proceed with action")


class StatusResponse(BaseModel):
    """System health and queue status information.

    Attributes:
        app_env: Running application environment.
        auth: Authentication status of Google NotebookLM credentials.
        queue_running: Whether active queue worker is running.
        total_courses: Total registered courses count.
        queue_counts: Summary of job counts across statuses.
    """

    app_env: str = Field(..., description="Application environment name")
    auth: dict[str, Any] = Field(..., description="NotebookLM credential status")
    queue_running: bool = Field(..., description="Whether worker queue is currently executing")
    total_courses: int = Field(..., description="Total number of registered courses")
    queue_counts: dict[str, int] = Field(..., description="Job count per lifecycle status")


class CourseSummaryResponse(BaseModel):
    """Summary item representation for registered course listing.

    Attributes:
        code: Unique course identifier.
        name: Course name.
        profile: Active generation profile.
        lecture_count: Total lecture PDFs detected.
        notebook_id: Linked NotebookLM notebook identifier.
        notebook_url: Direct web URL to NotebookLM.
        total_jobs: Total scheduled artifact tasks.
        done_jobs: Count of completed artifact tasks.
        progress_percent: Percentage of finished tasks (0.0 - 100.0).
        counts: Detailed breakdown by job status.
    """

    code: str
    name: str
    profile: str
    lecture_count: int
    notebook_id: str | None = None
    notebook_url: str | None = None
    total_jobs: int
    done_jobs: int
    progress_percent: float
    counts: dict[str, int]


class GenericActionResponse(BaseModel):
    """Generic action confirmation response.

    Attributes:
        success: Whether the requested operation succeeded.
        message: Informational description of the action result.
        data: Optional structured payload returned by the operation.
    """

    success: bool
    message: str
    data: Any = None
