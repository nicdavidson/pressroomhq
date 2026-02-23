"""Scout — Signal ingestion from GitHub, Hacker News, Reddit, RSS."""

import httpx
import feedparser
from datetime import datetime, timedelta

from config import settings
from models import SignalType


async def scout_github_releases(repo: str, since_hours: int = 24) -> list[dict]:
    """Pull recent releases from a GitHub repo."""
    headers = {"Authorization": f"token {settings.github_token}"} if settings.github_token else {}
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


async def scout_github_commits(repo: str, since_hours: int = 24) -> list[dict]:
    """Pull recent commits from a GitHub repo."""
    headers = {"Authorization": f"token {settings.github_token}"} if settings.github_token else {}
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
    """Pull front page HN stories, optionally filtered by keywords."""
    kw = keywords or settings.scout_hn_keywords
    async with httpx.AsyncClient() as client:
        resp = await client.get("https://hacker-news.firebaseio.com/v0/topstories.json")
        if resp.status_code != 200:
            return []

        story_ids = resp.json()[:30]
        signals = []
        for sid in story_ids:
            sr = await client.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json")
            if sr.status_code != 200:
                continue
            story = sr.json()
            if not story or "title" not in story:
                continue
            title = story["title"]
            # keyword match (case-insensitive) or take top stories regardless
            if kw and not any(k.lower() in title.lower() for k in kw):
                continue
            signals.append({
                "type": SignalType.hackernews,
                "source": "hackernews",
                "title": title,
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
            resp = await client.get(
                f"https://www.reddit.com/r/{sub}/hot.json",
                headers={"User-Agent": "Pressroom/0.1"},
                params={"limit": 10},
            )
            if resp.status_code != 200:
                continue
            data = resp.json().get("data", {}).get("children", [])
            for post in data:
                p = post["data"]
                signals.append({
                    "type": SignalType.reddit,
                    "source": f"r/{sub}",
                    "title": p["title"],
                    "body": p.get("selftext", "")[:1000],
                    "url": f"https://reddit.com{p['permalink']}",
                    "raw_data": str(p)[:5000],
                })
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


async def run_full_scout(since_hours: int = 24) -> list[dict]:
    """Run all scout sources and return combined signals."""
    all_signals = []

    for repo in settings.scout_github_repos:
        all_signals.extend(await scout_github_releases(repo, since_hours))
        all_signals.extend(await scout_github_commits(repo, since_hours))

    all_signals.extend(await scout_hackernews())
    all_signals.extend(await scout_reddit())
    all_signals.extend(await scout_rss())

    return all_signals
