"""ORM models (database tables). Only the adapters layer imports these."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from notebooklm_batch_studio.adapters.db.base import Base


def utc_now() -> datetime:
    """Return the current time in UTC (default for timestamp columns).

    Returns:
        Timezone-aware UTC datetime.
    """
    return datetime.now(timezone.utc)


class CourseRecord(Base):
    """Database record for a course.

    Attributes:
        code: Unique course identifier (primary key).
        name: Course name.
        source_dir: Filesystem path to course materials.
        notebook_id: Associated NotebookLM notebook ID.
        profile: Active generation profile.
        language: Output language preference.
        exam_date: Date of upcoming exam.
        watch: Whether folder watcher is active.
        mock_exam_questions: Number of questions in course-wide mock exam.
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """

    __tablename__ = "courses"

    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_dir: Mapped[str] = mapped_column(String(1024), nullable=False)
    notebook_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    profile: Mapped[str] = mapped_column(String(50), nullable=False, default="full")
    language: Mapped[str] = mapped_column(String(20), nullable=False, default="zh-TW")
    exam_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    watch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    mock_exam_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class LectureRecord(Base):
    """Database record for a lecture PDF source.

    Attributes:
        id: Auto-increment primary key.
        course_code: Foreign key to course.
        no: Lecture sequence number.
        topic: Lecture topic title.
        filename: PDF filename.
        sha256: SHA-256 hash of the PDF file.
        created_at: Creation timestamp.
    """

    __tablename__ = "lectures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_code: Mapped[str] = mapped_column(ForeignKey("courses.code"), nullable=False, index=True)
    no: Mapped[int] = mapped_column(Integer, nullable=False)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    upload_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ArtifactJobRecord(Base):
    """Database record for a scheduled artifact generation job in the queue.

    Attributes:
        id: UUID primary key string.
        course_code: Foreign key to course.
        lecture_no: Sequence number of the lecture (or None for course-wide).
        artifact_type: Type of artifact (audio, quiz_1, mind_map, etc.).
        status: Job lifecycle status (pending, running, done, quota_wait, etc.).
        attempts: Number of execution attempts.
        worker_id: Worker currently holding the job.
        error_message: Error log if failed.
        output_file: Path to final generated output file.
        quota_blocked_at: Timestamp when quota limit was hit.
        cooldown_until: Timestamp when eligible for retry/probe.
        created_at: Creation timestamp.
        updated_at: Last state transition timestamp.
    """

    __tablename__ = "artifact_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    course_code: Mapped[str] = mapped_column(ForeignKey("courses.code"), nullable=False, index=True)
    lecture_no: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_file: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    custom_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    style_options: Mapped[str | None] = mapped_column(Text, nullable=True)
    interactive_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_origin: Mapped[str] = mapped_column(String(30), nullable=False, default="auto")
    quota_blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cooldown_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class QuotaRecord(Base):
    """Database record tracking quota and rate limits per artifact type.

    Attributes:
        artifact_type: Artifact type primary key.
        used_today: Number of generations performed today.
        last_blocked_at: Timestamp of last quota block.
        cooldown_until: End time of cooldown window.
    """

    __tablename__ = "quota_records"

    artifact_type: Mapped[str] = mapped_column(String(50), primary_key=True)
    used_today: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GreetingRecord(Base):
    """One stored greeting (table `greetings`).

    Attributes:
        id: Primary key.
        user_name: Name that was greeted.
        message: Greeting text.
        created_at: When the greeting was stored (UTC).
    """

    __tablename__ = "greetings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_name: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
