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
        chapter_artifacts: Granular selection of chapter-level artifact types.
        course_artifacts: Granular selection of course-wide aggregated artifact types.
    """

    folders: list[str] = Field(..., description="List of folder paths to scan for course PDFs")
    chapter_artifacts: list[str] | None = Field(
        default=None, description="Optional custom chapter artifact types"
    )
    course_artifacts: list[str] | None = Field(
        default=None, description="Optional custom course artifact types"
    )


class AddCoursesRequest(BaseModel):
    """Payload to register course folders and enqueue artifact processing.

    Attributes:
        folders: List of folder paths to register.
        profile: Generation profile ('full', 'quiz-only', 'exam-prep').
        chapter_artifacts: Granular selection of chapter-level artifact types.
        course_artifacts: Granular selection of course-wide aggregated artifact types.
        language: Output language preference ('zh-TW', 'en', 'bilingual').
        paused: Hold the course until it is started.
        reuse_notebook: Reuse an existing Gemini Notebook notebook with the same title.
        options: Generation options applied before any job runs.
    """

    folders: list[str] = Field(..., description="List of course folder paths to register")
    profile: str = Field(
        default="full",
        description="Artifact generation profile ('full', 'quiz-only', 'exam-prep')",
    )
    chapter_artifacts: list[str] | None = Field(
        default=None, description="Selected chapter-level artifact types"
    )
    course_artifacts: list[str] | None = Field(
        default=None, description="Selected course-wide artifact types"
    )
    language: str = Field(default="zh-TW", description="Output language ('zh-TW', 'en', 'bilingual')")
    paused: bool = Field(default=False, description="Hold the course until it is started")
    reuse_notebook: bool = Field(default=True, description="Reuse a Gemini Notebook with the same title")
    options: dict[str, Any] | None = Field(default=None, description="Generation options to set first")


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
        auth: Authentication status of Google Gemini Notebook credentials.
        queue_running: Whether active queue worker is running.
        total_courses: Total registered courses count.
        queue_counts: Summary of job counts across statuses.
    """

    app_env: str = Field(..., description="Application environment name")
    auth: dict[str, Any] = Field(..., description="Gemini Notebook credential status")
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
        notebook_id: Linked Gemini Notebook notebook identifier.
        notebook_url: Direct web URL to Gemini Notebook.
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
    paused: bool = False


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


class UpdateOptionsRequest(BaseModel):
    """Payload changing a course's Gemini Notebook generation options.

    Attributes:
        options: Option name to new value (see GET /api/courses/{code}/options for choices).
    """

    options: dict[str, Any] = Field(..., description="Option name to new value")


class RegenerateRequest(BaseModel):
    """Payload asking for a new version of one artifact.

    Attributes:
        artifact_type: Artifact type value, e.g. 'infographic'.
        lecture_no: Lecture number, or null for a course-wide artifact.
    """

    artifact_type: str = Field(..., description="Artifact type value, e.g. 'infographic'")
    lecture_no: int | None = Field(default=None, description="Lecture number; null for course-wide")


class ArtifactSelectionRequest(BaseModel):
    """Payload choosing which artifact types a course generates.

    Attributes:
        chapter: Per-lecture artifact type values.
        course: Course-wide artifact type values.
    """

    chapter: list[str] = Field(default_factory=list, description="Per-lecture artifact types")
    course: list[str] = Field(default_factory=list, description="Course-wide artifact types")
