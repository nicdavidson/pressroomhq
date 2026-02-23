"""Data layer — routes to DF when available, falls back to local SQLite.

This is the abstraction that lets Pressroom work standalone (SQLite) or
with DreamFactory as the backend. The API endpoints don't care which.
"""

import datetime
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Signal, Brief, Content, Setting, SignalType, ContentChannel, ContentStatus
from services.df_client import df


# DF database service name for pressroom tables
DF_DB_SERVICE = "pressroom_db"


class DataLayer:
    """Unified data access — checks DF first, falls back to SQLite."""

    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self._use_df = None  # lazy check

    async def _should_use_df(self) -> bool:
        """Check once per request if DF is available and has our DB service."""
        if self._use_df is not None:
            return self._use_df
        if not df.available:
            self._use_df = False
            return False
        try:
            health = await df.health_check()
            self._use_df = health.get("connected", False)
        except Exception:
            self._use_df = False
        return self._use_df

    # ──────────────────────────────────────
    # Signals
    # ──────────────────────────────────────

    async def save_signal(self, data: dict) -> dict:
        if await self._should_use_df():
            records = await df.db_create(DF_DB_SERVICE, "pressroom_signals", [{
                "type": data["type"] if isinstance(data["type"], str) else data["type"].value,
                "source": data["source"],
                "title": data["title"],
                "body": data.get("body", ""),
                "url": data.get("url", ""),
                "raw_data": data.get("raw_data", ""),
                "created_at": datetime.datetime.utcnow().isoformat(),
            }])
            return records[0] if records else {}

        signal = Signal(
            type=data["type"] if isinstance(data["type"], SignalType) else SignalType(data["type"]),
            source=data["source"],
            title=data["title"],
            body=data.get("body", ""),
            url=data.get("url", ""),
            raw_data=data.get("raw_data", ""),
        )
        self.db.add(signal)
        await self.db.flush()
        return {"id": signal.id, "type": signal.type.value, "source": signal.source,
                "title": signal.title, "body": signal.body}

    async def get_signal(self, signal_id: int) -> dict | None:
        if await self._should_use_df():
            try:
                return await df.db_get(DF_DB_SERVICE, "pressroom_signals", signal_id)
            except Exception:
                return None

        result = await self.db.execute(select(Signal).where(Signal.id == signal_id))
        s = result.scalar_one_or_none()
        if not s:
            return None
        return {"id": s.id, "type": s.type.value, "source": s.source, "title": s.title,
                "body": s.body, "url": s.url, "created_at": s.created_at.isoformat() if s.created_at else None}

    async def list_signals(self, limit: int = 30) -> list[dict]:
        if await self._should_use_df():
            return await df.db_query(DF_DB_SERVICE, "pressroom_signals",
                                     order="created_at DESC", limit=limit)

        result = await self.db.execute(select(Signal).order_by(Signal.created_at.desc()).limit(limit))
        return [{"id": s.id, "type": s.type.value, "source": s.source, "title": s.title,
                 "body": s.body, "url": s.url, "created_at": s.created_at.isoformat() if s.created_at else None}
                for s in result.scalars().all()]

    # ──────────────────────────────────────
    # Briefs
    # ──────────────────────────────────────

    async def save_brief(self, data: dict) -> dict:
        if await self._should_use_df():
            records = await df.db_create(DF_DB_SERVICE, "pressroom_briefs", [{
                "date": data["date"],
                "summary": data["summary"],
                "angle": data.get("angle", ""),
                "signal_ids": data.get("signal_ids", ""),
                "created_at": datetime.datetime.utcnow().isoformat(),
            }])
            return records[0] if records else {}

        brief = Brief(
            date=data["date"],
            summary=data["summary"],
            angle=data.get("angle", ""),
            signal_ids=data.get("signal_ids", ""),
        )
        self.db.add(brief)
        await self.db.flush()
        return {"id": brief.id, "date": brief.date, "summary": brief.summary, "angle": brief.angle}

    # ──────────────────────────────────────
    # Content
    # ──────────────────────────────────────

    async def save_content(self, data: dict) -> dict:
        if await self._should_use_df():
            records = await df.db_create(DF_DB_SERVICE, "pressroom_content", [{
                "signal_id": data.get("signal_id"),
                "brief_id": data.get("brief_id"),
                "channel": data["channel"] if isinstance(data["channel"], str) else data["channel"].value,
                "status": data.get("status", "queued"),
                "headline": data.get("headline", ""),
                "body": data["body"],
                "body_raw": data.get("body_raw", ""),
                "author": data.get("author", "company"),
                "created_at": datetime.datetime.utcnow().isoformat(),
            }])
            return records[0] if records else {}

        content = Content(
            signal_id=data.get("signal_id"),
            brief_id=data.get("brief_id"),
            channel=data["channel"] if isinstance(data["channel"], ContentChannel) else ContentChannel(data["channel"]),
            status=ContentStatus(data.get("status", "queued")),
            headline=data.get("headline", ""),
            body=data["body"],
            body_raw=data.get("body_raw", ""),
            author=data.get("author", "company"),
        )
        self.db.add(content)
        await self.db.flush()
        return {"id": content.id, "channel": content.channel.value, "headline": content.headline,
                "status": content.status.value}

    async def list_content(self, status: str | None = None, limit: int = 50) -> list[dict]:
        if await self._should_use_df():
            filter_str = f"status = '{status}'" if status else None
            return await df.db_query(DF_DB_SERVICE, "pressroom_content",
                                     filter_str=filter_str, order="created_at DESC", limit=limit)

        query = select(Content).order_by(Content.created_at.desc()).limit(limit)
        if status:
            query = query.where(Content.status == ContentStatus(status))
        result = await self.db.execute(query)
        return [_serialize_content(c) for c in result.scalars().all()]

    async def get_content(self, content_id: int) -> dict | None:
        if await self._should_use_df():
            try:
                return await df.db_get(DF_DB_SERVICE, "pressroom_content", content_id)
            except Exception:
                return None

        result = await self.db.execute(select(Content).where(Content.id == content_id))
        c = result.scalar_one_or_none()
        return _serialize_content(c) if c else None

    async def update_content_status(self, content_id: int, status: str, **extra) -> dict:
        if await self._should_use_df():
            update = {"id": content_id, "status": status}
            if status == "approved":
                update["approved_at"] = datetime.datetime.utcnow().isoformat()
            if status == "published":
                update["published_at"] = datetime.datetime.utcnow().isoformat()
            update.update(extra)
            records = await df.db_update(DF_DB_SERVICE, "pressroom_content", [update])
            return records[0] if records else {}

        result = await self.db.execute(select(Content).where(Content.id == content_id))
        c = result.scalar_one_or_none()
        if not c:
            return {}
        c.status = ContentStatus(status)
        if status == "approved":
            c.approved_at = datetime.datetime.utcnow()
        if status == "published":
            c.published_at = datetime.datetime.utcnow()
        await self.db.flush()
        return _serialize_content(c)

    async def get_approved_unpublished(self) -> list[dict]:
        if await self._should_use_df():
            return await df.db_query(
                DF_DB_SERVICE, "pressroom_content",
                filter_str="status = 'approved' AND published_at IS NULL",
                order="created_at DESC",
            )

        result = await self.db.execute(
            select(Content).where(Content.status == ContentStatus.approved, Content.published_at.is_(None))
        )
        return [_serialize_content(c) for c in result.scalars().all()]

    # ──────────────────────────────────────
    # Memory queries (for the engine flywheel)
    # ──────────────────────────────────────

    async def get_approved_by_channel(self, channel: str, limit: int = 5) -> list[dict]:
        """Get recent approved content for a channel — few-shot examples for the engine."""
        if await self._should_use_df():
            return await df.db_query(
                DF_DB_SERVICE, "pressroom_content",
                filter_str=f"channel = '{channel}' AND status = 'approved'",
                order="approved_at DESC", limit=limit,
            )

        result = await self.db.execute(
            select(Content)
            .where(Content.channel == ContentChannel(channel), Content.status == ContentStatus.approved)
            .order_by(Content.approved_at.desc()).limit(limit)
        )
        return [_serialize_content(c) for c in result.scalars().all()]

    async def get_spiked_by_channel(self, channel: str, limit: int = 5) -> list[dict]:
        """Get recently spiked content — what NOT to generate."""
        if await self._should_use_df():
            return await df.db_query(
                DF_DB_SERVICE, "pressroom_content",
                filter_str=f"channel = '{channel}' AND status = 'spiked'",
                order="created_at DESC", limit=limit,
            )

        result = await self.db.execute(
            select(Content)
            .where(Content.channel == ContentChannel(channel), Content.status == ContentStatus.spiked)
            .order_by(Content.created_at.desc()).limit(limit)
        )
        return [_serialize_content(c) for c in result.scalars().all()]

    async def get_recent_topics(self, days: int = 21) -> list[dict]:
        """What angles/headlines have been covered recently — topic fatigue check."""
        cutoff = (datetime.datetime.utcnow() - datetime.timedelta(days=days)).isoformat()
        if await self._should_use_df():
            return await df.db_query(
                DF_DB_SERVICE, "pressroom_content",
                filter_str=f"created_at > '{cutoff}'",
                order="created_at DESC", limit=100,
            )

        cutoff_dt = datetime.datetime.utcnow() - datetime.timedelta(days=days)
        result = await self.db.execute(
            select(Content).where(Content.created_at > cutoff_dt).order_by(Content.created_at.desc()).limit(100)
        )
        return [{"headline": c.headline, "channel": c.channel.value, "status": c.status.value}
                for c in result.scalars().all()]

    # ──────────────────────────────────────
    # Aggregated memory context for generation
    # ──────────────────────────────────────

    async def get_memory_context(self) -> dict:
        """Gather the full memory context for the engine — approved examples,
        spiked anti-patterns, recent topics per channel. This is the flywheel."""
        channels = ["linkedin", "x_thread", "blog", "release_email", "newsletter"]
        memory = {"approved": {}, "spiked": {}, "recent_topics": []}
        for ch in channels:
            memory["approved"][ch] = await self.get_approved_by_channel(ch, limit=3)
            memory["spiked"][ch] = await self.get_spiked_by_channel(ch, limit=3)
        memory["recent_topics"] = await self.get_recent_topics(days=21)
        return memory

    async def commit(self):
        await self.db.commit()


def _serialize_content(c: Content) -> dict:
    return {
        "id": c.id, "signal_id": c.signal_id, "brief_id": c.brief_id,
        "channel": c.channel.value, "status": c.status.value,
        "headline": c.headline, "body": c.body, "body_raw": c.body_raw,
        "author": c.author,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "approved_at": c.approved_at.isoformat() if c.approved_at else None,
        "published_at": c.published_at.isoformat() if c.published_at else None,
    }
