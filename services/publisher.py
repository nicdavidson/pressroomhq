"""Publisher — Post approved content directly via social OAuth tokens.

Pressroom owns the OAuth tokens per-org. No DreamFactory needed for publishing.
Each org connects their social accounts, and we post directly via platform APIs.
"""

import logging
from services import social_auth
from services.data_layer import DataLayer

log = logging.getLogger("pressroom")

# Channels that support direct publishing
DIRECT_CHANNELS = {"linkedin", "facebook"}


async def publish_single(content: dict, settings: dict) -> dict:
    """Post a single content item using stored OAuth tokens."""
    channel = content.get("channel", "")
    text = content.get("body", "")

    if channel == "linkedin":
        token = settings.get("linkedin_access_token", "")
        author = settings.get("linkedin_author_urn", "")
        if not token or not author:
            return {"error": "LinkedIn not connected — authorize in Connections"}
        return await social_auth.linkedin_post(token, author, text)

    elif channel == "facebook":
        page_token = settings.get("facebook_page_token", "")
        page_id = settings.get("facebook_page_id", "")
        if not page_token or not page_id:
            return {"error": "Facebook not connected — authorize in Connections"}
        return await social_auth.facebook_post(page_token, page_id, text)

    else:
        return {"status": "no_destination", "note": f"No publisher for channel: {channel}"}


async def publish_approved(dl: DataLayer) -> list[dict]:
    """Publish all approved content that hasn't been published yet."""
    items = await dl.get_approved_unpublished()
    if not items:
        return []

    # Load org settings once for all items
    settings = await dl.get_all_settings()

    results = []
    for content in items:
        channel = content.get("channel", "")
        content_id = content.get("id")

        if channel in DIRECT_CHANNELS:
            try:
                pub_result = await publish_single(content, settings)
                if pub_result.get("success"):
                    await dl.update_content_status(content_id, "published")
                    log.info("Published %s content #%s", channel, content_id)
                results.append({"id": content_id, "channel": channel, "result": pub_result})
            except Exception as e:
                log.error("Publish failed for %s #%s: %s", channel, content_id, e)
                results.append({"id": content_id, "channel": channel, "error": str(e)})
        else:
            # No live publisher for this channel — mark published for demo
            await dl.update_content_status(content_id, "published")
            results.append({
                "id": content_id, "channel": channel,
                "result": {"status": "no_destination", "note": f"No direct publisher for {channel}"},
            })

    await dl.commit()
    return results
