"""Durable, fail-closed lifecycle registry for candidate AI skills.

This module records evidence and state. It does not execute skills or activate them
automatically. Activation is an explicit, reviewer-attributed transition after gates pass.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

STATUSES = {
    "DISCOVERED", "ANALYZED", "PROPOSED", "TESTED",
    "APPROVED", "ACTIVE", "REJECTED", "RETIRED",
}
ALLOWED_TRANSITIONS = {
    "DISCOVERED": {"ANALYZED", "REJECTED"},
    "ANALYZED": {"PROPOSED", "REJECTED"},
    "PROPOSED": {"TESTED", "REJECTED"},
    "TESTED": {"APPROVED", "REJECTED"},
    "APPROVED": {"ACTIVE", "REJECTED"},
    "ACTIVE": {"RETIRED"},
    "REJECTED": set(),
    "RETIRED": set(),
}
UNKNOWN_LICENSES = {"", "unknown", "none", "n/a", "noassertion", "other", "not specified"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db_path(db_path: str | Path | None = None) -> Path:
    raw = db_path or os.getenv("SCOUT_SKILL_DB_PATH", "data/skills.sqlite")
    return Path(raw)


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = _db_path(db_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def init_db(db_path: str | Path | None = None) -> None:
    """Create the registry schema idempotently; never delete or reset existing data."""
    with _connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS skill_records (
                skill_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT '1',
                status TEXT NOT NULL CHECK(status IN
                    ('DISCOVERED','ANALYZED','PROPOSED','TESTED','APPROVED','ACTIVE','REJECTED','RETIRED')),
                source_url TEXT NOT NULL,
                source_revision TEXT NOT NULL DEFAULT '',
                license_spdx TEXT NOT NULL DEFAULT '',
                license_evidence TEXT NOT NULL DEFAULT '',
                license_verified INTEGER NOT NULL DEFAULT 0 CHECK(license_verified IN (0,1)),
                inspected_files_json TEXT NOT NULL DEFAULT '[]',
                evidence_json TEXT NOT NULL DEFAULT '{}',
                risk_flags_json TEXT NOT NULL DEFAULT '[]',
                source_content_sha256 TEXT NOT NULL DEFAULT '',
                content_sha256 TEXT NOT NULL DEFAULT '',
                test_result TEXT NOT NULL DEFAULT 'NOT_RUN'
                    CHECK(test_result IN ('NOT_RUN','PASSED','FAILED')),
                test_command TEXT NOT NULL DEFAULT '',
                test_report_json TEXT NOT NULL DEFAULT '{}',
                reviewer TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                activated_at TEXT NOT NULL DEFAULT ''
            )
        """)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(skill_records)")}
        if "source_content_sha256" not in columns:
            conn.execute("ALTER TABLE skill_records ADD COLUMN source_content_sha256 TEXT NOT NULL DEFAULT ''")
        if "license_verified" not in columns:
            conn.execute("ALTER TABLE skill_records ADD COLUMN license_verified INTEGER NOT NULL DEFAULT 0")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_records_status ON skill_records(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_records_name ON skill_records(name)")


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _decode(row: sqlite3.Row) -> dict:
    item = dict(row)
    for column, target in (
        ("inspected_files_json", "inspected_files"),
        ("evidence_json", "evidence"),
        ("risk_flags_json", "risk_flags"),
        ("test_report_json", "test_report"),
    ):
        item[target] = json.loads(item.pop(column))
    return item


def register_discovery(
    name: str,
    source_url: str,
    *,
    version: str = "1",
    source_revision: str = "",
    license_spdx: str = "",
    license_evidence: str = "",
    inspected_files: list[str] | None = None,
    evidence: dict | None = None,
    risk_flags: list[str] | None = None,
    content: str = "",
    source_content_sha256: str = "",
    db_path: str | Path | None = None,
) -> dict:
    """Record a discovered candidate without trusting or executing its contents."""
    name = (name or "").strip().lower()
    parsed = urlparse((source_url or "").strip())
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        raise ValueError("name must be a lowercase slug")
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ValueError("source_url must be an absolute HTTP(S) URL")
    if len(source_url) > 2048:
        raise ValueError("source_url is too long")
    flags = sorted({str(flag)[:120] for flag in (risk_flags or [])})
    files = [str(item)[:500] for item in (inspected_files or [])[:100]]
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest() if content else source_content_sha256.strip().lower()
    if digest and not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("source_content_sha256 must be a 64-character SHA-256 hex digest")
    identity = "|".join((name, source_url.strip(), str(source_revision)[:200], digest))
    skill_id = str(uuid.uuid5(uuid.NAMESPACE_URL, identity))
    now = _now()
    init_db(db_path)
    with _connect(db_path) as conn:
        conn.execute("""
            INSERT OR IGNORE INTO skill_records (
                skill_id,name,version,status,source_url,source_revision,license_spdx,
                license_evidence,license_verified,inspected_files_json,evidence_json,risk_flags_json,
                source_content_sha256,content_sha256,created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (skill_id, name, str(version)[:80], "DISCOVERED", source_url.strip(),
              str(source_revision)[:200], str(license_spdx)[:80],
              str(license_evidence)[:2000], 0, _json(files), _json(evidence or {}),
              _json(flags), digest, "", now, now))
    return get_skill(skill_id, db_path)


def get_skill(skill_id: str, db_path: str | Path | None = None) -> dict | None:
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM skill_records WHERE skill_id=?", (skill_id,)).fetchone()
    return _decode(row) if row else None


def list_skills(status: str | None = None, db_path: str | Path | None = None) -> list[dict]:
    init_db(db_path)
    with _connect(db_path) as conn:
        if status is not None:
            if status not in STATUSES:
                raise ValueError("Unknown skill status")
            rows = conn.execute(
                "SELECT * FROM skill_records WHERE status=? ORDER BY updated_at DESC, name",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM skill_records ORDER BY updated_at DESC, name").fetchall()
    return [_decode(row) for row in rows]


def transition_skill(
    skill_id: str,
    target_status: str,
    *,
    db_path: str | Path | None = None,
    reviewer: str = "",
    test_result: str | None = None,
    test_command: str | None = None,
    test_report: dict | None = None,
    license_spdx: str | None = None,
    license_evidence: str | None = None,
    license_verified: bool | None = None,
    risk_flags: list[str] | None = None,
    inspected_files: list[str] | None = None,
    evidence: dict | None = None,
    content: str | None = None,
) -> dict:
    """Apply one explicit lifecycle transition, enforcing gates in code."""
    if target_status not in STATUSES:
        raise ValueError("Unknown target status")
    init_db(db_path)
    with _connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM skill_records WHERE skill_id=?", (skill_id,)).fetchone()
        if row is None:
            raise ValueError("Skill record not found")
        current = row["status"]
        if target_status not in ALLOWED_TRANSITIONS[current]:
            raise ValueError(f"Invalid lifecycle transition: {current} -> {target_status}")

        updates: dict[str, object] = {"status": target_status, "updated_at": _now()}
        if license_spdx is not None:
            updates["license_spdx"] = license_spdx.strip()[:80]
        if license_evidence is not None:
            updates["license_evidence"] = license_evidence.strip()[:2000]
        if license_verified is not None:
            updates["license_verified"] = 1 if license_verified else 0
        if risk_flags is not None:
            updates["risk_flags_json"] = _json(sorted({str(x)[:120] for x in risk_flags}))
        if inspected_files is not None:
            updates["inspected_files_json"] = _json([str(x)[:500] for x in inspected_files[:100]])
        if evidence is not None:
            updates["evidence_json"] = _json(evidence)
        if content is not None:
            updates["content_sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if target_status == "ANALYZED":
            effective_files = updates.get("inspected_files_json", row["inspected_files_json"])
            effective_evidence = updates.get("evidence_json", row["evidence_json"])
            if not json.loads(effective_files):
                raise ValueError("Analysis requires a record of inspected files")
            if not json.loads(effective_evidence):
                raise ValueError("Analysis requires concrete evidence")
        if target_status == "PROPOSED":
            effective_hash = updates.get("content_sha256", row["content_sha256"])
            if not effective_hash:
                raise ValueError("Proposal requires a skill document content hash")
        if test_result is not None:
            if target_status != "TESTED" or test_result not in {"PASSED", "FAILED"}:
                raise ValueError("A TESTED transition requires test_result PASSED or FAILED")
            if not test_command or not test_command.strip():
                raise ValueError("A reproducible test command is required")
            if not isinstance(test_report, dict) or not test_report:
                raise ValueError("A structured test report is required")
            failures = int(test_report.get("failures", 0) or 0)
            errors = int(test_report.get("errors", 0) or 0)
            exit_code = test_report.get("exit_code", 0)
            if test_result == "PASSED" and (failures or errors or exit_code != 0):
                raise ValueError("A passing test result cannot include failures, errors, or a nonzero exit code")
            updates.update({
                "test_result": test_result,
                "test_command": test_command.strip()[:1000],
                "test_report_json": _json(test_report),
            })
        elif target_status == "TESTED":
            raise ValueError("A TESTED transition requires an explicit test result")
        if target_status == "APPROVED":
            effective_license = (updates.get("license_spdx", row["license_spdx"]) or "").strip().lower()
            effective_license_evidence = (updates.get("license_evidence", row["license_evidence"]) or "").strip()
            effective_flags = json.loads(updates.get("risk_flags_json", row["risk_flags_json"]))
            if row["test_result"] != "PASSED":
                raise ValueError("Approval blocked: passing test evidence is required")
            effective_license_verified = bool(updates.get("license_verified", False))
            if ("license_verified" not in updates or not effective_license_verified
                    or "license_evidence" not in updates or not effective_license_evidence
                    or effective_license.lower() in UNKNOWN_LICENSES):
                raise ValueError("Approval blocked: license must be verified with explicit supporting evidence in this review")
            if effective_flags:
                raise ValueError("Approval blocked: unresolved risk flags remain")
            if not reviewer.strip():
                raise ValueError("Approval requires an explicit reviewer")
            updates["reviewer"] = reviewer.strip()[:200]
        if target_status == "ACTIVE":
            if not reviewer.strip():
                raise ValueError("Activation requires an explicit reviewer")
            if row["status"] != "APPROVED":
                raise ValueError("Activation requires APPROVED status")
            if row["test_result"] != "PASSED":
                raise ValueError("Activation blocked: passing test evidence is required")
            if ((row["license_spdx"] or "").strip().lower() in UNKNOWN_LICENSES
                    or not row["license_evidence"].strip() or not row["license_verified"]):
                raise ValueError("Activation blocked: verified license evidence is missing")
            if json.loads(row["risk_flags_json"]):
                raise ValueError("Activation blocked: unresolved risk flags remain")
            updates["reviewer"] = reviewer.strip()[:200]
            updates["activated_at"] = _now()
        assignments = ",".join(f"{key}=?" for key in updates)
        conn.execute(
            f"UPDATE skill_records SET {assignments} WHERE skill_id=?",
            (*updates.values(), skill_id),
        )
        result = conn.execute("SELECT * FROM skill_records WHERE skill_id=?", (skill_id,)).fetchone()
    return _decode(result)
