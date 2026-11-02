"""Domain exceptions: specialized error types for business and provider logic."""

from __future__ import annotations


class StudioError(Exception):
    """Base exception for all domain and service errors in Gemini Notebook 學習工作室."""


class QuotaExceededError(StudioError):
    """Raised when an operation exceeds Google Gemini Notebook's rate limit or daily quota.

    Attributes:
        artifact_type: The type of artifact that reached its quota.
        retry_after_seconds: Recommended cooldown period in seconds, if known.
    """

    def __init__(
        self, message: str, artifact_type: str | None = None, retry_after_seconds: int = 3600
    ) -> None:
        """Initialize QuotaExceededError.

        Args:
            message: Explanation of the quota limit encountered.
            artifact_type: The artifact type string (e.g. 'audio').
            retry_after_seconds: Suggested backoff duration in seconds.
        """
        super().__init__(message)
        self.artifact_type = artifact_type
        self.retry_after_seconds = retry_after_seconds


class AuthExpiredError(StudioError):
    """Raised when Gemini Notebook authentication credentials have expired or are missing."""


class IncompleteArtifactError(StudioError):
    """Raised when an extracted artifact fails validation (e.g., missing choices or empty tree)."""


class NeedsReviewError(StudioError):
    """Raised when an artifact was saved but failed quality checks and needs manual review.

    Attributes:
        output_file: Path of the quarantined file under `needs_review/`.
    """

    def __init__(self, message: str, output_file: str) -> None:
        """Initialize NeedsReviewError.

        Args:
            message: Why the artifact needs review (e.g. too few questions).
            output_file: Path of the quarantined file.
        """
        super().__init__(message)
        self.output_file = output_file


class OllamaUnavailableError(StudioError):
    """Raised when an operation needs local Ollama but no client is configured or it is unreachable."""


class SourceLimitExceededError(StudioError):
    """Raised when a course has more lectures than the account allows sources per notebook."""


class CourseNotFoundError(StudioError):
    """Raised when an operation targets a course code that does not exist."""


class DuplicateCourseError(StudioError):
    """Raised when attempting to add a course that already exists with conflicting settings."""


class FontDownloadError(StudioError):
    """Raised when a Google Fonts family cannot be downloaded (network error, unknown family, too large)."""
