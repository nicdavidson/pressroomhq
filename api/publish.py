"""Publish endpoints — push approved content to destinations."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.publisher import publish_approved, DFSocialPublisher
from config import settings

router = APIRouter(prefix="/api/publish", tags=["publish"])


@router.post("")
async def trigger_publish(db: AsyncSession = Depends(get_db)):
    """Publish all approved content that hasn't been published yet."""
    publisher = DFSocialPublisher(
        df_base_url=getattr(settings, "df_base_url", "http://localhost:8080"),
        api_key=getattr(settings, "df_api_key", ""),
    )
    results = await publish_approved(db, publisher)
    return {
        "published": len([r for r in results if "error" not in r]),
        "errors": len([r for r in results if "error" in r]),
        "results": results,
    }
