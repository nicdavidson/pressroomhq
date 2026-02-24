"""Slack notification service — incoming webhooks, no OAuth required.

Posts content suggestions and pipeline summaries to a Slack channel
via Block Kit messages. War room comms, not marketing fluff.
"""

import logging

import httpx

logger = logging.getLogger(__name__)


async def send_to_slack(webhook_url: str, blocks: list) -> dict:
    """Low-level: POST blocks to a Slack incoming webhook.

    Returns {"success": True} on 200, {"error": "..."} otherwise.
    """
    if not webhook_url:
        return {"error": "No webhook URL configured"}

    payload = {"blocks": blocks}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.status_code == 200:
                return {"success": True}
            else:
                error_msg = f"Slack returned {resp.status_code}: {resp.text[:200]}"
                logger.warning(error_msg)
                return {"error": error_msg}
    except httpx.TimeoutException:
        return {"error": "Slack webhook timed out"}
    except Exception as e:
        logger.exception("Slack webhook failed")
        return {"error": str(e)}


async def send_content_suggestion(
    webhook_url: str, content: dict, team_member: dict = None
) -> dict:
    """Send a content suggestion to Slack -- tells the right person
    'hey, here's a draft for you'.

    content dict expects: headline, channel, body, id (optional)
    team_member dict expects: name (optional)
    """
    headline = content.get("headline", "Untitled")
    channel = content.get("channel", "unknown")
    body = content.get("body", "")
    content_id = content.get("id", "")
    preview = body[:200] + ("..." if len(body) > 200 else "")

    # Build the greeting
    if team_member and team_member.get("name"):
        greeting = f"Hey {team_member['name']}, this *{channel}* draft is ready for your review."
    else:
        greeting = f"A new *{channel}* draft is ready for review."

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "New content ready for review",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": greeting,
            },
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Headline:*\n{headline}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Channel:*\n{channel}",
                },
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Preview:*\n>{preview}",
            },
        },
        {"type": "divider"},
    ]

    # Add content ID reference if available
    if content_id:
        blocks.insert(-1, {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Content ID: {content_id} | Pressroom",
                },
            ],
        })

    return await send_to_slack(webhook_url, blocks)


async def send_pipeline_summary(webhook_url: str, results: dict) -> dict:
    """Send a pipeline run summary -- 'scout found X signals, generated Y pieces'.

    results dict expects: signals_count, content_count, channels (list of str)
    """
    signals_count = results.get("signals_count", 0)
    content_count = results.get("content_count", 0)
    channels = results.get("channels", [])

    channels_str = ", ".join(channels) if channels else "none"

    summary_text = (
        f"Scout picked up *{signals_count}* signal{'s' if signals_count != 1 else ''}. "
        f"Generated *{content_count}* piece{'s' if content_count != 1 else ''} "
        f"across: {channels_str}."
    )

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "Pipeline run complete",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": summary_text,
            },
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Signals:*\n{signals_count}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Content pieces:*\n{content_count}",
                },
            ],
        },
        {"type": "divider"},
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "Pressroom pipeline",
                },
            ],
        },
    ]

    return await send_to_slack(webhook_url, blocks)
