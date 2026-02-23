"""Pipeline endpoints — trigger scout, generate, and full runs."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Signal, Brief, Content, ContentStatus, ContentChannel
from services.scout import run_full_scout
from services.engine import generate_brief, generate_all_content
from services.humanizer import humanize

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.post("/scout")
async def trigger_scout(since_hours: int = 24, db: AsyncSession = Depends(get_db)):
    """Run the scout — pull signals from all sources."""
    raw_signals = await run_full_scout(since_hours)

    saved = []
    for s in raw_signals:
        signal = Signal(
            type=s["type"],
            source=s["source"],
            title=s["title"],
            body=s.get("body", ""),
            url=s.get("url", ""),
            raw_data=s.get("raw_data", ""),
        )
        db.add(signal)
        saved.append(signal)

    await db.commit()
    return {"signals_found": len(saved), "signals": [{"title": s.title, "type": s.type.value, "source": s.source} for s in saved]}


@router.post("/generate")
async def trigger_generate(
    channels: list[str] | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Generate content from today's signals. Runs brief → content → humanizer."""
    # Get recent signals
    from sqlalchemy import select
    result = await db.execute(select(Signal).order_by(Signal.created_at.desc()).limit(20))
    signals = result.scalars().all()

    if not signals:
        return {"error": "No signals found. Run /api/pipeline/scout first."}

    signal_dicts = [{"type": s.type.value, "source": s.source, "title": s.title, "body": s.body} for s in signals]

    # Generate brief
    brief_data = await generate_brief(signal_dicts)
    brief = Brief(
        date=str(__import__("datetime").date.today()),
        summary=brief_data["summary"],
        angle=brief_data["angle"],
        signal_ids=",".join(str(s.id) for s in signals[:10]),
    )
    db.add(brief)
    await db.flush()

    # Parse channels
    target_channels = None
    if channels:
        target_channels = [ContentChannel(c) for c in channels]

    # Generate content
    content_items = await generate_all_content(brief_data["summary"], signal_dicts, target_channels)

    saved_content = []
    for item in content_items:
        raw_body = item["body"]
        clean_body = humanize(raw_body)

        content = Content(
            brief_id=brief.id,
            signal_id=signals[0].id if signals else None,
            channel=item["channel"],
            status=ContentStatus.queued,
            headline=item["headline"],
            body=clean_body,
            body_raw=raw_body,
            author="company",
        )
        db.add(content)
        saved_content.append(content)

    await db.commit()
    return {
        "brief": {"id": brief.id, "angle": brief.angle},
        "content_generated": len(saved_content),
        "items": [{"id": c.id, "channel": c.channel.value, "headline": c.headline} for c in saved_content],
    }


@router.post("/run")
async def full_run(since_hours: int = 24, db: AsyncSession = Depends(get_db)):
    """Full pipeline: scout → brief → generate → humanize → queue."""
    # Scout
    raw_signals = await run_full_scout(since_hours)
    saved_signals = []
    for s in raw_signals:
        signal = Signal(
            type=s["type"],
            source=s["source"],
            title=s["title"],
            body=s.get("body", ""),
            url=s.get("url", ""),
            raw_data=s.get("raw_data", ""),
        )
        db.add(signal)
        saved_signals.append(signal)
    await db.flush()

    if not saved_signals:
        await db.commit()
        return {"status": "no_signals", "message": "Scout found nothing. Wire is quiet."}

    signal_dicts = [{"type": s.type.value, "source": s.source, "title": s.title, "body": s.body} for s in saved_signals]

    # Brief
    brief_data = await generate_brief(signal_dicts)
    brief = Brief(
        date=str(__import__("datetime").date.today()),
        summary=brief_data["summary"],
        angle=brief_data["angle"],
        signal_ids=",".join(str(s.id) for s in saved_signals[:10]),
    )
    db.add(brief)
    await db.flush()

    # Generate all channels
    content_items = await generate_all_content(brief_data["summary"], signal_dicts)

    saved_content = []
    for item in content_items:
        raw_body = item["body"]
        clean_body = humanize(raw_body)
        content = Content(
            brief_id=brief.id,
            signal_id=saved_signals[0].id,
            channel=item["channel"],
            status=ContentStatus.queued,
            headline=item["headline"],
            body=clean_body,
            body_raw=raw_body,
            author="company",
        )
        db.add(content)
        saved_content.append(content)

    await db.commit()

    return {
        "status": "complete",
        "signals": len(saved_signals),
        "brief": {"id": brief.id, "angle": brief.angle},
        "content": [{"id": c.id, "channel": c.channel.value, "headline": c.headline} for c in saved_content],
    }
