"""Discover and quarantine reusable public agent skills from licensed GitHub repositories.

This module imports procedural SKILL.md documents plus bounded, licensed text support files.
It never installs dependencies, executes upstream code, or activates a candidate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from component_acquisition import (
    ALLOWED_LICENSES,
    _decode_content,
    inspect_repository,
    parse_repository_url,
    request_json,
    _safe_relative_path,
)
from skill_registry import register_discovery, transition_skill
from skill_runtime import inspect_candidate, save_proposal

ROOT = Path(__file__).resolve().parent
API = "https://api.github.com"
MAX_REPOSITORIES = 10
MAX_PROPOSALS = 3
MAX_SKILL_BYTES = 20_000
MAX_SUPPORT_FILES = 12
MAX_SUPPORT_BYTES = 100_000
DENIED_NAMES = {"", "skill", "skills", "default", "template", "example"}
# Seed a high-value, MIT-licensed general agent-skills repository before broad discovery.
SEED_REPOSITORIES = ("https://github.com/obra/superpowers",)
SEARCH_QUERIES = (
    "open source agent skills license:mit stars:>=20",
    "agent-skills license:mit stars:>=20",
    "SKILL.md AI agent in:readme license:mit stars:>=20",
    "coding agent skills in:name,description license:mit stars:>=20",
    "portable agent skill library license:mit stars:>=20",
    "Claude Code skills in:name,description license:mit stars:>=20",
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
    # Reject instructions tied to a third-party analytics CLI/integration absent from this app.
    re.compile(r"\bdeepline\b|snowflake_(?:get_semantic_layer|run_semantic_query)", re.I),
    re.compile(r"\bagentskillshub\b|@agentskillshub/", re.I),
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


def _quality_gate(content: str) -> tuple[bool, list[str]]:
    """Reject placeholder skills that merely restate a task without reusable procedure."""
    errors = []
    normalized = " ".join((content or "").lower().split())
    placeholder_phrases = (
        "do the task described above",
        "perform the task described above",
        "complete the task as requested",
        "follow the instructions above",
        "insert skill instructions here",
        "todo: add skill instructions",
        "replace this with the actual skill",
    )
    for phrase in placeholder_phrases:
        if phrase in normalized:
            errors.append("Placeholder instruction detected: " + phrase)
    body = (content or "").split("## Source provenance", 1)[0]
    action_lines = [
        line.strip() for line in body.splitlines()
        if re.match(r"^(?:[-*]|(?:step\s+)?[1-9][0-9]?[.)])\s+\S.{17,}$", line.strip(), re.I)
    ]
    if len(action_lines) < 3:
        errors.append("Skill needs at least three concrete, non-trivial action lines.")
    if len(body) < 350:
        errors.append("Skill body is too short to provide a reusable procedure.")
    return not errors, errors


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
        declares_runtime_tools = bool(re.search(r"(?im)^allowed-tools\s*:", upstream_document))
        if unsupported or declares_runtime_tools:
            proposals.append({
                "source_path": upstream_path,
                "status": "SKIPPED_PLATFORM_SPECIFIC",
                "reason": (
                    "Skill depends on an external integration or declares tool permissions "
                    "for a different agent runtime; only portable procedures are eligible."
                ),
            })
            continue
        referenced_docs = set(LOCAL_MARKDOWN_REFERENCE.findall(upstream_document))
        skill_parent = PurePosixPath(upstream_path).parent
        support_candidates = []
        for tree_item in tree_data.get("tree", []):
            if not isinstance(tree_item, dict) or tree_item.get("type") != "blob" or tree_item.get("mode") == "120000":
                continue
            support_path = str(tree_item.get("path", ""))
            if not support_path or support_path == upstream_path:
                continue
            safe_path = _safe_relative_path(support_path)
            if safe_path is None:
                continue
            parent = PurePosixPath(support_path).parent
            in_skill_folder = str(skill_parent) != "." and (parent == skill_parent or str(parent).startswith(str(skill_parent) + "/"))
            explicitly_referenced = PurePosixPath(support_path).name in referenced_docs
            if in_skill_folder or (str(skill_parent) == "." and parent == PurePosixPath(".") and explicitly_referenced):
                size = tree_item.get("size")
                if isinstance(size, int) and 0 <= size <= MAX_SKILL_BYTES:
                    support_candidates.append({"path": support_path, "size": size})
        support_candidates.sort(key=lambda item: item["path"].lower())
        support_candidates = support_candidates[:MAX_SUPPORT_FILES]
        support_candidates = [item for item in support_candidates if item["size"] > 0]
        available_basenames = {PurePosixPath(item["path"]).name for item in support_candidates}
        missing_references = sorted(name for name in referenced_docs if name not in available_basenames)
        if missing_references:
            proposals.append({
                "source_path": upstream_path,
                "status": "SKIPPED_SUPPORT_FILES_NOT_BUNDLED",
                "referenced_files": missing_references[:12],
            })
            continue
        if sum(item["size"] for item in support_candidates) > MAX_SUPPORT_BYTES:
            bounded_support = []
            support_total = 0
            for support_item in support_candidates:
                if support_total + support_item["size"] > MAX_SUPPORT_BYTES:
                    continue
                bounded_support.append(support_item)
                support_total += support_item["size"]
            support_candidates = bounded_support
        quality_ok, quality_errors = _quality_gate(upstream_document)
        if not quality_ok:
            proposals.append({
                "source_path": upstream_path,
                "status": "REJECTED_LOW_QUALITY_OR_TEMPLATE",
                "errors": quality_errors,
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
            + ("- Related source/document files are bundled under bundle/ for review only.\n"
               if support_candidates else "- No additional eligible support files were bundled.\n")
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
        bundle_manifest = []
        bundle_total = 0
        for support_item in support_candidates:
            try:
                support_text = _get_skill_text(canonical, info["revision"], support_item["path"], fetcher)
            except (RuntimeError, ValueError):
                continue
            support_bytes = support_text.encode("utf-8")
            if len(support_bytes) != support_item["size"] or len(support_bytes) > MAX_SKILL_BYTES:
                continue
            if bundle_total + len(support_bytes) > MAX_SUPPORT_BYTES:
                continue
            source_path_obj = PurePosixPath(support_item["path"])
            relative = source_path_obj.relative_to(skill_parent) if str(skill_parent) != "." else source_path_obj
            if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
                continue
            target = proposal_dir / "bundle" / Path(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            if (proposal_dir / "bundle").resolve() not in target.resolve().parents:
                raise RuntimeError("Unsafe bundled skill path.")
            target.write_text(support_text, encoding="utf-8")
            bundle_total += len(support_bytes)
            bundle_manifest.append({
                "path": relative.as_posix(),
                "source_path": support_item["path"],
                "source_url": f"{info['repository_url']}/blob/{info['revision']}/{urllib.parse.quote(support_item['path'], safe='/')}",
                "bytes": len(support_bytes),
                "sha256": hashlib.sha256(support_bytes).hexdigest(),
                "executed": False,
            })
        (proposal_dir / "BUNDLE_MANIFEST.json").write_text(
            json.dumps({"files": bundle_manifest, "total_bytes": bundle_total,
                        "policy": "review-only; no dependency install or execution"},
                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
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
                inspected_files=[upstream_path, *info.get("license_file_paths", []), *[item["source_path"] for item in bundle_manifest]],
                evidence={
                    "capability": checked_final["metadata"].get("description", ""),
                    "repository": info["repository"],
                    "source_path": upstream_path,
                    "source_revision": info["revision"],
                    "license_text_verified": True,
                    "static_skill_validation": checked_final,
                    "bundled_support_files": bundle_manifest,
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
                "bundled_file_count": len(bundle_manifest),
                "bundled_bytes": bundle_total,
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



def run_harvest(*, limit: int = MAX_PROPOSALS, root: Path | None = None,
                db_path: str | Path | None = None, fetcher=request_json) -> dict:
    """Search public GitHub efficiently; inspect the seeded skill source before broad search."""
    max_proposals = max(1, min(int(limit), MAX_PROPOSALS))
    max_inspections = 18
    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "policy": "GitHub public sources only; verified permissive license; immutable revision; quarantined proposals; no code execution.",
        "repositories_searched": 0,
        "proposals_created": 0,
        "results": [],
    }
    seen_repositories: set[str] = set()
    seen_names: set[str] = set()

    def inspect_candidate(candidate: dict) -> None:
        if report["proposals_created"] >= max_proposals or report["repositories_searched"] >= max_inspections:
            return
        url = str(candidate.get("url") or "")
        if not url or url.lower() in seen_repositories:
            return
        seen_repositories.add(url.lower())
        report["repositories_searched"] += 1
        if candidate.get("license_spdx") not in ALLOWED_LICENSES:
            report["results"].append({
                "repository": candidate.get("repository", url),
                "status": "SKIPPED_LICENSE_METADATA",
                "license_spdx": candidate.get("license_spdx", "UNKNOWN"),
            })
            return
        try:
            result = harvest_repository(
                url, root=root, db_path=db_path, fetcher=fetcher,
                max_skills=max_proposals - report["proposals_created"],
            )
        except (RuntimeError, ValueError, OSError) as exc:
            report["results"].append({
                "repository": candidate.get("repository", url),
                "status": "SKIPPED",
                "reason": str(exc)[:300],
            })
            return
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

    # Check the known general-purpose skill source first. Do not spend search quota
    # on broad queries if this source already provides enough eligible skill documents.
    for url in SEED_REPOSITORIES:
        inspect_candidate({
            "url": url,
            "repository": "/".join(url.rstrip("/").split("/")[-2:]),
            "license_spdx": "MIT",
        })
        if report["proposals_created"] >= max_proposals:
            return report

    # Search queries sequentially and stop as soon as enough eligible skills are found.
    # A hard inspection cap bounds API calls even if results contain no usable skills.
    for query in SEARCH_QUERIES:
        if report["proposals_created"] >= max_proposals or report["repositories_searched"] >= max_inspections:
            break
        try:
            candidates = search_skill_repositories(query, fetcher=fetcher)
        except (RuntimeError, ValueError) as exc:
            report["results"].append({
                "query": query, "status": "SEARCH_ERROR", "error": str(exc)[:250]
            })
            continue
        for candidate in candidates:
            inspect_candidate(candidate)
            if report["proposals_created"] >= max_proposals or report["repositories_searched"] >= max_inspections:
                break
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
