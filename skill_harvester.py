"""Discover and quarantine reusable public agent skills from licensed GitHub repositories.

This module imports procedural SKILL.md documents only. It never imports Python modules,
installs dependencies, executes upstream code, or activates a candidate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from component_acquisition import (
    ALLOWED_LICENSES,
    _decode_content,
    inspect_repository,
    parse_repository_url,
    request_json,
)
from skill_registry import register_discovery, transition_skill
from skill_runtime import inspect_candidate, save_proposal
from web_search import search_web

ROOT = Path(__file__).resolve().parent
API = "https://api.github.com"
MAX_REPOSITORIES = 10
MAX_PROPOSALS = 3
MAX_SKILL_BYTES = 20_000
DENIED_NAMES = {"", "skill", "skills", "default", "template", "example"}
# Seed a high-value, MIT-licensed general agent-skills repository before broad discovery.
SEED_REPOSITORIES = ("https://github.com/obra/superpowers",)
SEARCH_QUERIES = (
    "agent skills research coding in:name,description stars:>=10",
    "SKILL.md software engineering agent in:readme stars:>=10",
)
SKILL_PRIORITY = {
    "verification-before-completion": 100,
    "writing-plans": 90,
    "receiving-code-review": 80,
    "requesting-code-review": 75,
    "systematic-debugging": 70,
    "test-driven-development": 65,
    "brainstorming": 50,
}
PLATFORM_DEPENDENCY_PATTERNS = (
    re.compile(r"\bbrowser_skill_cli\b", re.I),
    re.compile(r"\bDINGTALK_[A-Z0-9_]+\b|钉钉", re.I),
    re.compile(r"\bCowork\b|Skill Center", re.I),
    re.compile(r"\bAIRFLOW_(?:API_URL|AUTH_TOKEN|USERNAME|PASSWORD)\b|\brun_af\b|astro-airflow-mcp", re.I),
    re.compile(r"\bsubagents?\b|\bparallel agents?\b|\bdispatch(?:ing)?[- ](?:parallel[- ])?agents?\b", re.I),
)
LOCAL_MARKDOWN_REFERENCE = re.compile(r"(?<![/:A-Za-z0-9])([A-Za-z0-9_.-]+\.md)(?:#[A-Za-z0-9_-]+)?")


def search_skill_repositories(query: str, limit: int = MAX_REPOSITORIES, fetcher=request_json) -> list[dict]:
    """Search public GitHub repositories; search results are leads, not trusted evidence."""
    bounded = max(1, min(int(limit), MAX_REPOSITORIES))
    params = urllib.parse.urlencode({
        "q": query[:200],
        "sort": "updated",
        "order": "desc",
        "per_page": str(bounded),
    })
    data = fetcher(f"{API}/search/repositories?{params}")
    items = []
    seen = set()
    for item in data.get("items", []):
        if not isinstance(item, dict):
            continue
        url = str(item.get("html_url") or "")
        try:
            owner, name = parse_repository_url(url)
        except ValueError:
            continue
        canonical = f"https://github.com/{owner}/{name}"
        if canonical.lower() in seen or item.get("archived") or item.get("fork"):
            continue
        seen.add(canonical.lower())
        license_data = item.get("license") or {}
        items.append({
            "url": canonical,
            "repository": str(item.get("full_name") or f"{owner}/{name}"),
            "description": str(item.get("description") or "")[:400],
            "stars": int(item.get("stargazers_count") or 0),
            "license_spdx": str(license_data.get("spdx_id") or "UNKNOWN"),
            "pushed_at": str(item.get("pushed_at") or ""),
        })
    return items


def _slug(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    if not value or value in DENIED_NAMES:
        return ""
    return value[:64].rstrip("-")


def _get_skill_text(repository_url: str, revision: str, path: str, fetcher=request_json) -> str:
    owner, repo = parse_repository_url(repository_url)
    encoded_path = urllib.parse.quote(path, safe="/")
    encoded_revision = urllib.parse.quote(revision, safe="")
    payload = fetcher(f"{API}/repos/{owner}/{repo}/contents/{encoded_path}?ref={encoded_revision}")
    raw = _decode_content(payload)
    if len(raw) > MAX_SKILL_BYTES:
        raise ValueError("SKILL.md exceeds the bounded size limit.")
    try:
        document = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("SKILL.md is not valid UTF-8 text.") from None
    if "\x00" in document:
        raise ValueError("SKILL.md contains binary data.")
    return document


def harvest_repository(repository_url: str, *, root: Path | None = None,
                       db_path: str | Path | None = None, fetcher=request_json,
                       max_skills: int = MAX_PROPOSALS) -> dict:
    """Inspect one repository and save its eligible SKILL.md files as review-only proposals."""
    owner, repo = parse_repository_url(repository_url)
    canonical = f"https://github.com/{owner}/{repo}"
    info = inspect_repository(canonical, fetcher=fetcher)
    if info.get("license_spdx") not in ALLOWED_LICENSES or not info.get("license_text_verified"):
        raise ValueError("A verified allowlisted license is required.")
    tree_url = f"{API}/repos/{owner}/{repo}/git/trees/{info['revision']}?recursive=1"
    tree_data = fetcher(tree_url)
    if tree_data.get("truncated"):
        raise ValueError("GitHub truncated the skill tree; refusing an incomplete discovery pass.")
    candidates = [
        item for item in tree_data.get("tree", [])
        if isinstance(item, dict)
        and item.get("type") == "blob"
        and item.get("mode") != "120000"
        and Path(str(item.get("path", ""))).name.lower() == "skill.md"
        and isinstance(item.get("size"), int)
        and 0 < item.get("size") <= MAX_SKILL_BYTES
    ]
    candidates.sort(key=lambda item: (
        -SKILL_PRIORITY.get(Path(str(item.get("path", ""))).parent.name.lower(), 0),
        str(item.get("path", "")).lower(),
    ))
    if not candidates:
        return {"repository": info["repository"], "status": "NO_SKILL_DOCUMENT", "proposals": []}

    proposals = []
    proposal_limit = max(1, min(int(max_skills), MAX_PROPOSALS))
    for item in candidates:
        if sum(1 for proposal in proposals if proposal.get("status") == "PROPOSED_REVIEW_REQUIRED") >= proposal_limit:
            break
        upstream_path = str(item["path"])
        upstream_document = _get_skill_text(canonical, info["revision"], upstream_path, fetcher)
        unsupported = [pattern.pattern for pattern in PLATFORM_DEPENDENCY_PATTERNS
                       if pattern.search(upstream_document)]
        if unsupported:
            proposals.append({
                "source_path": upstream_path,
                "status": "SKIPPED_PLATFORM_SPECIFIC",
                "reason": "Skill depends on an external integration not provided by this agent.",
            })
            continue
        referenced_docs = set(LOCAL_MARKDOWN_REFERENCE.findall(upstream_document))
        if referenced_docs:
            # The runtime currently loads one SKILL.md, not arbitrary upstream reference trees.
            # Refuse incomplete copies rather than pretending referenced docs were imported.
            proposals.append({
                "source_path": upstream_path,
                "status": "SKIPPED_SUPPORT_FILES_NOT_BUNDLED",
                "referenced_files": sorted(referenced_docs)[:12],
            })
            continue
        checked = inspect_candidate(upstream_document)
        if not checked.get("valid"):
            proposals.append({
                "source_path": upstream_path,
                "status": "REJECTED_STATIC_CHECKS",
                "errors": checked.get("errors", []),
                "warnings": checked.get("warnings", []),
            })
            continue

        name = _slug(checked["metadata"].get("name", ""))
        if not name:
            proposals.append({"source_path": upstream_path, "status": "REJECTED_INVALID_NAME"})
            continue
        license_paths = info.get("license_file_paths", [])
        if not license_paths:
            proposals.append({"source_path": upstream_path, "name": name, "status": "REJECTED_MISSING_LICENSE_TEXT"})
            continue
        try:
            upstream_license = _get_skill_text(canonical, info["revision"], str(license_paths[0]), fetcher)
        except (RuntimeError, ValueError):
            proposals.append({"source_path": upstream_path, "name": name, "status": "REJECTED_LICENSE_TEXT_UNAVAILABLE"})
            continue
        document = upstream_document.rstrip() + (
            "\n\n## Source provenance\n"
            f"- Original repository: {info['repository_url']}\n"
            f"- Original file: {info['repository_url']}/blob/{info['revision']}/"
            f"{urllib.parse.quote(upstream_path, safe='/')}\n"
            f"- Immutable source revision: {info['revision']}\n"
            f"- Declared SPDX license: {info['license_spdx']}\n"
            "- Import status: untrusted proposal; not executed, installed, or activated.\n"
            "- The original license text is preserved in UPSTREAM_LICENSE.txt.\n"
        )
        if len(document.encode("utf-8")) > MAX_SKILL_BYTES:
            proposals.append({"source_path": upstream_path, "name": name, "status": "REJECTED_SIZE_LIMIT"})
            continue
        checked_final = inspect_candidate(document)
        if not checked_final.get("valid"):
            proposals.append({
                "source_path": upstream_path, "name": name,
                "status": "REJECTED_PROVENANCE_CHECK",
                "errors": checked_final.get("errors", []),
            })
            continue

        proposal = save_proposal(document, root=root)
        if not proposal.get("valid"):
            proposals.append({
                "source_path": upstream_path, "name": name, "status": "SKIPPED_EXISTING_OR_INVALID",
                "errors": proposal.get("errors", []),
            })
            continue

        proposal_dir = Path(proposal["saved_path"]).parent
        attribution = (
            f"# Upstream skill attribution\n\n"
            f"- Repository: {info['repository_url']}\n"
            f"- Skill file: {info['repository_url']}/blob/{info['revision']}/"
            f"{urllib.parse.quote(upstream_path, safe='/')}\n"
            f"- Immutable revision: {info['revision']}\n"
            f"- Declared SPDX license: {info['license_spdx']}\n"
            f"- Original license file: {', '.join(str(p) for p in license_paths)}\n"
            "- This is an untrusted proposal. It has not been executed, installed, approved, or activated.\n"
        )
        (proposal_dir / "ATTRIBUTION.md").write_text(attribution, encoding="utf-8")
        (proposal_dir / "UPSTREAM_LICENSE.txt").write_text(upstream_license, encoding="utf-8")
        source_url = (
            f"{info['repository_url']}/blob/{info['revision']}/"
            f"{urllib.parse.quote(upstream_path, safe='/')}"
        )
        digest = hashlib.sha256(upstream_document.encode("utf-8")).hexdigest()
        try:
            record = register_discovery(
                name, source_url, version=checked_final["metadata"].get("version", "1"),
                source_revision=info["revision"], license_spdx=info["license_spdx"],
                license_evidence=(
                    f"GitHub repository metadata and LICENSE text checked at revision {info['revision']}; "
                    "license is on the explicit acquisition allowlist."
                ),
                inspected_files=[upstream_path, *info.get("license_file_paths", [])],
                evidence={
                    "capability": checked_final["metadata"].get("description", ""),
                    "repository": info["repository"],
                    "source_path": upstream_path,
                    "source_revision": info["revision"],
                    "license_text_verified": True,
                    "static_skill_validation": checked_final,
                    "policy": "proposal only; human review required",
                },
                risk_flags=[],
                content=upstream_document,
                source_content_sha256=digest,
                db_path=db_path,
            )
            transition_skill(
                record["skill_id"], "ANALYZED", db_path=db_path,
                inspected_files=[upstream_path, *info.get("license_file_paths", [])],
                evidence={
                    "capability": checked_final["metadata"].get("description", ""),
                    "source_revision": info["revision"],
                    "license_text_verified": True,
                    "static_validation": "passed",
                },
            )
            transition_skill(
                record["skill_id"], "PROPOSED", db_path=db_path, content=document
            )
            proposals.append({
                "name": name, "skill_id": record["skill_id"],
                "source_path": upstream_path, "source_url": source_url,
                "revision": info["revision"], "license_spdx": info["license_spdx"],
                "status": "PROPOSED_REVIEW_REQUIRED",
                "proposal_path": proposal.get("saved_path"),
                "auto_activated": False,
            })
        except Exception as exc:
            # Do not label a proposal as lifecycle-complete if registry persistence failed.
            proposals.append({
                "name": name, "source_path": upstream_path, "status": "REGISTRY_ERROR",
                "error": str(exc)[:300],
                "proposal_path": proposal.get("saved_path"),
            })
    return {
        "repository": info["repository"],
        "revision": info["revision"],
        "license_spdx": info["license_spdx"],
        "license_text_verified": True,
        "status": "INSPECTED",
        "proposals": proposals,
    }



def discover_video_related_repositories(*, searcher=search_web, fetcher=request_json) -> tuple[list[dict], list[dict]]:
    """Use public web/YouTube tutorials as discovery leads, then resolve linked source repos.

    A video is never treated as a license or permission to copy its code. Only linked
    repositories whose GitHub metadata names an allowlisted license can proceed.
    """
    repository_candidates: list[dict] = []
    video_leads: list[dict] = []
    seen_videos: set[str] = set()
    seen_repositories: set[str] = set()
    discovery_results: list[dict] = []
    search_errors: list[str] = []
    # Search in both languages so Arabic tutorials and English source repositories
    # can lead to the same licensed-skill review pipeline.
    for query in (
        "open source AI agent skills tutorial source code",
        "مهارات وكلاء الذكاء الاصطناعي شرح فيديو كود المصدر مفتوح المصدر",
    ):
        try:
            discovery = searcher(query, timeout=12)
            discovery_results.extend(
                item for item in discovery.get("results", []) if isinstance(item, dict)
            )
        except (RuntimeError, ValueError, TypeError) as exc:
            search_errors.append(str(exc)[:200])
    if not discovery_results:
        reason = "; ".join(search_errors)[:200] or "No usable public-web results."
        return [], [{"status": "VIDEO_DISCOVERY_UNAVAILABLE", "reason": reason}]

    videos = [item for item in discovery_results
              if "youtube.com/watch" in str(item.get("url", "")) or "youtu.be/" in str(item.get("url", ""))]
    for video in videos[:3]:
        video_url = str(video.get("url", ""))
        if not video_url or video_url in seen_videos:
            continue
        seen_videos.add(video_url)
        title = str(video.get("title", ""))[:180]
        video_leads.append({
            "status": "VIDEO_DISCOVERED_NOT_COPIED",
            "title": title,
            "url": video_url,
            "reason": "Video is a discovery lead only; source code is imported only from a separately verified, licensed repository.",
        })
        try:
            related = searcher(f'"{title}" source code GitHub repository license', timeout=12)
        except (RuntimeError, ValueError, TypeError):
            continue
        possible_urls = [str(item.get("url", "")) for item in related.get("results", [])]
        possible_urls += re.findall(
            r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",
            " ".join(str(item.get("snippet", "")) for item in related.get("results", []))
        )
        for candidate_url in possible_urls:
            try:
                owner, name = parse_repository_url(candidate_url)
            except ValueError:
                continue
            canonical = f"https://github.com/{owner}/{name}"
            if canonical.lower() in seen_repositories:
                continue
            seen_repositories.add(canonical.lower())
            try:
                meta = fetcher(f"{API}/repos/{owner}/{name}")
            except (RuntimeError, ValueError):
                continue
            if meta.get("archived") or meta.get("fork"):
                continue
            license_data = meta.get("license") or {}
            license_id = str(license_data.get("spdx_id") or "UNKNOWN")
            if license_id not in ALLOWED_LICENSES:
                continue
            repository_candidates.append({
                "url": canonical,
                "repository": str(meta.get("full_name") or f"{owner}/{name}"),
                "description": str(meta.get("description") or "")[:400],
                "stars": int(meta.get("stargazers_count") or 0),
                "license_spdx": license_id,
                "pushed_at": str(meta.get("pushed_at") or ""),
                "discovered_from_video": video_url,
                "video_title": title,
            })
            if len(repository_candidates) >= 5:
                return repository_candidates, video_leads
    return repository_candidates, video_leads

def run_harvest(*, limit: int = MAX_PROPOSALS, root: Path | None = None,
                db_path: str | Path | None = None, fetcher=request_json) -> dict:
    """Search, inspect, and stage at most three eligible skill documents."""
    max_proposals = max(1, min(int(limit), MAX_PROPOSALS))
    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "policy": "Public sources only; verified permissive license; immutable revision; quarantined proposals; no code execution.",
        "repositories_searched": 0,
        "proposals_created": 0,
        "results": [],
    }
    seen_repositories = set()
    seen_names = set()
    discovered = [
        {
            "url": url,
            "repository": url.rstrip("/").split("/")[-2] + "/" + url.rstrip("/").split("/")[-1],
            "license_spdx": "MIT",
            "description": "Seeded general-purpose agent skill repository",
        }
        for url in SEED_REPOSITORIES
    ]
    for query in SEARCH_QUERIES:
        try:
            discovered.extend(search_skill_repositories(query, fetcher=fetcher))
        except (RuntimeError, ValueError) as exc:
            report["results"].append({
                "query": query, "status": "SEARCH_ERROR", "error": str(exc)[:250]
            })

    video_repositories, video_leads = discover_video_related_repositories(fetcher=fetcher)
    report["results"].extend(video_leads)
    discovered.extend(video_repositories)

    for candidate in discovered:
        remaining = max_proposals - report["proposals_created"]
        if remaining <= 0:
            break
        url = candidate.get("url", "")
        if not url or url.lower() in seen_repositories:
            continue
        seen_repositories.add(url.lower())
        report["repositories_searched"] += 1
        if candidate.get("license_spdx") not in ALLOWED_LICENSES:
            report["results"].append({
                "repository": candidate.get("repository", url),
                "status": "SKIPPED_LICENSE_METADATA",
                "license_spdx": candidate.get("license_spdx", "UNKNOWN"),
            })
            continue
        try:
            result = harvest_repository(
                url, root=root, db_path=db_path, fetcher=fetcher, max_skills=remaining
            )
        except (RuntimeError, ValueError, OSError) as exc:
            report["results"].append({
                "repository": candidate.get("repository", url),
                "status": "SKIPPED",
                "reason": str(exc)[:300],
            })
            continue
        for proposal in result.get("proposals", []):
            if proposal.get("status") != "PROPOSED_REVIEW_REQUIRED":
                continue
            name = proposal.get("name", "")
            if name in seen_names:
                proposal["status"] = "DUPLICATE_NAME_IN_RUN"
                continue
            seen_names.add(name)
            report["proposals_created"] += 1
        report["results"].append(result)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Harvest licensed public agent skill documents into review-only proposals.")
    parser.add_argument("--limit", type=int, default=2, choices=(1, 2, 3))
    parser.add_argument("--repository", help="Inspect one public GitHub repository instead of searching.")
    parser.add_argument("--report", default="reports/skill-harvest.json")
    parser.add_argument("--root", default=None, help="Project root for proposal storage.")
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else ROOT
    db_path = os.getenv("SCOUT_SKILL_DB_PATH", str(root / "data" / "skills.sqlite"))
    if args.repository:
        report = {"generated_at": datetime.now(timezone.utc).isoformat(),
                  "results": [harvest_repository(args.repository, root=root, db_path=db_path)]}
    else:
        report = run_harvest(limit=args.limit, root=root, db_path=db_path)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
