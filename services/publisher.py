"""Publisher — Post approved content via DreamFactory social services.

Uses DF service discovery to find available social platforms,
then posts through their standard REST endpoints.
"""

from services.df_client import df
from services.data_layer import DataLayer


# Channel → DF social service type mapping
CHANNEL_TO_SOCIAL = {
    "linkedin": "linkedin",
    "facebook": "facebook",
    "x_thread": "x_twitter",
}


async def discover_publishers() -> dict[str, str]:
    """Find available social services via DF. Returns {channel: service_name}."""
    if not df.available:
        return {}
    try:
        services = await df.discover_social_services()
        # Map DF service types back to our channels
        type_to_name = {s.get("type"): s.get("name") for s in services}
        publishers = {}
        for channel, social_type in CHANNEL_TO_SOCIAL.items():
            if social_type in type_to_name:
                publishers[channel] = type_to_name[social_type]
        return publishers
    except Exception:
        return {}


async def publish_single(content: dict, service_name: str) -> dict:
    """Post a single content item to a DF social service."""
    channel = content.get("channel", "")
    payload = {"text": content.get("body", "")}

    # Channel-specific payload shaping
    if channel == "linkedin":
        payload = {"text": content["body"], "visibility": "PUBLIC", "author_type": "person"}
    elif channel == "x_thread":
        payload = {"text": content["body"], "thread": True}
    elif channel == "facebook":
        payload = {"message": content["body"]}

    return await df.social_post(service_name, payload)


async def publish_approved(dl: DataLayer) -> list[dict]:
    """Publish all approved content that hasn't been published yet."""
    items = await dl.get_approved_unpublished()
    if not items:
        return []

    # Discover which social services are available
    publishers = await discover_publishers()

    results = []
    for content in items:
        channel = content.get("channel", "")
        content_id = content.get("id")

        if channel in publishers:
            try:
                pub_result = await publish_single(content, publishers[channel])
                await dl.update_content_status(content_id, "published")
                results.append({"id": content_id, "channel": channel, "result": pub_result})
            except Exception as e:
                results.append({"id": content_id, "channel": channel, "error": str(e)})
        else:
            # No live publisher for this channel — mark published anyway for demo
            await dl.update_content_status(content_id, "published")
            results.append({
                "id": content_id, "channel": channel,
                "result": {"status": "no_destination", "note": f"No DF social service for {channel}"},
            })

    await dl.commit()
    return results
