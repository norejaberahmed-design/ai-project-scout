"""Tests for Atlas deterministic business decision APIs."""
from atlas import app as atlas_app


def test_roi_calculation_is_transparent_and_repeatable():
    client = atlas_app.app.test_client()
    response = client.post("/api/decision/analyze", json={
        "monthly_volume": 1000,
        "minutes_per_item": 6,
        "hourly_cost": 35,
        "automation_rate": 0.5,
        "software_monthly_cost": 299,
        "implementation_cost": 1200,
        "amortization_months": 12,
        "currency": "SAR",
    })

    assert response.status_code == 200
    data = response.get_json()
    assert data["baseline_monthly_hours"] == 100
    assert data["estimated_hours_saved_monthly"] == 50
    assert data["estimated_gross_savings_monthly"] == 1750
    assert data["software_monthly_cost"] == 299
    assert data["status"] == "scenario_not_verified"
    assert data["estimated_net_benefit_monthly"] == 1351


def test_roi_rejects_invalid_rates_and_inconsistent_review_time():
    client = atlas_app.app.test_client()
    bad_rate = client.post("/api/decision/analyze", json={
        "monthly_volume": 100, "minutes_per_item": 5,
        "hourly_cost": 30, "automation_rate": 1.2,
    })
    bad_review = client.post("/api/decision/analyze", json={
        "monthly_volume": 100, "minutes_per_item": 5,
        "hourly_cost": 30, "automation_rate": 0.5,
        "review_minutes_per_automated_item": 6,
    })

    assert bad_rate.status_code == 400
    assert bad_review.status_code == 400


def test_comparison_marks_missing_evidence_instead_of_assuming_it():
    client = atlas_app.app.test_client()
    response = client.post("/api/decision/compare", json={"solutions": [
        {"name": "Vendor A", "source_url": "https://example.com", "pricing": "299 SAR/month"},
        {"name": "Vendor B"},
    ]})

    assert response.status_code == 200
    data = response.get_json()
    assert data["method"] == "evidence_completeness_only"
    assert data["items"][0]["evidence_completeness_percent"] == 20
    assert data["items"][1]["source_status"] == "no_source_provided"
    assert data["items"][1]["recommendation"] == "requires_human_review"


def test_report_is_explicitly_draft_and_not_saved():
    client = atlas_app.app.test_client()
    response = client.post("/api/decision/report", json={
        "title": "Invoice automation",
        "problem": "Manual invoice processing",
        "roi_inputs": {
            "monthly_volume": 1000, "minutes_per_item": 6,
            "hourly_cost": 35, "automation_rate": 0.5,
        },
        "solutions": [{"name": "Example platform"}],
    })

    assert response.status_code == 200
    data = response.get_json()
    assert data["report_status"] == "draft_not_saved"
    assert data["decision"] == "not_enough_verified_evidence"
    assert data["roi"]["estimated_gross_savings_monthly"] == 1750


def test_report_requires_problem_and_compare_requires_named_solutions():
    client = atlas_app.app.test_client()
    missing_problem = client.post("/api/decision/report", json={"roi_inputs": {}})
    missing_name = client.post("/api/decision/compare", json={"solutions": [{}]})

    assert missing_problem.status_code == 400
    assert missing_name.status_code == 400
