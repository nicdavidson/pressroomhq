"""Publish endpoints — push approved content to destinations via DF social services."""

from fastapi import APIRouter, Depends

from database import get_data_layer
from services.data_layer import DataLayer
from services.publisher import publish_approved

router = APIRouter(prefix="/api/publish", tags=["publish"])


@router.post("")
async def trigger_publish(dl: DataLayer = Depends(get_data_layer)):
    """Publish all approved content that hasn't been published yet."""
    results = await publish_approved(dl)
    return {
        "published": len([r for r in results if "error" not in r]),
        "errors": len([r for r in results if "error" in r]),
        "results": results,
    }
