"""Publisher — Post approved content to destinations via DreamFactory/df-social."""

import httpx
import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config import settings
from models import Content, ContentStatus, ContentChannel


class DFSocialPublisher:
    """Posts content through DreamFactory's df-social service endpoints."""

    def __init__(self, df_base_url: str = "http://localhost:8080", api_key: str = ""):
        self.df_base_url = df_base_url.rstrip("/")
        self.api_key = api_key

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["X-DreamFactory-Api-Key"] = self.api_key
        return h

    async def publish_to_linkedin(self, text: str, visibility: str = "PUBLIC") -> dict:
        """Post to LinkedIn via DF df-social endpoint."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.df_base_url}/api/v2/linkedin/posts",
                headers=self._headers(),
                json={"text": text, "visibility": visibility, "author_type": "person"},
            )
            resp.raise_for_status()
            return resp.json()

    async def publish_to_facebook(self, message: str, link: str | None = None) -> dict:
        """Post to Facebook page via DF df-social endpoint."""
        payload = {"message": message}
        if link:
            payload["link"] = link
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.df_base_url}/api/v2/facebook/posts",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    async def publish(self, content: Content) -> dict:
        """Route content to the right destination based on channel."""
        channel = content.channel

        if channel == ContentChannel.linkedin:
            return await self.publish_to_linkedin(content.body)
        elif channel == ContentChannel.facebook:
            return await self.publish_to_facebook(content.body)
        else:
            # Channels without live posting yet — mark as published anyway for demo
            return {"status": "no_destination", "channel": channel.value, "note": "No live publisher configured for this channel"}


async def publish_approved(db: AsyncSession, publisher: DFSocialPublisher | None = None) -> list[dict]:
    """Publish all approved content that hasn't been published yet."""
    if publisher is None:
        publisher = DFSocialPublisher(
            df_base_url=getattr(settings, "df_base_url", "http://localhost:8080"),
            api_key=getattr(settings, "df_api_key", ""),
        )

    result = await db.execute(
        select(Content).where(
            Content.status == ContentStatus.approved,
            Content.published_at.is_(None),
        )
    )
    items = result.scalars().all()
    results = []

    for content in items:
        try:
            pub_result = await publisher.publish(content)
            content.status = ContentStatus.published
            content.published_at = datetime.datetime.utcnow()
            results.append({"id": content.id, "channel": content.channel.value, "result": pub_result})
        except Exception as e:
            results.append({"id": content.id, "channel": content.channel.value, "error": str(e)})

    await db.commit()
    return results
