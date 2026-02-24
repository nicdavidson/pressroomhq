"""Blog Scraper — discover and extract recent blog posts from RSS or HTML.

Scrapes a blog URL for recent posts. Tries RSS feed discovery first
(faster, more structured), falls back to HTML link extraction.
"""

import datetime
import logging
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse

import httpx

log = logging.getLogger("pressroom")

HEADERS = {"User-Agent": "Pressroom/0.1 (blog-scraper)"}
MAX_POSTS = 50

# Common RSS feed paths to probe
_RSS_PATHS = ["/feed", "/rss", "/feed.xml", "/rss.xml", "/atom.xml",
              "/blog/feed", "/blog/rss", "/blog/feed.xml", "/index.xml"]


def _parse_date(date_str: str) -> datetime.datetime | None:
    """Best-effort date parsing from RSS/Atom date strings."""
    if not date_str:
        return None
    date_str = date_str.strip()

    # RFC 2822 (RSS)
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        pass

    # ISO 8601 (Atom, common blogs)
    for fmt in [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]:
        try:
            return datetime.datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    return None


def _strip_tags(html: str) -> str:
    """Rough HTML tag stripping."""
    text = re.sub(r'<[^>]+>', ' ', html)
    return re.sub(r'\s+', ' ', text).strip()


def _within_days(dt: datetime.datetime | None, days: int) -> bool:
    """Check if a datetime is within the last N days. If no date, include it."""
    if dt is None:
        return True
    now = datetime.datetime.now(datetime.timezone.utc)
    # Make dt offset-aware if naive
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return (now - dt).days <= days


async def _find_rss_feed(client: httpx.AsyncClient, blog_url: str) -> str | None:
    """Try to discover an RSS/Atom feed URL from a blog.

    1. Check <link> tags in HTML head for feed autodiscovery.
    2. Probe common feed paths.
    """
    # Step 1: Check HTML for feed autodiscovery link
    try:
        resp = await client.get(blog_url, headers=HEADERS)
        if resp.status_code == 200:
            # Look for <link rel="alternate" type="application/rss+xml" ...>
            feed_match = re.search(
                r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]+href=["\']([^"\']+)["\']',
                resp.text, re.IGNORECASE,
            )
            if not feed_match:
                # Try reversed attribute order
                feed_match = re.search(
                    r'<link[^>]+href=["\']([^"\']+)["\'][^>]+type=["\']application/(?:rss|atom)\+xml["\']',
                    resp.text, re.IGNORECASE,
                )
            if feed_match:
                feed_url = urljoin(blog_url, feed_match.group(1))
                log.info("BLOG SCRAPER — autodiscovered feed: %s", feed_url)
                return feed_url
    except Exception:
        pass

    # Step 2: Probe common paths
    base = blog_url.rstrip("/")
    # Also try the domain root if the blog URL has a path
    parsed = urlparse(blog_url)
    roots = [base]
    domain_root = f"{parsed.scheme}://{parsed.netloc}"
    if domain_root != base:
        roots.append(domain_root)

    for root in roots:
        for path in _RSS_PATHS:
            url = f"{root}{path}"
            try:
                resp = await client.get(url, headers=HEADERS)
                if resp.status_code == 200 and (
                    "xml" in resp.headers.get("content-type", "")
                    or resp.text.strip().startswith("<?xml")
                    or "<rss" in resp.text[:500]
                    or "<feed" in resp.text[:500]
                ):
                    log.info("BLOG SCRAPER — probed feed at: %s", url)
                    return url
            except Exception:
                continue

    return None


def _parse_rss_xml(xml_text: str, days: int) -> list[dict]:
    """Parse RSS or Atom XML into blog post dicts."""
    posts = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        log.warning("BLOG SCRAPER — failed to parse RSS XML")
        return []

    # Handle namespaces (Atom uses them)
    ns = {"atom": "http://www.w3.org/2005/Atom",
          "content": "http://purl.org/rss/1.0/modules/content/",
          "dc": "http://purl.org/dc/elements/1.1/"}

    # RSS 2.0: <rss><channel><item>
    items = root.findall(".//item")
    if items:
        for item in items:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            pub_date = item.findtext("pubDate", "")
            if not pub_date:
                pub_date = item.findtext("{http://purl.org/dc/elements/1.1/}date", "")

            # Description / excerpt
            desc = item.findtext("description", "")
            content_encoded = item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded", "")

            excerpt = _strip_tags(desc) if desc else ""
            if not excerpt and content_encoded:
                excerpt = _strip_tags(content_encoded)
            excerpt = excerpt[:500]

            dt = _parse_date(pub_date)
            if not _within_days(dt, days):
                continue

            posts.append({
                "title": title,
                "url": link,
                "published_at": dt.isoformat() if dt else None,
                "excerpt": excerpt,
            })
    else:
        # Atom: <feed><entry>
        entries = root.findall("{http://www.w3.org/2005/Atom}entry")
        if not entries:
            entries = root.findall("entry")
        for entry in entries:
            title_el = entry.find("{http://www.w3.org/2005/Atom}title")
            if title_el is None:
                title_el = entry.find("title")
            title = (title_el.text or "").strip() if title_el is not None else ""

            # Atom links: <link href="..." rel="alternate" />
            link = ""
            for link_el in entry.findall("{http://www.w3.org/2005/Atom}link"):
                rel = link_el.get("rel", "alternate")
                if rel == "alternate":
                    link = link_el.get("href", "")
                    break
            if not link:
                for link_el in entry.findall("link"):
                    link = link_el.get("href", link_el.text or "")
                    if link:
                        break

            updated = entry.findtext("{http://www.w3.org/2005/Atom}updated", "")
            published = entry.findtext("{http://www.w3.org/2005/Atom}published", "")
            date_str = published or updated
            if not date_str:
                date_str = entry.findtext("updated", "") or entry.findtext("published", "")

            summary_el = entry.find("{http://www.w3.org/2005/Atom}summary")
            if summary_el is None:
                summary_el = entry.find("{http://www.w3.org/2005/Atom}content")
            if summary_el is None:
                summary_el = entry.find("summary") or entry.find("content")
            excerpt = _strip_tags(summary_el.text or "") if summary_el is not None else ""
            excerpt = excerpt[:500]

            dt = _parse_date(date_str)
            if not _within_days(dt, days):
                continue

            posts.append({
                "title": title,
                "url": link,
                "published_at": dt.isoformat() if dt else None,
                "excerpt": excerpt,
            })

    return posts[:MAX_POSTS]


def _extract_posts_from_html(html: str, blog_url: str, days: int) -> list[dict]:
    """Fallback: extract article links from blog HTML.

    Looks for <article> tags, common blog post URL patterns, etc.
    """
    posts = []
    seen_urls = set()

    # Strategy 1: Find links that look like blog posts
    # Common patterns: /blog/slug, /post/slug, /YYYY/MM/slug, /articles/slug
    blog_link_pattern = re.compile(
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    post_url_pattern = re.compile(
        r'/(blog|post|posts|article|articles|news|insights|resources)/[^/]+/?$'
        r'|/\d{4}/\d{2}/[^/]+/?$',
        re.IGNORECASE,
    )

    for match in blog_link_pattern.finditer(html):
        href = match.group(1).strip()
        link_text = _strip_tags(match.group(2)).strip()

        full_url = urljoin(blog_url, href)
        parsed = urlparse(full_url)

        # Must be same domain or subdomain
        blog_host = urlparse(blog_url).netloc
        if parsed.netloc and parsed.netloc != blog_host:
            # Allow subdomains of same root
            blog_root = ".".join(blog_host.split(".")[-2:])
            link_root = ".".join(parsed.netloc.split(".")[-2:])
            if blog_root != link_root:
                continue

        # Check if URL looks like a blog post
        if not post_url_pattern.search(parsed.path):
            continue

        # Skip if no meaningful link text or too short
        if not link_text or len(link_text) < 5:
            continue

        # Skip pagination, tags, categories
        skip_words = ["page", "category", "tag", "author", "archive", "next", "previous", "older", "newer"]
        if any(w in parsed.path.lower() for w in skip_words):
            continue

        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        posts.append({
            "title": link_text[:500],
            "url": full_url,
            "published_at": None,
            "excerpt": "",
        })

    # Strategy 2: Check for <article> or <h2>/<h3> within blog-like containers
    # These often have titles without links matching our pattern
    article_titles = re.findall(
        r'<(?:article|div[^>]*class=["\'][^"\']*(?:post|article|entry)[^"\']*["\'])[^>]*>.*?'
        r'<(?:h[1-3])[^>]*>(.*?)</(?:h[1-3])>',
        html, re.IGNORECASE | re.DOTALL,
    )
    # These are harder to link without URLs, so we skip them unless we found very few above

    return posts[:MAX_POSTS]


async def scrape_blog_posts(
    blog_url: str,
    days: int = 30,
    api_key: str | None = None,
) -> list[dict]:
    """Scrape recent blog posts from a URL.

    Tries RSS feed first, falls back to HTML parsing.
    Returns list of dicts: [{"title", "url", "published_at", "excerpt"}]
    """
    if not blog_url:
        return []

    if not blog_url.startswith("http"):
        blog_url = f"https://{blog_url}"
    blog_url = blog_url.rstrip("/")

    log.info("BLOG SCRAPER — scraping %s (last %d days)", blog_url, days)

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        # Try RSS first
        feed_url = await _find_rss_feed(client, blog_url)
        if feed_url:
            try:
                resp = await client.get(feed_url, headers=HEADERS)
                if resp.status_code == 200:
                    posts = _parse_rss_xml(resp.text, days)
                    if posts:
                        log.info("BLOG SCRAPER — found %d posts via RSS from %s", len(posts), feed_url)
                        return posts
            except Exception as e:
                log.warning("BLOG SCRAPER — RSS fetch/parse failed: %s", e)

        # Fallback: HTML scraping
        try:
            resp = await client.get(blog_url, headers=HEADERS)
            if resp.status_code == 200:
                posts = _extract_posts_from_html(resp.text, blog_url, days)
                log.info("BLOG SCRAPER — found %d posts via HTML from %s", len(posts), blog_url)
                return posts
        except Exception as e:
            log.warning("BLOG SCRAPER — HTML fetch failed: %s", e)

    return []
