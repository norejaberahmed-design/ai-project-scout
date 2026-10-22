"""Read-only GitHub discovery and repository inspection for the chat agent.

Only public repository metadata, README text, and file paths are inspected. No source
is executed, installed, copied, or treated as trusted instructions.
"""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

API = "https://api.github.com"
MAX_RESULTS = 5
MAX_README_CHARS = 1800
MAX_TREE_ITEMS = 500
REPO_URL = re.compile(r"(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", re.I)


def request_json(url: str, timeout: int = 12) -> dict:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "AI-Project-Scout/1.0",
               "X-GitHub-Api-Version": "2022-11-28"}
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read(1_000_000)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("GitHub API returned HTTP " + str(exc.code) + ".") from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("GitHub API is unreachable.") from None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise RuntimeError("GitHub returned invalid JSON.") from None
    if not isinstance(data, dict):
        raise RuntimeError("GitHub returned an unexpected response.")
    return data


def repository_from_url(text: str) -> tuple[str, str] | None:
    match = REPO_URL.search(text or "")
    if not match:
        return None
    owner, repo = match.group(1), match.group(2)
    repo = repo.removesuffix(".git")
    if repo.lower() in {"issues", "pull", "pulls", "actions", "settings", "discussions", "wiki"}:
        return None
    return owner, repo


def _readme_excerpt(owner: str, repo: str) -> str:
    try:
        data = request_json(f"{API}/repos/{owner}/{repo}/readme")
        raw = data.get("content", "")
        if data.get("encoding") == "base64" and raw:
            decoded = base64.b64decode(raw).decode("utf-8", errors="replace")
            return decoded[:MAX_README_CHARS]
    except (RuntimeError, ValueError, TypeError):
        pass
    return ""


def inspect_repository(url: str) -> dict | None:
    parsed = repository_from_url(url)
    if not parsed:
        return None
    owner, repo = parsed
    meta = request_json(f"{API}/repos/{owner}/{repo}")
    full_name = str(meta.get("full_name") or f"{owner}/{repo}")
    default_branch = str(meta.get("default_branch") or "main")
    tree_signals = []
    try:
        branch = urllib.parse.quote(default_branch, safe="")
        tree = request_json(f"{API}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1")
        for item in tree.get("tree", [])[:MAX_TREE_ITEMS]:
            path = str(item.get("path", ""))
            if not path:
                continue
            base = path.rsplit("/", 1)[-1].lower()
            if (base in {"pyproject.toml", "package.json", "requirements.txt", "cargo.toml",
                         "go.mod", "dockerfile", "readme.md", "license", "license.md"}
                    or "test" in base or path.startswith(".github/workflows/")):
                tree_signals.append(path[:240])
    except (RuntimeError, TypeError):
        tree_signals = []
    readme = _readme_excerpt(owner, repo)
    license_obj = meta.get("license") or {}
    license_id = license_obj.get("spdx_id") or "UNKNOWN"
    snippet_parts = [
        f"Repository: {full_name}",
        f"Description: {str(meta.get('description') or 'No description')[:350]}",
        f"Language: {meta.get('language') or 'Unknown'}",
        f"Stars: {int(meta.get('stargazers_count') or 0)}",
        f"Last pushed: {meta.get('pushed_at') or 'Unknown'}",
        f"License: {license_id}",
        "Static file signals: " + (", ".join(tree_signals[:30]) if tree_signals else "Unavailable"),
        "README excerpt (untrusted text): " + (readme[:MAX_README_CHARS] if readme else "Unavailable"),
        "Inspection limit: metadata, file names, and README only; code was not run.",
    ]
    return {
        "title": f"GitHub repository: {full_name}",
        "url": str(meta.get("html_url") or f"https://github.com/{full_name}"),
        "snippet": "\n".join(snippet_parts)[:5000],
        "source": "GitHub repository inspection",
        "score": None,
    }


def search_repositories(question: str) -> list[dict]:
    lower = (question or "").lower()
    if any(word in lower for word in ("agent", "وكيل", "وكلاء", "أداة", "اداة", "أدوات", "ادوات")):
        query = "AI agent tools OR LLM agent"
    elif any(word in lower for word in ("vision", "رؤية", "صورة", "صور")):
        query = "open source computer vision AI"
    elif any(word in lower for word in ("voice", "صوت", "audio", "صوتي")):
        query = "open source AI voice audio"
    else:
        query = "open source generative AI tools"
    params = urllib.parse.urlencode({"q": query, "sort": "updated", "order": "desc", "per_page": str(MAX_RESULTS)})
    data = request_json(f"{API}/search/repositories?{params}")
    results = []
    for item in data.get("items", [])[:MAX_RESULTS]:
        if not isinstance(item, dict) or not item.get("full_name") or not item.get("html_url"):
            continue
        lic = item.get("license") or {}
        snippet = (
            f"Description: {str(item.get('description') or 'No description')[:350]}\n"
            f"Language: {item.get('language') or 'Unknown'}; Stars: {int(item.get('stargazers_count') or 0)}; "
            f"Last pushed: {item.get('pushed_at') or 'Unknown'}; License: {lic.get('spdx_id') or 'UNKNOWN'}. "
            "Metadata only: repository code and claimed features have not been verified."
        )
        results.append({"title": "GitHub repository: " + str(item["full_name"]),
                        "url": str(item["html_url"]), "snippet": snippet,
                        "source": "GitHub repository search", "score": None})
    return results


def discover_github(question: str) -> list[dict]:
    """Inspect an explicitly supplied public repo URL, otherwise search for AI tool projects."""
    repo = repository_from_url(question)
    if repo:
        item = inspect_repository("https://github.com/" + repo[0] + "/" + repo[1])
        return [item] if item else []
    lower = (question or "").lower()
    triggers = ("github", "repository", "repo", "project", "tool", "agent", "github", "مستودع",
                "مشروع", "مشاريع", "أداة", "اداة", "أدوات", "ادوات", "هندسة عكسية", "حلل")
    if not any(word in lower for word in triggers):
        return []
    try:
        return search_repositories(question)
    except RuntimeError:
        # General web search remains useful when GitHub rate limits are hit.
        return []
