"""SEO PR Pipeline — audit a site, analyze issues, implement fixes, create a PR.

This is the server-side pipeline that:
1. Runs an SEO audit (reuses seo_audit.py)
2. Sends audit results to Claude for tiered analysis
3. Clones the target repo
4. Uses Claude API to generate file edits for each tier
5. Commits tier-by-tier, pushes, and creates a PR

CRITICAL: Never merges to main/master — only creates PRs for human review.
"""

import datetime
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import anthropic

from config import settings
from services.seo_audit import audit_domain

log = logging.getLogger("pressroom.seo_pipeline")


# ──────────────────────────────────────
# Analysis
# ──────────────────────────────────────

ANALYSIS_SYSTEM_PROMPT = """You are an expert SEO analyst. You will receive an SEO audit of a website.

Your task: produce a prioritized SEO improvement plan as JSON. Analyze the audit data and identify concrete, implementable changes organized into priority tiers.

## Output Format

You MUST output valid JSON matching this schema exactly:

```json
{
  "summary": "2-3 sentence executive summary of the biggest opportunities",
  "tiers": [
    {
      "tier": "P0",
      "description": "Critical fixes - highest impact",
      "changes": [
        {
          "page_url": "the URL of the page",
          "file_path": "best guess at repo file path (e.g. docs/getting-started.md)",
          "change_type": "title | description | heading | body | internal_link | front_matter",
          "current_value": "what exists currently",
          "suggested_value": "the exact new text or a specific directive for body changes",
          "justification": "why this change matters, citing specific audit data",
          "priority_score": 95
        }
      ]
    },
    {
      "tier": "P1",
      "description": "Important improvements",
      "changes": []
    },
    {
      "tier": "P2",
      "description": "Incremental optimizations",
      "changes": []
    }
  ]
}
```

## Constraints

- P0: Maximum 5 changes. Highest-impact fixes only.
- P1: Maximum 7 changes. Important but not urgent.
- P2: Maximum 8 changes. Incremental improvements.
- Every suggestion MUST reference specific audit data (issues found, missing elements, etc.).
- Titles should be under 60 characters. Descriptions under 155 characters.
- Be specific and actionable — every change should be implementable without ambiguity.
- For body changes, describe exactly what content to add and where.
- Do NOT suggest changes for pages that are already performing well.

## CRITICAL: Output Instructions

Your ENTIRE response must be a single valid JSON object. No markdown fences, no commentary.
Start with `{` and end with `}`. Nothing else."""


async def analyze_seo_issues(audit_result: dict, repo_info: dict, api_key: str) -> dict:
    """Take audit data, send to Claude with analysis prompt. Returns tiered plan."""
    # Build the audit summary for Claude
    summary_parts = [
        f"SEO AUDIT RESULTS FOR {audit_result.get('domain', 'unknown')}",
        f"{audit_result.get('pages_audited', 0)} pages crawled.\n",
    ]

    pages = audit_result.get("pages", [])
    total_issues = 0

    for p in pages:
        issues = p.get("issues", [])
        total_issues += len(issues)
        summary_parts.append(f"\n--- {p['url']} ---")
        summary_parts.append(f"Title ({p.get('title_length', 0)} chars): {p.get('title', 'MISSING')}")
        summary_parts.append(f"Meta desc ({p.get('meta_description_length', 0)} chars): {p.get('meta_description', 'MISSING')[:100]}")
        summary_parts.append(f"H1s: {p.get('h1_count', 0)} | H2s: {p.get('h2_count', 0)} | Words: {p.get('word_count', 0)}")
        summary_parts.append(f"Images: {p.get('total_images', 0)} total, {p.get('images_missing_alt', 0)} missing alt")
        summary_parts.append(f"Links: {p.get('internal_links', 0)} internal, {p.get('external_links', 0)} external")
        summary_parts.append(f"Schema: {'Yes' if p.get('has_schema') else 'No'} | Canonical: {'Yes' if p.get('canonical') else 'No'} | OG: {'Yes' if p.get('og_image') else 'No'}")
        if issues:
            summary_parts.append(f"Issues: {', '.join(issues)}")

    summary_parts.append(f"\nTOTAL ISSUES: {total_issues} across {len(pages)} pages")

    # Add existing analysis if available
    recs = audit_result.get("recommendations", {})
    if recs.get("analysis"):
        summary_parts.append(f"\n\nEXISTING ANALYSIS:\n{recs['analysis']}")

    # Add repo context if available
    if repo_info.get("repo_url"):
        summary_parts.append(f"\n\nTARGET REPO: {repo_info['repo_url']}")
    if repo_info.get("base_branch"):
        summary_parts.append(f"BASE BRANCH: {repo_info['base_branch']}")

    # Add company context if available
    if repo_info.get("company_description"):
        summary_parts.append(f"\nCOMPANY CONTEXT: {repo_info['company_description']}")

    user_message = "\n".join(summary_parts)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=8000,
            system=ANALYSIS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        raw_text = response.content[0].text
        plan = _extract_json(raw_text)
        return plan

    except Exception as e:
        log.error("SEO analysis failed: %s", e)
        return {
            "summary": f"Analysis failed: {str(e)}",
            "tiers": [],
            "error": str(e),
        }


def _extract_json(text: str) -> dict:
    """Extract JSON from Claude's response, handling various formats."""
    text = text.lstrip("\ufeff").strip()

    # Strip code fences
    if text.startswith("```"):
        first_newline = text.index("\n")
        text = text[first_newline + 1:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()
            text = text[: text.rfind("```")].rstrip()

    text = text.strip()

    # Direct parse
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # First { to last }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        candidate = text[first_brace:last_brace + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract JSON from response (length={len(text)})")


# ──────────────────────────────────────
# Implementation
# ──────────────────────────────────────

IMPLEMENT_SYSTEM_PROMPT = """You are an SEO implementation specialist. You will receive a list of SEO changes to make to specific files in a repository.

For each change, output the exact file edits needed as a JSON array. Each edit should specify:
- file_path: the file to edit
- search: the exact text to find in the file (must be unique within the file)
- replace: the text to replace it with

If you need to add new content (like a meta description that doesn't exist), use a nearby unique string as the search anchor and include it plus the new content in the replace.

Your ENTIRE response must be a JSON array of edits:
```json
[
  {
    "file_path": "docs/getting-started.md",
    "search": "exact text to find",
    "replace": "replacement text"
  }
]
```

Rules:
- The `search` string MUST be unique within the file — include enough surrounding context.
- Preserve existing formatting (indentation, line endings).
- Do NOT remove or break existing content unless the change specifically requires it.
- For front matter changes (title, description), include the full front matter key-value line.
- For heading changes, include the full heading line with markdown markers.
- Output ONLY the JSON array. No commentary."""


async def implement_seo_changes(plan: dict, repo_path: str, api_key: str) -> list[dict]:
    """For each tier, send implementation directives to Claude. Returns list of tier results."""
    tiers = plan.get("tiers", [])
    results = []

    for tier in tiers:
        tier_name = tier.get("tier", "P0")
        changes = tier.get("changes", [])
        if not changes:
            results.append({"tier": tier_name, "edits_applied": 0, "errors": []})
            continue

        # Build the implementation prompt
        lines = [
            f"# SEO Changes: {tier_name}",
            f"Apply these {len(changes)} changes to the repository at {repo_path}.",
            "",
        ]

        for i, change in enumerate(changes, 1):
            lines.append(f"## Change {i}: {change.get('change_type', 'update').upper()}")
            if change.get("file_path"):
                lines.append(f"**File**: `{change['file_path']}`")
            if change.get("page_url"):
                lines.append(f"**Page**: {change['page_url']}")
            lines.append(f"**Type**: {change.get('change_type', 'N/A')}")
            if change.get("current_value"):
                lines.append(f"**Current value**: {change['current_value']}")
            if change.get("suggested_value"):
                lines.append(f"**Change to**: {change['suggested_value']}")
            if change.get("justification"):
                lines.append(f"**Why**: {change['justification']}")
            lines.append("")

        # Read the current content of referenced files to give Claude context
        file_contexts = []
        seen_files = set()
        for change in changes:
            fp = change.get("file_path", "")
            if fp and fp not in seen_files:
                seen_files.add(fp)
                full_path = Path(repo_path) / fp
                if full_path.exists():
                    try:
                        content = full_path.read_text(encoding="utf-8")
                        # Truncate very large files
                        if len(content) > 10000:
                            content = content[:10000] + "\n... (truncated)"
                        file_contexts.append(f"\n--- Current content of {fp} ---\n{content}\n--- End of {fp} ---")
                    except Exception:
                        pass

        if file_contexts:
            lines.append("\n# Current File Contents")
            lines.extend(file_contexts)

        user_message = "\n".join(lines)

        try:
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model=settings.claude_model,
                max_tokens=8000,
                system=IMPLEMENT_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )

            raw_text = response.content[0].text
            edits = _extract_edits(raw_text)

            # Apply edits
            applied = 0
            errors = []
            for edit in edits:
                try:
                    _apply_edit(repo_path, edit)
                    applied += 1
                except Exception as e:
                    errors.append(f"{edit.get('file_path', '?')}: {str(e)}")

            results.append({
                "tier": tier_name,
                "edits_applied": applied,
                "edits_total": len(edits),
                "errors": errors,
            })

        except Exception as e:
            log.error("Implementation failed for %s: %s", tier_name, e)
            results.append({
                "tier": tier_name,
                "edits_applied": 0,
                "errors": [str(e)],
            })

    return results


def _extract_edits(text: str) -> list[dict]:
    """Extract a JSON array of edits from Claude's response."""
    text = text.lstrip("\ufeff").strip()

    # Strip code fences
    if text.startswith("```"):
        first_newline = text.index("\n")
        text = text[first_newline + 1:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()
            text = text[: text.rfind("```")].rstrip()

    text = text.strip()

    # Try direct parse
    if text.startswith("["):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # Find array boundaries
    first_bracket = text.find("[")
    last_bracket = text.rfind("]")
    if first_bracket != -1 and last_bracket > first_bracket:
        try:
            return json.loads(text[first_bracket:last_bracket + 1])
        except json.JSONDecodeError:
            pass

    log.warning("Could not parse edits from Claude response")
    return []


def _apply_edit(repo_path: str, edit: dict):
    """Apply a single search-and-replace edit to a file."""
    file_path = edit.get("file_path", "")
    search = edit.get("search", "")
    replace = edit.get("replace", "")

    if not file_path or not search:
        raise ValueError("Missing file_path or search text")

    full_path = Path(repo_path) / file_path
    if not full_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    content = full_path.read_text(encoding="utf-8")

    if search not in content:
        # Try a more lenient match (strip whitespace differences)
        search_stripped = " ".join(search.split())
        lines = content.split("\n")
        found = False
        for i, line in enumerate(lines):
            if search_stripped in " ".join(line.split()):
                # Found approximate match — use the original line
                content = content.replace(line, replace, 1)
                found = True
                break
        if not found:
            raise ValueError(f"Search text not found in {file_path}")
    else:
        content = content.replace(search, replace, 1)

    full_path.write_text(content, encoding="utf-8")


# ──────────────────────────────────────
# Git / PR Operations
# ──────────────────────────────────────

def clone_repo(repo_url: str, branch: str = "main") -> str:
    """Clone repo to temp dir, return path."""
    tmp_dir = tempfile.mkdtemp(prefix="seo-pr-")
    log.info("Cloning %s (branch: %s) to %s", repo_url, branch, tmp_dir)

    result = subprocess.run(
        ["git", "clone", "--depth", "1", "--branch", branch, repo_url, tmp_dir],
        capture_output=True, text=True, timeout=120,
    )

    if result.returncode != 0:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise RuntimeError(f"git clone failed: {result.stderr}")

    return tmp_dir


def create_seo_pr(repo_path: str, repo_url: str, branch_name: str, base_branch: str, plan: dict, domain: str) -> dict:
    """Git operations: branch, commit per tier, push, create PR via gh CLI.

    CRITICAL: Never merges to main/master — only creates PRs.
    """
    def _git(cmd, **kwargs):
        r = subprocess.run(
            ["git"] + cmd,
            capture_output=True, text=True, cwd=repo_path, timeout=60,
            **kwargs,
        )
        return r

    # Create branch
    result = _git(["checkout", "-b", branch_name])
    if result.returncode != 0:
        raise RuntimeError(f"Failed to create branch: {result.stderr}")

    tiers = plan.get("tiers", [])
    total_changes = 0

    for tier in tiers:
        tier_name = tier.get("tier", "P0")
        changes = tier.get("changes", [])
        if not changes:
            continue

        # Check for uncommitted changes
        status = _git(["status", "--porcelain"])
        if not status.stdout.strip():
            continue

        # Stage all changes
        _git(["add", "-A"])

        # Commit this tier
        desc = tier.get("description", "SEO improvements")
        commit_msg = f"[SEO {tier_name}] {domain}: {desc}"
        commit_result = _git(["commit", "-m", commit_msg])
        if commit_result.returncode == 0:
            total_changes += len(changes)

    if total_changes == 0:
        return {"pr_url": "", "changes_made": 0, "error": "No changes to commit"}

    # Push
    push_result = _git(["push", "origin", branch_name])
    if push_result.returncode != 0:
        return {
            "pr_url": "",
            "changes_made": total_changes,
            "error": f"Push failed: {push_result.stderr}",
        }

    # Build PR body
    pr_body = _build_pr_body(plan, domain)
    pr_title = f"[SEO] {domain}: Automated improvements ({datetime.date.today().strftime('%Y-%m-%d')})"

    # Extract repo slug from URL
    repo_slug = repo_url.replace("https://github.com/", "").replace(".git", "")

    # Create PR via gh CLI
    pr_result = subprocess.run(
        [
            "gh", "pr", "create",
            "--repo", repo_slug,
            "--title", pr_title,
            "--body", pr_body,
            "--base", base_branch,
            "--head", branch_name,
            "--label", "seo-auto",
        ],
        capture_output=True, text=True, cwd=repo_path, timeout=60,
    )

    if pr_result.returncode != 0:
        # Try creating the label first if that's the issue
        if "label" in pr_result.stderr.lower():
            subprocess.run(
                ["gh", "label", "create", "seo-auto", "--repo", repo_slug,
                 "--description", "Automated SEO improvements", "--color", "0E8A16"],
                capture_output=True, text=True, timeout=30,
            )
            pr_result = subprocess.run(
                [
                    "gh", "pr", "create",
                    "--repo", repo_slug,
                    "--title", pr_title,
                    "--body", pr_body,
                    "--base", base_branch,
                    "--head", branch_name,
                    "--label", "seo-auto",
                ],
                capture_output=True, text=True, cwd=repo_path, timeout=60,
            )

    pr_url = pr_result.stdout.strip() if pr_result.returncode == 0 else ""
    error = pr_result.stderr.strip() if pr_result.returncode != 0 else ""

    return {
        "pr_url": pr_url,
        "changes_made": total_changes,
        "branch_name": branch_name,
        "error": error,
    }


def _build_pr_body(plan: dict, domain: str) -> str:
    """Build the PR description."""
    tiers = plan.get("tiers", [])
    all_changes = []
    tier_sections = []

    for tier in tiers:
        tier_name = tier.get("tier", "P0")
        changes = tier.get("changes", [])
        if not changes:
            continue

        all_changes.extend(changes)
        change_lines = []
        for c in changes:
            change_type = c.get("change_type", "update")
            page = c.get("page_url", c.get("file_path", "N/A"))
            justification = c.get("justification", "")
            change_lines.append(f"- **{change_type}** on `{page}`: {justification}")

        tier_sections.append(
            f"### {tier_name} — {tier.get('description', '')} ({len(changes)} changes)\n"
            + "\n".join(change_lines)
        )

    body = f"""## SEO Improvements for {domain}

Automated analysis identified {len(all_changes)} improvements across {len([t for t in tiers if t.get('changes')])} priority tiers.

{chr(10).join(tier_sections)}

---
*Generated by Pressroom SEO Pipeline. Human review required before merge.*"""

    return body


# ──────────────────────────────────────
# Main Pipeline
# ──────────────────────────────────────

async def run_seo_pipeline(org_id: int, config: dict, api_key: str, update_fn=None) -> dict:
    """Full SEO pipeline:
    1. Run SEO audit on the domain
    2. Analyze audit results with Claude to create tiered improvement plan
    3. Clone the target repo
    4. Implement changes via Claude API
    5. Create branch, commit tier-by-tier, push, create PR

    config keys: domain, repo_url, base_branch, run_id, company_description
    update_fn: async callable(updates_dict) to update the run record in real-time
    """
    domain = config["domain"]
    repo_url = config["repo_url"]
    base_branch = config.get("base_branch", "main")
    run_id = config.get("run_id")

    async def _update(updates):
        if update_fn:
            try:
                await update_fn(updates)
            except Exception as e:
                log.warning("Failed to update run status: %s", e)

    result = {
        "status": "complete",
        "pr_url": "",
        "branch_name": "",
        "changes_made": 0,
        "plan": {},
        "error": "",
    }

    repo_path = None

    try:
        # ── Phase 1: SEO Audit ──
        await _update({"status": "auditing"})
        log.info("[SEO PR] Auditing %s...", domain)

        audit_result = await audit_domain(domain, max_pages=15, api_key=api_key)
        if "error" in audit_result:
            result["status"] = "failed"
            result["error"] = f"Audit failed: {audit_result['error']}"
            await _update({"status": "failed", "error": result["error"]})
            return result

        audit_id = audit_result.get("audit_id")
        await _update({"audit_id": audit_id} if audit_id else {})

        # ── Phase 2: Claude Analysis ──
        await _update({"status": "analyzing"})
        log.info("[SEO PR] Analyzing audit results...")

        repo_info = {
            "repo_url": repo_url,
            "base_branch": base_branch,
            "company_description": config.get("company_description", ""),
        }
        plan = await analyze_seo_issues(audit_result, repo_info, api_key)

        if plan.get("error"):
            result["status"] = "failed"
            result["error"] = f"Analysis failed: {plan['error']}"
            await _update({"status": "failed", "error": result["error"], "plan_json": json.dumps(plan)})
            return result

        result["plan"] = plan
        await _update({"plan_json": json.dumps(plan)})

        # Count total planned changes
        total_planned = sum(len(t.get("changes", [])) for t in plan.get("tiers", []))
        if total_planned == 0:
            result["status"] = "complete"
            result["error"] = "No SEO improvements identified"
            await _update({"status": "complete", "error": result["error"], "plan_json": json.dumps(plan)})
            return result

        # ── Phase 3: Clone Repo ──
        await _update({"status": "implementing"})
        log.info("[SEO PR] Cloning %s...", repo_url)

        repo_path = clone_repo(repo_url, base_branch)

        # ── Phase 4: Implement Changes ──
        log.info("[SEO PR] Implementing %d planned changes...", total_planned)

        tier_results = await implement_seo_changes(plan, repo_path, api_key)

        total_applied = sum(r.get("edits_applied", 0) for r in tier_results)
        result["changes_made"] = total_applied

        if total_applied == 0:
            result["status"] = "complete"
            result["error"] = "No changes could be applied to repo files"
            await _update({
                "status": "complete",
                "error": result["error"],
                "changes_made": 0,
                "plan_json": json.dumps(plan),
            })
            return result

        # ── Phase 5: Create PR ──
        await _update({"status": "pushing", "changes_made": total_applied})
        log.info("[SEO PR] Pushing changes and creating PR...")

        today = datetime.date.today().strftime("%Y-%m-%d")
        clean_domain = domain.replace("https://", "").replace("http://", "").replace("/", "_")
        branch_name = f"seo-auto/{clean_domain}/{today}"

        pr_result = create_seo_pr(repo_path, repo_url, branch_name, base_branch, plan, domain)

        result["pr_url"] = pr_result.get("pr_url", "")
        result["branch_name"] = pr_result.get("branch_name", branch_name)
        result["changes_made"] = pr_result.get("changes_made", total_applied)

        if pr_result.get("error") and not pr_result.get("pr_url"):
            result["status"] = "failed"
            result["error"] = pr_result["error"]
        else:
            result["status"] = "complete"
            if pr_result.get("error"):
                result["error"] = pr_result["error"]

        await _update({
            "status": result["status"],
            "pr_url": result["pr_url"],
            "branch_name": result["branch_name"],
            "changes_made": result["changes_made"],
            "error": result["error"],
            "completed_at": datetime.datetime.utcnow(),
            "plan_json": json.dumps(plan),
        })

        return result

    except Exception as e:
        log.error("[SEO PR] Pipeline failed: %s", e, exc_info=True)
        result["status"] = "failed"
        result["error"] = str(e)
        await _update({
            "status": "failed",
            "error": str(e),
            "completed_at": datetime.datetime.utcnow(),
        })
        return result

    finally:
        # Cleanup temp repo
        if repo_path and os.path.exists(repo_path):
            try:
                shutil.rmtree(repo_path)
            except Exception:
                pass
