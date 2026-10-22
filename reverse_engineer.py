"""Static architecture reconnaissance for public AI repositories.

This module does not decompile binaries, run repositories, install packages, or copy code.
It uses GitHub metadata, README text, file paths, and small manifest excerpts as untrusted evidence.
"""
import ast
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
MAX_SOURCE_FILES = 8
SOURCE_EXTENSIONS = {".py", ".js", ".ts", ".mjs", ".cjs", ".go", ".rs"}
CODE_PATTERNS = [
    ("model_provider_calls", re.compile(r"openai|anthropic|chat\.completions|completion\.create|litellm|genai\.generate", re.I)),
    ("tool_or_mcp_registration", re.compile(r"fastmcp|mcpserver|register_tool|@tool\b|tool_call|function_call|tools\s*=", re.I)),
    ("http_or_network_clients", re.compile(r"requests\.(get|post)|httpx\.|urllib\.request|fetch\(|axios\.|aiohttp", re.I)),
    ("shell_or_dynamic_execution", re.compile(r"subprocess\.|os\.system\(|shell\s*=\s*true|\beval\s*\(|\bexec\s*\(", re.I)),
    ("environment_or_secret_access", re.compile(r"os\.getenv|os\.environ|process\.env|dotenv|secret", re.I)),
    ("filesystem_operations", re.compile(r"open\s*\(|write_text\(|writeFile\(|unlink\(|rmtree\(", re.I)),
    ("vector_or_retrieval", re.compile(r"chromadb|faiss|pinecone|weaviate|qdrant|vectorstore|embedding", re.I)),
    ("web_framework_or_routes", re.compile(r"FastAPI|Flask|express\(|app\.(get|post|put|delete)\(|router\.(get|post)\(", re.I)),
    ("memory_or_state", re.compile(r"conversation.?memory|memory.?store|chat.?history|redis|sqlite|session\.", re.I)),
    ("structured_outputs", re.compile(r"json_schema|structured.?output|response_format|pydantic\.BaseModel", re.I)),
    ("evaluation_or_tracing", re.compile(r"langsmith|langfuse|opentelemetry|tracer|evaluation|pytest", re.I)),
    ("retry_or_rate_limit", re.compile(r"tenacity|backoff|retry\(|rate.?limit|429", re.I)),
    ("streaming_responses", re.compile(r"stream=True|streaming|StreamingResponse|text/event-stream", re.I)),
]
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

def extract_structure(path, source):
    """Extract names and imports without executing code or returning source snippets."""
    suffix = Path(path).suffix.lower()
    symbols, imports = [], []
    if suffix == ".py":
        try:
            tree = ast.parse(source or "")
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    symbols.append(node.name)
                elif isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module)
        except (SyntaxError, ValueError, TypeError):
            pass
    else:
        text = source or ""
        symbol_patterns = [
            re.compile(r"\b(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)"),
            re.compile(r"\bclass\s+([A-Za-z_$][\w$]*)"),
            re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>"),
        ]
        for pattern in symbol_patterns:
            symbols.extend(pattern.findall(text))
        imports.extend(re.findall(r"""import\s+(?:[^'"]*?\s+from\s+)?['"]([^'"]+)['"]""", text))
        imports.extend(re.findall(r"""require\(\s*['"]([^'"]+)['"]\s*\)""", text))
    return {"symbols": sorted(set(symbols))[:20], "imports": sorted(set(imports))[:20]}


def scan_source(path, source):
    """Return structural names and pattern evidence, never source excerpts."""
    structure = extract_structure(path, source)
    findings = []
    for label, pattern in CODE_PATTERNS:
        matches = []
        for number, line in enumerate((source or "").splitlines(), 1):
            if pattern.search(line):
                matches.append(number)
                if len(matches) >= 5:
                    break
        if matches:
            findings.append({"signal": label, "line_numbers": matches})
    return {"path": path, "signals": findings, "lines_analyzed": len((source or "").splitlines()), **structure}


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
        "source_analysis": [],
        "risk_flags": risk_flags[:40],
        "integration_assessment": (
            "Inspect the identified entrypoints, dependencies, API contracts and tests; design a small adapter rather than copying the project wholesale."
            if entrypoints and manifest_paths else
            "Evidence is incomplete; inspect the source tree and project documentation manually before proposing integration."
        ),
        "reverse_engineering_scope": "public-source static architecture review; no binary decompilation, execution, authentication bypass, or proprietary extraction",
        "decision": "manual_review_required",
    }


def derive_feature_opportunities(source_analysis, architecture_signals=None):
    """Map observed source signals to cautious, evidence-linked integration leads."""
    signal_paths = {}
    for source in source_analysis or []:
        path = source.get("path", "")
        for item in source.get("signals", []):
            signal = item.get("signal", "")
            if signal:
                signal_paths.setdefault(signal, []).append({
                    "path": path,
                    "line_numbers": item.get("line_numbers", [])[:5],
                })
    rules = [
        ("tool_or_mcp_registration", "قابلية إضافة أدوات جديدة", "افحص عقود الأدوات المكتشفة وقارنها بواجهات الوكيل؛ اقترح موصلًا داخليًا فقط عند إثبات فجوة.", "medium"),
        ("vector_or_retrieval", "استرجاع المعرفة", "تحقق من وجود بحث أو استرجاع مكافئ داخل الوكيل قبل اقتراح واجهة جديدة.", "medium"),
        ("model_provider_calls", "تكامل مزوّد النماذج", "قارن نمط استدعاء النموذج بإعدادات المزوّد الحالية؛ لا تنقل مفاتيح أو إعدادات سرية.", "medium"),
        ("environment_or_secret_access", "إدارة الأسرار", "راجع فصل الإعدادات عن الكود؛ لا تستورد أسرارًا أو ملفات بيئة من المشروع الخارجي.", "high"),
        ("shell_or_dynamic_execution", "تنفيذ الكود ومخاطره", "اعتبر التنفيذ الديناميكي إشارة خطر؛ لا تنقل هذا السلوك إلى الوكيل.", "high"),
        ("memory_or_state", "الذاكرة وحالة المحادثة", "افحص التخزين والاسترجاع والخصوصية قبل اقتراح ذاكرة جديدة، وتجنب التكرار.", "medium"),
        ("structured_outputs", "المخرجات المنظمة", "تحقق من التحقق الحالي لمخططات JSON؛ أضف تحققًا واختبارًا فقط إذا كانت الفجوة حقيقية.", "low"),
        ("evaluation_or_tracing", "تقييم الجودة والتتبع", "تحقق من الاختبارات والتقارير الحالية قبل اقتراح تقييم محلي لا يرسل بيانات المستخدمين.", "low"),
        ("retry_or_rate_limit", "التعامل مع الفشل وحدود الطلبات", "راجع سياسة إعادة المحاولة الحالية لتجنب التكرار أو المحاولات غير المحدودة.", "medium"),
        ("streaming_responses", "تدفق الردود", "قارن تجربة الرد الحالية بواجهات التدفق قبل اقتراح تغيير مناسب للواجهة.", "medium"),
        ("web_framework_or_routes", "واجهات API", "افحص عقود المسارات والاختبارات قبل اقتراح تكامل متوافق.", "medium"),
    ]
    result = []
    for signal, title, action, risk in rules:
        evidence = signal_paths.get(signal, [])
        if evidence:
            result.append({
                "title": title, "source_signal": signal, "evidence": evidence[:4],
                "risk": risk, "recommended_action": action,
                "status": "candidate_requires_gap_check",
                "implementation_policy": "native_adapter_only_no_third_party_code_copy",
            })
    if not result and architecture_signals:
        result.append({
            "title": "الأدلة البرمجية غير كافية",
            "source_signal": "readme_architecture_only",
            "evidence": [{"path": "README", "line_numbers": []}],
            "risk": "unknown",
            "recommended_action": "لا تنفذ ميزة بناءً على وصف README فقط؛ اجمع أدلة من المصدر والاختبارات.",
            "status": "insufficient_source_evidence",
            "implementation_policy": "no_change_until_evidence",
        })
    return result


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
            source_blobs = []
            for blob in blobs:
                path = blob.get("path", "")
                suffix = Path(path).suffix.lower()
                if suffix in SOURCE_EXTENSIONS and blob.get("sha"):
                    priority = 0 if any(rx.search(path) for rx in ENTRYPOINT_PATTERNS) else 1
                    source_blobs.append((priority, path, blob["sha"]))
            source_blobs.sort(key=lambda item: (item[0], item[1].count("/"), item[1]))
            source_analysis = []
            for _, path, sha in source_blobs[:MAX_SOURCE_FILES]:
                payload = fetcher(API + "/repos/" + name + "/git/blobs/" + sha)
                source_analysis.append(scan_source(path, _decode_blob(payload)))
            result["source_analysis"] = source_analysis
            result["feature_opportunities"] = derive_feature_opportunities(source_analysis, result.get("architecture_signals"))
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
            "- تحليل الشيفرة المختارة: " + ("؛ ".join(src["path"] + " [" + ", ".join(sig["signal"] + ":" + ",".join(map(str, sig["line_numbers"])) for sig in src["signals"]) + "]" for src in item.get("source_analysis", [])) or "لم تتوفر ملفات مصدر مناسبة"),
            "- مؤشرات تحتاج فحصًا: " + ("؛ ".join(x["flag"] + " (" + x["path"] + ")" for x in item["risk_flags"]) or "لا توجد مؤشرات مسجلة من القواعد المحدودة"),
            "- فرص الميزات المبنية على دليل: " + ("؛ ".join(x["title"] + " (" + x["source_signal"] + ")" for x in item.get("feature_opportunities", [])) or "لم تثبت فرصة من الملفات المفحوصة"),
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
