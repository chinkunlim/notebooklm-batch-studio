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
    study_state: str = "not_started"


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


class CopyOptionsRequest(BaseModel):
    """Payload copying a course's options to other courses (preserving each target's exam date).

    Attributes:
        targets: Target course codes to update.
    """

    targets: list[str] = Field(..., description="Target course codes to update")


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


class UploadSourceRequest(BaseModel):
    """Payload to upload a lecture PDF or custom PDF source to a course's notebook.

    Attributes:
        lecture_no: Lecture sequence number to upload or re-upload.
        file_path: Local PDF file path to upload.
        filename: Filename for browser-uploaded PDF.
        content_base64: Base64-encoded PDF content.
    """

    lecture_no: int | None = Field(default=None, description="Lecture sequence number to upload or re-upload")
    file_path: str | None = Field(default=None, description="Local PDF file path to upload")
    filename: str | None = Field(default=None, description="Filename for browser-uploaded PDF")
    content_base64: str | None = Field(default=None, description="Base64-encoded PDF content")


class AskQARequest(BaseModel):
    """Payload to ask an exploratory question to Gemini Notebook.

    Attributes:
        question: Student question text.
        lecture_no: Optional lecture sequence number to restrict context.
        conversation_id: Optional existing conversation ID for follow-up turns.
    """

    question: str = Field(..., min_length=1, description="Question text")
    lecture_no: int | None = Field(default=None, description="Optional lecture number filter")
    conversation_id: str | None = Field(default=None, description="Existing conversation ID")


class SummarizeQARequest(BaseModel):
    """Payload to format an active NotebookLM conversation into Markdown notes.

    Attributes:
        conversation_id: Conversation ID to summarize.
        lecture_no: Optional lecture number metadata.
        scene: Origin context (`chat_drawer`, `study_tab`, `quiz_explain`).
    """

    conversation_id: str = Field(..., min_length=1, description="Conversation ID")
    lecture_no: int | None = Field(default=None, description="Optional lecture number")
    scene: str = Field(default="chat_drawer", description="Originating UI scene")


class SaveQANoteRequest(BaseModel):
    """Payload to create or update a saved Markdown Q&A note.

    Attributes:
        title: Note heading title.
        content_markdown: Note Markdown body text.
        lecture_no: Optional lecture number.
        tags: Optional list of hierarchical tags.
        source_scene: Originating UI scene.
        personal_memo: Optional student reminder note.
        note_id: Optional existing note ID to overwrite.
    """

    title: str = Field(..., min_length=1, description="Note title")
    content_markdown: str = Field(..., min_length=1, description="Markdown content")
    lecture_no: int | None = Field(default=None, description="Lecture sequence number")
    tags: list[str] = Field(default_factory=list, description="Hierarchical tags")
    source_scene: str = Field(default="chat_drawer", description="Originating scene")
    personal_memo: str | None = Field(default=None, description="Personal reminder")
    note_id: str | None = Field(default=None, description="Optional ID for updates")


class MasteryUpdateRequest(BaseModel):
    """Payload to toggle note mastery status.

    Attributes:
        status: Target status (`needs_review` or `mastered`).
    """

    status: str = Field(..., description="Target status: needs_review or mastered")


class MemoUpdateRequest(BaseModel):
    """Payload to update personal reminder on a Q&A note.

    Attributes:
        personal_memo: Personal annotation text.
    """

    personal_memo: str = Field(default="", description="Personal annotation text")


class BundleNotesRequest(BaseModel):
    """Payload to bundle multiple notes into one PDF source.

    Attributes:
        note_ids: Selected note IDs.
        title: Bundled PDF document title.
    """

    note_ids: list[str] = Field(..., min_length=1, description="Note IDs to bundle")
    title: str = Field(..., min_length=1, description="Bundle document title")


class CinematicVideoRequest(BaseModel):
    """Payload to generate a cinematic video overview in Gemini Notebook."""

    instructions: str = ""
    lecture_no: int | None = None


class ReviseSlideRequest(BaseModel):
    """Payload to revise a single slide in an existing slide deck artifact."""

    slide_index: int = Field(ge=0)
    prompt: str = Field(min_length=1)


class ExportArtifactRequest(BaseModel):
    """Payload to export a report or data table to Google Docs / Sheets."""

    title: str = "Export"
    kind: str = "report"


class UrlSourceRequest(BaseModel):
    """Payload to add a web or YouTube URL source to a course notebook."""

    url: str = Field(min_length=4)
    title: str | None = None


class TextSourceRequest(BaseModel):
    """Payload to add pasted plain text as a source in a course notebook."""

    title: str = Field(min_length=1)
    content: str = Field(min_length=1)


class ResearchQueryRequest(BaseModel):
    """Payload to start web discovery research in a course notebook."""

    query: str = Field(min_length=1)
    mode: str = "fast"


class ResearchImportRequest(BaseModel):
    """Payload to import discovered research sources into a course notebook."""

    task_id: str = Field(min_length=1)
    sources: list[dict[str, str]] = Field(min_length=1)


class ChatConfigureRequest(BaseModel):
    """Payload to configure NotebookLM chat goal and response length."""

    goal: str = "default"
    response_length: str = "default"
    custom_prompt: str | None = None


class GenerateScopedArtifactRequest(BaseModel):
    """Payload to generate a Studio artifact or custom report for selected sources."""

    kind: str = Field(min_length=1)
    source_ids: list[str] | None = None
    instructions: str = ""
