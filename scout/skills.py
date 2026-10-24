"""Discover, validate and stage public Markdown skills without executing them."""
import hashlib, json, re, time
from pathlib import Path
from urllib.parse import quote
import requests, yaml
from .config import ACTIVE_DIR, PROPOSED_DIR, int_setting, setting

ALLOWED_LICENSES = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD"}
MAX_SKILL_BYTES = 20_000
MAX_PROPOSALS_PER_DISCOVERY = 10
DENIED_NAMES = {"", "skill", "skills", "default", "template", "example"}
RISK_MARKERS = ("ignore all previous instructions", "reveal system prompt", "exfiltrate",
                "steal credentials", "send api key", "disable security", "bypass safeguards",
                "ignore your system prompt")

class SkillError(RuntimeError):
    pass

def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    if not value or value in DENIED_NAMES or value in {".", ".."}:
        return ""
    return value[:64].rstrip("-")

def license_text_matches(spdx: str, text: str) -> bool:
    sample = text[:100000].lower()
    markers = {
        "MIT": ("permission is hereby granted", "the software is provided"),
        "Apache-2.0": ("apache license", "version 2.0"),
        "BSD-2-Clause": ("redistribution and use in source and binary forms", "neither the name"),
        "BSD-3-Clause": ("redistribution and use in source and binary forms", "neither the name"),
        "ISC": ("permission to use, copy, modify, and/or distribute", "the software is provided"),
        "0BSD": ("permission to use, copy, modify, and/or distribute",),
    }
    required = markers.get(spdx)
    return bool(required and all(marker in sample for marker in required))

def parse_skill(content: str) -> tuple[dict, str]:
    if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_SKILL_BYTES:
        raise ValueError("skill document is too large or invalid")
    if "\x00" in content:
        raise ValueError("binary-like content rejected")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        raise ValueError("SKILL.md must start with YAML frontmatter")
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise ValueError("invalid YAML frontmatter") from exc
    if not isinstance(meta, dict):
        raise ValueError("frontmatter must be a YAML mapping")
    raw_name = str(meta.get("name", "")).strip()
    name = slugify(raw_name)
    description = str(meta.get("description", "")).strip()
    if not name or raw_name != name or not description or len(description) > 500:
        raise ValueError("name must use lowercase kebab-case and a valid description is required")
    lowered = content.lower()
    flags = [marker for marker in RISK_MARKERS if marker in lowered]
    if flags:
        raise ValueError("unsafe instruction marker detected: " + ", ".join(flags))
    return {"name": name, "description": description[:500],
            "version": str(meta.get("version", "1"))[:40]}, content[match.end():].strip()

def list_skills() -> dict:
    def scan(root: Path, active: bool) -> list[dict]:
        output = []
        if not root.exists():
            return output
        for path in sorted(root.glob("*/SKILL.md")):
            try:
                content = path.read_text(encoding="utf-8")
                meta, _ = parse_skill(content)
                mp = path.parent / "manifest.json"
                manifest = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}
                output.append({"name": meta["name"], "description": meta["description"],
                    "version": meta["version"], "status": "active" if active else "proposed",
                    "source_url": manifest.get("source_url", ""), "license": manifest.get("license", ""),
                    "sha256": manifest.get("sha256", "")})
            except (OSError, ValueError, yaml.YAMLError, json.JSONDecodeError):
                continue
        return output
    return {"active": scan(ACTIVE_DIR, True), "proposed": scan(PROPOSED_DIR, False)}

def _github_get(url: str) -> dict:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = setting("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    response = requests.get(url, headers=headers, timeout=15)
    if response.status_code >= 400:
        raise SkillError(f"GITHUB_HTTP_{response.status_code}")
    return response.json()

def task_search_terms(task_query: str) -> list[str]:
    """Turn an Arabic/English task into bounded English GitHub search terms."""
    text = str(task_query or "").lower()
    words = re.findall(r"[a-z][a-z0-9+#.-]{1,30}", text)
    stop = {"please", "help", "want", "need", "make", "build", "create", "write", "with",
            "from", "that", "this", "into", "using", "for", "and", "the", "you", "can", "github", "skill", "skills", "search", "discover", "find"}
    words = [word.strip(".-") for word in words if word not in stop and len(word.strip(".-")) > 1]
    arabic_map = {
        "تطبيق": ["web", "app", "application"], "موقع": ["website", "web"],
        "موقعا": ["website", "web"], "ويب": ["web", "frontend"],
        "بايثون": ["python"], "بايثون": ["python"], "برمجة": ["software", "coding"],
        "برمجي": ["software", "coding"], "برمجية": ["software", "coding"],
        "قاعدة": ["database", "sql"], "بيانات": ["database", "data"],
        "ذكاء": ["ai", "agent", "llm"], "اصطناعي": ["ai", "agent", "llm"],
        "ايجنت": ["agent", "llm"], "وكيل": ["agent", "llm"],
        "واجهة": ["frontend", "ui"], "خادم": ["backend", "api"],
        "api": ["api", "integration"], "اختبار": ["testing", "pytest"],
        "اختبارات": ["testing", "pytest"], "أمان": ["security"], "امن": ["security"],
        "بحث": ["research", "search"], "مهارة": ["agent", "skills"],
        "مهارات": ["agent", "skills"], "تلقائي": ["automation"], "اتصال": ["integration"],
    }
    for arabic, mapped in arabic_map.items():
        if arabic in text:
            words.extend(mapped)
    result, seen_terms = [], set()
    for word in words:
        word = re.sub(r"[^a-z0-9+#.-]", "", word).strip(".-")
        if word and word not in seen_terms:
            result.append(word)
            seen_terms.add(word)
        if len(result) >= 6:
            break
    return result


def _reverse_engineering_report(repository: str, revision: str, skill_path: str,
                                tree_paths: list[str], license_spdx: str,
                                skill_content: str = "",
                                repository_evidence: list[str] | None = None) -> str:
    """Create a reproducible static map of a skill repository without running its code."""
    names = [Path(path).name.lower() for path in tree_paths]
    readmes = [path for path in tree_paths if Path(path).name.lower().startswith("readme")][:3]
    manifests = [path for path in tree_paths if Path(path).name.lower() in {
        "pyproject.toml", "requirements.txt", "setup.py", "setup.cfg", "package.json",
        "go.mod", "cargo.toml", "pom.xml", "composer.json"
    }][:12]
    tests = [path for path in tree_paths if re.search(r"(^|/)(tests?|specs?)(/|$)|(^|/)(test_|.*_test\\.)", path.lower())][:20]
    entrypoints = [path for path in tree_paths if Path(path).name.lower() in {
        "main.py", "app.py", "cli.py", "__main__.py", "index.js", "index.ts", "server.py"
    }][:15]
    scripts = [path for path in tree_paths if Path(path).suffix.lower() in {
        ".py", ".js", ".ts", ".sh", ".ps1", ".go", ".rs"
    }][:30]
    headings = [line.strip("# ").strip() for line in skill_content.splitlines() if line.startswith("#")][:20]
    steps = [line.strip() for line in skill_content.splitlines() if re.match(r"^[0-9]+[.)]\s", line.strip()) or line.strip().startswith(("- ", "* "))][:25]
    commands = [line.strip() for line in skill_content.splitlines() if any(token in line for token in ("pip install", "npm install", "python ", "pytest", "npx "))][:20]
    lines = [
        "# Static reverse-engineering report", "",
        "- Repository: " + repository,
        "- Immutable revision: " + revision,
        "- Skill document: " + skill_path,
        "- Declared license: " + license_spdx,
        "- Analysis mode: static file-tree inspection only; no source code was executed.",
        "",
        "## Procedure analysis",
        "- Headings observed in the skill procedure: " + ("; ".join(headings) if headings else "no Markdown headings"),
        "- Numbered/bulleted procedural steps observed: " + str(len(steps)),
        "- Commands/install hints observed in text: " + ("; ".join(commands) if commands else "none detected"),
        "",
        "### Procedure steps (static excerpt)",
        *(["- " + step for step in steps] if steps else ["- No numbered or bulleted steps detected."]),
        "",
        "## Repository structure signals",
        "- README files: " + (", ".join(readmes) if readmes else "not found"),
        "- Dependency/build manifests: " + (", ".join(manifests) if manifests else "not found"),
        "- Test paths: " + (", ".join(tests) if tests else "not found"),
        "- Likely entry points: " + (", ".join(entrypoints) if entrypoints else "not identified"),
        "- Source/script files (first 30): " + (", ".join(scripts) if scripts else "not identified"),
        "",
        "## Source inspection evidence",
        *(["### " + item.splitlines()[0] + "\\n" + "\\n".join(item.splitlines()[1:]) for item in (repository_evidence or [])]
          if repository_evidence else ["No README, manifest, entry-point or test file could be inspected from the selected bounded set."]),
        "",
        "## Reuse decision",
        "- The SKILL.md procedure may be supplied to the language model as guidance after selection.",
        "- Source scripts and dependencies are not imported, installed, or executed by discovery.",
        "- If executable functionality is required, create a separate sandboxed package proposal, review dependencies and license obligations, add tests, and require explicit approval before activation.",
        "- File-tree names are evidence of repository structure, not proof that a feature works.",
    ]
    return "\n".join(lines) + "\n"


def _inspect_repository_files(owner: str, repo: str, revision: str,
                              tree_paths: list[str]) -> list[str]:
    """Read a tiny allowlisted set of public text files for static analysis only."""
    readmes = [p for p in tree_paths if Path(p).name.lower() in {"readme.md", "readme.rst", "readme.txt"}][:1]
    manifests = [p for p in tree_paths if Path(p).name.lower() in {
        "pyproject.toml", "requirements.txt", "package.json", "setup.cfg", "go.mod", "cargo.toml"
    }][:2]
    entrypoints = [p for p in tree_paths if Path(p).name.lower() in {
        "main.py", "app.py", "cli.py", "__main__.py", "index.js", "index.ts", "server.py"
    }][:2]
    tests = [p for p in tree_paths if re.search(r"(^|/)(tests?|specs?)(/|$)", p.lower()) and
             Path(p).suffix.lower() in {".py", ".js", ".ts"}][:1]
    selected = list(dict.fromkeys(readmes + manifests + entrypoints + tests))[:6]
    evidence, total = [], 0
    for path in selected:
        if len(path) > 240 or path.startswith(".") or any(part in {"", ".", ".."} for part in Path(path).parts):
            continue
        try:
            response = requests.get(
                f"https://raw.githubusercontent.com/{owner}/{repo}/{revision}/{quote(path, safe='/')}",
                timeout=10)
        except requests.RequestException:
            continue
        if response.status_code != 200:
            continue
        raw = response.content
        if not raw or len(raw) > 12000 or b"\x00" in raw or total + len(raw) > 30000:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if Path(path).name.lower().startswith("readme"):
            lines = text.splitlines()[:35]
            excerpt = "\n".join(lines)[:3000]
            evidence.append("README excerpt from " + path + ":\n" + excerpt)
        elif Path(path).suffix.lower() in {".toml", ".txt", ".json", ".cfg"}:
            excerpt = "\n".join(text.splitlines()[:50])[:3000]
            evidence.append("Dependency/build manifest excerpt from " + path + ":\n" + excerpt)
        elif re.search(r"(^|/)(tests?|specs?)(/|$)", path.lower()):
            test_names = [line.strip() for line in text.splitlines()
                          if re.search(r"def test_|it\(|describe\(|test\(", line)][:25]
            evidence.append("Test declarations from " + path + ":\n" +
                            ("\n".join(test_names) if test_names else "No conventional test names detected."))
        else:
            signatures = [line.strip() for line in text.splitlines()
                          if re.match(r"^\s*(?:import |from |def |class |async def |export |function |app\.(?:get|post|route)|if __name__)", line)][:35]
            evidence.append("Entry-point/source signatures from " + path + ":\n" +
                            ("\n".join(signatures) if signatures else "No common entry-point signatures detected."))
        total += len(raw)
    return evidence


def discover_skills(max_proposals: int = 2, task_query: str = "") -> dict:
    max_proposals = max(1, min(int(max_proposals), int_setting("SCOUT_MAX_SKILLS_PER_DISCOVERY", MAX_PROPOSALS_PER_DISCOVERY, 1, MAX_PROPOSALS_PER_DISCOVERY)))
    PROPOSED_DIR.mkdir(parents=True, exist_ok=True)
    # Search repository metadata and READMEs for real reusable skill packs.
    # GitHub code search is used as an additional source when GITHUB_TOKEN exists.
    task_terms = task_search_terms(task_query)
    queries = []
    if task_terms:
        queries.append(" ".join(task_terms) + " skills in:readme stars:>=1")
    queries.extend([
        "agent-skills in:name stars:>=5",
        "SKILL.md in:readme stars:>=5",
        "agent skills in:name,description stars:>=5",
        "awesome agent skills stars:>=5",
        "claude-code-skills in:name stars:>=5",
        "awesome-claude-skills stars:>=5",
        "copilot instructions skills in:readme stars:>=5",
        "openai agents skills in:readme stars:>=5",
        "gemini agent skills in:readme stars:>=5",
    ])
    repositories, seen = [], set()

    # Authenticated code search finds actual SKILL.md files rather than relying only
    # on repository descriptions. If no token is configured, public repository
    # search below remains available without exposing or requiring credentials.
    if setting("GITHUB_TOKEN"):
        for code_query in ("filename:SKILL.md", "path:skills filename:SKILL.md"):
            try:
                code_url = "https://api.github.com/search/code?q=" + quote(code_query, safe="") + "&per_page=20"
                code_payload = _github_get(code_url)
            except (requests.RequestException, ValueError, SkillError):
                continue
            for code_item in code_payload.get("items", []):
                full = str((code_item.get("repository") or {}).get("full_name", ""))
                if not full or full.lower() in seen:
                    continue
                seen.add(full.lower())
                try:
                    metadata = _github_get(f"https://api.github.com/repos/{full}")
                except (requests.RequestException, ValueError, SkillError):
                    continue
                if metadata.get("fork") or metadata.get("archived"):
                    continue
                license_id = str((metadata.get("license") or {}).get("spdx_id") or "UNKNOWN")
                if license_id not in ALLOWED_LICENSES:
                    continue
                repositories.append({
                    "full_name": full,
                    "license": license_id,
                    "branch": metadata.get("default_branch") or "main",
                    "html_url": metadata.get("html_url") or f"https://github.com/{full}",
                })

    for query_index, query in enumerate(queries):
        # Unauthenticated GitHub search has a much lower per-minute quota.
        if query_index and not setting("GITHUB_TOKEN"):
            time.sleep(1.1)
        url = "https://api.github.com/search/repositories?q=" + quote(query) + "&sort=updated&order=desc&per_page=15"
        try:
            payload = _github_get(url)
        except (requests.RequestException, ValueError, SkillError) as exc:
            if not repositories:
                raise SkillError(f"GitHub repository discovery failed: {str(exc)[:180]}") from exc
            continue
        for item in payload.get("items", []):
            full = str(item.get("full_name", ""))
            if not full or full.lower() in seen or item.get("fork") or item.get("archived"):
                continue
            seen.add(full.lower())
            license_id = str((item.get("license") or {}).get("spdx_id") or "UNKNOWN")
            if license_id in ALLOWED_LICENSES:
                repositories.append({"full_name": full, "license": license_id,
                    "branch": item.get("default_branch") or "main",
                    "html_url": item.get("html_url") or f"https://github.com/{full}"})
    created, inspected, skipped = [], 0, []
    for repo in repositories:
        if len(created) >= max_proposals:
            break
        full, branch = repo["full_name"], repo["branch"]
        try:
            owner, name = full.split("/", 1)
            commit = _github_get(f"https://api.github.com/repos/{full}/commits/{quote(branch, safe='')}")
            revision = str(commit.get("sha", ""))
            if not re.fullmatch(r"[0-9a-f]{40}", revision):
                skipped.append({"repository": full, "reason": "invalid immutable revision"}); continue
            tree = _github_get(f"https://api.github.com/repos/{full}/git/trees/{revision}?recursive=1")
            nodes = [x for x in tree.get("tree", []) if x.get("type") == "blob"]
            paths = [x["path"] for x in nodes if Path(x.get("path", "")).name.lower() == "skill.md"]
            license_paths = [x["path"] for x in nodes if Path(x.get("path", "")).name.lower()
                in {"license", "license.md", "license.txt", "license-mit"}]
            if not license_paths:
                skipped.append({"repository": full, "reason": "license text file not found"}); continue
            repository_evidence = _inspect_repository_files(
                owner, name, revision, [node.get("path", "") for node in nodes])
            lr = requests.get(f"https://raw.githubusercontent.com/{owner}/{name}/{revision}/{quote(license_paths[0], safe='/')}", timeout=15)
            if lr.status_code != 200 or not lr.text.strip() or not license_text_matches(repo["license"], lr.text):
                skipped.append({"repository": full, "reason": "license text does not match declared SPDX license"}); continue
            for path in paths[:5]:
                if len(created) >= max_proposals: break
                if len(path) > 240 or path.startswith("."): continue
                raw = requests.get(f"https://raw.githubusercontent.com/{owner}/{name}/{revision}/{quote(path, safe='/')}", timeout=15)
                if raw.status_code != 200: continue
                content = raw.text; inspected += 1
                try: meta, _ = parse_skill(content)
                except ValueError as exc:
                    skipped.append({"repository": full, "path": path, "reason": str(exc)[:180]}); continue
                slug = meta["name"]
                if (PROPOSED_DIR / slug).exists() or (ACTIVE_DIR / slug).exists():
                    skipped.append({"repository": full, "path": path, "reason": "skill name already exists"}); continue
                source_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
                stored_content = content.rstrip() + "\n"
                digest = hashlib.sha256(stored_content.encode("utf-8")).hexdigest()
                dest = PROPOSED_DIR / slug
                dest.mkdir(parents=True, exist_ok=False)
                (dest / "SKILL.md").write_text(stored_content, encoding="utf-8")
                (dest / "UPSTREAM_LICENSE.txt").write_text(lr.text[:100000], encoding="utf-8")
                # Preserve a small set of supporting text/source files referenced by the skill.
                # They remain quarantined and are never imported or executed by this process.
                skill_parent = str(Path(path).parent).replace("\\", "/")
                allowed_extensions = {".md", ".py", ".js", ".ts", ".sh", ".json", ".yaml", ".yml",
                                      ".toml", ".txt", ".sql", ".html", ".css"}
                supporting_files = []
                total_support_bytes = 0
                support_root = dest / "supporting_files"
                for node in nodes:
                    support_path = str(node.get("path", ""))
                    if support_path == path or not support_path or len(support_path) > 240:
                        continue
                    if node.get("mode") == "120000" or node.get("type") != "blob":
                        continue
                    parent_prefix = "" if skill_parent in {"", "."} else skill_parent.rstrip("/") + "/"
                    under_skill = support_path.startswith(parent_prefix) if parent_prefix else "/" not in support_path
                    relative = support_path[len(parent_prefix):] if under_skill else ""
                    allowed_area = (under_skill and relative and
                                    ("/" not in relative or relative.split("/", 1)[0].lower()
                                     in {"scripts", "references", "assets", "examples"}))
                    if not allowed_area or Path(support_path).suffix.lower() not in allowed_extensions:
                        continue
                    if Path(support_path).name.lower() == "skill.md":
                        continue
                    try:
                        support_response = requests.get(
                            f"https://raw.githubusercontent.com/{owner}/{name}/{revision}/{quote(support_path, safe='/')}",
                            timeout=15)
                    except requests.RequestException:
                        continue
                    if support_response.status_code != 200:
                        continue
                    support_text = support_response.text
                    support_bytes = support_text.encode("utf-8")
                    if (not support_text or "\\x00" in support_text or len(support_bytes) > 40000
                            or total_support_bytes + len(support_bytes) > 120000):
                        continue
                    if any(part in {"", ".", ".."} for part in Path(relative).parts):
                        continue
                    support_target = support_root / relative
                    support_target.parent.mkdir(parents=True, exist_ok=True)
                    support_target.write_bytes(support_bytes)
                    support_digest = hashlib.sha256(support_bytes).hexdigest()
                    supporting_files.append({"path": str(Path("supporting_files") / relative).replace("\\", "/"),
                                             "source_path": support_path, "sha256": support_digest,
                                             "size_bytes": len(support_bytes)})
                    total_support_bytes += len(support_bytes)
                    if len(supporting_files) >= 8:
                        break
                source_url = f"{repo['html_url']}/blob/{revision}/{quote(path, safe='/')}"
                (dest / "ATTRIBUTION.md").write_text(
                    f"# Attribution\n\n- Repository: {repo['html_url']}\n- File: {source_url}\n- Revision: {revision}\n- SPDX: {repo['license']}\n- Source SHA-256: {source_digest}\n- Stored SHA-256: {digest}\n- Status: proposal only; not executed or activated.\n", encoding="utf-8")
                (dest / "REVERSE_ENGINEERING.md").write_text(
                    _reverse_engineering_report(repo["html_url"], revision, path,
                                                [node.get("path", "") for node in nodes],
                                                repo["license"], content, repository_evidence),
                    encoding="utf-8")
                manifest = {"name": slug, "description": meta["description"], "source_url": source_url,
                    "repository": full, "revision": revision, "path": path, "license": repo["license"],
                    "license_text_verified": True, "sha256": digest, "source_sha256": source_digest,
                    "supporting_files": supporting_files, "reverse_engineering_report": "REVERSE_ENGINEERING.md",
                    "created_at": int(time.time()), "status": "proposed"}
                (dest / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                created.append({"name": slug, "description": meta["description"], "source_url": source_url,
                                "license": repo["license"], "sha256": digest, "status": "proposed"})
        except (requests.RequestException, ValueError, KeyError, OSError, SkillError) as exc:
            skipped.append({"repository": full, "reason": str(exc)[:180]})
    return {"task_query": str(task_query or "")[:500], "search_terms": task_terms,
            "repositories_considered": len(repositories), "documents_inspected": inspected,
            "created": created, "skipped": skipped[:30]}

def approve_skill(name: str) -> dict:
    slug = slugify(name)
    if not slug: raise ValueError("invalid skill name")
    source, target = PROPOSED_DIR / slug, ACTIVE_DIR / slug
    if not source.is_dir() or not (source / "SKILL.md").is_file(): raise FileNotFoundError("proposal not found")
    if target.exists(): raise FileExistsError("active skill already exists; refusing to overwrite")
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("license") not in ALLOWED_LICENSES or not manifest.get("license_text_verified"):
        raise ValueError("verified allowlisted license required")
    content = (source / "SKILL.md").read_text(encoding="utf-8")
    meta, _ = parse_skill(content)
    if hashlib.sha256(content.rstrip().encode("utf-8")).hexdigest() != manifest.get("sha256"):
        # Account for the newline added during storage without silently accepting modified content.
        if hashlib.sha256(content.encode("utf-8")).hexdigest() != manifest.get("sha256"):
            raise ValueError("skill content digest mismatch")
    manifest["status"] = "active"; manifest["approved_at"] = int(time.time())
    (source / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    ACTIVE_DIR.mkdir(parents=True, exist_ok=True); source.rename(target)
    return {"name": meta["name"], "status": "active", "source_url": manifest.get("source_url", "")}
