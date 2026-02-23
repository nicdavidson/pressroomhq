"""Onboarding — domain crawl, profile synthesis, DF service classification.

The onboarding flow:
1. User enters their domain → we crawl key pages
2. Claude synthesizes a company profile from the crawl
3. If DF is connected → discover services, introspect schemas, classify with Claude
4. User reviews → apply as voice settings + service map
"""

import re
import json
import httpx
import anthropic

from config import settings


def _get_client():
    """Lazy client — picks up the API key at call time, not import time."""
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


# ──────────────────────────────────────
# Domain Crawl
# ──────────────────────────────────────

async def crawl_domain(domain: str) -> dict:
    """Crawl a domain's key pages and extract text content."""
    if not domain.startswith("http"):
        domain = f"https://{domain}"
    domain = domain.rstrip("/")

    pages = {}
    targets = {
        "homepage": domain,
        "about": f"{domain}/about",
        "blog": f"{domain}/blog",
        "pricing": f"{domain}/pricing",
        "docs": f"{domain}/docs",
    }

    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
        for label, url in targets.items():
            try:
                resp = await c.get(url, headers={"User-Agent": "Pressroom/0.1 (content-engine)"})
                if resp.status_code == 200:
                    text = _extract_text(resp.text)
                    if text and len(text) > 50:
                        pages[label] = {"url": url, "text": text[:5000]}
            except Exception:
                continue

    return {
        "domain": domain,
        "pages_found": list(pages.keys()),
        "pages": pages,
    }


def _extract_text(html: str) -> str:
    """Rough text extraction from HTML — strip tags, collapse whitespace."""
    # Remove script/style blocks
    html = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', html)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Remove common boilerplate patterns
    text = re.sub(r'(cookie|privacy|terms of service|all rights reserved).*?\.', '', text, flags=re.IGNORECASE)
    return text


# ──────────────────────────────────────
# Profile Synthesis
# ──────────────────────────────────────

async def synthesize_profile(crawl_data: dict, extra_context: str = "") -> dict:
    """Claude synthesizes a company profile from crawled page data."""
    pages_text = ""
    for label, page in crawl_data.get("pages", {}).items():
        pages_text += f"\n--- {label.upper()} ({page['url']}) ---\n{page['text'][:3000]}\n"

    if not pages_text.strip():
        return {"error": "No page content to analyze"}

    prompt = f"""Analyze this company's website content and create a content operations profile.

Website: {crawl_data.get('domain', 'unknown')}

{pages_text}

{f'Additional context from user: {extra_context}' if extra_context else ''}

Return a JSON object with these exact fields:
{{
  "company_name": "The company name",
  "industry": "Primary industry/sector",
  "persona": "2-3 sentence description of the company voice/persona for content",
  "bio": "One-line company bio for author attribution",
  "audience": "Who their content targets",
  "tone": "Tone descriptors (e.g. 'Technical, direct, no-nonsense')",
  "never_say": ["list", "of", "words/phrases", "to", "avoid"],
  "brand_keywords": ["key", "brand", "terms", "product names"],
  "always": "What their content should always do/include",
  "topics": ["key", "content", "topics", "they", "cover"],
  "competitors": ["known", "competitors"],
  "linkedin_style": "LinkedIn-specific voice notes",
  "x_style": "X/Twitter-specific voice notes",
  "blog_style": "Blog-specific voice notes"
}}

Be specific to THIS company. Not generic marketing advice. Derive everything from what you actually see on their site."""

    response = _get_client().messages.create(
        model=settings.claude_model,
        max_tokens=2000,
        system="You are a content strategist analyzing a company to set up their AI content engine. Return valid JSON only.",
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text
    # Extract JSON from response (handle markdown code blocks)
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            return {"error": "Failed to parse profile", "raw": text}
    return {"error": "No profile generated", "raw": text}


# ──────────────────────────────────────
# DF Service Classification
# ──────────────────────────────────────

async def classify_df_services(db_services: list[dict], social_services: list[dict]) -> dict:
    """Claude classifies discovered DF services by role for the content engine.

    Takes introspected DB services (with schemas/samples) and social services,
    returns a service map that tells the engine what each service IS and how to use it.
    """
    # Build a description of what we found
    service_desc = "CONNECTED DREAMFACTORY SERVICES:\n\n"

    for svc in db_services:
        service_desc += f"DATABASE: {svc['name']} ({svc['type']})\n"
        if svc.get("description"):
            service_desc += f"  Description: {svc['description']}\n"
        for tbl in svc.get("tables", []):
            cols = ", ".join(tbl["columns"][:20]) if tbl.get("columns") else "unknown"
            service_desc += f"  Table: {tbl['name']} — columns: [{cols}]\n"
            if tbl.get("sample_row"):
                # Truncate values for prompt
                sample = {k: str(v)[:100] for k, v in list(tbl["sample_row"].items())[:8]}
                service_desc += f"  Sample: {json.dumps(sample)}\n"
        service_desc += "\n"

    for svc in social_services:
        stype = svc.get("type", "unknown")
        connected = svc.get("auth_status", {}).get("connected", False)
        service_desc += f"SOCIAL: {svc['name']} ({stype}) — {'authenticated' if connected else 'not authenticated'}\n"

    prompt = f"""{service_desc}

Classify each service for use in an AI content operations platform (Pressroom).

The platform needs to understand:
- Which databases contain customer data (CRM, support tickets, feedback)
- Which databases contain analytics/performance data
- Which databases contain product/company data
- Which are Pressroom's own internal databases
- Which social services are publishing channels

Return a JSON object:
{{
  "service_map": {{
    "service_name": {{
      "role": "customer_intelligence|performance_data|product_data|internal|publishing_channel|unknown",
      "description": "What this service provides to the content engine",
      "data_type": "What kind of data it holds",
      "useful_tables": ["table_names", "the engine should query"],
      "query_hints": "How to query this for content intelligence (DF filter syntax)"
    }}
  }},
  "intelligence_sources": ["service names that provide content intelligence"],
  "publishing_channels": ["service names for publishing content"]
}}"""

    response = _get_client().messages.create(
        model=settings.claude_model,
        max_tokens=2000,
        system="You are a data architect classifying connected services for an AI content platform. Return valid JSON only. Be specific about what each service provides.",
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            return {"error": "Failed to parse classification", "raw": text}
    return {"error": "No classification generated", "raw": text}


# ──────────────────────────────────────
# Apply Profile
# ──────────────────────────────────────

def profile_to_settings(profile: dict) -> dict:
    """Convert a synthesized profile into the settings key/value pairs."""
    mapping = {}

    if profile.get("persona"):
        mapping["voice_persona"] = profile["persona"]
    if profile.get("bio"):
        mapping["voice_bio"] = profile["bio"]
    if profile.get("audience"):
        mapping["voice_audience"] = profile["audience"]
    if profile.get("tone"):
        mapping["voice_tone"] = profile["tone"]
    if profile.get("always"):
        mapping["voice_always"] = profile["always"]
    if profile.get("never_say"):
        mapping["voice_never_say"] = json.dumps(profile["never_say"])
    if profile.get("brand_keywords"):
        mapping["voice_brand_keywords"] = json.dumps(profile["brand_keywords"])
    if profile.get("linkedin_style"):
        mapping["voice_linkedin_style"] = profile["linkedin_style"]
    if profile.get("x_style"):
        mapping["voice_x_style"] = profile["x_style"]
    if profile.get("blog_style"):
        mapping["voice_blog_style"] = profile["blog_style"]

    return mapping
