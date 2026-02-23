"""Content Engine — Claude-powered content generation from signals and briefs.

Uses memory context (approved examples, spiked anti-patterns, recent topics)
from the content ledger to improve generation quality over time.
"""

import anthropic
from config import settings
from models import ContentChannel

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

VOICE_PROFILE = """
Voice: Montana-based engineer building real AI infrastructure.
Audience: Engineers and technical decision-makers.
Tone: Direct, opinionated, no corporate-speak.
Never say: "excited to share", "game-changer", "leverage", "synergy", "thrilled", "comprehensive"
Always: "Here's what I built, here's what broke, here's what I learned"
"""

CHANNEL_PROMPTS = {
    ContentChannel.linkedin: {
        "system": f"""You are a content engine for a 1970s-style AI pressroom. Generate a LinkedIn post.
{VOICE_PROFILE}
Rules:
- 150-300 words max
- Hook in first line (pattern interrupt, bold claim, or question)
- No hashtags unless they're genuinely useful (max 3)
- End with a thought or question, not a CTA
- Write like a human engineer sharing what they built, not a marketer
- No bullet-point listicles unless the content genuinely demands it""",
        "headline_prefix": "LINKEDIN",
    },
    ContentChannel.x_thread: {
        "system": f"""You are a content engine for a 1970s-style AI pressroom. Generate an X/Twitter thread (5-8 tweets).
{VOICE_PROFILE}
Rules:
- Tweet 1 is the hook — must stand alone and stop the scroll
- Each tweet under 280 characters
- Number them 1/, 2/, etc.
- Last tweet: takeaway or link
- Conversational, not performative
- No "thread 🧵" opener""",
        "headline_prefix": "X THREAD",
    },
    ContentChannel.blog: {
        "system": f"""You are a content engine for a 1970s-style AI pressroom. Generate a blog post draft.
{VOICE_PROFILE}
Rules:
- 800-1500 words
- SEO-aware title (include primary keyword naturally)
- H2 subheadings every 200-300 words
- Technical depth — code snippets where relevant
- No fluff intro paragraphs. Start with the point.
- End with what's next, not a generic conclusion""",
        "headline_prefix": "BLOG DRAFT",
    },
    ContentChannel.release_email: {
        "system": f"""You are a content engine for a 1970s-style AI pressroom. Generate a release announcement email.
{VOICE_PROFILE}
Rules:
- Subject line that gets opened (not clickbait, just clear value)
- 200-400 words
- What shipped, why it matters, how to use it
- One clear CTA
- Plain text feel, not HTML newsletter energy""",
        "headline_prefix": "RELEASE EMAIL",
    },
    ContentChannel.newsletter: {
        "system": f"""You are a content engine for a 1970s-style AI pressroom. Generate a developer newsletter section.
{VOICE_PROFILE}
Rules:
- 300-500 words
- "This week in [product]" format
- What shipped, what's coming, one community highlight
- Links to docs/blog where relevant
- Casual, informative, not salesy""",
        "headline_prefix": "NEWSLETTER",
    },
    ContentChannel.yt_script: {
        "system": f"""You are a content engine for a 1970s-style AI pressroom. Generate a YouTube video script (teleprompter-ready).
{VOICE_PROFILE}
Rules:
- 2-4 minutes when read aloud (~300-600 words)
- Open with the hook (what you'll learn / why this matters)
- Conversational — written for speaking, not reading
- Include [B-ROLL: description] markers for visual cuts
- End with a clear next step""",
        "headline_prefix": "YT SCRIPT",
    },
}


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


async def generate_brief(signals: list[dict]) -> dict:
    """Synthesize signals into a daily brief with recommended angle."""
    signal_text = "\n\n".join(
        f"[{s.get('type', 'unknown')}] {s.get('title', '')}\n{s.get('body', '')[:500]}"
        for s in signals
    )

    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=1000,
        system="""You are the wire editor at a 1970s pressroom. You receive the day's signals — releases, trends, community posts, support patterns — and synthesize them into a daily brief.

Output format:
SUMMARY: 2-3 sentence overview of what's happening today.
ANGLE: The single strongest content angle for today (one sentence).
TOP SIGNALS: Ranked list of the 3-5 most actionable signals with one-line reasoning.""",
        messages=[{"role": "user", "content": f"Today's wire:\n\n{signal_text}"}],
    )

    text = response.content[0].text
    return {"summary": text, "angle": text.split("ANGLE:")[-1].split("\n")[0].strip() if "ANGLE:" in text else ""}


async def generate_content(brief: str, signals: list[dict], channel: ContentChannel,
                           memory: dict | None = None) -> dict:
    """Generate content for a specific channel from a brief and signals."""
    prompt_config = CHANNEL_PROMPTS.get(channel)
    if not prompt_config:
        raise ValueError(f"No prompt config for channel: {channel}")

    signal_context = "\n\n".join(
        f"[{s.get('type', 'unknown')}] {s.get('title', '')}\n{s.get('body', '')[:300]}"
        for s in signals[:5]
    )

    memory_block = _build_memory_block(memory, channel)
    memory_section = f"\n\nContent memory (learn from past approvals/rejections):\n{memory_block}" if memory_block else ""

    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=2000,
        system=prompt_config["system"],
        messages=[{
            "role": "user",
            "content": f"Daily brief:\n{brief}\n\nKey signals:\n{signal_context}{memory_section}\n\nGenerate the content now.",
        }],
    )

    body = response.content[0].text
    lines = body.strip().split("\n")
    headline = lines[0].strip().strip("#").strip('"').strip("*").strip()

    return {
        "channel": channel,
        "headline": f"{prompt_config['headline_prefix']}  {headline[:200]}",
        "body": body,
    }


async def generate_all_content(brief: str, signals: list[dict],
                                channels: list[ContentChannel] | None = None,
                                memory: dict | None = None) -> list[dict]:
    """Generate content across all channels (or specified subset)."""
    target_channels = channels or [
        ContentChannel.linkedin,
        ContentChannel.x_thread,
        ContentChannel.release_email,
        ContentChannel.blog,
    ]

    results = []
    for channel in target_channels:
        result = await generate_content(brief, signals, channel, memory=memory)
        results.append(result)

    return results
