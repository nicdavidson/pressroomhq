"""Settings endpoints — configure API keys, scout sources, voice profile.

All settings are org-scoped via the X-Org-Id header.
Global settings (no org) are used for shared config like API keys.
"""

import json
import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from database import get_data_layer
from services.data_layer import DataLayer

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Default settings structure
DEFAULTS = {
    # API Keys (typically global, but can be per-org)
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
    # Voice profile — core
    "voice_persona": "",
    "voice_audience": "",
    "voice_tone": "",
    "voice_never_say": '[]',
    "voice_always": "",
    "voice_brand_keywords": '[]',
    "voice_writing_examples": "",
    "voice_bio": "",
    # Voice profile — per-channel overrides
    "voice_linkedin_style": "",
    "voice_x_style": "",
    "voice_blog_style": "",
    "voice_email_style": "",
    "voice_newsletter_style": "",
    "voice_yt_style": "",
    # Engine
    "claude_model": "claude-sonnet-4-6",
    "claude_model_fast": "claude-haiku-4-5-20251001",
    # Social OAuth (app credentials — typically global)
    "linkedin_client_id": "",
    "linkedin_client_secret": "",
    "facebook_app_id": "",
    "facebook_app_secret": "",
    # Social OAuth (per-org tokens — set by OAuth callback)
    "linkedin_access_token": "",
    "linkedin_author_urn": "",
    "linkedin_profile_name": "",
    "facebook_page_token": "",
    "facebook_page_id": "",
    "facebook_page_name": "",
    # Webhook
    "github_webhook_secret": "",
    # Onboarding metadata
    "onboard_company_name": "",
    "onboard_industry": "",
    "onboard_topics": "[]",
    "onboard_competitors": "[]",
    "onboard_complete": "",
    "df_service_map": "",
}

# Account-level keys — shared across all companies, saved with org_id=NULL
ACCOUNT_KEYS = {
    "anthropic_api_key", "github_token",
    "df_base_url", "df_api_key",
    "claude_model", "claude_model_fast",
    "linkedin_client_id", "linkedin_client_secret",
    "facebook_app_id", "facebook_app_secret",
    "github_webhook_secret",
}

# Keys that should be masked in GET responses
SENSITIVE_KEYS = {
    "anthropic_api_key", "github_token", "df_api_key", "github_webhook_secret",
    "linkedin_client_secret", "facebook_app_secret",
    "linkedin_access_token", "facebook_page_token",
}


def _mask(key: str, value: str) -> str:
    if key in SENSITIVE_KEYS and value:
        return value[:8] + "..." if len(value) > 8 else "***"
    return value


class SettingsUpdate(BaseModel):
    settings: dict[str, str]


@router.get("")
async def get_settings(dl: DataLayer = Depends(get_data_layer)):
    """Get all settings (sensitive values masked). Merges account + org settings."""
    stored = await dl.get_all_settings()

    merged = {}
    for key, default in DEFAULTS.items():
        raw = stored.get(key, default)
        merged[key] = {
            "value": _mask(key, raw),
            "is_set": bool(raw and raw != default),
            "sensitive": key in SENSITIVE_KEYS,
            "scope": "account" if key in ACCOUNT_KEYS else "company",
        }
    return merged


@router.get("/raw/{key}")
async def get_setting_raw(key: str, dl: DataLayer = Depends(get_data_layer)):
    """Get a single setting value (unmasked). Use sparingly."""
    value = await dl.get_setting(key)
    return {"key": key, "value": value or DEFAULTS.get(key, "")}


@router.put("")
async def update_settings(req: SettingsUpdate, dl: DataLayer = Depends(get_data_layer)):
    """Update one or more settings. Account keys route to org_id=NULL, company keys to current org."""
    updated = []
    for key, value in req.settings.items():
        if key not in DEFAULTS:
            continue
        if key in ACCOUNT_KEYS:
            await dl.set_account_setting(key, value)
        else:
            await dl.set_setting(key, value)
        updated.append(key)

    await dl.commit()

    # Reload runtime config from DB
    await _sync_to_runtime(dl)

    return {"updated": updated}


@router.get("/status")
async def connection_status(dl: DataLayer = Depends(get_data_layer)):
    """Check connection status for all configured services. Uses merged account + org settings."""
    stored = await dl.get_all_settings()

    status = {}

    # Anthropic
    api_key = stored.get("anthropic_api_key", "")
    status["anthropic"] = {
        "configured": bool(api_key),
        "model": stored.get("claude_model", DEFAULTS["claude_model"]),
    }

    # GitHub
    gh_token = stored.get("github_token", "")
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
    df_url = stored.get("df_base_url", DEFAULTS["df_base_url"])
    df_key = stored.get("df_api_key", "")
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
    repos = json.loads(stored.get("scout_github_repos", DEFAULTS["scout_github_repos"]))
    hn_kw = json.loads(stored.get("scout_hn_keywords", DEFAULTS["scout_hn_keywords"]))
    subs = json.loads(stored.get("scout_subreddits", DEFAULTS["scout_subreddits"]))
    rss = json.loads(stored.get("scout_rss_feeds", DEFAULTS["scout_rss_feeds"]))
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


async def _sync_to_runtime(dl: DataLayer):
    """Push account-level DB settings into the runtime config object."""
    from config import settings as cfg
    stored = await dl.get_account_settings()

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
    if stored.get("claude_model_fast"):
        cfg.claude_model_fast = stored["claude_model_fast"]
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
