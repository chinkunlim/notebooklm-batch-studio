"""Services package: core business logic, course parsing, and worker pool management."""

from __future__ import annotations

from notebooklm_batch_studio.services.course_parser import (
    compute_pdf_sha256,
    parse_course_folder_name,
    parse_lecture_filename,
    read_course_toml,
    scan_course_directory,
    write_course_toml,
)
from notebooklm_batch_studio.services.worker_pool import WorkerPool, generate_jobs_for_course

__all__ = [
    "WorkerPool",
    "compute_pdf_sha256",
    "generate_jobs_for_course",
    "parse_course_folder_name",
    "parse_lecture_filename",
    "read_course_toml",
    "scan_course_directory",
    "write_course_toml",
]
