"""Middleware for request-level memory monitoring in SentinelOps API."""

from __future__ import annotations

import logging
import time

import psutil
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

DEFAULT_MEMORY_THRESHOLD_MB = 150


class MemoryMonitorMiddleware(BaseHTTPMiddleware):
    """Tracks request-level memory usage and logs warnings above threshold."""

    def __init__(self, app, threshold_mb: int = DEFAULT_MEMORY_THRESHOLD_MB):
        super().__init__(app)
        self.threshold_mb = threshold_mb

    async def dispatch(self, request: Request, call_next):
        app = request.app
        if not hasattr(app.state, "request_count"):
            app.state.request_count = 0
        if not hasattr(app.state, "start_time"):
            app.state.start_time = time.time()

        app.state.request_count += 1
        proc = psutil.Process()
        mem_before = proc.memory_info().rss / (1024 * 1024)

        response = await call_next(request)

        mem_after = proc.memory_info().rss / (1024 * 1024)
        mem_delta = mem_after - mem_before

        if mem_delta > self.threshold_mb:
            logger.warning(
                "Memory spike: +%.1fMB (total %.1fMB) on %s %s",
                mem_delta, mem_after, request.method, request.url.path,
            )

        return response


def get_memory_stats(app) -> dict:
    """Collect current memory and process statistics."""
    proc = psutil.Process()
    rss = proc.memory_info().rss / (1024 * 1024)
    try:
        import tracemalloc
        if not tracemalloc.is_tracing():
            tracemalloc.start()
        current, peak = tracemalloc.get_traced_memory()
        python_heap_mb = peak / (1024 * 1024)
    except Exception:
        python_heap_mb = 0.0

    request_count = getattr(app.state, "request_count", 0)
    uptime = time.time() - getattr(app.state, "start_time", time.time())

    return {
        "rss_memory_mb": round(rss, 2),
        "python_heap_mb": round(python_heap_mb, 2),
        "request_count": request_count,
        "uptime_seconds": round(uptime, 2),
    }
