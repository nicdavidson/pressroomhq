"""Company Assets — CRUD for discovered and manually added digital assets.

Assets represent a company's digital footprint: subdomains, blogs, docs,
repos, social profiles, API endpoints. Discovered during onboarding or
added manually by the editor.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from database import get_data_layer
from services.data_layer import DataLayer

router = APIRouter(prefix="/api/assets", tags=["assets"])


class AssetCreate(BaseModel):
    asset_type: str  # subdomain, blog, docs, repo, social, api_endpoint
    url: str
    label: str = ""
    description: str = ""


class AssetUpdate(BaseModel):
    asset_type: str | None = None
    url: str | None = None
    label: str | None = None
    description: str | None = None


@router.get("")
async def list_assets(type: str | None = None, dl: DataLayer = Depends(get_data_layer)):
    """List company assets, optionally filtered by type."""
    return await dl.list_assets(asset_type=type)


@router.post("")
async def create_asset(req: AssetCreate, dl: DataLayer = Depends(get_data_layer)):
    """Manually add a company asset."""
    asset = await dl.save_asset({
        "asset_type": req.asset_type,
        "url": req.url,
        "label": req.label,
        "description": req.description,
        "discovered_via": "manual",
    })
    await dl.commit()
    return asset


@router.put("/{asset_id}")
async def update_asset(asset_id: int, req: AssetUpdate, dl: DataLayer = Depends(get_data_layer)):
    """Update an asset's label, description, type, or URL."""
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    if not fields:
        return {"error": "No fields to update"}
    asset = await dl.update_asset(asset_id, **fields)
    if not asset:
        return {"error": "Asset not found"}
    await dl.commit()
    return asset


@router.delete("/{asset_id}")
async def delete_asset(asset_id: int, dl: DataLayer = Depends(get_data_layer)):
    """Remove an asset."""
    deleted = await dl.delete_asset(asset_id)
    if not deleted:
        return {"error": "Asset not found"}
    await dl.commit()
    return {"deleted": asset_id}
