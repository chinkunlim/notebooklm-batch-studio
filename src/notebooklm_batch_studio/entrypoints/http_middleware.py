"""HTTP middlewares and static-file helpers for the local FastAPI server (Refs: ISSUE-046, ISSUE-049).

- `HostValidationMiddleware`: blocks DNS-rebinding by accepting only loopback Host headers.
- `SecurityHeadersMiddleware`: adds a Content-Security-Policy and related headers so that
  injected script cannot send data to other hosts, load plugins, or frame the dashboard.
- `NoCacheStaticFiles`: static files that browsers must revalidate.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, cast

from fastapi import Request, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# The dashboard still relies on inline <script> blocks and on* handlers, so scripts allow
# 'unsafe-inline'; HTML escaping is the primary XSS defense. The policy still stops data leaving
# for other hosts (connect-src / form-action), plugins, <base> hijacking and foreign framing.
CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "media-src 'self' blob:",
        "font-src 'self' data:",
        "worker-src 'self' blob:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'self'",
    )
)

SECURITY_HEADERS: dict[str, str] = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


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
        """Verify the Host header is present and matches the allowed hosts.

        Args:
            request: Incoming HTTP request.
            call_next: Next request handler in pipeline.

        Returns:
            HTTP response from downstream handler, or 400 when the Host header is missing or untrusted.
        """
        host_header = request.headers.get("host", "").split(":")[0]
        if host_header not in self.allowed_hosts:
            logger.warning("Rejected request with untrusted Host header: %r", host_header)
            return Response(content="Untrusted Host header", status_code=400)
        res = await call_next(request)
        return cast(Response, res)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach the Content-Security-Policy and hardening headers to every response."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        """Add security headers without overriding ones a route set explicitly.

        Args:
            request: Incoming HTTP request.
            call_next: Next request handler in pipeline.

        Returns:
            The downstream response with security headers.
        """
        response = cast(Response, await call_next(request))
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response


class NoCacheStaticFiles(StaticFiles):
    """Static files that browsers must revalidate, so an updated page never runs with stale CSS / JS.

    Unchanged files still answer 304 (ETag), so this costs almost nothing on a local server.
    """

    def file_response(self, *args: Any, **kwargs: Any) -> Response:
        """Serve a file with `Cache-Control: no-cache`.

        Args:
            *args: Passed to StaticFiles.file_response.
            **kwargs: Passed to StaticFiles.file_response.

        Returns:
            The file response with the cache header.
        """
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response
