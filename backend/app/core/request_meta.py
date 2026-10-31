"""Client metadata captured for audit and login records."""

from __future__ import annotations

import contextlib
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
        # Behind nginx, uvicorn's proxy-header support (--forwarded-allow-ips) resolves the
        # client address. Behind an edge that overwrites a client-IP header (Vercel sets
        # x-real-ip), CLIENT_IP_HEADER names it; only enable it when the edge is trusted.
        from ipaddress import ip_address

        from app.core.config import get_settings

        ip = request.client.host if request.client else None
        header = get_settings().client_ip_header
        if header:
            candidate = request.headers.get(header, "").split(",")[0].strip()
            with contextlib.suppress(ValueError):
                ip = str(ip_address(candidate))
        if ip == "testclient":
            ip = None
        ua = request.headers.get("user-agent")
        return cls(ip=ip, user_agent=ua[:400] if ua else None, request_id=get_request_id())

    @classmethod
    def system(cls) -> RequestMeta:
        return cls(ip=None, user_agent="system", request_id=get_request_id())
