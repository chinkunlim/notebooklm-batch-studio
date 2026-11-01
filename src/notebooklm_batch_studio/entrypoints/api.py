"""FastAPI HTTP service and web management dashboard for Gemini Notebook 學習工作室.

Exposes RESTful endpoints, auto-generated OpenAPI documentation for AI tools (Open WebUI),
and serves a local browser management dashboard on 127.0.0.1:8768.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, cast

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Engine
from sqlalchemy.orm import Session, scoped_session, sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware

from notebooklm_batch_studio.adapters.db.learning_repository import LearningRepository
from notebooklm_batch_studio.adapters.db.repository import CourseRepository, QueueRepository
from notebooklm_batch_studio.adapters.db.review_repository import ReviewRepository
from notebooklm_batch_studio.adapters.db.session import create_db_engine, session_scope
from notebooklm_batch_studio.adapters.db.study_repository import StudyRepository
from notebooklm_batch_studio.adapters.notebooklm.client import NotebookLMAdapter
from notebooklm_batch_studio.adapters.ollama.client import OllamaClient
from notebooklm_batch_studio.config.logging_setup import setup_logging
from notebooklm_batch_studio.config.settings import AppConfig, load_config
from notebooklm_batch_studio.domain.repositories import QueueRepositoryProtocol
from notebooklm_batch_studio.entrypoints.http.artifacts import artifacts_router
from notebooklm_batch_studio.entrypoints.http.courses import courses_router
from notebooklm_batch_studio.entrypoints.http.learning import learning_router
from notebooklm_batch_studio.entrypoints.http.plan import plan_router
from notebooklm_batch_studio.entrypoints.http.queue import queue_router
from notebooklm_batch_studio.entrypoints.http.settings import settings_router
from notebooklm_batch_studio.entrypoints.http.study import study_router
from notebooklm_batch_studio.entrypoints.http.system import system_router
from notebooklm_batch_studio.entrypoints.mcp_server import build_mcp_server
from notebooklm_batch_studio.entrypoints.port_check import busy_port_message, port_is_free
from notebooklm_batch_studio.services.learning_service import LearningService
from notebooklm_batch_studio.services.orchestrator import BatchStudioService
from notebooklm_batch_studio.services.study_plan_service import StudyPlanService
from notebooklm_batch_studio.services.study_service import StudyTrackerService

logger = logging.getLogger(__name__)


# Each HTTP request gets its own database session, released when the request ends. Without this,
# sessions were per thread: FastAPI's thread pool kept one open connection per worker thread and
# the pool ran out ("QueuePool limit reached") after enough requests. Refs: ISSUE-023
_DB_SCOPE: ContextVar[object] = ContextVar("db_scope", default="background")
_SCOPED_REGISTRIES: list[scoped_session[Session]] = []


def _request_scoped(factory: sessionmaker[Session]) -> scoped_session[Session]:
    """Create a session registry whose sessions live for one request (or the background scope).

    Args:
        factory: Session factory.

    Returns:
        Scoped session registry, also remembered so the request middleware can release it.
    """
    registry = scoped_session(factory, scopefunc=_DB_SCOPE.get)
    _SCOPED_REGISTRIES.append(registry)
    return registry


class DbSessionScopeMiddleware(BaseHTTPMiddleware):
    """Give every request its own session scope and close the sessions when it finishes."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        """Run the request inside a fresh session scope.

        Args:
            request: Incoming HTTP request.
            call_next: Next request handler in pipeline.

        Returns:
            HTTP response from downstream handler.
        """
        token = _DB_SCOPE.set(object())
        try:
            res = await call_next(request)
            return cast(Response, res)
        finally:
            for registry in _SCOPED_REGISTRIES:
                registry.remove()
            _DB_SCOPE.reset(token)


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
    session = _request_scoped(sessionmaker(bind=eng, expire_on_commit=False))
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
    session = _request_scoped(sessionmaker(bind=eng, expire_on_commit=False))
    study_repo = StudyRepository(cast(Session, session))
    return StudyTrackerService(study_repo=study_repo, config=cfg)


def _build_lifespan(service: BatchStudioService, cfg: AppConfig) -> Callable[[FastAPI], Any]:
    """Create the app lifespan: start the queue on startup (if enabled) and stop it on shutdown.

    With the queue running, jobs blocked by quota sit in QUOTA_WAIT and the worker pool's probe
    loop puts them back to PENDING once their cooldown passes, so work continues on its own.

    Args:
        service: Orchestrator whose queue is managed.
        cfg: Application configuration (`auto_start_queue`).

    Returns:
        An async context manager factory accepted by FastAPI(lifespan=...).
    """

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        """Run startup and shutdown hooks around the application's lifetime.

        Args:
            _app: The FastAPI application.

        Yields:
            Control while the application serves requests.
        """
        if cfg.auto_start_queue:
            logger.info("AUTO_START_QUEUE is on: starting the job queue")
            service.start_queue()
        yield
        if service.worker_pool is not None:
            await service.worker_pool.stop()

    return lifespan


def _build_study_plan(
    service: BatchStudioService, study: StudyTrackerService, cfg: AppConfig, engine: Engine | None
) -> StudyPlanService:
    """Create the study-plan service on the same repositories as the other services.

    Args:
        service: Orchestrator (course / queue repositories and Gemini Notebook client).
        study: Study tracker (quiz attempts and mistakes).
        cfg: Application configuration.
        engine: Shared engine, or None to open one from the configured database URL.

    Returns:
        StudyPlanService.
    """
    session = _request_scoped(
        sessionmaker(bind=engine or create_db_engine(cfg.database_url), expire_on_commit=False)
    )
    return StudyPlanService(
        course_repo=service.course_repo,
        queue_repo=service.queue_repo,
        study_repo=study.study_repo,
        review_repo=ReviewRepository(cast(Session, session)),
        notebooklm_client=service.notebooklm_client,
    )


def _build_learning(service: BatchStudioService, cfg: AppConfig, engine: Engine | None) -> LearningService:
    """Create the learning service (reader, key points, memory, tutor) with request-scoped storage.

    Args:
        service: Orchestrator (course repository and Gemini Notebook client).
        cfg: Application configuration.
        engine: Shared engine, or None to open one from the configured database URL.

    Returns:
        LearningService.
    """
    session = _request_scoped(
        sessionmaker(bind=engine or create_db_engine(cfg.database_url), expire_on_commit=False)
    )
    return LearningService(
        course_repo=service.course_repo,
        learning_repo=LearningRepository(cast(Session, session)),
        notebooklm_client=service.notebooklm_client,
    )


def create_app(
    config: AppConfig | None = None,
    service: BatchStudioService | None = None,
    study_service: StudyTrackerService | None = None,
    study_plan: StudyPlanService | None = None,
) -> FastAPI:
    """Construct and configure the FastAPI application.

    Args:
        config: Application configuration (defaults to loaded config).
        service: Optional pre-configured BatchStudioService instance for testing.
        study_service: Optional pre-configured StudyTrackerService instance.
        study_plan: Optional pre-configured StudyPlanService instance.

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
        title="Gemini Notebook 學習工作室",
        description="Batch upload PDFs to Gemini Notebook, generate quizzes, mind maps, and audio.",
        version="0.1.0",
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=_build_lifespan(active_service, cfg),
    )

    app.state.service = active_service
    app.state.study_service = active_study
    app.state.study_plan = study_plan or _build_study_plan(active_service, active_study, cfg, shared_engine)
    app.state.learning = _build_learning(active_service, cfg, shared_engine)
    app.state.config = cfg

    app.add_middleware(HostValidationMiddleware, allowed_hosts=cfg.http_allowed_hosts)
    app.add_middleware(DbSessionScopeMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cfg.http_allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    mcp_server = build_mcp_server(
        service=active_service,
        study_service=active_study,
        config=cfg,
        study_plan=app.state.study_plan,
        learning=app.state.learning,
    )
    app.mount("/mcp", mcp_server.streamable_http_app())
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

    app.include_router(system_router)
    app.include_router(courses_router)
    app.include_router(artifacts_router)
    app.include_router(queue_router)
    app.include_router(study_router)
    app.include_router(settings_router)
    app.include_router(plan_router)
    app.include_router(learning_router)

    return app


def main() -> None:
    """Entrypoint to run the local FastAPI service on 127.0.0.1:8768."""
    config = load_config()
    setup_logging(config.log_level, config.logs_dir if config.log_to_file else None)
    if not port_is_free(config.http_host, config.http_port):
        message = busy_port_message(config.http_host, config.http_port)
        logger.error("Port busy, not starting: %s", message)
        print(message)
        raise SystemExit(1)
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
