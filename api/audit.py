"""SEO Audit endpoints — trigger and retrieve site audits."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from database import get_data_layer
from services.data_layer import DataLayer
from services.seo_audit import audit_domain

router = APIRouter(prefix="/api/audit", tags=["audit"])


class AuditRequest(BaseModel):
    domain: str = ""  # if empty, uses the org's onboarded domain
    max_pages: int = 15


@router.post("/seo")
async def run_seo_audit(req: AuditRequest, dl: DataLayer = Depends(get_data_layer)):
    """Run an SEO audit on the org's domain (or a specified domain)."""
    domain = req.domain

    if not domain:
        # Try to get domain from org settings
        settings = await dl.get_all_settings()
        domain = settings.get("onboard_domain", "")

        if not domain:
            # Try org record
            if dl.org_id:
                org = await dl.get_org(dl.org_id)
                domain = org.get("domain", "") if org else ""

    if not domain:
        return {"error": "No domain specified and no org domain found. Pass a domain in the request."}

    result = await audit_domain(domain, max_pages=req.max_pages)
    return result
