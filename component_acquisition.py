"""License-aware acquisition of public AI components into a review-only quarantine.

This module copies eligible source files for inspection. It never installs dependencies,
executes downloaded code, or makes imported code active automatically.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

API = "https://api.github.com"
USER_AGENT = "AI-Project-Scout-component-acquisition/1.0"
MAX_FILES = 60
MAX_FILE_BYTES = 80_000
MAX_TOTAL_BYTES = 1_000_000
ALLOWED_LICENSES = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD"}
ALLOWED_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".md", ".rst", ".txt", ".json", ".toml", ".yaml", ".yml", ".css", ".html", ".go", ".rs"}
DENIED_NAMES = {
    ".env", ".env.local", ".env.production", "id_rsa", "id_ed25519",
    "credentials.json", "secrets.json", "service-account.json",
}
DENIED_PARTS = {".git", "node_modules", "dist", "build", "coverage", "__pycache__", ".venv", "venv"}
REPO_RE = re.compile(r"^https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/?$", re.I)


def parse_repository_url(url: str) -> tuple[str, str]:
    match = REPO_RE.fullmatch((url or "").strip())
    if not match:
        raise ValueError("Provide a public GitHub repository root URL, not an issue, file, or branch URL.")
    owner, repo = match.group(1), match.group(2).removesuffix(".git")
    if repo.lower() in {"issues", "pull", "pulls", "actions", "settings", "discussions", "wiki"}:
        raise ValueError("The URL does not identify a repository root.")
    return owner, repo


def request_json(url: str, timeout: int = 15) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_TOTAL_BYTES + 250_000)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("GitHub API returned HTTP " + str(exc.code) + ".") from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("GitHub API is unreachable.") from None
    if len(raw) > MAX_TOTAL_BYTES + 250_000:
        raise RuntimeError("GitHub response exceeded the configured size limit.")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise RuntimeError("GitHub returned invalid JSON.") from None
    if not isinstance(data, dict):
        raise RuntimeError("GitHub returned an unexpected response.")
    return data


def _decode_content(payload: dict) -> bytes:
    raw = payload.get("content", "")
    if payload.get("encoding") == "base64":
        try:
            return base64.b64decode(raw, validate=False)
        except (ValueError, TypeError):
            raise RuntimeError("A repository file could not be decoded.") from None
    if isinstance(raw, str):
        return raw.encode("utf-8")
    raise RuntimeError("GitHub returned an unsupported file representation.")


def _safe_relative_path(raw: str) -> Path | None:
    path = PurePosixPath(raw)
    if path.is_absolute() or not path.parts or any(part in {"..", "."} for part in path.parts):
        return None
    if any(part.lower() in DENIED_PARTS or part.startswith(".") for part in path.parts[:-1]):
        return None
    name = path.name.lower()
    if name in DENIED_NAMES or name.endswith((".pem", ".key", ".p12", ".pfx", ".crt", ".sqlite", ".db")):
        return None
    if name in {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock", "uv.lock", "cargo.lock"}:
        return None
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        return None
    return Path(*path.parts)


def inspect_repository(url: str, fetcher=request_json) -> dict:
    """Inspect public metadata, revision, file inventory, and declared license only."""
    owner, repo = parse_repository_url(url)
    base = f"{API}/repos/{owner}/{repo}"
    meta = fetcher(base)
    if meta.get("private") or meta.get("archived"):
        raise ValueError("Private or archived repositories are not eligible for automatic acquisition.")
    license_obj = meta.get("license") or {}
    license_spdx = str(license_obj.get("spdx_id") or "UNKNOWN")
    if license_spdx not in ALLOWED_LICENSES:
        raise ValueError("License is not on the acquisition allowlist; manual legal review is required.")
    branch = str(meta.get("default_branch") or "main")
    branch_url = urllib.parse.quote(branch, safe="")
    commit_data = fetcher(f"{base}/commits/{branch_url}")
    revision = str(commit_data.get("sha") or "")
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("Could not resolve an immutable 40-character commit revision.")
    tree = fetcher(f"{base}/git/trees/{revision}?recursive=1")
    items = tree.get("tree", [])
    if tree.get("truncated"):
        raise ValueError("GitHub truncated the repository tree; acquisition is refused to avoid an incomplete copy.")
    license_paths = [i for i in items if i.get("type") == "blob" and PurePosixPath(str(i.get("path", ""))).name.lower() in {"license", "license.md", "license.txt", "copying"}]
    if not license_paths:
        raise ValueError("No license text file was found; manual license verification is required.")
    candidates = []
    for item in items:
        if item.get("type") != "blob" or item.get("mode") == "120000":
            continue
        raw_path = str(item.get("path") or "")
        safe_path = _safe_relative_path(raw_path)
        size = item.get("size")
        if safe_path is None or not isinstance(size, int) or size < 0 or size > MAX_FILE_BYTES:
            continue
        candidates.append({"path": raw_path, "size": size})
    candidates.sort(key=lambda x: x["path"].lower())
    bounded = candidates[:MAX_FILES]
    total = sum(item["size"] for item in bounded)
    if not bounded:
        raise ValueError("No eligible source/document files were found.")
    if total > MAX_TOTAL_BYTES:
        accepted = []
        total = 0
        for item in bounded:
            if total + item["size"] > MAX_TOTAL_BYTES:
                continue
            accepted.append(item)
            total += item["size"]
        bounded = accepted
    return {
        "repository": str(meta.get("full_name") or f"{owner}/{repo}"),
        "repository_url": str(meta.get("html_url") or f"https://github.com/{owner}/{repo}"),
        "description": str(meta.get("description") or "")[:500],
        "default_branch": branch,
        "revision": revision,
        "license_spdx": license_spdx,
        "license_file_paths": [str(i.get("path")) for i in license_paths[:5]],
        "stars": int(meta.get("stargazers_count") or 0),
        "last_pushed_at": str(meta.get("pushed_at") or ""),
        "eligible_files": bounded,
        "eligible_file_count": len(bounded),
        "eligible_bytes_estimate": total,
        "policy": "review-only; no install; no execution; no automatic activation",
    }


def acquire_repository(url: str, *, approved: bool = False, root: str | Path | None = None, fetcher=request_json) -> dict:
    """Copy an allowlisted repository's bounded text source into components/proposed.

    The caller must explicitly pass approved=True. This is an import confirmation, not
    a security certification: imported code remains untrusted and must not be executed.
    """
    if approved is not True:
        raise PermissionError("Acquisition requires explicit approval (approved=True / --confirm-copy).")
    info = inspect_repository(url, fetcher=fetcher)
    owner, repo = parse_repository_url(url)
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", f"{owner}__{repo}").strip("-")[:100]
    target_root = Path(root) if root is not None else Path(__file__).resolve().parent
    destination = target_root / "components" / "proposed" / f"{slug}-{info['revision'][:12]}"
    destination.mkdir(parents=True, exist_ok=False)
    file_manifest = []
    total = 0
    try:
        base = f"{API}/repos/{owner}/{repo}/contents/"
        for item in info["eligible_files"]:
            relative = _safe_relative_path(item["path"])
            if relative is None:
                continue
            encoded = urllib.parse.quote(item["path"], safe="/")
            ref = urllib.parse.quote(info["revision"], safe="")
            payload = fetcher(base + encoded + "?ref=" + ref)
            content = _decode_content(payload)
            if len(content) > MAX_FILE_BYTES or len(content) != item["size"]:
                raise RuntimeError("File size changed or exceeded limits; acquisition was stopped.")
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                # Only text sources are allowed; binary or invalid UTF-8 files are never copied.
                continue
            if "\x00" in text:
                continue
            if total + len(content) > MAX_TOTAL_BYTES:
                raise RuntimeError("Total acquired size exceeded limits; acquisition was stopped.")
            output = destination / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            # Re-check containment after path normalization.
            if destination.resolve() not in output.resolve().parents:
                raise RuntimeError("Unsafe destination path detected.")
            output.write_text(text, encoding="utf-8")
            total += len(content)
            file_manifest.append({
                "path": relative.as_posix(),
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "source_url": f"{info['repository_url']}/blob/{info['revision']}/{urllib.parse.quote(item['path'], safe='/')}",
            })
        if not file_manifest:
            raise RuntimeError("No valid UTF-8 source/document files were acquired.")
        manifest = {
            **{k: v for k, v in info.items() if k != "eligible_files"},
            "acquired_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "status": "PROPOSED_REVIEW_REQUIRED",
            "execution_allowed": False,
            "installation_allowed": False,
            "activation_allowed": False,
            "files": file_manifest,
            "copied_file_count": len(file_manifest),
            "copied_bytes": total,
            "review_checklist": [
                "Verify the license text and obligations for every copied file.",
                "Review all copied source and dependency manifests for security risks.",
                "Resolve and review dependencies before any installation.",
                "Run tests only in an isolated disposable environment after human approval.",
                "Create a separate integration change and regression tests.",
            ],
        }
        (destination / "ACQUISITION_MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return {"status": manifest["status"], "destination": str(destination), "manifest": manifest}
    except Exception:
        # A partial import is never left looking like a complete proposal.
        import shutil
        shutil.rmtree(destination, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect and stage eligible open-source repository files.")
    parser.add_argument("repository_url", help="Public GitHub repository root URL")
    parser.add_argument("--inspect-only", action="store_true", help="Inspect metadata and license without copying files")
    parser.add_argument("--confirm-copy", action="store_true", help="Explicitly approve copying eligible files into quarantine")
    parser.add_argument("--root", default=None, help="Project root (defaults to this file's directory)")
    args = parser.parse_args()
    if args.inspect_only:
        result = inspect_repository(args.repository_url)
    else:
        result = acquire_repository(args.repository_url, approved=args.confirm_copy, root=args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
