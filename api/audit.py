"""Audit endpoints — SEO site audits and GitHub README audits, with persistence."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from database import get_data_layer
from services.data_layer import DataLayer
from services.seo_audit import audit_domain
from services.readme_audit import audit_readme

router = APIRouter(prefix="/api/audit", tags=["audit"])


class AuditRequest(BaseModel):
    domain: str = ""  # if empty, uses the org's onboarded domain
    max_pages: int = 15


class ReadmeAuditRequest(BaseModel):
    repo: str = ""  # owner/repo or full GitHub URL


@router.post("/seo")
async def run_seo_audit(req: AuditRequest, dl: DataLayer = Depends(get_data_layer)):
    """Run an SEO audit on the org's domain (or a specified domain). Saves result."""
    domain = req.domain

    if not domain:
        settings = await dl.get_all_settings()
        domain = settings.get("onboard_domain", "")

        if not domain:
            if dl.org_id:
                org = await dl.get_org(dl.org_id)
                domain = org.get("domain", "") if org else ""

    if not domain:
        return {"error": "No domain specified and no org domain found. Pass a domain in the request."}

    api_key = await dl.resolve_api_key()
    result = await audit_domain(domain, max_pages=req.max_pages, api_key=api_key)

    if "error" not in result:
        saved = await dl.save_audit({
            "audit_type": "seo",
            "target": result.get("domain", domain),
            "score": result.get("recommendations", {}).get("score", 0),
            "total_issues": result.get("recommendations", {}).get("total_issues", 0),
            "result": result,
        })
        await dl.commit()
        result["audit_id"] = saved["id"]

    return result


@router.post("/readme")
async def run_readme_audit(req: ReadmeAuditRequest, dl: DataLayer = Depends(get_data_layer)):
    """Run a README quality audit on a GitHub repo. Saves result."""
    repo = req.repo

    if not repo:
        return {"error": "No repo specified. Pass a repo like 'owner/repo' or a GitHub URL."}

    api_key = await dl.resolve_api_key()
    result = await audit_readme(repo, api_key=api_key)

    if "error" not in result:
        saved = await dl.save_audit({
            "audit_type": "readme",
            "target": result.get("repo", repo),
            "score": result.get("recommendations", {}).get("score", 0),
            "total_issues": result.get("recommendations", {}).get("total_issues", 0),
            "result": result,
        })
        await dl.commit()
        result["audit_id"] = saved["id"]

    return result


@router.get("/history")
async def list_audits(
    audit_type: str | None = Query(None),
    limit: int = Query(20),
    dl: DataLayer = Depends(get_data_layer),
):
    """List saved audit results for this org."""
    return await dl.list_audits(audit_type=audit_type, limit=limit)


@router.get("/history/{audit_id}")
async def get_audit(audit_id: int, dl: DataLayer = Depends(get_data_layer)):
    """Get a single saved audit result with full data."""
    result = await dl.get_audit(audit_id)
    if not result:
        return {"error": "Audit not found"}
    return result


@router.delete("/history/{audit_id}")
async def delete_audit(audit_id: int, dl: DataLayer = Depends(get_data_layer)):
    """Delete a saved audit result."""
    deleted = await dl.delete_audit(audit_id)
    await dl.commit()
    if not deleted:
        return {"error": "Audit not found"}
    return {"deleted": audit_id}
