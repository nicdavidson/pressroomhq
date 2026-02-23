"""Content Engine — Claude-powered content generation from signals and briefs.

Uses:
- Voice settings from the DB (onboarding-configured or manually set)
- Memory context (approved examples, spiked anti-patterns, recent topics)
- DF intelligence (customer data, analytics, CRM data from connected services)
"""

import json
import anthropic
from config import settings
from models import ContentChannel


def _get_client():
    """Lazy client — picks up the API key at call time, not import time."""
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)

# Fallback voice if no settings configured
DEFAULT_VOICE = {
    "voice_persona": "A company sharing updates and insights with their audience.",
    "voice_audience": "Industry professionals and customers",
    "voice_tone": "Professional, clear, informative",
    "voice_never_say": '["excited to share", "game-changer", "leverage", "synergy"]',
    "voice_always": "Be specific, share real data, focus on value",
}

CHANNEL_RULES = {
    ContentChannel.linkedin: {
        "rules": """- 150-300 words max
- Hook in first line (pattern interrupt, bold claim, or question)
- No hashtags unless they're genuinely useful (max 3)
- End with a thought or question, not a CTA
- Write like a human sharing insight, not a marketer
- No bullet-point listicles unless the content genuinely demands it""",
        "headline_prefix": "LINKEDIN",
        "style_key": "voice_linkedin_style",
    },
    ContentChannel.x_thread: {
        "rules": """- 5-8 tweets
- Tweet 1 is the hook — must stand alone and stop the scroll
- Each tweet under 280 characters
- Number them 1/, 2/, etc.
- Last tweet: takeaway or link
- Conversational, not performative
- No "thread" opener""",
        "headline_prefix": "X THREAD",
        "style_key": "voice_x_style",
    },
    ContentChannel.blog: {
        "rules": """- 800-1500 words
- SEO-aware title (include primary keyword naturally)
- H2 subheadings every 200-300 words
- Technical depth — code snippets where relevant
- No fluff intro paragraphs. Start with the point.
- End with what's next, not a generic conclusion""",
        "headline_prefix": "BLOG DRAFT",
        "style_key": "voice_blog_style",
    },
    ContentChannel.release_email: {
        "rules": """- Subject line that gets opened (not clickbait, just clear value)
- 200-400 words
- What shipped, why it matters, how to use it
- One clear CTA
- Plain text feel, not HTML newsletter energy""",
        "headline_prefix": "RELEASE EMAIL",
        "style_key": "voice_email_style",
    },
    ContentChannel.newsletter: {
        "rules": """- 300-500 words
- "This week in [company]" format
- What shipped, what's coming, one community highlight
- Links to docs/blog where relevant
- Casual, informative, not salesy""",
        "headline_prefix": "NEWSLETTER",
        "style_key": "voice_newsletter_style",
    },
    ContentChannel.yt_script: {
        "rules": """- 2-4 minutes when read aloud (~300-600 words)
- Open with the hook (what you'll learn / why this matters)
- Conversational — written for speaking, not reading
- Include [B-ROLL: description] markers for visual cuts
- End with a clear next step""",
        "headline_prefix": "YT SCRIPT",
        "style_key": "voice_yt_style",
    },
}


def _build_voice_block(voice_settings: dict | None) -> str:
    """Build the voice profile section from DB settings."""
    v = voice_settings or DEFAULT_VOICE

    parts = []
    company = v.get("onboard_company_name", "")
    if company:
        parts.append(f"Company: {company}")
    industry = v.get("onboard_industry", "")
    if industry:
        parts.append(f"Industry: {industry}")
    parts.append(f"Voice: {v.get('voice_persona', DEFAULT_VOICE['voice_persona'])}")
    parts.append(f"Audience: {v.get('voice_audience', DEFAULT_VOICE['voice_audience'])}")
    parts.append(f"Tone: {v.get('voice_tone', DEFAULT_VOICE['voice_tone'])}")

    # Never say
    never_raw = v.get("voice_never_say", DEFAULT_VOICE["voice_never_say"])
    try:
        never_list = json.loads(never_raw) if isinstance(never_raw, str) else never_raw
        if never_list:
            parts.append(f"Never say: {', '.join(f'\"{w}\"' for w in never_list)}")
    except (json.JSONDecodeError, TypeError):
        pass

    parts.append(f"Always: {v.get('voice_always', DEFAULT_VOICE['voice_always'])}")

    # Brand keywords
    brand_raw = v.get("voice_brand_keywords", "")
    try:
        brand_list = json.loads(brand_raw) if isinstance(brand_raw, str) and brand_raw else []
        if brand_list:
            parts.append(f"Brand keywords (use naturally): {', '.join(brand_list)}")
    except (json.JSONDecodeError, TypeError):
        pass

    # Topics
    topics_raw = v.get("onboard_topics", "")
    try:
        topics = json.loads(topics_raw) if isinstance(topics_raw, str) and topics_raw else []
        if topics:
            parts.append(f"Key topics: {', '.join(topics)}")
    except (json.JSONDecodeError, TypeError):
        pass

    # Competitors
    comp_raw = v.get("onboard_competitors", "")
    try:
        comps = json.loads(comp_raw) if isinstance(comp_raw, str) and comp_raw else []
        if comps:
            parts.append(f"Competitors (differentiate from): {', '.join(comps)}")
    except (json.JSONDecodeError, TypeError):
        pass

    return "\n".join(parts)


def _build_system_prompt(channel: ContentChannel, voice_settings: dict | None) -> str:
    """Build the full system prompt for a channel using voice settings."""
    channel_config = CHANNEL_RULES.get(channel)
    if not channel_config:
        return "You are a content engine. Generate content."

    voice_block = _build_voice_block(voice_settings)

    # Get channel-specific style override
    v = voice_settings or {}
    style_key = channel_config.get("style_key", "")
    channel_style = v.get(style_key, "")
    style_line = f"\nChannel style: {channel_style}" if channel_style else ""

    # Writing examples
    examples = v.get("voice_writing_examples", "")
    examples_block = ""
    if examples and len(examples) > 20:
        examples_block = f"\n\nWRITING EXAMPLES (match this style):\n{examples[:2000]}"

    return f"""You are a content engine for Pressroom — an AI-powered content operations platform. Generate a {channel_config['headline_prefix']} post.

{voice_block}{style_line}

Rules:
{channel_config['rules']}{examples_block}"""


def _build_memory_block(memory: dict | None, channel: ContentChannel) -> str:
    """Build a memory context block for the generation prompt."""
    if not memory:
        return ""

    ch = channel.value
    parts = []

    approved = memory.get("approved", {}).get(ch, [])
    if approved:
        parts.append("PREVIOUSLY APPROVED (write MORE like these):")
        for item in approved[:3]:
            parts.append(f"  - {item.get('headline', 'N/A')}")

    spiked = memory.get("spiked", {}).get(ch, [])
    if spiked:
        parts.append("PREVIOUSLY SPIKED (write LESS like these):")
        for item in spiked[:3]:
            parts.append(f"  - {item.get('headline', 'N/A')}")

    recent = memory.get("recent_topics", [])
    if recent:
        recent_headlines = [r.get("headline", "") for r in recent[:10] if r.get("headline")]
        if recent_headlines:
            parts.append("RECENT TOPICS (avoid repeating):")
            for h in recent_headlines:
                parts.append(f"  - {h}")

    return "\n".join(parts) if parts else ""


def _build_intelligence_block(memory: dict | None) -> str:
    """Build a DF intelligence section from queried service data."""
    if not memory:
        return ""

    intelligence = memory.get("df_intelligence", {})
    if not intelligence:
        return ""

    parts = ["COMPANY INTELLIGENCE (from connected data sources):"]
    for svc_name, svc_data in intelligence.items():
        role = svc_data.get("role", "").replace("_", " ")
        desc = svc_data.get("description", "")
        parts.append(f"\n[{role.upper()}] {svc_name}: {desc}")

        for table_data in svc_data.get("data", []):
            table = table_data.get("table", "")
            rows = table_data.get("recent_rows", [])
            if rows:
                parts.append(f"  Recent from {table}:")
                for row in rows[:5]:
                    # Format row as key highlights
                    highlights = []
                    for k, v in list(row.items())[:4]:
                        if v and k not in ("id", "created_at", "updated_at"):
                            highlights.append(f"{k}: {v[:100]}")
                    if highlights:
                        parts.append(f"    - {' | '.join(highlights)}")

    return "\n".join(parts)


async def generate_brief(signals: list[dict], memory: dict | None = None,
                          voice_settings: dict | None = None) -> dict:
    """Synthesize signals into a daily brief with recommended angle."""
    signal_text = "\n\n".join(
        f"[{s.get('type', 'unknown')}] {s.get('title', '')}\n{s.get('body', '')[:500]}"
        for s in signals
    )

    intel_block = _build_intelligence_block(memory)
    intel_section = f"\n\nCompany data from connected sources:\n{intel_block}" if intel_block else ""

    voice_block = _build_voice_block(voice_settings)

    response = _get_client().messages.create(
        model=settings.claude_model,
        max_tokens=1000,
        system=f"""You are the wire editor at a content operations platform. You receive the day's signals — releases, trends, community posts, support patterns — and synthesize them into a daily brief.

Company context:
{voice_block}

Output format:
SUMMARY: 2-3 sentence overview of what's happening today.
ANGLE: The single strongest content angle for today (one sentence).
TOP SIGNALS: Ranked list of the 3-5 most actionable signals with one-line reasoning.
RECOMMENDATIONS: 2-3 specific content pieces to write, with channel and angle for each.""",
        messages=[{"role": "user", "content": f"Today's wire:\n\n{signal_text}{intel_section}"}],
    )

    text = response.content[0].text
    return {"summary": text, "angle": text.split("ANGLE:")[-1].split("\n")[0].strip() if "ANGLE:" in text else ""}


async def generate_content(brief: str, signals: list[dict], channel: ContentChannel,
                           memory: dict | None = None,
                           voice_settings: dict | None = None) -> dict:
    """Generate content for a specific channel from a brief and signals."""
    channel_config = CHANNEL_RULES.get(channel)
    if not channel_config:
        raise ValueError(f"No config for channel: {channel}")

    system_prompt = _build_system_prompt(channel, voice_settings)

    signal_context = "\n\n".join(
        f"[{s.get('type', 'unknown')}] {s.get('title', '')}\n{s.get('body', '')[:300]}"
        for s in signals[:5]
    )

    memory_block = _build_memory_block(memory, channel)
    memory_section = f"\n\nContent memory (learn from past approvals/rejections):\n{memory_block}" if memory_block else ""

    intel_block = _build_intelligence_block(memory)
    intel_section = f"\n\nCompany intelligence:\n{intel_block}" if intel_block else ""

    response = _get_client().messages.create(
        model=settings.claude_model,
        max_tokens=2000,
        system=system_prompt,
        messages=[{
            "role": "user",
            "content": f"Daily brief:\n{brief}\n\nKey signals:\n{signal_context}{memory_section}{intel_section}\n\nGenerate the content now.",
        }],
    )

    body = response.content[0].text
    lines = body.strip().split("\n")
    headline = lines[0].strip().strip("#").strip('"').strip("*").strip()

    return {
        "channel": channel,
        "headline": f"{channel_config['headline_prefix']}  {headline[:200]}",
        "body": body,
    }


async def generate_all_content(brief: str, signals: list[dict],
                                channels: list[ContentChannel] | None = None,
                                memory: dict | None = None,
                                voice_settings: dict | None = None) -> list[dict]:
    """Generate content across all channels (or specified subset)."""
    target_channels = channels or [
        ContentChannel.linkedin,
        ContentChannel.x_thread,
        ContentChannel.release_email,
        ContentChannel.blog,
    ]

    results = []
    for channel in target_channels:
        result = await generate_content(brief, signals, channel, memory=memory, voice_settings=voice_settings)
        results.append(result)

    return results
