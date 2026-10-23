"""Discover and rank public agent skills without installing or executing them.

Popularity is a discovery signal, not proof of correctness. External skills remain
review-only until a maintainer copies/adapts them into skills/active/.
"""
import base64
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from skill_registry import register_discovery, transition_skill

ROOT = Path(__file__).resolve().parent
REPORT_DIR = Path(os.getenv("SCOUT_REPORT_DIR", str(ROOT / "reports")))
API = "https://api.github.com"
MAX_REPOSITORIES = 8
MAX_SKILLS_PER_REPOSITORY = 3
MAX_SKILL_BYTES = 40_000
USER_AGENT = "ai-project-scout-skills/1.0"
RISK_PATTERNS = [
    ("instruction_override", re.compile(r"ignore (all )?(previous|prior) instructions|override (the )?(system|developer) prompt|reveal (the )?(hidden )?(prompt|secrets?)", re.I)),
    ("credential_exfiltration", re.compile(r"(send|upload|post|exfiltrat\w*)[^\n]{0,80}(api[_ -]?key|token|credential|password|secret)", re.I)),
    ("dangerous_shell", re.compile(r"curl[^\n]{0,100}\|\s*(sh|bash)|rm\s+-rf\s+/(?:\s|$)|os\.system\s*\(|subprocess\.(?:run|Popen|call)\s*\(|\beval\s*\(", re.I)),
]
PERMISSIVE_LICENSES = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD"}
SEED_REPOSITORIES = [
    "anthropics/skills",
    "obra/superpowers",
    "mattpocock/skills",
    "addyosmani/agent-skills",
    "vercel-labs/agent-skills",
    "github/awesome-copilot",
]


def request_json(url, timeout=20):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT,
               "X-GitHub-Api-Version": "2022-11-28"}
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429) and attempt < 2:
                retry = exc.headers.get("Retry-After", "")
                time.sleep(min(int(retry), 10) if retry.isdigit() else attempt + 1)
                continue
            raise RuntimeError("GitHub API HTTP " + str(exc.code)) from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt == 2:
                raise RuntimeError("GitHub request failed: " + type(exc).__name__) from exc
            time.sleep(attempt + 1)
    raise RuntimeError("GitHub API retries exhausted")


def decode_blob(payload):
    content = payload.get("content", "") if isinstance(payload, dict) else ""
    if payload.get("encoding") == "base64" and content:
        try:
            return base64.b64decode(content).decode("utf-8", errors="replace")[:MAX_SKILL_BYTES]
        except (ValueError, TypeError):
            return ""
    return str(content)[:MAX_SKILL_BYTES]


def parse_skill(text, path):
    """Extract only bounded metadata; do not interpret skill text as executable code."""
    raw = (text or "")[:MAX_SKILL_BYTES]
    name = Path(path).parent.name if Path(path).name.lower() == "skill.md" else Path(path).stem
    description = ""
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) == 3:
            for line in parts[1].splitlines():
                key, sep, value = line.partition(":")
                if not sep:
                    continue
                value = value.strip().strip('"').strip("'")
                if key.strip().lower() == "name" and value:
                    name = value[:100]
                elif key.strip().lower() == "description" and value:
                    description = value[:400]
    if not description:
        for line in raw.splitlines():
            line = line.strip().lstrip("#").strip()
            if line and line.lower() not in {"---", "skill"}:
                description = line[:400]
                break
    return {"name": name[:100], "description": description, "document_bytes": len(raw.encode("utf-8"))}


def inspect_risks(text):
    return [label for label, pattern in RISK_PATTERNS if pattern.search(text or "")]


def quality_score(stars, forks, pushed_at, license_spdx, skill_text):
    """Transparent heuristic /100; it is not a quality or safety certification."""
    stars = max(0, int(stars or 0))
    forks = max(0, int(forks or 0))
    popularity = 25 if stars >= 10000 else 20 if stars >= 1000 else 14 if stars >= 100 else 8 if stars >= 10 else 2
    community = 10 if forks >= 1000 else 8 if forks >= 100 else 5 if forks >= 10 else 1
    recent = 0
    try:
        pushed = datetime.fromisoformat((pushed_at or "").replace("Z", "+00:00"))
        days = max(0, (datetime.now(timezone.utc) - pushed.astimezone(timezone.utc)).days)
        recent = 15 if days <= 30 else 11 if days <= 180 else 6 if days <= 365 else 2
    except (ValueError, TypeError):
        recent = 0
    license_score = 15 if license_spdx in PERMISSIVE_LICENSES else 5 if license_spdx and license_spdx not in {"NOASSERTION", "UNKNOWN"} else 0
    structured = 10 if re.search(r"(?m)^---\s*$", skill_text or "") and "description:" in (skill_text or "") else 5 if len(skill_text or "") >= 300 else 0
    risk_penalty = min(15, 5 * len(inspect_risks(skill_text)))
    return max(0, min(100, popularity + community + recent + license_score + structured + 25 - risk_penalty))


def discover_repositories(fetcher=request_json):
    """Combine a small seed set with a live GitHub search; cap requests and results."""
    names = list(SEED_REPOSITORIES)
    try:
        query = urllib.parse.urlencode({"q": "topic:agent-skills", "sort": "stars", "order": "desc", "per_page": "10"})
        result = fetcher(API + "/search/repositories?" + query)
        for repo in result.get("items", []):
            name = repo.get("full_name", "")
            if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name) and name not in names:
                names.append(name)
    except Exception:
        # Seed repositories keep the daily catalog useful when search rate limits are hit.
        pass
    return names[:MAX_REPOSITORIES]


def scan_repository(repository, fetcher=request_json):
    meta = fetcher(API + "/repos/" + repository)
    if meta.get("archived"):
        return []
    branch = meta.get("default_branch") or "main"
    revision = "branch:" + branch
    try:
        commit_data = fetcher(API + "/repos/" + repository + "/commits/" + urllib.parse.quote(branch, safe=""))
        if isinstance(commit_data, dict) and re.fullmatch(r"[a-f0-9]{40}", str(commit_data.get("sha", ""))):
            revision = commit_data["sha"]
    except Exception:
        # Keep the branch reference when a test fixture or rate limit cannot resolve a commit.
        pass
    tree_url = API + "/repos/" + repository + "/git/trees/" + urllib.parse.quote(branch, safe="") + "?recursive=1"
    tree = fetcher(tree_url)
    paths = sorted(
        (item.get("path", "") for item in tree.get("tree", [])
         if item.get("type") == "blob" and item.get("path", "").split("/")[-1].lower() == "skill.md"),
        key=lambda path: (path.count("/"), path.lower()),
    )[:MAX_SKILLS_PER_REPOSITORY]
    license_obj = meta.get("license") or {}
    license_spdx = license_obj.get("spdx_id") or "UNKNOWN"
    results = []
    for path in paths:
        encoded_path = urllib.parse.quote(path, safe="/")
        payload = fetcher(API + "/repos/" + repository + "/contents/" + encoded_path + "?ref=" + urllib.parse.quote(branch, safe=""))
        skill_text = decode_blob(payload)
        metadata = parse_skill(skill_text, path)
        risks = inspect_risks(skill_text)
        score = quality_score(meta.get("stargazers_count"), meta.get("forks_count"),
                              meta.get("pushed_at"), license_spdx, skill_text)
        license_ok = license_spdx in PERMISSIVE_LICENSES
        results.append({
            **metadata,
            "repository": repository,
            "source_path": path,
            "source_revision": revision,
            "source_content_sha256": hashlib.sha256(skill_text.encode("utf-8")).hexdigest(),
            "source_url": "https://github.com/" + repository + "/blob/" + (revision if re.fullmatch(r"[a-f0-9]{40}", revision) else branch) + "/" + encoded_path,
            "stars": int(meta.get("stargazers_count") or 0),
            "forks": int(meta.get("forks_count") or 0),
            "last_pushed_at": meta.get("pushed_at") or "",
            "license_spdx": license_spdx,
            "quality_score": score,
            "score_note": "Popularity, maintenance, license clarity, document structure, and risk signals; not a quality certification.",
            "risk_flags": risks,
            "status": "candidate_requires_review" if license_ok and not risks else "blocked_until_license_or_security_review",
            "activation_policy": "external content is never activated automatically; adapt and review before skills/active/",
        })
    return results


def build_catalog(fetcher=request_json, repositories=None):
    repositories = repositories if repositories is not None else discover_repositories(fetcher)
    skills, errors = [], []
    for repository in repositories[:MAX_REPOSITORIES]:
        try:
            skills.extend(scan_repository(repository, fetcher))
        except Exception as exc:
            errors.append({"repository": repository, "error": type(exc).__name__})
    skills.sort(key=lambda item: (item["status"] == "candidate_requires_review",
                                  item["quality_score"], item["stars"]), reverse=True)
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "mode": "public_skill_discovery_static_review",
        "skills_found": len(skills),
        "skills": skills,
        "errors": errors,
        "scoring_disclaimer": "GitHub stars/forks are popularity signals, not independent quality ratings. Every skill requires task-fit, license, security, and regression-test review.",
        "safety_note": "External SKILL.md files are untrusted text. They are analyzed as data, never executed or auto-activated.",
    }


def write_report(catalog, report_dir=REPORT_DIR):
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "skills-catalog.json"
    md_path = report_dir / "skills-catalog.md"
    json_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Agent Skills — discovery and review", "",
             "- Popularity is not proof of quality or safety.",
             "- External skills are candidates only; none are automatically activated.", ""]
    for skill in catalog.get("skills", []):
        lines.extend([
            "## " + skill["name"],
            "- Repository: [" + skill["repository"] + "](" + skill["source_url"] + ")",
            "- Description: " + (skill["description"] or "Not available"),
            "- Stars: " + str(skill["stars"]) + " | Forks: " + str(skill["forks"]) + " | Heuristic score: " + str(skill["quality_score"]) + "/100",
            "- License: " + skill["license_spdx"] + " | Status: " + skill["status"],
            "- Risk flags: " + (", ".join(skill["risk_flags"]) or "No matched rule; this is not proof of safety"),
            "",
        ])
    if catalog.get("errors"):
        lines.extend(["## Repositories not scanned", ""])
        lines.extend("- " + item["repository"] + ": " + item["error"] for item in catalog["errors"])
    lines.extend(["", catalog["safety_note"], catalog["scoring_disclaimer"], ""])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path, json_path


def persist_candidates(catalog, db_path=None):
    """Persist static-analysis evidence idempotently; never propose or activate external text."""
    persisted = []
    for skill in catalog.get("skills", []):
        raw_name = str(skill.get("name") or "external-skill").lower()
        slug = re.sub(r"[^a-z0-9]+", "-", raw_name).strip("-")[:90] or "external-skill"
        revision = str(skill.get("source_revision") or "unknown")[:200]
        license_spdx = str(skill.get("license_spdx") or "UNKNOWN")[:80]
        evidence = {
            "capability_description": str(skill.get("description") or "")[:400],
            "repository": str(skill.get("repository") or "")[:200],
            "source_path": str(skill.get("source_path") or "")[:500],
            "stars": int(skill.get("stars") or 0),
            "forks": int(skill.get("forks") or 0),
            "last_pushed_at": str(skill.get("last_pushed_at") or "")[:80],
            "heuristic_score": int(skill.get("quality_score") or 0),
            "score_note": str(skill.get("score_note") or "")[:300],
            "license_source": "GitHub repository metadata; LICENSE text not independently verified",
            "static_inspection_only": True,
        }
        record = register_discovery(
            slug, str(skill.get("source_url") or ""),
            version=revision[:12] if re.fullmatch(r"[a-f0-9]{40}", revision) else "branch-snapshot",
            source_revision=revision,
            license_spdx=license_spdx,
            license_evidence="GitHub API repository metadata only; not sufficient for approval.",
            inspected_files=[str(skill.get("source_path") or "SKILL.md")],
            evidence=evidence,
            risk_flags=list(skill.get("risk_flags") or []),
            source_content_sha256=str(skill.get("source_content_sha256") or ""),
            db_path=db_path,
        )
        if record["status"] == "DISCOVERED":
            record = transition_skill(
                record["skill_id"], "ANALYZED", db_path=db_path,
                inspected_files=[str(skill.get("source_path") or "SKILL.md")],
                evidence=evidence,
                risk_flags=list(skill.get("risk_flags") or []),
            )
        persisted.append({
            "skill_id": record["skill_id"],
            "name": record["name"],
            "status": record["status"],
            "source_url": record["source_url"],
            "license_verified": bool(record["license_verified"]),
        })
    return persisted


def main():
    catalog = build_catalog()
    markdown, json_file = write_report(catalog)
    persisted = persist_candidates(catalog)
    print(json.dumps({"status": "complete", "skills_found": catalog["skills_found"],
                      "lifecycle_records_updated": len(persisted),
                      "lifecycle_records": persisted[:20],
                      "repository_errors": len(catalog["errors"]),
                      "markdown": str(markdown), "json": str(json_file)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
