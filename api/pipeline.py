"""Pipeline endpoints — trigger scout, generate, and full runs."""

import datetime

from fastapi import APIRouter, Depends

from database import get_data_layer
from models import ContentChannel
from services.data_layer import DataLayer
from services.scout import run_full_scout
from services.engine import generate_brief, generate_all_content
from services.humanizer import humanize

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.post("/scout")
async def trigger_scout(since_hours: int = 24, dl: DataLayer = Depends(get_data_layer)):
    """Run the scout — pull signals from all sources."""
    raw_signals = await run_full_scout(since_hours)

    saved = []
    for s in raw_signals:
        result = await dl.save_signal(s)
        saved.append(result)

    await dl.commit()
    return {"signals_found": len(saved), "signals": [{"title": s.get("title", ""), "type": s.get("type", ""), "source": s.get("source", "")} for s in saved]}


@router.post("/generate")
async def trigger_generate(
    channels: list[str] | None = None,
    dl: DataLayer = Depends(get_data_layer),
):
    """Generate content from today's signals. Runs brief → content → humanizer."""
    signal_dicts = await dl.list_signals(limit=20)

    if not signal_dicts:
        return {"error": "No signals found. Run /api/pipeline/scout first."}

    # Load voice settings and memory context
    voice = await dl.get_voice_settings()
    memory = await dl.get_memory_context()

    # Generate brief (now voice-aware and intelligence-aware)
    brief_data = await generate_brief(signal_dicts, memory=memory, voice_settings=voice)
    brief = await dl.save_brief({
        "date": str(datetime.date.today()),
        "summary": brief_data["summary"],
        "angle": brief_data["angle"],
        "signal_ids": ",".join(str(s.get("id", "")) for s in signal_dicts[:10]),
    })

    # Parse channels
    target_channels = None
    if channels:
        target_channels = [ContentChannel(c) for c in channels]

    # Generate content with memory + voice + DF intelligence
    content_items = await generate_all_content(
        brief_data["summary"], signal_dicts, target_channels,
        memory=memory, voice_settings=voice,
    )

    saved_content = []
    for item in content_items:
        raw_body = item["body"]
        clean_body = humanize(raw_body)
        result = await dl.save_content({
            "brief_id": brief.get("id"),
            "signal_id": signal_dicts[0].get("id") if signal_dicts else None,
            "channel": item["channel"],
            "status": "queued",
            "headline": item["headline"],
            "body": clean_body,
            "body_raw": raw_body,
            "author": "company",
        })
        saved_content.append(result)

    await dl.commit()
    return {
        "brief": {"id": brief.get("id"), "angle": brief_data["angle"]},
        "content_generated": len(saved_content),
        "items": [{"id": c.get("id"), "channel": c.get("channel", ""), "headline": c.get("headline", "")} for c in saved_content],
    }


@router.post("/run")
async def full_run(since_hours: int = 24, dl: DataLayer = Depends(get_data_layer)):
    """Full pipeline: scout → brief → generate → humanize → queue."""
    raw_signals = await run_full_scout(since_hours)

    saved_signals = []
    for s in raw_signals:
        result = await dl.save_signal(s)
        saved_signals.append(result)

    if not saved_signals:
        await dl.commit()
        return {"status": "no_signals", "message": "Scout found nothing. Wire is quiet."}

    signal_dicts = saved_signals

    # Load voice settings and memory context
    voice = await dl.get_voice_settings()
    memory = await dl.get_memory_context()

    # Brief (voice-aware, intelligence-aware)
    brief_data = await generate_brief(signal_dicts, memory=memory, voice_settings=voice)
    brief = await dl.save_brief({
        "date": str(datetime.date.today()),
        "summary": brief_data["summary"],
        "angle": brief_data["angle"],
        "signal_ids": ",".join(str(s.get("id", "")) for s in signal_dicts[:10]),
    })

    # Generate all channels with full context
    content_items = await generate_all_content(
        brief_data["summary"], signal_dicts,
        memory=memory, voice_settings=voice,
    )

    saved_content = []
    for item in content_items:
        raw_body = item["body"]
        clean_body = humanize(raw_body)
        result = await dl.save_content({
            "brief_id": brief.get("id"),
            "signal_id": signal_dicts[0].get("id") if signal_dicts else None,
            "channel": item["channel"],
            "status": "queued",
            "headline": item["headline"],
            "body": clean_body,
            "body_raw": raw_body,
            "author": "company",
        })
        saved_content.append(result)

    await dl.commit()

    return {
        "status": "complete",
        "signals": len(saved_signals),
        "brief": {"id": brief.get("id"), "angle": brief_data["angle"]},
        "content": [{"id": c.get("id"), "channel": c.get("channel", ""), "headline": c.get("headline", "")} for c in saved_content],
    }
