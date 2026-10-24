"""Discover, validate and stage public Markdown skills without executing them."""
import hashlib, json, re, time
from pathlib import Path
from urllib.parse import quote
import requests, yaml
from .config import ACTIVE_DIR, PROPOSED_DIR, int_setting, setting

ALLOWED_LICENSES = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD"}
MAX_SKILL_BYTES = 20_000
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
    name = slugify(meta.get("name", ""))
    description = str(meta.get("description", "")).strip()
    if not name or not description or len(description) > 500:
        raise ValueError("valid name and description are required")
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

def discover_skills(max_proposals: int = 2) -> dict:
    max_proposals = max(1, min(int(max_proposals), int_setting("SCOUT_MAX_SKILLS_PER_DISCOVERY", 3, 1, 3)))
    PROPOSED_DIR.mkdir(parents=True, exist_ok=True)
    queries = ["agent skills in:name,description stars:>=5", "SKILL.md agent skills stars:>=5"]
    repositories, seen = [], set()
    for query in queries:
        url = "https://api.github.com/search/repositories?q=" + quote(query) + "&sort=updated&order=desc&per_page=10"
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
            lr = requests.get(f"https://raw.githubusercontent.com/{owner}/{name}/{revision}/{quote(license_paths[0], safe='/')}", timeout=15)
            if lr.status_code != 200 or not lr.text.strip():
                skipped.append({"repository": full, "reason": "license text could not be verified"}); continue
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
                digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
                dest = PROPOSED_DIR / slug
                dest.mkdir(parents=True, exist_ok=False)
                (dest / "SKILL.md").write_text(content.rstrip() + "\n", encoding="utf-8")
                (dest / "UPSTREAM_LICENSE.txt").write_text(lr.text[:100000], encoding="utf-8")
                source_url = f"{repo['html_url']}/blob/{revision}/{quote(path, safe='/')}"
                (dest / "ATTRIBUTION.md").write_text(
                    f"# Attribution\n\n- Repository: {repo['html_url']}\n- File: {source_url}\n- Revision: {revision}\n- SPDX: {repo['license']}\n- SHA-256: {digest}\n- Status: proposal only; not executed or activated.\n", encoding="utf-8")
                manifest = {"name": slug, "description": meta["description"], "source_url": source_url,
                    "repository": full, "revision": revision, "path": path, "license": repo["license"],
                    "license_text_verified": True, "sha256": digest, "created_at": int(time.time()), "status": "proposed"}
                (dest / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                created.append({"name": slug, "description": meta["description"], "source_url": source_url,
                                "license": repo["license"], "sha256": digest, "status": "proposed"})
        except (requests.RequestException, ValueError, KeyError, OSError, SkillError) as exc:
            skipped.append({"repository": full, "reason": str(exc)[:180]})
    return {"repositories_considered": len(repositories), "documents_inspected": inspected,
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
