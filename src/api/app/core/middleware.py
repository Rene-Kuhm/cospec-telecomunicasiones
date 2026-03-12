import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


log = structlog.get_logger(__name__)


class TraceIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id=trace_id)

        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple in-memory rate limiter using sliding window per (IP, path).
    For production, replace with Redis-backed implementation.
    """

    def __init__(self, app) -> None:
        super().__init__(app)
        # {key: [(timestamp, count), ...]}
        self._windows: dict[str, list[float]] = defaultdict(list)

    def _get_limit_for_path(self, path: str) -> int:
        from app.config import settings  # noqa: PLC0415

        if path.endswith("/auth/login"):
            return settings.RATE_LIMIT_LOGIN_PER_MINUTE
        if path.endswith("/auth/register"):
            return settings.RATE_LIMIT_REGISTER_PER_MINUTE
        return settings.RATE_LIMIT_API_PER_MINUTE

    async def dispatch(self, request: Request, call_next) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        key = f"{client_ip}:{path}"
        limit = self._get_limit_for_path(path)

        now = time.monotonic()
        window_start = now - 60.0

        # Prune old entries
        self._windows[key] = [ts for ts in self._windows[key] if ts > window_start]

        if len(self._windows[key]) >= limit:
            trace_id = request.headers.get("X-Trace-Id", str(uuid.uuid4()))
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "data": None,
                    "error": {
                        "type": "RateLimitError",
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Too many requests. Please slow down.",
                        "trace_id": trace_id,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                    "meta": {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "version": "v1",
                    },
                },
                headers={"Retry-After": "60"},
            )

        self._windows[key].append(now)
        return await call_next(request)
