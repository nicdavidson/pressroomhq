"""Settings endpoints — configure API keys, scout sources, voice profile."""

import json
import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Setting

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Default settings structure
DEFAULTS = {
    # API Keys
    "anthropic_api_key": "",
    "github_token": "",
    # DreamFactory
    "df_base_url": "http://localhost:8080",
    "df_api_key": "",
    # Scout sources
    "scout_github_repos": '["dreamfactorysoftware/dreamfactory"]',
    "scout_hn_keywords": '["DreamFactory", "REST API", "API gateway"]',
    "scout_subreddits": '["selfhosted", "webdev"]',
    "scout_rss_feeds": '[]',
    # Voice profile
    "voice_persona": "Montana-based engineer building real AI infrastructure",
    "voice_audience": "Engineers and technical decision-makers",
    "voice_tone": "Direct, opinionated, no corporate-speak",
    "voice_never_say": '["excited to share", "game-changer", "leverage", "synergy", "thrilled"]',
    "voice_always": "Here's what I built, here's what broke, here's what I learned",
    # Engine
    "claude_model": "claude-sonnet-4-20250514",
    # Webhook
    "github_webhook_secret": "",
}

# Keys that should be masked in GET responses
SENSITIVE_KEYS = {"anthropic_api_key", "github_token", "df_api_key", "github_webhook_secret"}


def _mask(key: str, value: str) -> str:
    if key in SENSITIVE_KEYS and value:
        return value[:8] + "..." if len(value) > 8 else "***"
    return value


class SettingsUpdate(BaseModel):
    settings: dict[str, str]


@router.get("")
async def get_settings(db: AsyncSession = Depends(get_db)):
    """Get all settings (sensitive values masked)."""
    result = await db.execute(select(Setting))
    stored = {s.key: s.value for s in result.scalars().all()}

    # Merge defaults with stored
    merged = {}
    for key, default in DEFAULTS.items():
        raw = stored.get(key, default)
        merged[key] = {
            "value": _mask(key, raw),
            "is_set": bool(raw and raw != default),
            "sensitive": key in SENSITIVE_KEYS,
        }
    return merged


@router.get("/raw/{key}")
async def get_setting_raw(key: str, db: AsyncSession = Depends(get_db)):
    """Get a single setting value (unmasked). Use sparingly."""
    result = await db.execute(select(Setting).where(Setting.key == key))
    s = result.scalar_one_or_none()
    if s:
        return {"key": key, "value": s.value}
    return {"key": key, "value": DEFAULTS.get(key, "")}


@router.put("")
async def update_settings(req: SettingsUpdate, db: AsyncSession = Depends(get_db)):
    """Update one or more settings."""
    updated = []
    for key, value in req.settings.items():
        if key not in DEFAULTS:
            continue
        result = await db.execute(select(Setting).where(Setting.key == key))
        existing = result.scalar_one_or_none()
        if existing:
            existing.value = value
        else:
            db.add(Setting(key=key, value=value))
        updated.append(key)

    await db.commit()

    # Reload runtime config from DB
    await _sync_to_runtime(db)

    return {"updated": updated}


@router.get("/status")
async def connection_status(db: AsyncSession = Depends(get_db)):
    """Check connection status for all configured services."""
    settings = {}
    result = await db.execute(select(Setting))
    for s in result.scalars().all():
        settings[s.key] = s.value

    status = {}

    # Anthropic
    api_key = settings.get("anthropic_api_key", "")
    status["anthropic"] = {
        "configured": bool(api_key),
        "model": settings.get("claude_model", DEFAULTS["claude_model"]),
    }

    # GitHub
    gh_token = settings.get("github_token", "")
    if gh_token:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.github.com/user",
                    headers={"Authorization": f"token {gh_token}"},
                    timeout=5,
                )
                if resp.status_code == 200:
                    user = resp.json()
                    status["github"] = {"configured": True, "connected": True, "user": user.get("login", "")}
                else:
                    status["github"] = {"configured": True, "connected": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            status["github"] = {"configured": True, "connected": False, "error": str(e)}
    else:
        status["github"] = {"configured": False}

    # DreamFactory
    df_url = settings.get("df_base_url", DEFAULTS["df_base_url"])
    df_key = settings.get("df_api_key", "")
    if df_key:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{df_url}/api/v2/system/environment",
                    headers={"X-DreamFactory-Api-Key": df_key},
                    timeout=5,
                )
                status["dreamfactory"] = {
                    "configured": True,
                    "connected": resp.status_code == 200,
                    "url": df_url,
                }
        except Exception as e:
            status["dreamfactory"] = {"configured": True, "connected": False, "url": df_url, "error": str(e)}
    else:
        status["dreamfactory"] = {"configured": False, "url": df_url}

    # Scout sources
    repos = json.loads(settings.get("scout_github_repos", DEFAULTS["scout_github_repos"]))
    hn_kw = json.loads(settings.get("scout_hn_keywords", DEFAULTS["scout_hn_keywords"]))
    subs = json.loads(settings.get("scout_subreddits", DEFAULTS["scout_subreddits"]))
    rss = json.loads(settings.get("scout_rss_feeds", DEFAULTS["scout_rss_feeds"]))
    status["scout"] = {
        "github_repos": len(repos),
        "hn_keywords": len(hn_kw),
        "subreddits": len(subs),
        "rss_feeds": len(rss),
        "total_sources": len(repos) + len(subs) + len(rss) + (1 if hn_kw else 0),
    }

    return status


@router.get("/df-services")
async def df_services():
    """Discover DF services — databases, social platforms, etc."""
    from services.df_client import df
    if not df.available:
        return {"available": False, "services": [], "social": [], "databases": []}
    try:
        all_services = await df.list_services()
        social = await df.discover_social_services()
        databases = await df.discover_db_services()

        # Check social auth status for each
        social_with_auth = []
        for svc in social:
            name = svc.get("name", "")
            try:
                auth = await df.social_auth_status(name)
                svc["auth_status"] = auth
            except Exception:
                svc["auth_status"] = {"connected": False}
            social_with_auth.append(svc)

        return {
            "available": True,
            "services": all_services,
            "social": social_with_auth,
            "databases": databases,
        }
    except Exception as e:
        return {"available": False, "error": str(e), "services": [], "social": [], "databases": []}


async def _sync_to_runtime(db: AsyncSession):
    """Push DB settings into the runtime config object."""
    from config import settings as cfg
    result = await db.execute(select(Setting))
    stored = {s.key: s.value for s in result.scalars().all()}

    if stored.get("anthropic_api_key"):
        cfg.anthropic_api_key = stored["anthropic_api_key"]
    if stored.get("github_token"):
        cfg.github_token = stored["github_token"]
    if stored.get("df_base_url"):
        cfg.df_base_url = stored["df_base_url"]
    if stored.get("df_api_key"):
        cfg.df_api_key = stored["df_api_key"]
    if stored.get("claude_model"):
        cfg.claude_model = stored["claude_model"]
    if stored.get("github_webhook_secret"):
        cfg.github_webhook_secret = stored["github_webhook_secret"]

    try:
        if stored.get("scout_github_repos"):
            cfg.scout_github_repos = json.loads(stored["scout_github_repos"])
        if stored.get("scout_hn_keywords"):
            cfg.scout_hn_keywords = json.loads(stored["scout_hn_keywords"])
        if stored.get("scout_subreddits"):
            cfg.scout_subreddits = json.loads(stored["scout_subreddits"])
        if stored.get("scout_rss_feeds"):
            cfg.scout_rss_feeds = json.loads(stored["scout_rss_feeds"])
    except json.JSONDecodeError:
        pass
