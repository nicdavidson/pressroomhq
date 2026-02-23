"""Import endpoints — bulk data intake for signals, content, voice samples, and blog scraping."""

import csv
import io
import json
import re
import logging
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import APIRouter, Depends, UploadFile, File, Form
from pydantic import BaseModel

from database import get_data_layer
from services.data_layer import DataLayer

log = logging.getLogger("pressroom")

router = APIRouter(prefix="/api/import", tags=["import"])


class PasteImport(BaseModel):
    target: str  # "signals" | "content" | "voice_examples"
    format: str = "json"  # "json" | "csv" | "text"
    data: str


class BlogScrapeRequest(BaseModel):
    url: str
    max_posts: int = 20


@router.post("/paste")
async def import_paste(req: PasteImport, dl: DataLayer = Depends(get_data_layer)):
    """Import data from pasted text — JSON array, CSV, or plain text."""
    try:
        records = _parse_data(req.data, req.format)
    except Exception as e:
        return {"error": f"Parse error: {str(e)}", "imported": 0}

    return await _route_import(req.target, records, dl)


@router.post("/file")
async def import_file(
    target: str = Form(...),
    file: UploadFile = File(...),
    dl: DataLayer = Depends(get_data_layer),
):
    """Import data from uploaded file (JSON or CSV)."""
    content = await file.read()
    text = content.decode("utf-8")
    fmt = "csv" if file.filename and file.filename.endswith(".csv") else "json"

    try:
        records = _parse_data(text, fmt)
    except Exception as e:
        return {"error": f"Parse error: {str(e)}", "imported": 0}

    return await _route_import(target, records, dl)


@router.post("/blog")
async def import_blog(req: BlogScrapeRequest, dl: DataLayer = Depends(get_data_layer)):
    """Scrape a blog URL, discover posts, import them as approved content.

    This teaches the engine what topics have already been covered,
    preventing repetition and building voice memory.
    """
    blog_url = req.url.rstrip("/")
    if not blog_url.startswith("http"):
        blog_url = f"https://{blog_url}"

    headers = {"User-Agent": "Pressroom/0.1 (content-engine)"}
    base_host = urlparse(blog_url).netloc

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            # Fetch the blog index page
            resp = await client.get(blog_url, headers=headers)
            if resp.status_code != 200:
                return {"error": f"Failed to fetch blog page: HTTP {resp.status_code}", "imported": 0}

            html = resp.text

            # Discover post URLs from the page
            post_urls = _discover_blog_posts(html, blog_url, base_host)
            log.info("Blog scrape: found %d candidate post URLs from %s", len(post_urls), blog_url)

            if not post_urls:
                return {"error": "No blog posts found on that page. Try a direct blog listing URL.", "imported": 0}

            # Fetch and extract each post (up to max)
            imported = 0
            posts_found = []
            for url in post_urls[:req.max_posts]:
                try:
                    post_resp = await client.get(url, headers=headers)
                    if post_resp.status_code != 200:
                        continue

                    post_html = post_resp.text
                    title = _extract_title(post_html)
                    body = _extract_article_text(post_html)

                    if not body or len(body) < 100:
                        continue

                    # Save as approved blog content — this feeds into the engine's memory
                    await dl.save_content({
                        "channel": "blog",
                        "status": "approved",
                        "headline": title or url.split("/")[-1][:100],
                        "body": body[:5000],
                        "author": "imported",
                    })
                    imported += 1
                    posts_found.append({"title": title, "url": url})

                except Exception as e:
                    log.warning("Blog scrape: failed to fetch %s: %s", url, e)
                    continue

            await dl.commit()
            return {
                "imported": imported,
                "target": "content",
                "source_url": blog_url,
                "posts": posts_found,
            }

    except Exception as e:
        return {"error": f"Blog scrape failed: {str(e)}", "imported": 0}


@router.get("/templates")
async def import_templates():
    """Return example templates for each import target."""
    return {
        "signals": {
            "format": "json",
            "example": json.dumps([{
                "type": "rss",
                "source": "techcrunch.com",
                "title": "New API platform launches",
                "body": "Article body text...",
                "url": "https://example.com/article",
            }], indent=2),
            "fields": ["type", "source", "title", "body", "url"],
            "required": ["type", "source", "title"],
        },
        "content": {
            "format": "json",
            "example": json.dumps([{
                "channel": "linkedin",
                "status": "approved",
                "headline": "We just shipped v2.0",
                "body": "Full post text...",
                "author": "company",
            }], indent=2),
            "fields": ["channel", "status", "headline", "body", "author"],
            "required": ["channel", "body"],
        },
        "voice_examples": {
            "format": "text",
            "example": "Paste examples of your ideal writing style here.\n\nEach block separated by a blank line becomes one example.\n\nThe engine uses these as few-shot references.",
            "fields": ["text"],
            "required": ["text"],
        },
    }


def _parse_data(data: str, fmt: str) -> list[dict]:
    """Parse input data into a list of dicts."""
    if fmt == "json":
        parsed = json.loads(data)
        if isinstance(parsed, dict):
            parsed = [parsed]
        return parsed

    if fmt == "csv":
        reader = csv.DictReader(io.StringIO(data))
        return list(reader)

    if fmt == "text":
        # Split on double newlines, each block is one record
        blocks = [b.strip() for b in data.split("\n\n") if b.strip()]
        return [{"text": b} for b in blocks]

    raise ValueError(f"Unknown format: {fmt}")


async def _route_import(target: str, records: list[dict], dl: DataLayer) -> dict:
    """Route parsed records to the right storage."""
    imported = 0

    if target == "signals":
        for r in records:
            if not r.get("type") or not r.get("source") or not r.get("title"):
                continue
            await dl.save_signal(r)
            imported += 1
        await dl.commit()
        return {"imported": imported, "target": "signals"}

    if target == "content":
        for r in records:
            if not r.get("channel") or not r.get("body"):
                continue
            r.setdefault("status", "approved")
            r.setdefault("headline", r["body"][:100])
            r.setdefault("author", "imported")
            await dl.save_content(r)
            imported += 1
        await dl.commit()
        return {"imported": imported, "target": "content"}

    if target == "voice_examples":
        # Store as a single setting value
        from sqlalchemy import select
        from models import Setting
        examples = [r.get("text", "") for r in records if r.get("text")]
        combined = "\n---\n".join(examples)
        result = await dl.db.execute(select(Setting).where(Setting.key == "voice_writing_examples"))
        existing = result.scalar_one_or_none()
        if existing:
            # Append to existing
            if existing.value:
                existing.value = existing.value + "\n---\n" + combined
            else:
                existing.value = combined
        else:
            dl.db.add(Setting(key="voice_writing_examples", value=combined))
        await dl.commit()
        return {"imported": len(examples), "target": "voice_examples"}

    return {"error": f"Unknown target: {target}", "imported": 0}


# ──────────────────────────────────────
# Blog scraping helpers
# ──────────────────────────────────────

def _discover_blog_posts(html: str, base_url: str, base_host: str) -> list[str]:
    """Find blog post URLs from a blog listing page."""
    hrefs = re.findall(r'<a[^>]+href=["\']([^"\'#]+)["\']', html, re.IGNORECASE)
    seen = set()
    posts = []

    for href in hrefs:
        url = urljoin(base_url, href)
        parsed = urlparse(url)

        # Same host only
        if parsed.netloc != base_host:
            continue

        path = parsed.path.rstrip("/")

        # Skip non-content paths
        if any(path.endswith(ext) for ext in (".png", ".jpg", ".svg", ".css", ".js", ".xml", ".pdf")):
            continue
        skip = ["login", "signup", "register", "cart", "checkout", "account",
                "privacy", "terms", "cookie", "legal", "sitemap", "category",
                "tag/", "author/", "page/", "/feed", "/rss"]
        if any(s in path.lower() for s in skip):
            continue

        # Blog posts typically have deeper paths (e.g. /blog/post-title or /2024/01/post)
        segments = [s for s in path.split("/") if s]
        if len(segments) < 2:
            continue

        # Deduplicate
        if url in seen:
            continue
        seen.add(url)
        posts.append(url)

    return posts


def _extract_title(html: str) -> str:
    """Extract page title from HTML."""
    # Try <title> tag
    match = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL | re.IGNORECASE)
    if match:
        title = re.sub(r'\s+', ' ', match.group(1)).strip()
        # Clean common suffixes like " | Company Name" or " - Blog"
        title = re.split(r'\s*[|–—-]\s*', title)[0].strip()
        return title

    # Try <h1>
    match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL | re.IGNORECASE)
    if match:
        return re.sub(r'<[^>]+>', '', match.group(1)).strip()

    return ""


def _extract_article_text(html: str) -> str:
    """Extract article body text, prioritizing <article> and main content areas."""
    # Try <article> tag first
    article = re.search(r'<article[^>]*>(.*?)</article>', html, re.DOTALL | re.IGNORECASE)
    if article:
        html_content = article.group(1)
    else:
        # Try common content containers
        for pattern in [r'<div[^>]+class="[^"]*(?:post-content|entry-content|article-body|blog-content|content-body)[^"]*"[^>]*>(.*?)</div>',
                        r'<main[^>]*>(.*?)</main>']:
            match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if match:
                html_content = match.group(1)
                break
        else:
            # Fall back to stripping the whole page
            html_content = html

    # Remove script/style blocks
    html_content = re.sub(r'<(script|style|nav|header|footer)[^>]*>.*?</\1>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', html_content)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text
