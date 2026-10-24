"""Runtime utilities for selecting trusted internal skills and validating candidates.

External skill files are never activated by this module automatically. It loads only
maintainer-controlled files from skills/active and validates proposals before review.
"""
from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

from skill_registry import get_skill, transition_skill

ROOT = Path(__file__).resolve().parent
ACTIVE_DIR = ROOT / "skills" / "active"
PROPOSED_DIR = ROOT / "skills" / "proposed"
MAX_SKILL_BYTES = 20_000
MAX_ACTIVE_SKILLS = 100

RISK_PATTERNS = {
    "instruction_override": re.compile(r"ignore (all |any )?(previous|prior|system) instructions|disregard (all |your) rules", re.I),
    "secret_exfiltration": re.compile(r"(exfiltrat|print|reveal|upload|send).{0,50}(secret|api.?key|token|credential|password)", re.I | re.S),
    "dangerous_execution": re.compile(r"\b(os\.system|subprocess\.(run|Popen|call)|eval\s*\(|exec\s*\()"),
}


def parse_frontmatter(document: str) -> dict:
    """Parse the intentionally small YAML-like frontmatter subset used by our skills."""
    if not isinstance(document, str) or not document.startswith("---\n"):
        raise ValueError("Skill must begin with YAML frontmatter.")
    end = document.find("\n---", 4)
    if end < 0:
        raise ValueError("Skill frontmatter is not closed.")
    metadata = {}
    for line in document[4:end].splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            raise ValueError("Malformed skill metadata line.")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key not in {"name", "description", "version"}:
            continue
        if not value:
            raise ValueError(f"Empty required metadata: {key}")
        metadata[key] = value
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", metadata.get("name", "")):
        raise ValueError("Skill name must be a lowercase slug.")
    if len(metadata.get("description", "")) < 12:
        raise ValueError("Skill description must explain its purpose.")
    return metadata


def inspect_candidate(document: str) -> dict:
    """Return validation evidence; passing this check is not automatic approval."""
    errors = []
    warnings = []
    try:
        metadata = parse_frontmatter(document)
    except ValueError as exc:
        metadata = {}
        errors.append(str(exc))
    if len(document.encode("utf-8")) > MAX_SKILL_BYTES:
        errors.append(f"Skill exceeds {MAX_SKILL_BYTES} bytes.")
    if len(document.strip()) < 100:
        errors.append("Skill content is too short to be actionable.")
    risks = [name for name, pattern in RISK_PATTERNS.items() if pattern.search(document)]
    if risks:
        errors.append("Risk indicators detected: " + ", ".join(risks))
    if "license:" not in document.lower() and "licence:" not in document.lower():
        warnings.append("License/provenance is not documented; review before adapting third-party material.")
    if "test" not in document.lower() and "verify" not in document.lower():
        warnings.append("No testing or verification guidance found.")
    return {"valid": not errors, "metadata": metadata, "errors": errors,
            "warnings": warnings, "requires_human_review": True,
            "auto_activated": False}


def load_active_skills(root: Path | None = None) -> list[dict]:
    """Load active skills from the trusted local directory, skipping invalid documents."""
    directory = (root or ROOT) / "skills" / "active"
    loaded = []
    if not directory.exists():
        return loaded
    for path in sorted(directory.glob("*/SKILL.md"))[:MAX_ACTIVE_SKILLS]:
        try:
            document = path.read_text(encoding="utf-8")
            metadata = parse_frontmatter(document)
        except (OSError, UnicodeError, ValueError):
            continue
        loaded.append({"name": metadata["name"], "description": metadata["description"],
                       "path": str(path), "content": document})
    return loaded


def _proposal_is_usable(document: str) -> bool:
    """Keep placeholders and procedures requiring unavailable shell integrations out of chat context."""
    lowered = (document or "").lower()
    if any(phrase in lowered for phrase in (
        "do the task described above",
        "perform the task described above",
        "insert skill instructions here",
        "todo: add skill instructions",
        "replace this with the actual skill",
    )):
        return False
    # This app's chat runtime does not expose a shell or GitHub CLI. Do not
    # feed tool-specific instructions that would encourage pretending to run them.
    if re.search(r"(?im)^\s*allowed-tools\s*:", document):
        return False
    if re.search(r"\bgh\s+(?:issue|pr|repo|api)\b|\bgit\s+worktree\b|\bgh\s+pr\s+merge\b", lowered):
        return False
    body = document.split("## Source provenance", 1)[0]
    action_lines = [
        line.strip() for line in body.splitlines()
        if re.match(r"^(?:[-*]|(?:step\s+)?[1-9][0-9]?[.)])\s+\S.{17,}$", line.strip(), re.I)
    ]
    return len(body) >= 180 and len(action_lines) >= 3


def load_proposed_skills(root: Path | None = None, limit: int = 50) -> list[dict]:
    """Load statically valid proposals as untrusted reference material, never as trusted instructions."""
    directory = (root or ROOT) / "skills" / "proposed"
    loaded = []
    if limit < 1 or not directory.exists():
        return loaded
    for path in sorted(directory.glob("*/SKILL.md"))[:min(int(limit), 100)]:
        try:
            document = path.read_text(encoding="utf-8")
            checked = inspect_candidate(document)
            if not checked.get("valid") or not _proposal_is_usable(document):
                continue
            metadata = checked["metadata"]
            if path.parent.name != metadata.get("name"):
                continue
            loaded.append({
                "name": metadata["name"],
                "description": metadata["description"],
                "path": str(path),
                "content": document,
                "trust_level": "UNTRUSTED_PROPOSAL",
            })
        except (OSError, UnicodeError, ValueError):
            continue
    return loaded


def activate_approved_skill(skill_id: str, reviewer: str, root: Path | None = None,
                           db_path: str | Path | None = None) -> dict:
    """Activate one reviewed registry record only when its saved proposal matches the approved hash."""
    reviewer = (reviewer or "").strip()
    if not reviewer:
        raise ValueError("An explicit reviewer is required for activation.")
    base = root or ROOT
    record = get_skill(skill_id, db_path=db_path)
    if record is None:
        raise ValueError("Skill record not found.")
    if record.get("status") != "APPROVED":
        raise ValueError("Only an APPROVED skill can be activated.")
    name = record.get("name", "")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        raise ValueError("Approved skill has an invalid name.")
    proposal = base / "skills" / "proposed" / name / "SKILL.md"
    document = proposal.read_text(encoding="utf-8")
    checked = inspect_candidate(document)
    if not checked["valid"] or checked["metadata"].get("name") != name:
        raise ValueError("Saved proposal failed validation or does not match the approved skill.")
    digest = hashlib.sha256(document.encode("utf-8")).hexdigest()
    if not record.get("content_sha256") or digest != record["content_sha256"]:
        raise ValueError("Saved proposal content does not match the approved registry hash.")
    target_dir = base / "skills" / "active" / name
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    if target_dir.exists():
        raise ValueError("An active skill with this name already exists; refusing to overwrite it.")
    target_dir.mkdir()
    target = target_dir / "SKILL.md"
    try:
        target.write_text(document, encoding="utf-8")
        proposal_bundle = proposal.parent / "bundle"
        if proposal_bundle.is_dir():
            shutil.copytree(proposal_bundle, target_dir / "bundle", dirs_exist_ok=False)
        active_record = transition_skill(
            skill_id, "ACTIVE", db_path=db_path, reviewer=reviewer
        )
    except Exception:
        # Do not leave an unregistered skill in the runtime library after a failed transition.
        shutil.rmtree(target_dir, ignore_errors=True)
        raise
    return {"skill_id": skill_id, "name": name, "status": active_record["status"],
            "reviewer": active_record["reviewer"], "path": str(target),
            "content_sha256": digest, "runtime_loaded": True}


ENGLISH_SKILL_TERMS = {
    "verification-before-completion": {"verify", "verification", "completion", "complete", "passed", "pass", "claim", "done", "success", "tests", "test", "build"},
    "accessibility-check": {"accessibility", "accessible", "contrast", "alt", "labels", "keyboard", "screen-reader", "wcag"},
    "api-docs-writer": {"api", "documentation", "docs", "endpoint", "openapi", "schema", "reference"},
    "changelog-writer": {"changelog", "release", "release-notes", "version", "breaking", "changes"},
    "csv-cleaner": {"csv", "clean", "cleaning", "normalize", "normalise", "duplicate", "spreadsheet", "rows", "columns", "data"},
    "fact-checker": {"fact-check", "fact-checker", "verify", "claim", "claims", "accuracy", "outdated", "correct", "sources"},
}


ARABIC_SKILL_TERMS = {
    "test-driven-implementation": {"ابن", "ابني", "بناء", "تطبيق", "التطبيق", "برمجة", "برمج", "كود", "الكود", "مشروع", "تنفيذ", "اصلح", "أصلح", "خطأ", "خطا", "عطل", "مشكلة", "اختبار", "اختبر", "اختبره", "فحص", "تصحيح"},
    "planning-and-verification": {"خطة", "خطه", "خطوات", "معمارية", "معماريه", "متطلبات", "قواعد", "اسس", "أسس", "تصميم", "نفذ", "انجز", "أنجز", "انهاء", "إنهاء"},
    "evidence-first-research": {"ابحث", "بحث", "مصادر", "معلومات", "تحقق", "دليل", "تأكد", "تاكد", "مقارنة", "قارن", "احدث", "الأحدث", "السعر", "أسعار", "اسعار"},
    "ai-tool-discovery": {"مهارة", "مهارات", "ادوات", "أدوات", "ايجنت", "وكيل", "وكلاء", "ذكاء", "اصطناعي", "مكتبة", "مستودع", "جيت", "github"},
    "repository-security-review": {"أمان", "امن", "ثغرة", "ثغرات", "ترخيص", "تراخيص", "مفتاح", "مفاتيح", "سر", "اسرار", "أسرار", "استنساخ", "خارجي"},
    "structured-debugging": {"خطأ", "خطا", "عطل", "مشكلة", "فشل", "يتعطل", "تعطل", "تصحيح", "تشخيص", "يشتغل", "يعمل"},
    "product-market-validation": {"ربح", "سوق", "عميل", "عملاء", "بيع", "مبيعات", "تكلفة", "فكرة", "منتج", "مشروع", "طلب"},
    "accessibility-check": {"إتاحة", "اتاحة", "سهولة", "الوصول", "قارئ", "الشاشة", "تباين", "تسميات", "تسمية", "بديل", "صور", "الصور", "لوحة", "مفاتيح", "افحص", "فحص", "أزرار", "ازرار", "الأزرار"},
    "api-docs-writer": {"توثيق", "وثق", "واجهة", "برمجية", "نقطة", "نقاط", "النهاية", "نهايات", "وثائق"},
    "changelog-writer": {"سجل", "السجل", "التغييرات", "تغيير", "تغييرات", "إصدار", "اصدار", "الإصدار", "ملاحظات", "إطلاق", "اطلاق"},
    "csv-cleaner": {"ملف", "csv", "تنظيف", "نظف", "بيانات", "جدول", "جداول", "صفوف", "اعمدة", "أعمدة", "مكرر", "تكرار"},
    "fact-checker": {"دقق", "تدقيق", "تحقق", "صحة", "صحيح", "معلومة", "معلومات", "ادعاء", "ادعاءات", "دقة", "مصداقية", "قديم", "محدث"},
}


def select_skills(task: str, skills: list[dict] | None = None, limit: int = 4) -> list[dict]:
    """Rank active skills by explainable English token overlap and Arabic intent terms."""
    if limit < 1:
        return []
    available = skills if skills is not None else load_active_skills()
    words = set(re.findall(r"[a-z0-9_+-]+|[\u0600-\u06ff]+", (task or "").lower()))
    # Normalize common Arabic conjunctions, prepositions, and the definite article:
    # "واختبره" -> "اختبره", "بخطة" -> "خطة", "التطبيق" -> "تطبيق".
    arabic_prefixes = ("وال", "بال", "لل", "ال", "و", "ف", "ب", "ل", "ك")
    normalized_words = set(words)
    for word in words:
        for prefix in arabic_prefixes:
            if word.startswith(prefix) and len(word) > len(prefix) + 1:
                normalized_words.add(word[len(prefix):])
    words = normalized_words
    scored = []
    for skill in available:
        name = str(skill.get("name", ""))
        haystack = (name + " " + skill.get("description", "") + " " +
                    skill.get("content", "")[:2500]).lower()
        terms = set(re.findall(r"[a-z0-9_+-]+|[\u0600-\u06ff]+", haystack))
        score = len(words & terms)
        score += 2 * len(words & ENGLISH_SKILL_TERMS.get(name, set()))
        score += 3 * len(words & ARABIC_SKILL_TERMS.get(name, set()))
        if score:
            scored.append((score, name, skill))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [dict(item, relevance_score=score) for score, _, item in scored[:limit]]


def save_proposal(document: str, root: Path | None = None) -> dict:
    """Save a valid candidate under skills/proposed; never activate it automatically."""
    result = inspect_candidate(document)
    if not result["valid"]:
        return result
    directory = (root or ROOT) / "skills" / "proposed"
    directory.mkdir(parents=True, exist_ok=True)
    name = result["metadata"]["name"]
    active_target = (root or ROOT) / "skills" / "active" / name
    if active_target.exists():
        result["valid"] = False
        result["errors"].append("A skill with this name is already active; use a distinct proposal name.")
        return result
    target = directory / name / "SKILL.md"
    if target.exists():
        result["valid"] = False
        result["errors"].append("A proposal with this name already exists; review/update it explicitly.")
        return result
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document, encoding="utf-8")
    result.update({"saved_path": str(target), "status": "PROPOSED_REVIEW_REQUIRED",
                   "auto_activated": False})
    return result
