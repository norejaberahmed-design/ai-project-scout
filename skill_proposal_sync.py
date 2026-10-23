"""Reconcile committed review-only skill proposals into the local lifecycle registry.

This is metadata synchronization only. It never moves a proposal into skills/active,
loads candidate text into the model runtime, or executes upstream content.
"""
from __future__ import annotations

import re
from pathlib import Path

from component_acquisition import ALLOWED_LICENSES
from skill_registry import get_skill, register_discovery, transition_skill
from skill_runtime import inspect_candidate

ROOT = Path(__file__).resolve().parent
REVISION_RE = re.compile(r"^[a-f0-9]{40}$")
SKILL_URL_RE = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/blob/([a-f0-9]{40})/.+$"
)


def _field(document: str, label: str) -> str:
    match = re.search(rf"(?m)^- {re.escape(label)}:\s*(\S.*?)\s*$", document)
    return match.group(1).strip() if match else ""


def sync_proposed_skill_records(root: Path | None = None, db_path: str | Path | None = None) -> dict:
    """Register valid committed proposals idempotently while keeping them inactive."""
    base = root or ROOT
    proposed_dir = base / "skills" / "proposed"
    report = {"scanned": 0, "registered": 0, "skipped": 0, "items": [],
              "policy": "registry sync only; proposal text is never activated or executed"}
    if not proposed_dir.is_dir():
        return report

    for path in sorted(proposed_dir.glob("*/SKILL.md"))[:100]:
        report["scanned"] += 1
        name = path.parent.name
        attribution_path = path.parent / "ATTRIBUTION.md"
        license_path = path.parent / "UPSTREAM_LICENSE.txt"
        try:
            document = path.read_text(encoding="utf-8")
            attribution = attribution_path.read_text(encoding="utf-8")
            license_text = license_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            report["skipped"] += 1
            report["items"].append({"name": name, "status": "SKIPPED_MISSING_PROVENANCE"})
            continue

        checked = inspect_candidate(document)
        source_url = _field(attribution, "Skill file")
        revision = _field(attribution, "Immutable revision")
        license_spdx = _field(attribution, "Declared SPDX license")
        if (
            not checked.get("valid")
            or checked.get("metadata", {}).get("name") != name
            or not SKILL_URL_RE.fullmatch(source_url)
            or not REVISION_RE.fullmatch(revision)
            or source_url.split("/blob/", 1)[-1].split("/", 1)[0] != revision
            or license_spdx not in ALLOWED_LICENSES
            or len(license_text.strip()) < 100
        ):
            report["skipped"] += 1
            report["items"].append({"name": name, "status": "SKIPPED_INVALID_PROVENANCE_OR_CONTENT"})
            continue

        try:
            record = register_discovery(
                name, source_url,
                version=checked["metadata"].get("version", "1"),
                source_revision=revision,
                license_spdx=license_spdx,
                license_evidence=(
                    f"Upstream license text is retained at {license_path.relative_to(base)}; "
                    "automated verification passed during the harvest workflow; reviewer approval remains required."
                ),
                inspected_files=[str(path.relative_to(base)), str(attribution_path.relative_to(base)),
                                 str(license_path.relative_to(base))],
                evidence={
                    "capability": checked["metadata"].get("description", ""),
                    "source_revision": revision,
                    "license_text_retained": True,
                    "static_validation": checked,
                    "review_required": True,
                    "source_attribution": source_url,
                },
                risk_flags=["external_content_requires_human_review"],
                content=document,
                db_path=db_path,
            )
            current = get_skill(record["skill_id"], db_path=db_path)
            if current and current["status"] == "DISCOVERED":
                transition_skill(
                    record["skill_id"], "ANALYZED", db_path=db_path,
                    inspected_files=[str(path.relative_to(base)), str(attribution_path.relative_to(base)),
                                     str(license_path.relative_to(base))],
                    evidence={
                        "capability": checked["metadata"].get("description", ""),
                        "source_revision": revision,
                        "license_text_retained": True,
                        "static_validation": "passed",
                        "review_required": True,
                    },
                )
                current = get_skill(record["skill_id"], db_path=db_path)
            if current and current["status"] == "ANALYZED":
                transition_skill(record["skill_id"], "PROPOSED", db_path=db_path, content=document)
                current = get_skill(record["skill_id"], db_path=db_path)
            status = current["status"] if current else "REGISTRY_ERROR"
            created = status == "PROPOSED" and record.get("status") == "DISCOVERED"
            if created:
                report["registered"] += 1
            else:
                report["skipped"] += 1
            report["items"].append({"name": name, "skill_id": record["skill_id"], "status": status})
        except (OSError, ValueError, RuntimeError) as exc:
            report["skipped"] += 1
            report["items"].append({"name": name, "status": "REGISTRY_ERROR", "error": str(exc)[:250]})
    return report
