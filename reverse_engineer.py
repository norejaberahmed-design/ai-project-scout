"""Static architecture reconnaissance for public AI repositories.

This module does not decompile binaries, run repositories, install packages, or copy code.
It uses GitHub metadata, README text, file paths, and small manifest excerpts as untrusted evidence.
"""
import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORT_DIR = Path(os.getenv("SCOUT_REPORT_DIR", str(ROOT / "reports")))
CANDIDATES_PATH = REPORT_DIR / "feature-candidates.json"
API = "https://api.github.com"
MAX_REPOS = int(os.getenv("SCOUT_REVERSE_MAX_REPOS", "5"))
MAX_BLOB_BYTES = 180_000
MANIFEST_NAMES = {
    "pyproject.toml", "requirements.txt", "setup.py", "package.json",
    "go.mod", "cargo.toml", "pom.xml", "dockerfile", "compose.yaml",
    "docker-compose.yml", "environment.yml",
}
ARCHITECTURE_SIGNALS = [
    ("MCP / tool server", ("mcp", "model context protocol", "mcp server")),
    ("HTTP API / backend", ("fastapi", "flask", "express", "fastify", "rest api", "http api")),
    ("واجهة ويب", ("next.js", "react", "vite", "frontend", "web ui")),
    ("RAG / فهرسة مستندات", ("retrieval augmented generation", "vector database", "vector store", "rag pipeline")),
    ("وكلاء / orchestration", ("multi-agent", "agent framework", "orchestration", "tool calling")),
    ("نماذج محلية", ("ollama", "llama.cpp", "local inference", "vllm")),
    ("تقييم / مراقبة", ("evaluation", "tracing", "observability", "benchmark")),
    ("صوت / صورة", ("speech-to-text", "text-to-speech", "vision model", "ocr")),
]
RISK_PATTERNS = [
    ("install_or_bootstrap_scripts", re.compile(r"(^|/)(install|setup|bootstrap)\.(sh|ps1|bat)$", re.I)),
    ("workflow_automation", re.compile(r"^\.github/workflows/.*\.ya?ml$", re.I)),
    ("native_or_binary_components", re.compile(r"\.(so|dll|dylib|exe|bin|whl)$", re.I)),
    ("container_build", re.compile(r"(^|/)(dockerfile|docker-compose\.ya?ml|compose\.ya?ml)$", re.I)),
    ("postinstall_lifecycle", re.compile(r'"(?:preinstall|install|postinstall)"\s*:', re.I)),
]
ENTRYPOINT_PATTERNS = [
    re.compile(r"(^|/)(main|app|server|cli|__main__)\.(py|js|ts|mjs|cjs)$", re.I),
    re.compile(r"(^|/)(main|lib|bin)/", re.I),
    re.compile(r"(^|/)src/(main|index|server|cli)\.(py|js|ts|mjs|cjs)$", re.I),
]

def request_json(url):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ai-project-scout-static-recon"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=18) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429) and attempt < 2:
                time.sleep(1 + attempt)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(1 + attempt)
    return {}

def _decode_blob(blob):
    if not isinstance(blob, dict):
        return ""
    content = blob.get("content", "")
    if blob.get("encoding") == "base64" and content:
        try:
            return base64.b64decode(content).decode("utf-8", errors="replace")[:MAX_BLOB_BYTES]
        except (ValueError, TypeError):
            return ""
    return str(content)[:MAX_BLOB_BYTES]

def _feature_matches(readme):
    text = (readme or "").lower()
    return [{"capability": label, "evidence_terms": [term for term in terms if term in text][:3]}
            for label, terms in ARCHITECTURE_SIGNALS
            if any(term in text for term in terms)]

def analyze_snapshot(repository, repo_meta, tree, readme, manifests=None):
    manifests = manifests or {}
    paths = [x.get("path", "") for x in (tree or {}).get("tree", []) if x.get("type") == "blob"]
    lower_paths = [p.lower() for p in paths]
    entrypoints = [p for p in paths if any(rx.search(p) for rx in ENTRYPOINT_PATTERNS)][:20]
    manifest_paths = [p for p in paths if p.split("/")[-1].lower() in MANIFEST_NAMES][:15]
    architecture = _feature_matches(readme)
    risk_flags = []
    for path in paths:
        for label, pattern in RISK_PATTERNS:
            if pattern.search(path):
                risk_flags.append({"flag": label, "path": path})
    package_text = "\n".join(str(v) for v in manifests.values())
    if any(pattern.search(package_text) for label, pattern in RISK_PATTERNS if label == "postinstall_lifecycle"):
        risk_flags.append({"flag": "postinstall_lifecycle", "path": "package manifest"})
    readme_sections = []
    for line in (readme or "").splitlines():
        if line.startswith("#"):
            heading = re.sub(r"^#+\s*", "", line).strip()
            if heading and len(heading) < 100:
                readme_sections.append(heading)
        if len(readme_sections) >= 18:
            break
    if not readme:
        readme_quality = "missing"
    elif len(readme.strip()) < 500:
        readme_quality = "short"
    else:
        readme_quality = "available"
    language = repo_meta.get("language") or ""
    license_obj = repo_meta.get("license") or {}
    spdx = license_obj.get("spdx_id") or "UNKNOWN"
    if spdx == "UNKNOWN" or spdx == "NOASSERTION":
        license_decision = "do_not_copy_until_license_verified"
    elif spdx in {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD"}:
        license_decision = "review_terms_and_attribution_before_reuse"
    else:
        license_decision = "legal_review_required"
    return {
        "repository": repository,
        "url": repo_meta.get("html_url") or "https://github.com/" + repository,
        "description": repo_meta.get("description") or "",
        "stars": repo_meta.get("stargazers_count", 0),
        "language": language,
        "license_spdx": spdx,
        "license_decision": license_decision,
        "default_branch": repo_meta.get("default_branch") or "",
        "last_pushed_at": repo_meta.get("pushed_at") or "",
        "readme_quality": readme_quality,
        "architecture_signals": architecture,
        "entrypoint_candidates": entrypoints,
        "manifest_paths": manifest_paths,
        "manifest_names": sorted({p.split("/")[-1] for p in manifest_paths}),
        "readme_headings": readme_sections,
        "risk_flags": risk_flags[:40],
        "integration_assessment": (
            "Inspect the identified entrypoints, dependencies, API contracts and tests; design a small adapter rather than copying the project wholesale."
            if entrypoints and manifest_paths else
            "Evidence is incomplete; inspect the source tree and project documentation manually before proposing integration."
        ),
        "reverse_engineering_scope": "public-source static architecture review; no binary decompilation, execution, authentication bypass, or proprietary extraction",
        "decision": "manual_review_required",
    }

def inspect_candidates(candidate_report, fetcher=request_json, limit=MAX_REPOS):
    candidates = (candidate_report or {}).get("candidates", [])[:max(0, min(int(limit), 8))]
    results, errors = [], []
    for candidate in candidates:
        name = candidate.get("repository", "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name):
            errors.append({"repository": name, "error": "invalid_repository_name"})
            continue
        try:
            meta = fetcher(API + "/repos/" + name)
            branch = meta.get("default_branch") or "main"
            tree = fetcher(API + "/repos/" + name + "/git/trees/" + urllib.parse.quote(branch, safe="") + "?recursive=1")
            blobs = [x for x in tree.get("tree", []) if x.get("type") == "blob"]
            by_name = {}
            for blob in blobs:
                filename = blob.get("path", "").split("/")[-1].lower()
                if filename in {"readme.md", "readme.rst", "readme.txt"} and "readme" not in by_name:
                    by_name["readme"] = blob
                if filename in MANIFEST_NAMES and filename not in by_name and len(by_name) < 5:
                    by_name[filename] = blob
            decoded = {}
            for key, blob in by_name.items():
                sha = blob.get("sha")
                if not sha:
                    continue
                payload = fetcher(API + "/repos/" + name + "/git/blobs/" + sha)
                decoded[key] = _decode_blob(payload)
            readme = decoded.pop("readme", "")
            result = analyze_snapshot(name, meta, tree, readme, decoded)
            result["tree_truncated"] = bool(tree.get("truncated"))
            result["readme_bytes_analyzed"] = len(readme.encode("utf-8"))
            results.append(result)
        except Exception as exc:
            errors.append({"repository": name, "error": type(exc).__name__ + ": " + str(exc)[:240]})
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "mode": "read_only_public_source_static_recon",
        "candidate_count": len(candidates),
        "analyzed_count": len(results),
        "results": results,
        "errors": errors,
        "safety_note": "Repository content is untrusted evidence. No code was copied, installed, executed, or decompiled."
    }

def write_report(report, report_dir=REPORT_DIR):
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "reverse-engineering.json"
    md_path = report_dir / "reverse-engineering.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# تقرير الاستطلاع الهندسي العكسي للمستودعات العامة",
        "",
        f"- وقت الفحص: {report['generated_at']}",
        f"- مرشحات: {report['candidate_count']} | تم تحليلها: {report['analyzed_count']}",
        "- النطاق: تحليل ساكن لمصادر عامة وملفاتها التعريفية؛ لا تشغيل ولا نسخ ولا تفكيك ثنائيات.",
        "",
    ]
    for item in report["results"]:
        lines.extend([
            f"## [{item['repository']}]({item['url']})",
            f"- اللغة: {item['language'] or 'غير معروفة'} | النجوم: {item['stars']} | الترخيص: {item['license_spdx']}",
            f"- قرار الترخيص: {item['license_decision']}",
            f"- جودة README: {item['readme_quality']}",
            "- إشارات معمارية: " + ("؛ ".join(x["capability"] for x in item["architecture_signals"]) or "لم تظهر إشارات كافية في README"),
            "- نقاط دخول محتملة: " + ("، ".join(item["entrypoint_candidates"]) or "غير محددة"),
            "- ملفات تعريف/اعتماديات: " + ("، ".join(item["manifest_paths"]) or "غير محددة"),
            "- عناوين الوثائق: " + ("؛ ".join(item["readme_headings"]) or "غير متوفرة"),
            "- مؤشرات تحتاج فحصًا: " + ("؛ ".join(x["flag"] + " (" + x["path"] + ")" for x in item["risk_flags"]) or "لا توجد مؤشرات مسجلة من القواعد المحدودة"),
            f"- تقييم الدمج: {item['integration_assessment']}",
            "- الحالة: مراجعة بشرية مطلوبة؛ لم يتم الدمج.",
            "",
        ])
    if report["errors"]:
        lines.extend(["## أخطاء أو مستودعات تعذر فحصها", ""])
        lines.extend(f"- {e['repository']}: {e['error']}" for e in report["errors"])
    lines.extend(["", "## تنبيه", "", report["safety_note"],
                  "هذا التحليل لا يثبت أمان المشروع ولا يعادل تفكيك برنامج مغلق. لا تنسخ الكود قبل مراجعة الترخيص، ولا تشغّل أدوات خارجية داخل مسار الاستكشاف."])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path

def main():
    candidates = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8")) if CANDIDATES_PATH.exists() else {}
    report = inspect_candidates(candidates)
    md, js = write_report(report)
    print(json.dumps({"mode": report["mode"], "candidates": report["candidate_count"],
                      "analyzed": report["analyzed_count"], "errors": len(report["errors"]),
                      "markdown": str(md), "json": str(js)}, ensure_ascii=False))

if __name__ == "__main__":
    main()
