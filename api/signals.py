"""Signal/Wire endpoints — view incoming signals."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Signal

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("")
async def list_signals(limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Signal).order_by(Signal.created_at.desc()).limit(limit))
    signals = result.scalars().all()
    return [
        {
            "id": s.id,
            "type": s.type.value,
            "source": s.source,
            "title": s.title,
            "body": s.body,
            "url": s.url,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in signals
    ]


@router.get("/{signal_id}")
async def get_signal(signal_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Signal).where(Signal.id == signal_id))
    s = result.scalar_one_or_none()
    if not s:
        return {"error": "Signal not found"}, 404
    return {
        "id": s.id,
        "type": s.type.value,
        "source": s.source,
        "title": s.title,
        "body": s.body,
        "url": s.url,
        "raw_data": s.raw_data,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }
