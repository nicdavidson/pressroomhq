"""HubSpot API client — blog CMS + CRM contact access via private app tokens."""

import logging
from typing import Any

import httpx

log = logging.getLogger("pressroom.hubspot")

HUBSPOT_API_BASE = "https://api.hubapi.com"


class HubSpotError(Exception):
    """Raised when HubSpot returns a non-success response."""

    def __init__(self, status_code: int, message: str, category: str = ""):
        self.status_code = status_code
        self.message = message
        self.category = category
        super().__init__(f"HubSpot {status_code}: {message}")


class HubSpotClient:
    """Async HubSpot API client using a private app access token."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated request to HubSpot, handling rate limits and errors."""
        url = f"{HUBSPOT_API_BASE}{path}"
        retries = 0
        max_retries = 2

        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                resp = await client.request(
                    method,
                    url,
                    headers=self._headers,
                    params=params,
                    json=json_body,
                )

                # Rate limit — back off and retry once
                if resp.status_code == 429 and retries < max_retries:
                    import asyncio
                    retry_after = int(resp.headers.get("Retry-After", "2"))
                    log.warning("HubSpot rate limited, retrying in %ds", retry_after)
                    await asyncio.sleep(retry_after)
                    retries += 1
                    continue

                if resp.status_code >= 400:
                    body = {}
                    try:
                        body = resp.json()
                    except Exception:
                        pass
                    raise HubSpotError(
                        status_code=resp.status_code,
                        message=body.get("message", resp.text[:200]),
                        category=body.get("category", ""),
                    )

                if resp.status_code == 204:
                    return {}
                return resp.json()

    # ──────────────────────────────────────
    # Blog Posts (CMS)
    # ──────────────────────────────────────

    async def list_blog_posts(self, limit: int = 50) -> list[dict]:
        """List recent blog posts from HubSpot CMS."""
        data = await self._request(
            "GET",
            "/cms/v3/blogs/posts",
            params={"limit": min(limit, 100), "sort": "-updated"},
        )
        results = data.get("results", [])
        return [
            {
                "id": p["id"],
                "title": p.get("name", p.get("htmlTitle", "")),
                "slug": p.get("slug", ""),
                "state": p.get("state", ""),
                "url": p.get("url", ""),
                "created": p.get("created", ""),
                "updated": p.get("updated", ""),
                "author_name": p.get("authorName", ""),
                "meta_description": p.get("metaDescription", ""),
            }
            for p in results
        ]

    async def get_blog_post(self, post_id: str) -> dict:
        """Get a single blog post by ID, including body content."""
        p = await self._request("GET", f"/cms/v3/blogs/posts/{post_id}")
        return {
            "id": p["id"],
            "title": p.get("name", p.get("htmlTitle", "")),
            "slug": p.get("slug", ""),
            "state": p.get("state", ""),
            "url": p.get("url", ""),
            "body": p.get("postBody", ""),
            "meta_description": p.get("metaDescription", ""),
            "author_name": p.get("authorName", ""),
            "created": p.get("created", ""),
            "updated": p.get("updated", ""),
        }

    async def create_blog_draft(
        self, title: str, body: str, slug: str = ""
    ) -> dict:
        """Create a new blog post as a DRAFT in HubSpot CMS."""
        payload: dict[str, Any] = {
            "name": title,
            "postBody": body,
            "state": "DRAFT",
        }
        if slug:
            payload["slug"] = slug

        result = await self._request("POST", "/cms/v3/blogs/posts", json_body=payload)
        return {
            "id": result.get("id"),
            "title": result.get("name", ""),
            "slug": result.get("slug", ""),
            "state": result.get("state", ""),
            "url": result.get("url", ""),
        }

    async def update_blog_post(self, post_id: str, updates: dict) -> dict:
        """Update an existing blog post (PATCH)."""
        result = await self._request(
            "PATCH", f"/cms/v3/blogs/posts/{post_id}", json_body=updates
        )
        return {
            "id": result.get("id"),
            "title": result.get("name", ""),
            "slug": result.get("slug", ""),
            "state": result.get("state", ""),
            "url": result.get("url", ""),
        }

    # ──────────────────────────────────────
    # Contacts (CRM)
    # ──────────────────────────────────────

    async def list_contacts(self, limit: int = 100) -> list[dict]:
        """List CRM contacts (for future email sending)."""
        data = await self._request(
            "GET",
            "/crm/v3/objects/contacts",
            params={
                "limit": min(limit, 100),
                "properties": "firstname,lastname,email,company",
            },
        )
        results = data.get("results", [])
        return [
            {
                "id": c["id"],
                "firstname": c.get("properties", {}).get("firstname", ""),
                "lastname": c.get("properties", {}).get("lastname", ""),
                "email": c.get("properties", {}).get("email", ""),
                "company": c.get("properties", {}).get("company", ""),
            }
            for c in results
        ]

    # ──────────────────────────────────────
    # Connection test
    # ──────────────────────────────────────

    async def test_connection(self) -> dict:
        """Verify the token works by hitting the account info endpoint."""
        try:
            data = await self._request("GET", "/integrations/v1/me")
            return {
                "connected": True,
                "portal_id": data.get("portalId"),
                "hub_domain": data.get("hubDomain", ""),
            }
        except HubSpotError as e:
            return {"connected": False, "error": str(e)}
        except Exception as e:
            return {"connected": False, "error": str(e)}
