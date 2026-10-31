"""Prometheus instrumentation (request counts/latency by route template, not raw path)."""

from __future__ import annotations

import time

from prometheus_client import Counter, Histogram
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUESTS = Counter("dgimews_http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram(
    "dgimews_http_request_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)


class MetricsMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        status = {"code": 500}

        async def wrapped(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, wrapped)
        finally:
            route = scope.get("route")
            template = getattr(route, "path", "unmatched")
            REQUESTS.labels(scope.get("method", ""), template, str(status["code"])).inc()
            LATENCY.labels(scope.get("method", ""), template).observe(time.perf_counter() - start)
