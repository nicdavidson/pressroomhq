"""Organization endpoints — create, list, switch companies."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from database import get_data_layer
from services.data_layer import DataLayer

router = APIRouter(prefix="/api/orgs", tags=["orgs"])


class CreateOrgRequest(BaseModel):
    name: str
    domain: str = ""


@router.get("")
async def list_orgs(dl: DataLayer = Depends(get_data_layer)):
    """List all organizations."""
    return await dl.list_orgs()


@router.post("")
async def create_org(req: CreateOrgRequest, dl: DataLayer = Depends(get_data_layer)):
    """Create a new organization."""
    org = await dl.create_org(name=req.name, domain=req.domain)
    await dl.commit()
    return org


@router.get("/{org_id}")
async def get_org(org_id: int, dl: DataLayer = Depends(get_data_layer)):
    """Get a single organization."""
    org = await dl.get_org(org_id)
    if not org:
        return {"error": "Organization not found"}
    return org


@router.delete("/{org_id}")
async def delete_org(org_id: int, dl: DataLayer = Depends(get_data_layer)):
    """Delete an organization."""
    deleted = await dl.delete_org(org_id)
    await dl.commit()
    return {"deleted": deleted}
