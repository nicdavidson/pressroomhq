"""Content endpoints — approval queue, content management."""

import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Content, ContentStatus

router = APIRouter(prefix="/api/content", tags=["content"])


class ActionRequest(BaseModel):
    action: str  # "approve" | "spike"


@router.get("")
async def list_content(
    status: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    query = select(Content).order_by(Content.created_at.desc()).limit(limit)
    if status:
        query = query.where(Content.status == ContentStatus(status))
    result = await db.execute(query)
    items = result.scalars().all()
    return [_serialize(c) for c in items]


@router.get("/queue")
async def approval_queue(db: AsyncSession = Depends(get_db)):
    """The editor's desk — all content awaiting approval."""
    result = await db.execute(
        select(Content)
        .where(Content.status == ContentStatus.queued)
        .order_by(Content.created_at.desc())
    )
    items = result.scalars().all()
    return [_serialize(c) for c in items]


@router.get("/{content_id}")
async def get_content(content_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Content).where(Content.id == content_id))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Content not found")
    return _serialize(c)


@router.post("/{content_id}/action")
async def content_action(content_id: int, req: ActionRequest, db: AsyncSession = Depends(get_db)):
    """Approve or spike a piece of content."""
    result = await db.execute(select(Content).where(Content.id == content_id))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Content not found")

    if req.action == "approve":
        c.status = ContentStatus.approved
        c.approved_at = datetime.datetime.utcnow()
    elif req.action == "spike":
        c.status = ContentStatus.spiked
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {req.action}")

    await db.commit()
    return _serialize(c)


def _serialize(c: Content) -> dict:
    return {
        "id": c.id,
        "signal_id": c.signal_id,
        "brief_id": c.brief_id,
        "channel": c.channel.value,
        "status": c.status.value,
        "headline": c.headline,
        "body": c.body,
        "body_raw": c.body_raw,
        "author": c.author,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "approved_at": c.approved_at.isoformat() if c.approved_at else None,
        "published_at": c.published_at.isoformat() if c.published_at else None,
    }
