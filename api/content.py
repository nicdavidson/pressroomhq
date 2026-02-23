"""Content endpoints — approval queue, content management."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import get_data_layer
from services.data_layer import DataLayer

router = APIRouter(prefix="/api/content", tags=["content"])


class ActionRequest(BaseModel):
    action: str  # "approve" | "spike"


@router.get("")
async def list_content(
    status: str | None = None,
    limit: int = 50,
    dl: DataLayer = Depends(get_data_layer),
):
    return await dl.list_content(status=status, limit=limit)


@router.get("/queue")
async def approval_queue(dl: DataLayer = Depends(get_data_layer)):
    """The editor's desk — all content awaiting approval."""
    return await dl.list_content(status="queued")


@router.get("/{content_id}")
async def get_content(content_id: int, dl: DataLayer = Depends(get_data_layer)):
    c = await dl.get_content(content_id)
    if not c:
        raise HTTPException(status_code=404, detail="Content not found")
    return c


@router.post("/{content_id}/action")
async def content_action(content_id: int, req: ActionRequest, dl: DataLayer = Depends(get_data_layer)):
    """Approve or spike a piece of content."""
    c = await dl.get_content(content_id)
    if not c:
        raise HTTPException(status_code=404, detail="Content not found")

    if req.action not in ("approve", "spike"):
        raise HTTPException(status_code=400, detail=f"Unknown action: {req.action}")

    result = await dl.update_content_status(content_id, "approved" if req.action == "approve" else "spiked")
    await dl.commit()
    return result
