"""Onboarding API — domain crawl, profile synthesis, DF classification, apply."""

import json
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Setting
from services.onboarding import crawl_domain, synthesize_profile, classify_df_services, profile_to_settings
from services.df_client import df

router = APIRouter(prefix="/api/onboard", tags=["onboard"])


# ──────────────────────────────────────
# Request models
# ──────────────────────────────────────

class CrawlRequest(BaseModel):
    domain: str

class ProfileRequest(BaseModel):
    crawl_data: dict | None = None
    domain: str | None = None
    extra_context: str = ""

class ApplyProfileRequest(BaseModel):
    profile: dict
    service_map: dict | None = None

class ClassifyRequest(BaseModel):
    """Optionally pass pre-fetched service data; otherwise we discover live."""
    pass


# ──────────────────────────────────────
# Endpoints
# ──────────────────────────────────────

@router.post("/crawl")
async def onboard_crawl(req: CrawlRequest):
    """Step 1: Crawl a domain and extract page content."""
    if not req.domain:
        return {"error": "Domain is required"}

    data = await crawl_domain(req.domain)
    return data


@router.post("/profile")
async def onboard_profile(req: ProfileRequest):
    """Step 2: Synthesize a company profile from crawl data.

    If crawl_data not provided, crawls the domain first.
    """
    crawl_data = req.crawl_data
    if not crawl_data and req.domain:
        crawl_data = await crawl_domain(req.domain)

    if not crawl_data:
        return {"error": "Need crawl_data or domain"}

    profile = await synthesize_profile(crawl_data, req.extra_context)
    return {"profile": profile, "crawl": crawl_data}


@router.post("/df-classify")
async def onboard_df_classify():
    """Step 3: Discover DF services, introspect schemas, classify with Claude.

    Requires DF to be connected (df_base_url + df_api_key in settings).
    """
    if not df.available:
        return {"available": False, "error": "DreamFactory not configured. Set df_base_url and df_api_key first."}

    try:
        # Introspect all DB services (schemas + sample data)
        db_services = await df.introspect_all_db_services()

        # Get social services with auth status
        social_services = await df.discover_social_services()
        for svc in social_services:
            try:
                svc["auth_status"] = await df.social_auth_status(svc.get("name", ""))
            except Exception:
                svc["auth_status"] = {"connected": False}

        # Claude classifies everything
        classification = await classify_df_services(db_services, social_services)

        return {
            "available": True,
            "db_services": db_services,
            "social_services": social_services,
            "classification": classification,
        }
    except Exception as e:
        return {"available": False, "error": str(e)}


@router.post("/apply")
async def onboard_apply(req: ApplyProfileRequest, db: AsyncSession = Depends(get_db)):
    """Step 4: Apply the reviewed profile as settings + store service map."""
    applied = []

    # Convert profile to settings and save
    settings_map = profile_to_settings(req.profile)
    for key, value in settings_map.items():
        result = await db.execute(select(Setting).where(Setting.key == key))
        existing = result.scalar_one_or_none()
        if existing:
            existing.value = value
        else:
            db.add(Setting(key=key, value=value))
        applied.append(key)

    # Store company metadata that doesn't map to voice settings
    meta_keys = {
        "company_name": "onboard_company_name",
        "industry": "onboard_industry",
        "topics": "onboard_topics",
        "competitors": "onboard_competitors",
    }
    for profile_key, setting_key in meta_keys.items():
        val = req.profile.get(profile_key)
        if val:
            str_val = json.dumps(val) if isinstance(val, (list, dict)) else str(val)
            result = await db.execute(select(Setting).where(Setting.key == setting_key))
            existing = result.scalar_one_or_none()
            if existing:
                existing.value = str_val
            else:
                db.add(Setting(key=setting_key, value=str_val))
            applied.append(setting_key)

    # Store DF service map if provided
    if req.service_map:
        result = await db.execute(select(Setting).where(Setting.key == "df_service_map"))
        existing = result.scalar_one_or_none()
        map_json = json.dumps(req.service_map)
        if existing:
            existing.value = map_json
        else:
            db.add(Setting(key="df_service_map", value=map_json))
        applied.append("df_service_map")

    # Mark onboarding as complete
    result = await db.execute(select(Setting).where(Setting.key == "onboard_complete"))
    existing = result.scalar_one_or_none()
    if existing:
        existing.value = "true"
    else:
        db.add(Setting(key="onboard_complete", value="true"))
    applied.append("onboard_complete")

    await db.commit()

    # Sync to runtime config
    from api.settings import _sync_to_runtime
    await _sync_to_runtime(db)

    return {"applied": applied, "count": len(applied)}


@router.get("/status")
async def onboard_status(db: AsyncSession = Depends(get_db)):
    """Check onboarding progress — what's been completed."""
    result = await db.execute(select(Setting))
    stored = {s.key: s.value for s in result.scalars().all()}

    return {
        "complete": stored.get("onboard_complete") == "true",
        "has_company": bool(stored.get("onboard_company_name")),
        "has_voice": bool(stored.get("voice_persona")),
        "has_df": bool(stored.get("df_api_key")),
        "has_service_map": bool(stored.get("df_service_map")),
        "company_name": stored.get("onboard_company_name", ""),
        "industry": stored.get("onboard_industry", ""),
    }
