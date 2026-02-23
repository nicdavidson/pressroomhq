"""DreamFactory REST client — all data goes through DF."""

import httpx
from typing import Any

from config import settings


class DFClient:
    """Talks to DreamFactory's REST API for database CRUD, service discovery, and social posting."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or settings.df_base_url).rstrip("/")
        self.api_key = api_key or settings.df_api_key

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            h["X-DreamFactory-Api-Key"] = self.api_key
        return h

    @property
    def available(self) -> bool:
        return bool(self.base_url and self.api_key)

    # ──────────────────────────────────────
    # Generic REST helpers
    # ──────────────────────────────────────

    async def get(self, path: str, params: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{self.base_url}{path}", headers=self._headers(), params=params)
            r.raise_for_status()
            return r.json()

    async def post(self, path: str, data: Any = None) -> dict:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{self.base_url}{path}", headers=self._headers(), json=data)
            r.raise_for_status()
            return r.json()

    async def put(self, path: str, data: Any = None) -> dict:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.put(f"{self.base_url}{path}", headers=self._headers(), json=data)
            r.raise_for_status()
            return r.json()

    async def delete(self, path: str, params: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.delete(f"{self.base_url}{path}", headers=self._headers(), params=params)
            r.raise_for_status()
            return r.json()

    # ──────────────────────────────────────
    # Service discovery
    # ──────────────────────────────────────

    async def list_services(self) -> list[dict]:
        """Get all services registered in DF."""
        data = await self.get("/api/v2/system/service")
        return data.get("resource", [])

    async def get_service(self, name: str) -> dict:
        """Get details about a specific service."""
        return await self.get(f"/api/v2/system/service/{name}")

    async def discover_social_services(self) -> list[dict]:
        """Find all df-social services (LinkedIn, Facebook, etc.)."""
        services = await self.list_services()
        social_types = {"linkedin", "facebook", "x_twitter", "youtube", "tiktok"}
        return [s for s in services if s.get("type") in social_types]

    async def discover_db_services(self) -> list[dict]:
        """Find all database services."""
        services = await self.list_services()
        db_types = {"mysql", "pgsql", "sqlite", "sqlsrv", "mongodb"}
        return [s for s in services if s.get("type") in db_types]

    # ──────────────────────────────────────
    # Database CRUD (content ledger)
    # ──────────────────────────────────────

    async def db_list(self, service: str, table: str, params: dict | None = None) -> list[dict]:
        """GET /api/v2/{service}/_table/{table}"""
        data = await self.get(f"/api/v2/{service}/_table/{table}", params=params)
        return data.get("resource", [])

    async def db_get(self, service: str, table: str, record_id: int) -> dict:
        """GET /api/v2/{service}/_table/{table}/{id}"""
        return await self.get(f"/api/v2/{service}/_table/{table}/{record_id}")

    async def db_create(self, service: str, table: str, records: list[dict]) -> list[dict]:
        """POST /api/v2/{service}/_table/{table}"""
        data = await self.post(f"/api/v2/{service}/_table/{table}", {"resource": records})
        return data.get("resource", [])

    async def db_update(self, service: str, table: str, records: list[dict]) -> list[dict]:
        """PUT /api/v2/{service}/_table/{table}"""
        data = await self.put(f"/api/v2/{service}/_table/{table}", {"resource": records})
        return data.get("resource", [])

    async def db_delete(self, service: str, table: str, record_id: int) -> dict:
        """DELETE /api/v2/{service}/_table/{table}/{id}"""
        return await self.delete(f"/api/v2/{service}/_table/{table}/{record_id}")

    async def db_query(self, service: str, table: str, filter_str: str | None = None,
                       order: str | None = None, limit: int = 50) -> list[dict]:
        """Query with DF filter syntax."""
        params = {"limit": limit}
        if filter_str:
            params["filter"] = filter_str
        if order:
            params["order"] = order
        return await self.db_list(service, table, params)

    # ──────────────────────────────────────
    # Social posting (via df-social)
    # ──────────────────────────────────────

    async def social_post(self, service_name: str, payload: dict) -> dict:
        """POST /api/v2/{service}/posts — create a social post."""
        return await self.post(f"/api/v2/{service_name}/posts", payload)

    async def social_auth_status(self, service_name: str) -> dict:
        """GET /api/v2/{service}/auth/status — check OAuth status."""
        return await self.get(f"/api/v2/{service_name}/auth/status")

    async def social_auth_url(self, service_name: str) -> dict:
        """GET /api/v2/{service}/auth/url — get OAuth authorization URL."""
        return await self.get(f"/api/v2/{service_name}/auth/url")

    # ──────────────────────────────────────
    # Health / connection test
    # ──────────────────────────────────────

    async def health_check(self) -> dict:
        """Check if DF is reachable and the API key works."""
        try:
            env = await self.get("/api/v2/system/environment")
            return {
                "connected": True,
                "platform": env.get("platform", {}),
                "server": env.get("server", {}),
            }
        except Exception as e:
            return {"connected": False, "error": str(e)}


# Singleton — use this everywhere
df = DFClient()
