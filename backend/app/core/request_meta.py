"""Client metadata captured for audit and login records."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from app.core.request_context import get_request_id


@dataclass(frozen=True)
class RequestMeta:
    ip: str | None
    user_agent: str | None
    request_id: str | None

    @classmethod
    def from_request(cls, request: Request) -> RequestMeta:
        # uvicorn's proxy-header support (--forwarded-allow-ips) already resolves the
        # client address from nginx's X-Forwarded-For.
        ip = request.client.host if request.client else None
        if ip == "testclient":
            ip = None
        ua = request.headers.get("user-agent")
        return cls(ip=ip, user_agent=ua[:400] if ua else None, request_id=get_request_id())

    @classmethod
    def system(cls) -> RequestMeta:
        return cls(ip=None, user_agent="system", request_id=get_request_id())
