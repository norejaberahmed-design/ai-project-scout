"""GitHub-wide AI agent catalog. Discovery is metadata/static inspection only."""
from __future__ import annotations

import base64
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from urllib.parse import quote

import requests

from .config import ROOT, setting, int_setting

DB_PATH = Path(setting("SCOUT_AGENT_DB_PATH", str(ROOT / "data" / "agents.sqlite3")))
API = "https://api.github.com"
TIMEOUT = 15
MAX_REPOS_PER_QUERY = 30
MAX_QUERIES = 6
MAX_README_CHARS = 12000

SEARCH_QUERIES = [
    'agent in:name,description stars:>=1 archived:false',
    '"AI agent" in:description,readme stars:>=1 archived:false',
    '"autonomous agent" in:description,readme stars:>=1 archived:false',
    '"multi-agent" in:description,readme stars:>=1 archived:false',
    'LLM agent framework in:description,readme stars:>=1 archived:false',
]

CATEGORY_RULES = {
    "coding": ("coding agent", "code agent", "software engineer", "programming agent", "coding", "code generation"),
    "research": ("research agent", "deep research", "web research", "research assistant"),
    "browser": ("browser agent", "web agent", "browser automation", "web automation"),
    "business": ("business agent", "business automation", "operations agent"),
    "sales": ("sales agent", "lead generation", "crm agent", "outbound sales"),
    "finance": ("financial agent", "finance agent", "trading agent", "investment agent"),
    "cybersecurity": ("security agent", "cybersecurity", "threat detection", "penetration testing"),
    "database": ("database agent", "sql agent", "data query agent", "text-to-sql"),
    "devops": ("devops agent", "sre agent", "incident response", "infrastructure agent"),
    "data": ("data agent", "analytics agent", "data analysis", "data pipeline"),
    "customer_support": ("customer support agent", "customer service agent", "support chatbot"),
    "workflow": ("workflow agent", "automation agent", "orchestration", "task automation"),
    "voice": ("voice agent", "speech agent", "conversational voice"),
    "robotics": ("robotics agent", "robot agent", "embodied agent"),
    "personal": ("personal assistant agent", "personal agent", "desktop assistant"),
    "multi_agent": ("multi-agent", "multi agent", "agent teams", "multiple agents"),
}
AGENT_SIGNALS = ("agent", "agents", "autonomous", "multi-agent", "llm-powered", "tool-using")
FRAMEWORK_SIGNALS = ("framework", "sdk", "library", "platform", "toolkit")
TUTORIAL_SIGNALS = ("tutorial", "course", "examples", "cookbook", "awesome list", "awesome-")
TOOL_SIGNALS = ("browser", "search", "terminal", "python", "shell", "sql", "api", "memory", "tools", "filesystem")


class DiscoveryError(RuntimeError):
    pass


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    with _connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS agents (
          github_id INTEGER PRIMARY KEY,
          full_name TEXT NOT NULL UNIQUE,
          html_url TEXT NOT NULL,
          name TEXT NOT NULL,
          description TEXT NOT NULL DEFAULT '',
          kind TEXT NOT NULL,
          categories_json TEXT NOT NULL DEFAULT '[]',
          capabilities_json TEXT NOT NULL DEFAULT '[]',
          language TEXT,
          license_spdx TEXT,
          stars INTEGER NOT NULL DEFAULT 0,
          forks INTEGER NOT NULL DEFAULT 0,
          open_issues INTEGER NOT NULL DEFAULT 0,
          pushed_at TEXT,
          default_branch TEXT,
          archived INTEGER NOT NULL DEFAULT 0,
          fork INTEGER NOT NULL DEFAULT 0,
          score INTEGER NOT NULL DEFAULT 0,
          evidence_json TEXT NOT NULL DEFAULT '[]',
          readme_excerpt TEXT NOT NULL DEFAULT '',
          first_seen INTEGER NOT NULL,
          last_seen INTEGER NOT NULL,
          last_scanned INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_agents_kind ON agents(kind);
        CREATE INDEX IF NOT EXISTS idx_agents_stars ON agents(stars DESC);
        CREATE INDEX IF NOT EXISTS idx_agents_updated ON agents(last_scanned DESC);
        CREATE TABLE IF NOT EXISTS discovery_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          query TEXT NOT NULL,
          started_at INTEGER NOT NULL,
          completed_at INTEGER,
          found INTEGER NOT NULL DEFAULT 0,
          inspected INTEGER NOT NULL DEFAULT 0,
          errors_json TEXT NOT NULL DEFAULT '[]'
        );
        """)


def _headers():
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = setting("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    return headers


def _get(url):
    try:
        response = requests.get(url, headers=_headers(), timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise DiscoveryError("GitHub connection failed: " + str(exc)[:160]) from exc
    if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
        reset = response.headers.get("X-RateLimit-Reset", "")
        raise DiscoveryError("GitHub API rate limit reached; reset timestamp: " + reset)
    if response.status_code == 401:
        raise DiscoveryError("GitHub rejected the configured token (401).")
    if response.status_code >= 400:
        raise DiscoveryError(f"GitHub API returned HTTP {response.status_code}.")
    try:
        return response.json()
    except ValueError as exc:
        raise DiscoveryError("GitHub returned invalid JSON.") from exc


def _classify(repo, readme):
    text = " ".join([
        str(repo.get("name") or ""), str(repo.get("description") or ""),
        " ".join(repo.get("topics") or []), readme[:MAX_README_CHARS]
    ]).lower()
    categories = [key for key, terms in CATEGORY_RULES.items() if any(term in text for term in terms)]
    signals = sum(1 for term in AGENT_SIGNALS if term in text)
    if any(term in text for term in TUTORIAL_SIGNALS):
        kind = "tutorial_or_collection"
    elif any(term in text for term in FRAMEWORK_SIGNALS):
        kind = "framework_or_library"
    elif signals >= 2 or ("agent" in text and any(x in text for x in ("autonomous", "tools", "memory", "llm"))):
        kind = "agent"
    elif "agent" in text or "agents" in text:
        kind = "agent_project_unverified"
    else:
        kind = "related_project_unverified"
    capabilities = [term for term in TOOL_SIGNALS if re.search(r"\b" + re.escape(term) + r"\b", text)]
    return kind, sorted(set(categories)), sorted(set(capabilities)), text


def _score(repo, kind, readme, evidence):
    score = 0
    if kind == "agent": score += 25
    elif kind == "framework_or_library": score += 18
    elif kind == "agent_project_unverified": score += 12
    elif kind == "tutorial_or_collection": score += 5
    if readme: score += 15
    if repo.get("license") and repo["license"].get("spdx_id"): score += 10
    if repo.get("pushed_at"): score += 10
    score += min(20, int((repo.get("stargazers_count") or 0) ** 0.5))
    if evidence: score += 10
    return min(100, score)


def _readme(full_name):
    try:
        payload = _get(f"{API}/repos/{full_name}/readme")
        raw = base64.b64decode(payload.get("content", "")).decode("utf-8", "replace")
        return raw[:MAX_README_CHARS], payload.get("html_url", "")
    except (DiscoveryError, ValueError, TypeError):
        return "", ""


def _save(repo, readme, readme_url):
    kind, categories, capabilities, _ = _classify(repo, readme)
    evidence = [
        {"claim": "Repository metadata", "source": repo.get("html_url", ""), "basis": "GitHub repository API fields"},
    ]
    if readme_url:
        evidence.append({"claim": "Description and capability signals", "source": readme_url,
                         "basis": "Static README text inspection; not runtime verification"})
    if (repo.get("license") or {}).get("spdx_id"):
        evidence.append({"claim": "Declared license", "source": repo.get("html_url", "") + "/blob/" + str(repo.get("default_branch") or "main") + "/LICENSE",
                         "basis": "GitHub metadata SPDX identifier; license text not independently certified"})
    now = int(time.time())
    score = _score(repo, kind, readme, evidence)
    license_obj = repo.get("license") or {}
    values = (
        int(repo["id"]), repo.get("full_name", ""), repo.get("html_url", ""), repo.get("name", ""),
        repo.get("description") or "", kind, json.dumps(categories), json.dumps(capabilities),
        repo.get("language"), license_obj.get("spdx_id"), int(repo.get("stargazers_count") or 0),
        int(repo.get("forks_count") or 0), int(repo.get("open_issues_count") or 0),
        repo.get("pushed_at"), repo.get("default_branch"), int(bool(repo.get("archived"))),
        int(bool(repo.get("fork"))), score, json.dumps(evidence), readme, now, now, now
    )
    with _connect() as db:
        db.execute("""
        INSERT INTO agents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(github_id) DO UPDATE SET
          full_name=excluded.full_name, html_url=excluded.html_url, name=excluded.name,
          description=excluded.description, kind=excluded.kind, categories_json=excluded.categories_json,
          capabilities_json=excluded.capabilities_json, language=excluded.language,
          license_spdx=excluded.license_spdx, stars=excluded.stars, forks=excluded.forks,
          open_issues=excluded.open_issues, pushed_at=excluded.pushed_at,
          default_branch=excluded.default_branch, archived=excluded.archived, fork=excluded.fork,
          score=excluded.score, evidence_json=excluded.evidence_json, readme_excerpt=excluded.readme_excerpt,
          last_seen=excluded.last_seen, last_scanned=excluded.last_scanned
        """, values)
    return kind


def discover_agents(query="", max_results=60):
    init_db()
    max_results = max(1, min(int(max_results), 100))
    queries = list(SEARCH_QUERIES)
    query = str(query or "").strip()[:180]
    if query:
        queries.insert(0, f"{query} agent in:name,description,readme")
    queries = queries[:MAX_QUERIES]
    started = int(time.time())
    errors, found, inspected = [], set(), 0
    with _connect() as db:
        cur = db.execute("INSERT INTO discovery_runs(query,started_at) VALUES (?,?)",
                         (query or "broad GitHub AI agent discovery", started))
        run_id = cur.lastrowid
    for search_query in queries:
        if len(found) >= max_results:
            break
        try:
            url = API + "/search/repositories?q=" + quote(search_query, safe="") + "&sort=updated&order=desc&per_page=30"
            payload = _get(url)
            for repo in payload.get("items", []):
                full = repo.get("full_name")
                if not full or repo.get("archived") or full.lower() in found:
                    continue
                found.add(full.lower())
                readme, readme_url = _readme(full)
                _save(repo, readme, readme_url)
                inspected += 1
                if inspected >= max_results:
                    break
        except DiscoveryError as exc:
            errors.append({"query": search_query, "error": str(exc)})
            if "rate limit" in str(exc).lower():
                break
    with _connect() as db:
        db.execute("UPDATE discovery_runs SET completed_at=?, found=?, inspected=?, errors_json=? WHERE id=?",
                   (int(time.time()), len(found), inspected, json.dumps(errors), run_id))
    if not inspected and errors:
        raise DiscoveryError(errors[0]["error"])
    return {"run_id": run_id, "queries_run": len(queries), "repositories_found": len(found),
            "repositories_inspected": inspected, "errors": errors, "mode": "catalog_only"}


def list_agents(query="", category="", kind="", sort="relevance", limit=50, offset=0):
    init_db()
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    clauses, params = [], []
    if query:
        clauses.append("(full_name LIKE ? OR name LIKE ? OR description LIKE ? OR readme_excerpt LIKE ?)")
        like = "%" + str(query)[:100] + "%"
        params.extend([like] * 4)
    if category:
        clauses.append("categories_json LIKE ?")
        params.append('%"' + str(category)[:60] + '"%')
    if kind:
        clauses.append("kind = ?")
        params.append(str(kind)[:60])
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    ordering = {"stars": "stars DESC", "updated": "pushed_at DESC", "name": "name COLLATE NOCASE"}.get(sort, "score DESC, stars DESC")
    with _connect() as db:
        total = db.execute("SELECT COUNT(*) FROM agents" + where, params).fetchone()[0]
        rows = db.execute("SELECT * FROM agents" + where + " ORDER BY " + ordering + " LIMIT ? OFFSET ?",
                          params + [limit, offset]).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            for key, target in (("categories_json", "categories"), ("capabilities_json", "capabilities"), ("evidence_json", "evidence")):
                item[target] = json.loads(item.pop(key) or "[]")
            item.pop("readme_excerpt", None)
            items.append(item)
        return {"items": items, "total": total, "limit": limit, "offset": offset}


def get_agent(github_id):
    init_db()
    with _connect() as db:
        row = db.execute("SELECT * FROM agents WHERE github_id=?", (int(github_id),)).fetchone()
        if not row:
            return None
        item = dict(row)
        for key, target in (("categories_json", "categories"), ("capabilities_json", "capabilities"), ("evidence_json", "evidence")):
            item[target] = json.loads(item.pop(key) or "[]")
        return item


def discovery_status():
    init_db()
    with _connect() as db:
        total = db.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
        kinds = {row[0]: row[1] for row in db.execute("SELECT kind, COUNT(*) FROM agents GROUP BY kind")}
        last = db.execute("SELECT id,started_at,completed_at,found,inspected,errors_json FROM discovery_runs ORDER BY id DESC LIMIT 1").fetchone()
        return {"total": total, "by_kind": kinds, "last_run": dict(last) if last else None,
                "database": "SQLite", "mode": "catalog_only"}
