from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth import CurrentUserDep, DbDep
from app.api.common import paging
from app.modules.notifications import service

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    id: uuid.UUID
    category: str
    title: str
    body: str | None
    link: str | None
    created_at: datetime
    read_at: datetime | None


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    total: int
    unread: int


@router.get("", response_model=NotificationPage)
def list_notifications(
    cu: CurrentUserDep,
    db: DbDep,
    pg: Annotated[tuple[int, int], Depends(paging)],
    unread_only: bool = False,
) -> NotificationPage:
    rows, total, unread = service.list_for(db, cu.id, unread_only=unread_only, limit=pg[0], offset=pg[1])
    return NotificationPage(
        items=[
            NotificationOut(
                id=r.id,
                category=r.category,
                title=r.title,
                body=r.body,
                link=r.link,
                created_at=r.created_at,
                read_at=r.read_at,
            )
            for r in rows
        ],
        total=total,
        unread=unread,
    )


@router.post("/{notification_id}/read", status_code=204)
def read_one(notification_id: uuid.UUID, cu: CurrentUserDep, db: DbDep) -> None:
    service.mark_read(db, cu.id, notification_id)


@router.post("/read-all", status_code=204)
def read_all(cu: CurrentUserDep, db: DbDep) -> None:
    service.mark_read(db, cu.id, None)
