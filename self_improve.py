"""Generate an evidence-backed self-improvement plan; never modify or execute external code."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORT_DIR = Path(os.getenv("SCOUT_REPORT_DIR", str(ROOT / "reports")))
CANDIDATES_PATH = REPORT_DIR / "feature-candidates.json"

CAPABILITIES = [
    {
        "id": "readme_review",
        "title": "تحليل README ووثائق المشاريع المرشحة",
        "status": "missing",
        "priority": "high",
        "why": "التصنيف الحالي يعتمد على بيانات المستودع والكلمات المفتاحية ولا يقرأ الوثائق قبل التوصية.",
        "acceptance": ["جلب README عبر GitHub API", "استخراج متطلبات التشغيل والاعتماديات والترخيص", "إظهار روابط الأدلة وتاريخ الفحص"],
        "risk": "محتوى المستودعات الخارجية غير موثوق ويجب التعامل معه كبيانات فقط."
    },
    {
        "id": "compatibility_audit",
        "title": "فحص التوافق مع بنية الوكيل الحالية",
        "status": "partial",
        "priority": "high",
        "why": "هناك مرشحات ميزات، لكن لا يوجد حتى الآن اختبار توافق آلي لكل مرشح مع ملفات المشروع واعتمادياته.",
        "acceptance": ["تحديد الملفات المتأثرة", "تسجيل الاعتماديات والتراخيص", "إنتاج خطة تغيير قابلة للمراجعة دون تنفيذ كود خارجي"],
        "risk": "مطابقة الكلمات لا تثبت أن الميزة قابلة للدمج."
    },
    {
        "id": "patch_test_loop",
        "title": "حلقة اقتراح تغيير ثم اختبارات",
        "status": "partial",
        "priority": "critical",
        "why": "أضيف محرك AutoDev اختياري ومقيّد يقترح تعديلًا لملف مصدر واختباره، ويشغّل الفحوصات قبل طلب مراجعة Draft؛ ما زال يحتاج إعداد مزود نموذج مجاني والتحقق العملي من أول اقتراح قبل الاعتماد عليه.",
        "acceptance": ["استخدام محرك توليد كود مُعدّ صراحة", "إنشاء فرع منفصل", "تشغيل الاختبارات وفحوصات الأمان", "فتح PR مع ملخص وتراجع واضح"],
        "risk": "لا يمكن تنفيذ توليد كود فعلي دون نموذج برمجي متصل؛ لا تُستخدم مفاتيح أو خدمات مدفوعة تلقائيًا."
    },
    {
        "id": "automated_security",
        "title": "فحص أمان الاعتماديات والتغييرات",
        "status": "missing",
        "priority": "high",
        "why": "نجاح اختبارات المشروع لا يثبت سلامة اعتماديات جديدة أو تغييرات مولّدة.",
        "acceptance": ["فحص الاعتماديات والتراخيص", "تشغيل أدوات فحص ثابتة عند توفرها", "منع الأسرار والاتصالات غير المتوقعة"],
        "risk": "لا تشغّل مستودعات مرشحة ولا تثبّت اعتمادياتها في مسار الاستكشاف."
    },
    {
        "id": "change_journal",
        "title": "سجل دائم للتغييرات ونتائجها",
        "status": "partial",
        "priority": "medium",
        "why": "تقارير التشغيل موجودة، لكن لا يوجد سجل موحد يفرق بين اقتراح وميزة منفذة ومختبرة.",
        "acceptance": ["تسجيل الحالة والتاريخ والدليل", "تمييز المقترحات عن التغييرات المدمجة", "إرفاق روابط التشغيل وPR"],
        "risk": "لا تسجّل أي مقترح على أنه منفذ قبل التحقق."
    }
]

FEATURE_IMPLEMENTATION_MARKERS = {
    "RAG / البحث في المستندات": ("def retrieve_documents(", "class VectorStore", "def search_documents("),
    "استخدام الأدوات واستدعاء الوظائف": ("def execute_tool(", "class ToolRegistry", "def call_tool("),
    "الذاكرة وتلخيص المحادثات": ("def save_conversation(", "def load_conversation(", "class ConversationMemory"),
    "تشغيل محلي وخصوصية": ("ollama.chat(", "llama_cpp.Llama(", "def run_local_model("),
    "الصوت وتحويل الكلام": ("def transcribe_audio(", "def synthesize_speech(", "whisper.load_model("),
    "الرؤية وقراءة الصور": ("def analyze_image(", "def extract_ocr(", "pytesseract.image_to_string("),
    "التقييم والاختبارات": ("def run_benchmark(", "class EvaluationSuite", "def evaluate_agent("),
    "تنسيق الوكلاء والمهام": ("class AgentOrchestrator", "def run_agent_workflow(", "def delegate_task("),
    "الأمان والحماية": ("def detect_prompt_injection(", "def scan_dependencies(", "def validate_generated_patch("),
}


def scan_existing_features(root=ROOT):
    """Static signature check; absence means 'not found by these markers', not mathematical proof."""
    root = Path(root)
    source_files = []
    for path in root.rglob("*.py"):
        if any(part in {"tests", ".git", ".venv", "reports", "__pycache__"} for part in path.parts):
            continue
        if path.name == "self_improve.py" or path.name == "feature_hunter.py":
            continue
        try:
            source_files.append((str(path.relative_to(root)), path.read_text(encoding="utf-8").lower()))
        except (OSError, UnicodeError):
            continue
    results = {}
    for feature, markers in FEATURE_IMPLEMENTATION_MARKERS.items():
        found = []
        for marker in markers:
            for path, content in source_files:
                if marker.lower() in content:
                    found.append({"marker": marker, "file": path})
                    break
        status = "present" if len(found) >= 2 else "partial" if found else "missing"
        results[feature] = {
            "status": status,
            "matched_signatures": found,
            "checked_source_files": len(source_files),
            "method": "static_signature_scan",
            "limitation": "Missing means no configured implementation signature was found; manual review is still required."
        }
    return results


def build_plan(candidates=None, generated_at=None, root=ROOT):
    candidates = candidates or {}
    rows = candidates.get("candidates", [])
    existing_features = scan_existing_features(root)
    top = []
    for item in rows[:12]:
        features = [x.get("feature", "") for x in item.get("feature_candidates", [])]
        verification = {name: existing_features[name] for name in features if name in existing_features}
        top.append({
            "repository": item.get("repository", ""),
            "url": item.get("url", ""),
            "features": features,
            "feature_verification": verification,
            "license_spdx": item.get("license_spdx", "UNKNOWN"),
            "license_status": item.get("license_status", "unknown_do_not_copy"),
            "priority_score": item.get("priority_score", 0),
            "next_action": "review_readme_and_license",
            "implementation_status": "not_implemented",
        })
    missing = sum(1 for c in CAPABILITIES if c["status"] == "missing")
    partial = sum(1 for c in CAPABILITIES if c["status"] == "partial")
    return {
        "generated_at": generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "mode": "planning_only_no_llm_no_external_code_execution",
        "summary": {
            "candidate_repositories_reviewed": len(top),
            "capabilities_tracked": len(CAPABILITIES),
            "missing_capabilities": missing,
            "partial_capabilities": partial,
            "code_changes_made_by_planner": 0,
            "candidate_features_missing_in_current_code": sum(
                1 for row in top for status in row.get("feature_verification", {}).values()
                if status.get("status") == "missing"
            ),
        },
        "capabilities": CAPABILITIES,
        "repository_review_queue": top,
        "verified_feature_gaps": [
            {"feature": feature, **verification}
            for row in top for feature, verification in row.get("feature_verification", {}).items()
            if verification.get("status") == "missing"
        ][:20],
        "next_recommended_step": "Configure a free model through GitHub Actions Secrets/Variables, then review the first generated Draft PR and its full test/security results; never auto-merge.",
        "safety": [
            "No third-party repository code was copied, installed, or executed.",
            "Candidate scores are triage signals, not proof of quality or safety.",
            "A proposed capability is not implemented until a code change and tests are verified. AutoDev proposals remain drafts and are never merged automatically.",
            "No paid model or API is called by this planner."
        ]
    }

def write_report(plan, report_dir=REPORT_DIR):
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "self-improvement-plan.json"
    md_path = report_dir / "self-improvement-plan.md"
    json_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# تقرير خطة التطوير الذاتي",
        "",
        f"- وقت الإنشاء: {plan['generated_at']}",
        f"- المستودعات في قائمة المراجعة: {plan['summary']['candidate_repositories_reviewed']}",
        f"- القدرات الناقصة: {plan['summary']['missing_capabilities']}",
        f"- القدرات الجزئية: {plan['summary']['partial_capabilities']}",
        "- تغييرات كود نفذها هذا المخطط: 0",
        "",
        "## خريطة القدرات",
        ""
    ]
    for cap in plan["capabilities"]:
        lines.extend([
            f"### {cap['title']}",
            f"- الحالة: {cap['status']} | الأولوية: {cap['priority']}",
            f"- السبب: {cap['why']}",
            "- شروط الإنجاز: " + "؛ ".join(cap["acceptance"]),
            f"- المخاطر: {cap['risk']}",
            ""
        ])
    lines.extend(["## قائمة المشاريع للمراجعة", ""])
    for repo in plan["repository_review_queue"]:
        lines.extend([
            f"### [{repo['repository']}]({repo['url']})",
            f"- الميزات: {'، '.join(repo['features']) or 'غير محددة'}",
            f"- الترخيص: {repo['license_spdx']} ({repo['license_status']})",
            f"- أولوية الفحص: {repo['priority_score']}/100",
            f"- الحالة: {repo['implementation_status']}",
            ""
        ])
    lines.extend(["## الخطوة التالية", "", plan["next_recommended_step"], "", "## ضوابط السلامة", ""])
    lines.extend("- " + item for item in plan["safety"])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path

def main():
    candidates = {}
    if CANDIDATES_PATH.exists():
        candidates = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    plan = build_plan(candidates)
    md_path, json_path = write_report(plan)
    print(json.dumps({
        "mode": plan["mode"],
        "candidates": plan["summary"]["candidate_repositories_reviewed"],
        "missing_capabilities": plan["summary"]["missing_capabilities"],
        "partial_capabilities": plan["summary"]["partial_capabilities"],
        "markdown": str(md_path),
        "json": str(json_path)
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
