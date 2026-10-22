"""Discover reusable AI feature candidates without copying or executing third-party code."""
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
API = "https://api.github.com"
QUERIES = [
    "AI agent framework stars:>50",
    "LLM tool calling OR function calling stars:>30",
    "RAG retrieval augmented generation stars:>50",
    "local AI assistant OR multimodal AI stars:>30",
]
FEATURES = [
    ("RAG / البحث في المستندات", ("retrieval augmented generation", "rag", "vector search", "document search")),
    ("استخدام الأدوات واستدعاء الوظائف", ("tool calling", "function calling", "tool use", "tools api")),
    ("الذاكرة وتلخيص المحادثات", ("memory", "conversation history", "long-term context")),
    ("تشغيل محلي وخصوصية", ("local inference", "offline", "on-device", "self-hosted")),
    ("الصوت وتحويل الكلام", ("speech to text", "text to speech", "voice", "whisper")),
    ("الرؤية وقراءة الصور", ("ocr", "vision", "image understanding", "document parsing")),
    ("التقييم والاختبارات", ("evaluation", "benchmark", "observability", "tracing")),
    ("تنسيق الوكلاء والمهام", ("multi-agent", "workflow", "orchestration", "planning")),
    ("الأمان والحماية", ("guardrails", "prompt injection", "sandbox", "security")),
]
PERMISSIVE = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD"}
BLOCKED_LICENSES = {"NOASSERTION", "OTHER", "UNLICENSED", ""}

def request_json(url):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ai-project-scout-feature-hunter"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429) and attempt < 2:
                time.sleep(min(2 ** attempt, 4))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    return {}

def feature_matches(text):
    normalized = re.sub(r"\s+", " ", (text or "").lower())
    matches = []
    for label, terms in FEATURES:
        found = [term for term in terms if term in normalized]
        if found:
            matches.append({"feature": label, "matched_terms": found[:4]})
    return matches

def license_status(spdx):
    if spdx in PERMISSIVE:
        return "permissive_review_required"
    if spdx in BLOCKED_LICENSES:
        return "unknown_do_not_copy"
    return "legal_review_required"

def discover(search_fn=request_json, max_per_query=10):
    candidates = {}
    errors = []
    for query in QUERIES:
        url = API + "/search/repositories?" + urllib.parse.urlencode({
            "q": query, "sort": "updated", "order": "desc", "per_page": max_per_query
        })
        try:
            payload = search_fn(url)
            for repo in payload.get("items", []):
                name = repo.get("full_name") or ""
                if not name:
                    continue
                lic = (repo.get("license") or {}).get("spdx_id") or ""
                text = " ".join([repo.get("name") or "", repo.get("description") or "", " ".join(repo.get("topics") or [])])
                matches = feature_matches(text)
                if not matches:
                    continue
                status = license_status(lic)
                score = min(100, len(matches) * 15 + (10 if lic in PERMISSIVE else 0)
                            + (10 if (repo.get("stargazers_count") or 0) >= 500 else 0)
                            + (10 if repo.get("description") else 0))
                item = {
                    "repository": name, "url": repo.get("html_url", ""),
                    "description": repo.get("description") or "",
                    "stars": repo.get("stargazers_count", 0),
                    "language": repo.get("language") or "",
                    "license_spdx": lic or "UNKNOWN",
                    "license_status": status,
                    "feature_candidates": matches,
                    "priority_score": score,
                    "decision": "review_candidate" if status == "permissive_review_required" else "manual_legal_review",
                    "evidence": "Repository metadata only; inspect README, source, dependencies, compatibility and license before implementation."
                }
                if name not in candidates or score > candidates[name]["priority_score"]:
                    candidates[name] = item
        except Exception as exc:
            errors.append({"query": query, "error": type(exc).__name__ + ": " + str(exc)})
    ordered = sorted(candidates.values(), key=lambda x: (-x["priority_score"], x["repository"]))
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "mode": "discovery_only_no_code_copy_or_execution",
        "candidate_count": len(ordered),
        "candidates": ordered,
        "errors": errors,
        "safety_note": "Feature matches are keyword-based leads, not proof of implementation quality. No third-party code was copied or executed."
    }

def write_report(report, report_dir=REPORT_DIR):
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "feature-candidates.json"
    md_path = report_dir / "feature-candidates.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# مرشحات ميزات الذكاء الاصطناعي",
        "",
        f"- تاريخ الجمع: {report['generated_at']}",
        f"- عدد المشاريع المرشحة: {report['candidate_count']}",
        "- الوضع: اكتشاف فقط؛ لا نسخ ولا تشغيل لكود خارجي.",
        "",
    ]
    for item in report["candidates"]:
        lines.extend([
            f"## [{item['repository']}]({item['url']})",
            f"- وصف المشروع: {item['description'] or 'غير متوفر'}",
            f"- الترخيص: {item['license_spdx']}",
            f"- حالة الترخيص: {item['license_status']}",
            f"- درجة أولوية الفحص: {item['priority_score']}/100 (ليست درجة جودة مؤكدة)",
            "- الميزات المحتملة: " + "، ".join(x["feature"] for x in item["feature_candidates"]),
            f"- النجوم: {item['stars']} | اللغة: {item['language'] or 'غير محددة'}",
            f"- القرار: {item['decision']}",
            "",
        ])
    if not report["candidates"]:
        lines.append("لم تُعثر على مرشحات موثوقة في هذه الجولة؛ راجع أخطاء الاتصال إن وجدت.")
    if report["errors"]:
        lines.extend(["## أخطاء البحث", ""] + [f"- {e['query']}: {e['error']}" for e in report["errors"]])
    lines.extend(["", "## بوابة الدمج", "", "قبل أي دمج: فحص README والكود والاعتماديات، التأكد من الترخيص، تقييم التوافق والأمان، ثم إنشاء فرع واختبارات وطلب مراجعة."])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path

if __name__ == "__main__":
    report = discover()
    md_path, json_path = write_report(report)
    print(json.dumps({"candidate_count": report["candidate_count"], "markdown": str(md_path), "json": str(json_path), "errors": len(report["errors"])}, ensure_ascii=False))
