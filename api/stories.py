"""Story Workbench — curate signals, add editorial context, generate targeted content.

A Story is an editorial container: selected signals + angle + notes.
Instead of generating from all signals blindly, the editor builds a focused
story and generates content from that curated context.
"""

import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from database import get_data_layer
from services.data_layer import DataLayer

log = logging.getLogger("pressroom")

router = APIRouter(prefix="/api/stories", tags=["stories"])


# ── Request models ──

class StoryCreate(BaseModel):
    title: str
    angle: str = ""
    editorial_notes: str = ""
    signal_ids: list[int] = []  # optionally attach signals at creation time


class StoryUpdate(BaseModel):
    title: str | None = None
    angle: str | None = None
    editorial_notes: str | None = None


class AddSignalRequest(BaseModel):
    signal_id: int
    editor_notes: str = ""


class UpdateSignalNotesRequest(BaseModel):
    editor_notes: str


class GenerateRequest(BaseModel):
    channels: list[str] = []  # which channels to generate — empty = all enabled


# ── CRUD ──

@router.get("")
async def list_stories(limit: int = 20, dl: DataLayer = Depends(get_data_layer)):
    return await dl.list_stories(limit=limit)


@router.post("")
async def create_story(req: StoryCreate, dl: DataLayer = Depends(get_data_layer)):
    story = await dl.create_story({
        "title": req.title,
        "angle": req.angle,
        "editorial_notes": req.editorial_notes,
    })
    # Attach initial signals if provided
    for sid in req.signal_ids:
        await dl.add_signal_to_story(story["id"], sid)
    await dl.commit()
    # Re-fetch to include signals
    return await dl.get_story(story["id"])


@router.get("/{story_id}")
async def get_story(story_id: int, dl: DataLayer = Depends(get_data_layer)):
    story = await dl.get_story(story_id)
    if not story:
        return {"error": "Story not found"}
    return story


@router.put("/{story_id}")
async def update_story(story_id: int, req: StoryUpdate, dl: DataLayer = Depends(get_data_layer)):
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    if not fields:
        return {"error": "No fields to update"}
    story = await dl.update_story(story_id, **fields)
    if not story:
        return {"error": "Story not found"}
    await dl.commit()
    return story


@router.delete("/{story_id}")
async def delete_story(story_id: int, dl: DataLayer = Depends(get_data_layer)):
    deleted = await dl.delete_story(story_id)
    if not deleted:
        return {"error": "Story not found"}
    await dl.commit()
    return {"deleted": story_id}


# ── Signal management ──

@router.post("/{story_id}/signals")
async def add_signal(story_id: int, req: AddSignalRequest, dl: DataLayer = Depends(get_data_layer)):
    ss = await dl.add_signal_to_story(story_id, req.signal_id, req.editor_notes)
    if not ss:
        return {"error": "Failed to add signal — check story and signal exist"}
    await dl.commit()
    return ss


@router.delete("/{story_id}/signals/{story_signal_id}")
async def remove_signal(story_id: int, story_signal_id: int, dl: DataLayer = Depends(get_data_layer)):
    removed = await dl.remove_signal_from_story(story_signal_id)
    if not removed:
        return {"error": "Story-signal not found"}
    await dl.commit()
    return {"deleted": story_signal_id}


@router.put("/{story_id}/signals/{story_signal_id}")
async def update_signal_notes(story_id: int, story_signal_id: int,
                               req: UpdateSignalNotesRequest,
                               dl: DataLayer = Depends(get_data_layer)):
    ss = await dl.update_story_signal_notes(story_signal_id, req.editor_notes)
    if not ss:
        return {"error": "Story-signal not found"}
    await dl.commit()
    return ss


# ── Generate from story ──

@router.post("/{story_id}/generate")
async def generate_from_story(story_id: int, req: GenerateRequest,
                               dl: DataLayer = Depends(get_data_layer)):
    """Generate content from a curated story — uses story signals + editorial context."""
    from services.engine import generate_from_story as engine_generate

    story = await dl.get_story(story_id)
    if not story:
        return {"error": "Story not found"}

    # Mark story as generating
    await dl.update_story(story_id, status="generating")
    await dl.commit()

    try:
        results = await engine_generate(story, dl, channels=req.channels or None)
        await dl.update_story(story_id, status="complete")
        await dl.commit()
        return {"story_id": story_id, "generated": len(results), "content": results}
    except Exception as e:
        log.error("Story generation failed (story=%s): %s", story_id, e)
        await dl.update_story(story_id, status="draft")
        await dl.commit()
        return {"error": str(e)}
