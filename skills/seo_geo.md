# SEO + GEO Audit Skill

Comprehensive SEO and Generative Engine Optimization analysis for a given URL.

**Core insight:** AI search engines don't rank pages — they cite sources. Being cited is the new ranking #1. Traditional SEO gets you found by Google. GEO gets you cited by ChatGPT, Perplexity, and Claude.

## Tools available
- WebFetch (fetch the target URL and robots.txt)
- WebSearch (keyword research, competitor analysis)

---

## Step 1 — Technical SEO Audit

Fetch the URL. Check:

**Critical (P0 — fix immediately):**
- Missing or duplicate H1 tags
- Missing title tag
- Missing meta description
- Page returns non-200 status

**Important (P1):**
- Title tag length: target 50-60 chars. Flag if over 60 or under 30.
- Meta description length: target 120-160 chars. Flag if over 160 or under 120.
- Missing Open Graph tags (og:title, og:description, og:image)
- No JSON-LD schema markup detected
- Thin content (under 300 words on a non-homepage)

**Incremental (P2):**
- Missing canonical tag
- Title or description appears truncated mid-word (indicates it was cut by a tool)
- Generic anchor text on internal links ("click here", "learn more")

---

## Step 2 — robots.txt Analysis

Fetch `{domain}/robots.txt`. Check:

**AI bot access** — these bots must NOT be blocked:
- GPTBot (ChatGPT)
- ChatGPT-User
- PerplexityBot
- ClaudeBot
- anthropic-ai
- Googlebot
- Bingbot

If any AI bot is explicitly disallowed, flag as P0: "**{BotName} is blocked — this page will not be cited by {platform}**"

**Sitemap reference** — robots.txt should include `Sitemap: https://domain.com/sitemap.xml`. Flag P1 if missing.

---

## Step 3 — GEO Optimization Analysis

Analyze the page content for AI citation readiness using the 9 Princeton-backed methods:

| Method | Visibility Boost | Check |
|--------|-----------------|-------|
| Source citations | +40% | Does content cite named sources, studies, or data? |
| Statistics | +37% | Are there specific numbers, percentages, dates? |
| Expert quotations | +30% | Are experts named and quoted directly? |
| Authoritative tone | +25% | Does it state things confidently or hedge everything? |
| Clear explanations | +20% | Are technical concepts defined? |
| Technical terminology | +18% | Is domain vocabulary used correctly? |
| Vocabulary diversity | +15% | Is there repetitive phrasing that reduces citability? |
| Fluency | +15-30% | Is it readable or stilted? |
| Keyword stuffing | -10% | **AVOID** — flag if present |

**Best combination for maximum boost:** Fluency + Statistics

**Citability assessment:** Would an AI search engine cite this page as a source for its topic? State yes/no and why in one sentence.

**FAQPage opportunity:** Generate 3-5 FAQ questions this page should answer for AI visibility. These become FAQPage schema in Step 4.

**E-E-A-T check:**
- Experience: Does the author/company demonstrate firsthand experience?
- Expertise: Is domain expertise evident?
- Authoritativeness: Are there signals of authority (citations, credentials, external links)?
- Trustworthiness: Is the content accurate and verifiable?

---

## Step 4 — Meta Tag Recommendations

Generate optimized replacements for any failing meta fields:

**Title** (if current fails length check or keyword positioning):
- Primary keyword in first 3 words where possible
- 50-60 chars
- No keyword duplication

**Meta description** (if current fails):
- Action-oriented language
- Include primary keyword naturally
- 120-160 chars
- Answer: "what will I get from this page?"

**Open Graph** (if missing):
- og:title — can match title or be slightly more conversational
- og:description — can match meta description
- og:type — "website" for homepage, "article" for posts

---

## Step 5 — Schema Markup

Generate JSON-LD schema appropriate for the page type:

**Always include:** WebPage or Article schema with name, description, url, dateModified

**If FAQ content exists or was identified in Step 3:** FAQPage schema — this is the highest-value GEO addition. Format:
```json
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [{
    "@type": "Question",
    "name": "What is [topic]?",
    "acceptedAnswer": {
      "@type": "Answer",
      "text": "According to [source], [answer with statistics]."
    }
  }]
}
```

**If homepage or about page:** Add Organization schema

**If software product page:** Add SoftwareApplication schema

---

## Output Format

Return a structured report:

```
## SEO + GEO Audit: {url}
Score: {0-100}/100

### Critical Issues (P0)
- [list]

### Important Issues (P1)
- [list]

### GEO Readiness
Citability: [Yes/No] — [one sentence why]
Top opportunity: [single highest-value improvement]

### Recommended Meta Tags
Title: "{optimized title}" ({n} chars)
Description: "{optimized description}" ({n} chars)

### Schema Markup
[JSON-LD block]

### Platform-Specific Notes
- ChatGPT: [note if relevant]
- Perplexity: [note if relevant]
- Google AI Overview: [note if relevant]
- Claude: [note if relevant]
```

Score calculation:
- Start at 100
- P0 issues: -15 each
- P1 issues: -8 each
- P2 issues: -3 each
- GEO: each missing high-value method (-3)
- AI bot blocked: -20 each
