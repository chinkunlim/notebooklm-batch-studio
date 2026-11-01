"""FastAPI HTTP service and web management dashboard for NotebookLM Batch Studio.

Exposes RESTful endpoints, auto-generated OpenAPI documentation for AI tools (Open WebUI),
and serves a local browser management dashboard on 127.0.0.1:8768.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, cast

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine
from sqlalchemy.orm import Session, scoped_session, sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware

from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.adapters.db.study_repository import StudyRepository
from notebooklm_batch_studio.adapters.notebooklm.client import NotebookLMAdapter
from notebooklm_batch_studio.adapters.ollama.client import OllamaClient
from notebooklm_batch_studio.config.logging_setup import setup_logging
from notebooklm_batch_studio.config.settings import AppConfig, load_config
from notebooklm_batch_studio.domain.repositories import QueueRepositoryProtocol
from notebooklm_batch_studio.entrypoints.http.artifacts import artifacts_router
from notebooklm_batch_studio.entrypoints.http.courses import courses_router
from notebooklm_batch_studio.entrypoints.http.queue import queue_router
from notebooklm_batch_studio.entrypoints.http.study import study_router
from notebooklm_batch_studio.entrypoints.http.system import system_router
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from notebooklm_batch_studio.services.study_service import StudyTrackerService

logger = logging.getLogger(__name__)


class HostValidationMiddleware(BaseHTTPMiddleware):
    """Restricts access to local loopback hosts (127.0.0.1 / localhost)."""

    def __init__(self, app: Any, allowed_hosts: tuple[str, ...]) -> None:
        """Initialize middleware with allowed host names.

        Args:
            app: Starlette/FastAPI application.
            allowed_hosts: Tuple of allowed hostname strings.
        """
        super().__init__(app)
        self.allowed_hosts = set(allowed_hosts)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        """Verify the Host header matches allowed hosts.

        Args:
            request: Incoming HTTP request.
            call_next: Next request handler in pipeline.

        Returns:
            HTTP response from downstream handler.

        Raises:
            HTTPException: 400 Bad Request if host header is untrusted.
        """
        host_header = request.headers.get("host", "").split(":")[0]
        if host_header and host_header not in self.allowed_hosts:
            logger.warning("Rejected request with untrusted Host header: %s", host_header)
            return Response(content="Untrusted Host header", status_code=400)
        res = await call_next(request)
        return cast(Response, res)


def _resolve_service(
    service: BatchStudioService | None,
    cfg: AppConfig,
    engine: Engine | None = None,
) -> BatchStudioService:
    """Resolve or construct orchestrator service.

    Args:
        service: Optional injected service instance.
        cfg: Application configuration.
        engine: Optional shared database engine.

    Returns:
        Active BatchStudioService instance.
    """
    if service is not None:
        return service

    eng = engine or create_db_engine(cfg.database_url)
    session = scoped_session(sessionmaker(bind=eng, expire_on_commit=False))
    course_repo = CourseRepository(cast(Session, session))
    queue_repo = QueueRepository(cast(Session, session))
    adapter = NotebookLMAdapter(cfg)

    @contextmanager
    def queue_provider() -> Iterator[QueueRepositoryProtocol]:
        """Provide a scoped QueueRepository for background workers.

        Yields:
            QueueRepository bound to an active transaction.
        """
        with session_scope(eng) as s:
            yield QueueRepository(s)

    return BatchStudioService(
        course_repo=course_repo,
        queue_repo=queue_repo,
        notebooklm_client=adapter,
        config=cfg,
        queue_provider=queue_provider,
        ollama_client=OllamaClient(config=cfg),
    )


def _resolve_study_service(
    study_service: StudyTrackerService | None,
    cfg: AppConfig,
    engine: Engine | None = None,
) -> StudyTrackerService:
    """Resolve or construct study tracking service.

    Args:
        study_service: Optional injected service instance.
        cfg: Application configuration.
        engine: Optional shared database engine.

    Returns:
        Active StudyTrackerService instance.
    """
    if study_service is not None:
        return study_service

    eng = engine or create_db_engine(cfg.database_url)
    session = scoped_session(sessionmaker(bind=eng, expire_on_commit=False))
    study_repo = StudyRepository(cast(Session, session))
    return StudyTrackerService(study_repo=study_repo, config=cfg)


def create_app(
    config: AppConfig | None = None,
    service: BatchStudioService | None = None,
    study_service: StudyTrackerService | None = None,
) -> FastAPI:
    """Construct and configure the FastAPI application.

    Args:
        config: Application configuration (defaults to loaded config).
        service: Optional pre-configured BatchStudioService instance for testing.
        study_service: Optional pre-configured StudyTrackerService instance.

    Returns:
        Configured FastAPI instance ready for serving or TestClient testing.
    """
    cfg = config or load_config()
    shared_engine = None
    if service is None or study_service is None:
        shared_engine = create_db_engine(cfg.database_url)

    active_service = _resolve_service(service, cfg, engine=shared_engine)
    active_study = _resolve_study_service(study_service, cfg, engine=shared_engine)

    app = FastAPI(
        title="NotebookLM Batch Studio",
        description="Batch upload PDFs to Gemini NotebookLM, generate quizzes, mind maps, and audio.",
        version="0.1.0",
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.state.service = active_service
    app.state.study_service = active_study
    app.state.config = cfg

    app.add_middleware(HostValidationMiddleware, allowed_hosts=cfg.http_allowed_hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cfg.http_allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    mcp_server = build_mcp_server(service=active_service, study_service=active_study, config=cfg)
    app.mount("/mcp", mcp_server.streamable_http_app())

    app.include_router(system_router)
    app.include_router(courses_router)
    app.include_router(artifacts_router)
    app.include_router(queue_router)
    app.include_router(study_router)

    return app


def main() -> None:
    """Entrypoint to run the local FastAPI service on 127.0.0.1:8768."""
    config = load_config()
    setup_logging(config.log_level, config.logs_dir if config.log_to_file else None)
    logger.info("Starting Web UI at http://%s:%d", config.http_host, config.http_port)
    uvicorn.run(
        "notebooklm_batch_studio.entrypoints.api:create_app",
        host=config.http_host,
        port=config.http_port,
        factory=True,
        log_level=config.log_level.lower(),
    )


if __name__ == "__main__":
    main()
