"""Scheduler — background loop that publishes content when scheduled_at is due.

Simple asyncio loop, checks every 60 seconds. No external scheduling library needed.
All times are UTC.
"""

import asyncio
import datetime
import logging

from sqlalchemy import text

from database import async_session
from services.data_layer import DataLayer
from services.publisher import publish_single

log = logging.getLogger("pressroom")


async def check_scheduled_content():
    """Check for content that's due to be published and publish it."""
    async with async_session() as session:
        # Find all approved content where scheduled_at has passed
        result = await session.execute(text(
            "SELECT id, org_id FROM content "
            "WHERE status = 'approved' AND scheduled_at IS NOT NULL AND scheduled_at <= :now"
        ), {"now": datetime.datetime.utcnow().isoformat()})
        rows = result.fetchall()

        for row in rows:
            content_id, org_id = row
            try:
                org_dl = DataLayer(session, org_id=org_id)
                content = await org_dl.get_content(content_id)
                if not content:
                    continue
                settings = await org_dl.get_all_settings()
                pub_result = await publish_single(content, settings)
                if pub_result.get("success") or pub_result.get("status") == "no_destination":
                    await org_dl.update_content_status(content_id, "published")
                    log.info("SCHEDULER — published content #%s (org=%s)", content_id, org_id)
                await org_dl.commit()
            except Exception as e:
                log.error("SCHEDULER — failed to publish #%s: %s", content_id, e)


async def scheduler_loop():
    """Run the scheduler check every 60 seconds."""
    while True:
        try:
            await check_scheduled_content()
        except Exception as e:
            log.error("SCHEDULER ERROR: %s", e)
        await asyncio.sleep(60)
