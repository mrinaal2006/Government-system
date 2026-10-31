"""Shared API schemas and helpers."""

from __future__ import annotations

from typing import TypeVar

from fastapi import Query, Response
from pydantic import BaseModel, ConfigDict

from app.core.config import get_settings
from app.modules.iam.service import IssuedSession

T = TypeVar("T")


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def paging(limit: int = Query(25, ge=1, le=200), offset: int = Query(0, ge=0, le=100_000)) -> tuple[int, int]:
    return limit, offset


def set_session_cookies(response: Response, issued: IssuedSession) -> None:
    s = get_settings()
    max_age = s.session_absolute_timeout_minutes * 60
    response.set_cookie(
        s.session_cookie_name,
        issued.token,
        max_age=max_age,
        httponly=True,
        secure=s.cookies_secure,
        samesite="strict",
        path="/",
    )
    # Readable by the SPA, which echoes it in the X-CSRF-Token header.
    response.set_cookie(
        s.csrf_cookie_name,
        issued.csrf_token,
        max_age=max_age,
        httponly=False,
        secure=s.cookies_secure,
        samesite="strict",
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(s.session_cookie_name, path="/", secure=s.cookies_secure, httponly=True, samesite="strict")
    response.delete_cookie(s.csrf_cookie_name, path="/", secure=s.cookies_secure, samesite="strict")
