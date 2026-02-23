"""Data Sources — CRUD for external data connections.

Users add named connections like "Intercom Data" or "HubSpot DB" with a
category and connection details. These feed intelligence into the content engine.
"""

import json
import logging
import httpx
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy import select

from database import async_session
from models import DataSource

log = logging.getLogger("pressroom")

router = APIRouter(prefix="/api/datasources", tags=["datasources"])


class DataSourceCreate(BaseModel):
    name: str
    description: str = ""
    category: str = "database"          # database, crm, analytics, support, custom
    connection_type: str = "mcp"  # mcp, rest_api
    base_url: str = ""
    api_key: str = ""
    config: str = "{}"


class DataSourceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    config: str | None = None


def _serialize(ds: DataSource) -> dict:
    return {
        "id": ds.id,
        "org_id": ds.org_id,
        "name": ds.name,
        "description": ds.description,
        "category": ds.category,
        "connection_type": ds.connection_type,
        "base_url": ds.base_url,
        "api_key_set": bool(ds.api_key),
        "config": ds.config,
        "created_at": ds.created_at.isoformat() if ds.created_at else None,
    }


@router.get("")
async def list_datasources(x_org_id: int | None = Header(default=None)):
    """List all data sources for this org."""
    async with async_session() as session:
        query = select(DataSource).order_by(DataSource.created_at.desc())
        if x_org_id:
            query = query.where(DataSource.org_id == x_org_id)
        result = await session.execute(query)
        return [_serialize(ds) for ds in result.scalars().all()]


@router.post("")
async def create_datasource(req: DataSourceCreate, x_org_id: int | None = Header(default=None)):
    """Add a new data source."""
    async with async_session() as session:
        ds = DataSource(
            org_id=x_org_id,
            name=req.name,
            description=req.description,
            category=req.category,
            connection_type=req.connection_type,
            base_url=req.base_url,
            api_key=req.api_key,
            config=req.config,
        )
        session.add(ds)
        await session.commit()
        await session.refresh(ds)
        log.info("Created data source '%s' (org=%s, type=%s)", req.name, x_org_id, req.connection_type)
        return _serialize(ds)


@router.put("/{ds_id}")
async def update_datasource(ds_id: int, req: DataSourceUpdate,
                            x_org_id: int | None = Header(default=None)):
    """Update a data source."""
    async with async_session() as session:
        query = select(DataSource).where(DataSource.id == ds_id)
        if x_org_id:
            query = query.where(DataSource.org_id == x_org_id)
        result = await session.execute(query)
        ds = result.scalar_one_or_none()
        if not ds:
            return {"error": "Not found"}

        if req.name is not None:
            ds.name = req.name
        if req.description is not None:
            ds.description = req.description
        if req.category is not None:
            ds.category = req.category
        if req.base_url is not None:
            ds.base_url = req.base_url
        if req.api_key is not None:
            ds.api_key = req.api_key
        if req.config is not None:
            ds.config = req.config

        await session.commit()
        await session.refresh(ds)
        return _serialize(ds)


@router.delete("/{ds_id}")
async def delete_datasource(ds_id: int, x_org_id: int | None = Header(default=None)):
    """Remove a data source."""
    async with async_session() as session:
        query = select(DataSource).where(DataSource.id == ds_id)
        if x_org_id:
            query = query.where(DataSource.org_id == x_org_id)
        result = await session.execute(query)
        ds = result.scalar_one_or_none()
        if not ds:
            return {"error": "Not found"}

        name = ds.name
        await session.delete(ds)
        await session.commit()
        log.info("Deleted data source '%s' (id=%s)", name, ds_id)
        return {"deleted": ds_id}


@router.post("/{ds_id}/test")
async def test_datasource(ds_id: int, x_org_id: int | None = Header(default=None)):
    """Test connectivity to a data source."""
    async with async_session() as session:
        query = select(DataSource).where(DataSource.id == ds_id)
        if x_org_id:
            query = query.where(DataSource.org_id == x_org_id)
        result = await session.execute(query)
        ds = result.scalar_one_or_none()
        if not ds:
            return {"error": "Not found"}

        if ds.connection_type == "mcp":
            if not ds.base_url:
                return {"connected": False, "error": "Missing MCP server URL"}
            try:
                headers = {}
                if ds.api_key:
                    headers["X-DreamFactory-Api-Key"] = ds.api_key
                async with httpx.AsyncClient(timeout=10) as client:
                    # Try the MCP endpoint — a GET should return method info or SSE stream
                    resp = await client.get(ds.base_url.rstrip("/"), headers=headers)
                    if resp.status_code < 400:
                        return {"connected": True, "detail": f"MCP server responding (HTTP {resp.status_code})"}
                    return {"connected": False, "error": f"HTTP {resp.status_code}"}
            except Exception as e:
                return {"connected": False, "error": str(e)}

        elif ds.connection_type == "rest_api":
            if not ds.base_url:
                return {"connected": False, "error": "Missing base URL"}
            try:
                headers = {}
                if ds.api_key:
                    headers["Authorization"] = f"Bearer {ds.api_key}"
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(ds.base_url, headers=headers)
                    return {"connected": resp.status_code < 400, "status": resp.status_code}
            except Exception as e:
                return {"connected": False, "error": str(e)}

        return {"connected": False, "error": f"Unknown connection type: {ds.connection_type}"}
