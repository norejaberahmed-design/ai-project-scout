"""Evidence-first business decision calculations for Atlas.

This module is deliberately deterministic: it never invents vendor evidence or
claims that a solution has been tested. LLM-assisted research can be layered
on top later, while these calculations remain auditable.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any


class InputError(ValueError):
    """Raised when a decision request contains invalid or incomplete inputs."""


def _number(data: dict[str, Any], key: str, *, minimum: float = 0.0,
            maximum: float | None = None, required: bool = True,
            default: float = 0.0) -> float:
    value = data.get(key, default)
    if value is None and not required:
        return default
    if isinstance(value, bool):
        raise InputError(f"{key} must be a number")
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise InputError(f"{key} must be a number") from None
    if not math.isfinite(parsed) or parsed < minimum:
        raise InputError(f"{key} must be at least {minimum}")
    if maximum is not None and parsed > maximum:
        raise InputError(f"{key} must be at most {maximum}")
    return parsed


def calculate_roi(payload: dict[str, Any]) -> dict[str, Any]:
    """Calculate a transparent monthly ROI scenario from user-provided inputs."""
    if not isinstance(payload, dict):
        raise InputError("Request body must be a JSON object")

    invoice_count = _number(payload, "monthly_volume", minimum=1)
    minutes_per_item = _number(payload, "minutes_per_item", minimum=0.01)
    hourly_cost = _number(payload, "hourly_cost", minimum=0)
    automation_rate = _number(payload, "automation_rate", minimum=0, maximum=1)
    review_minutes = _number(
        payload, "review_minutes_per_automated_item", minimum=0,
        required=False, default=0
    )
    software_cost = _number(
        payload, "software_monthly_cost", minimum=0,
        required=False, default=0
    )
    implementation_cost = _number(
        payload, "implementation_cost", minimum=0,
        required=False, default=0
    )
    amortization_months = _number(
        payload, "amortization_months", minimum=1, maximum=120,
        required=False, default=12
    )

    if review_minutes > minutes_per_item:
        raise InputError("review_minutes_per_automated_item cannot exceed minutes_per_item")

    baseline_hours = invoice_count * minutes_per_item / 60
    automated_items = invoice_count * automation_rate
    hours_saved = automated_items * (minutes_per_item - review_minutes) / 60
    gross_savings = hours_saved * hourly_cost
    amortized_implementation = implementation_cost / amortization_months
    monthly_total_cost = software_cost + amortized_implementation
    net_monthly_benefit = gross_savings - monthly_total_cost
    roi_percent = (
        (net_monthly_benefit / monthly_total_cost) * 100
        if monthly_total_cost > 0 else None
    )
    monthly_cash_surplus_before_amortization = gross_savings - software_cost
    payback_months = (
        implementation_cost / monthly_cash_surplus_before_amortization
        if implementation_cost > 0 and monthly_cash_surplus_before_amortization > 0
        else (0 if implementation_cost == 0 else None)
    )

    return {
        "currency": str(payload.get("currency") or "SAR")[:8],
        "monthly_volume": int(invoice_count),
        "baseline_monthly_hours": round(baseline_hours, 2),
        "estimated_hours_saved_monthly": round(hours_saved, 2),
        "estimated_gross_savings_monthly": round(gross_savings, 2),
        "software_monthly_cost": round(software_cost, 2),
        "implementation_cost": round(implementation_cost, 2),
        "amortized_implementation_monthly": round(amortized_implementation, 2),
        "estimated_net_benefit_monthly": round(net_monthly_benefit, 2),
        "estimated_roi_percent": round(roi_percent, 2) if roi_percent is not None else None,
        "estimated_payback_months": round(payback_months, 2) if payback_months is not None else None,
        "assumptions": [
            "All operational and cost inputs were supplied by the user.",
            "Automation rate is an assumption, not a measured vendor result.",
            "Savings exclude taxes, financing, change management and unprovided costs.",
            "Actual results require a pilot using the customer's own records."
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "scenario_not_verified"
    }


def compare_solutions(solutions: Any) -> dict[str, Any]:
    """Normalize solution evidence without treating missing facts as positives."""
    if not isinstance(solutions, list) or not 1 <= len(solutions) <= 20:
        raise InputError("solutions must be a list containing 1 to 20 items")

    results = []
    for index, raw in enumerate(solutions):
        if not isinstance(raw, dict):
            raise InputError(f"solutions[{index}] must be an object")
        name = str(raw.get("name") or "").strip()[:120]
        if not name:
            raise InputError(f"solutions[{index}].name is required")
        source_url = str(raw.get("source_url") or "").strip()[:500]
        if source_url and not source_url.startswith(("https://", "http://")):
            raise InputError(f"solutions[{index}].source_url must be an HTTP(S) URL")
        facts = {
            "pricing": raw.get("pricing"),
            "license": raw.get("license"),
            "integration": raw.get("integration"),
            "security": raw.get("security"),
            "support": raw.get("support"),
        }
        known = [key for key, value in facts.items() if value not in (None, "")]
        results.append({
            "name": name,
            "provider": str(raw.get("provider") or "")[:120],
            "source_url": source_url or None,
            "source_status": "source_provided_not_verified" if source_url else "no_source_provided",
            "facts": facts,
            "evidence_completeness_percent": round(len(known) / len(facts) * 100),
            "missing_facts": [key for key, value in facts.items() if value in (None, "")],
            "fit_score": None,
            "recommendation": "requires_human_review",
        })

    results.sort(key=lambda item: item["evidence_completeness_percent"], reverse=True)
    return {
        "items": results,
        "method": "evidence_completeness_only",
        "notice": "This is not a quality, security, compliance, or vendor endorsement ranking.",
        "status": "comparison_draft"
    }


def build_decision_report(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a report payload with calculations and explicit evidence limitations."""
    if not isinstance(payload, dict):
        raise InputError("Request body must be a JSON object")
    title = str(payload.get("title") or "تقرير قرار أطلس").strip()[:160]
    problem = str(payload.get("problem") or "").strip()[:2000]
    if not problem:
        raise InputError("problem is required")
    roi = calculate_roi(payload.get("roi_inputs") or {})
    comparison = compare_solutions(payload.get("solutions") or [])
    return {
        "title": title,
        "problem": problem,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "roi": roi,
        "comparison": comparison,
        "decision": "not_enough_verified_evidence",
        "limitations": [
            "No vendor has been independently tested by this report.",
            "Vendor claims and submitted source URLs require human verification.",
            "ROI is a scenario based on supplied assumptions, not a guaranteed outcome.",
            "Do not use this draft as legal, cybersecurity, or regulatory certification."
        ],
        "report_status": "draft_not_saved"
    }
