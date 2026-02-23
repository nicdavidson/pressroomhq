"""Scout — Signal ingestion from GitHub, Hacker News, Reddit, RSS.

Org-aware: reads scout sources from per-org settings, not global config.
Includes LLM relevance filtering to discard off-topic signals.
"""

import json
import logging
import httpx
import feedparser
import anthropic
from datetime import datetime, timedelta

from config import settings
from models import SignalType

log = logging.getLogger("pressroom")


# ──────────────────────────────────────
# GitHub Org/User Repo Discovery
# ──────────────────────────────────────

async def discover_github_repos(github_url: str, gh_token: str = "", max_repos: int = 20) -> list[str]:
    """Discover all active repos under a GitHub org or user.

    Takes a GitHub profile URL like 'https://github.com/dreamfactorysoftware'
    and returns a list of 'owner/repo' strings, sorted by most recently pushed.
    """
    import re
    # Extract org/user name from URL
    match = re.search(r'github\.com/([^/\s?#]+)', github_url)
    if not match:
        return []
    owner = match.group(1)

    token = gh_token or settings.github_token
    headers = {"Authorization": f"token {token}"} if token else {}
    headers["Accept"] = "application/vnd.github.v3+json"

    repos = []
    async with httpx.AsyncClient(timeout=15) as client:
        # Try as org first, fall back to user
        for endpoint in [f"orgs/{owner}/repos", f"users/{owner}/repos"]:
            try:
                resp = await client.get(
                    f"https://api.github.com/{endpoint}",
                    headers=headers,
                    params={"per_page": 100, "sort": "pushed", "direction": "desc"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for r in data:
                        if r.get("archived") or r.get("disabled"):
                            continue
                        repos.append(r["full_name"])
                    break  # got results, don't try the other endpoint
            except Exception:
                continue

    log.info("GITHUB DISCOVERY — %s → %d repos found", owner, len(repos))
    return repos[:max_repos]


async def scout_github_releases(repo: str, since_hours: int = 24, gh_token: str = "") -> list[dict]:
    """Pull recent releases from a GitHub repo."""
    token = gh_token or settings.github_token
    headers = {"Authorization": f"token {token}"} if token else {}
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.github.com/repos/{repo}/releases",
            headers=headers,
            params={"per_page": 10},
        )
        if resp.status_code != 200:
            return []

        cutoff = datetime.utcnow() - timedelta(hours=since_hours)
        signals = []
        for release in resp.json():
            published = datetime.fromisoformat(release["published_at"].replace("Z", "+00:00")).replace(tzinfo=None)
            if published > cutoff:
                signals.append({
                    "type": SignalType.github_release,
                    "source": repo,
                    "title": f"{repo} — {release['tag_name']}: {release['name']}",
                    "body": release.get("body", "")[:2000],
                    "url": release["html_url"],
                    "raw_data": str(release)[:5000],
                })
        return signals


async def scout_github_commits(repo: str, since_hours: int = 24, gh_token: str = "") -> list[dict]:
    """Pull recent commits from a GitHub repo."""
    token = gh_token or settings.github_token
    headers = {"Authorization": f"token {token}"} if token else {}
    since = (datetime.utcnow() - timedelta(hours=since_hours)).isoformat() + "Z"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.github.com/repos/{repo}/commits",
            headers=headers,
            params={"since": since, "per_page": 20},
        )
        if resp.status_code != 200:
            return []

        commits = resp.json()
        if not commits:
            return []

        messages = [c["commit"]["message"].split("\n")[0] for c in commits[:20]]
        return [{
            "type": SignalType.github_commit,
            "source": repo,
            "title": f"{repo} — {len(commits)} new commits",
            "body": "\n".join(f"• {m}" for m in messages),
            "url": f"https://github.com/{repo}/commits",
            "raw_data": str(commits[:5])[:5000],
        }]


async def scout_hackernews(keywords: list[str] | None = None) -> list[dict]:
    """Pull HN stories via Algolia search for better keyword matching."""
    kw = keywords or settings.scout_hn_keywords
    async with httpx.AsyncClient() as client:
        if kw:
            # Use Algolia HN search — way better than scanning top stories
            signals = []
            seen_ids = set()
            for term in kw[:8]:
                try:
                    resp = await client.get(
                        "https://hn.algolia.com/api/v1/search_by_date",
                        params={"query": term, "tags": "story", "hitsPerPage": 5},
                        timeout=10,
                    )
                    if resp.status_code != 200:
                        continue
                    hits = resp.json().get("hits", [])
                    for hit in hits:
                        oid = hit.get("objectID", "")
                        if oid in seen_ids:
                            continue
                        seen_ids.add(oid)
                        signals.append({
                            "type": SignalType.hackernews,
                            "source": "hackernews",
                            "title": hit.get("title", ""),
                            "body": f"Score: {hit.get('points', 0)} | Comments: {hit.get('num_comments', 0)} | Matched: \"{term}\"",
                            "url": hit.get("url") or f"https://news.ycombinator.com/item?id={oid}",
                            "raw_data": str(hit)[:5000],
                        })
                except Exception:
                    continue
            return signals

        # Fallback: top stories if no keywords
        resp = await client.get("https://hacker-news.firebaseio.com/v0/topstories.json")
        if resp.status_code != 200:
            return []

        story_ids = resp.json()[:15]
        signals = []
        for sid in story_ids:
            sr = await client.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json")
            if sr.status_code != 200:
                continue
            story = sr.json()
            if not story or "title" not in story:
                continue
            signals.append({
                "type": SignalType.hackernews,
                "source": "hackernews",
                "title": story["title"],
                "body": f"Score: {story.get('score', 0)} | Comments: {story.get('descendants', 0)}",
                "url": story.get("url", f"https://news.ycombinator.com/item?id={sid}"),
                "raw_data": str(story)[:5000],
            })
        return signals


async def scout_reddit(subreddits: list[str] | None = None) -> list[dict]:
    """Pull hot posts from subreddits."""
    subs = subreddits or settings.scout_subreddits
    signals = []
    async with httpx.AsyncClient() as client:
        for sub in subs:
            try:
                resp = await client.get(
                    f"https://www.reddit.com/r/{sub}/hot.json",
                    headers={"User-Agent": "Pressroom/0.1"},
                    params={"limit": 10},
                    timeout=10,
                )
                if resp.status_code != 200:
                    continue
                data = resp.json().get("data", {}).get("children", [])
                for post in data:
                    p = post["data"]
                    if p.get("stickied"):
                        continue  # skip pinned mod posts
                    signals.append({
                        "type": SignalType.reddit,
                        "source": f"r/{sub}",
                        "title": p["title"],
                        "body": p.get("selftext", "")[:1000],
                        "url": f"https://reddit.com{p['permalink']}",
                        "raw_data": str(p)[:5000],
                    })
            except Exception:
                continue
    return signals


async def scout_rss(feeds: list[str] | None = None) -> list[dict]:
    """Pull recent entries from RSS feeds."""
    feed_urls = feeds or settings.scout_rss_feeds
    signals = []
    for url in feed_urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                signals.append({
                    "type": SignalType.rss,
                    "source": feed.feed.get("title", url),
                    "title": entry.get("title", "Untitled"),
                    "body": entry.get("summary", "")[:1000],
                    "url": entry.get("link", ""),
                    "raw_data": str(entry)[:5000],
                })
        except Exception:
            continue
    return signals


async def run_full_scout(since_hours: int = 24, org_settings: dict | None = None) -> list[dict]:
    """Run all scout sources. Uses org-specific settings if provided."""
    all_signals = []

    # Parse org settings or fall back to global config
    if org_settings:
        repos = _parse_json_list(org_settings.get("scout_github_repos", ""), settings.scout_github_repos)
        hn_kw = _parse_json_list(org_settings.get("scout_hn_keywords", ""), settings.scout_hn_keywords)
        subs = _parse_json_list(org_settings.get("scout_subreddits", ""), settings.scout_subreddits)
        rss = _parse_json_list(org_settings.get("scout_rss_feeds", ""), settings.scout_rss_feeds)
        gh_token = org_settings.get("github_token", "") or settings.github_token

        # Auto-discover GitHub repos if we have a GitHub URL but few/no repos
        if len(repos) < 3:
            social_raw = org_settings.get("social_profiles", "")
            if social_raw:
                try:
                    socials = json.loads(social_raw) if isinstance(social_raw, str) else social_raw
                    github_url = socials.get("github", "")
                    if github_url:
                        discovered = await discover_github_repos(github_url, gh_token=gh_token)
                        if discovered:
                            # Merge: keep existing + add discovered, deduplicate
                            existing = set(r.lower() for r in repos)
                            for r in discovered:
                                if r.lower() not in existing:
                                    repos.append(r)
                                    existing.add(r.lower())
                            log.info("SCOUT — auto-discovered %d GitHub repos (total: %d)",
                                     len(discovered), len(repos))
                except Exception:
                    pass
    else:
        repos = settings.scout_github_repos
        hn_kw = settings.scout_hn_keywords
        subs = settings.scout_subreddits
        rss = settings.scout_rss_feeds
        gh_token = settings.github_token

    log.info("SCOUT — repos=%d repos, hn_kw=%d terms, subs=%d subs, rss=%d feeds",
             len(repos), len(hn_kw), len(subs), len(rss))

    for repo in repos:
        all_signals.extend(await scout_github_releases(repo, since_hours, gh_token))
        all_signals.extend(await scout_github_commits(repo, since_hours, gh_token))

    all_signals.extend(await scout_hackernews(hn_kw))
    all_signals.extend(await scout_reddit(subs))
    all_signals.extend(await scout_rss(rss))

    return all_signals


def _parse_json_list(raw: str, default: list) -> list:
    """Parse a JSON list from settings string, with fallback."""
    if not raw:
        return default
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) and parsed else default
    except (json.JSONDecodeError, TypeError):
        return default


# ──────────────────────────────────────
# Relevance Filter
# ──────────────────────────────────────

async def filter_signals_for_relevance(signals: list[dict], company_context: str) -> list[dict]:
    """Use Claude to score signals for relevance to this company. Discard junk."""
    if not signals or len(signals) <= 3:
        return signals  # not worth filtering tiny batches

    # Build a compact list for Claude
    signal_list = []
    for i, s in enumerate(signals):
        title = s.get("title", "?")
        body_preview = s.get("body", "")[:100].replace("\n", " ")
        signal_list.append(f"{i}. [{s.get('type', '?')}] {s.get('source', '?')}: {title}")
        if body_preview:
            signal_list.append(f"   {body_preview}")

    signals_text = "\n".join(signal_list)

    prompt = f"""Rate each signal for relevance to this company's content engine.

COMPANY:
{company_context}

SIGNALS:
{signals_text}

Return ONLY a JSON array:
[{{"i": 0, "r": true}}, {{"i": 1, "r": false}}, ...]

Rules:
- r=true if the signal could inspire content this company's audience cares about
- r=false if off-topic, about unrelated software/tools, or generic noise
- Own GitHub repos/releases → ALWAYS relevant
- Be strict. Quality over quantity."""

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.claude_model_fast,
            max_tokens=1500,
            system="Strict relevance filter. Return valid JSON array only.",
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        # Find the array
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            text = text[start:end + 1]

        ratings = json.loads(text)
        if not isinstance(ratings, list):
            return signals

        relevant_indices = {r.get("i", r.get("index", -1)) for r in ratings if r.get("r", r.get("relevant"))}
        filtered = [s for i, s in enumerate(signals) if i in relevant_indices]

        dropped = len(signals) - len(filtered)
        if dropped:
            log.info("RELEVANCE FILTER — kept %d/%d signals (dropped %d)",
                     len(filtered), len(signals), dropped)

        return filtered if filtered else signals  # never return empty

    except Exception as e:
        log.warning("Relevance filter failed (%s), keeping all signals", e)
        return signals
