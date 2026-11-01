"""Offline tests for the GitHub agent catalog."""
import base64
import json
from scout import catalog


def test_classification_distinguishes_agent_framework_and_tutorial():
    repo = {"name": "demo-agent", "description": "Autonomous AI agent with tools and memory", "topics": []}
    kind, cats, caps, _ = catalog._classify(repo, "This autonomous agent uses browser and Python tools.")
    assert kind == "agent"
    assert "browser" in caps

    framework = {"name": "agent-framework", "description": "Framework and SDK for building LLM agents", "topics": []}
    assert catalog._classify(framework, "")[0] == "framework_or_library"

    tutorial = {"name": "awesome-agents", "description": "A tutorial and awesome list of agents", "topics": []}
    assert catalog._classify(tutorial, "")[0] == "tutorial_or_collection"


def test_score_is_bounded():
    repo = {"stargazers_count": 100000, "license": {"spdx_id": "MIT"}, "pushed_at": "2026-01-01"}
    assert 0 <= catalog._score(repo, "agent", "README", [{"claim": "x"}]) <= 100


def test_database_upsert_and_search(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "DB_PATH", tmp_path / "catalog.sqlite3")
    repo = {"id": 123, "full_name": "sample/demo-agent", "html_url": "https://github.com/sample/demo-agent",
            "name": "demo-agent", "description": "Autonomous coding agent", "topics": ["ai-agent"],
            "language": "Python", "license": {"spdx_id": "MIT"}, "stargazers_count": 12,
            "forks_count": 1, "open_issues_count": 0, "pushed_at": "2026-10-01T00:00:00Z",
            "default_branch": "main", "archived": False, "fork": False}
    catalog._save(repo, "README autonomous coding agent", "https://github.com/sample/demo-agent/blob/main/README.md")
    catalog._save(repo, "Updated README", "https://github.com/sample/demo-agent/blob/main/README.md")
    result = catalog.list_agents(query="demo-agent")
    assert result["total"] == 1
    assert result["items"][0]["github_id"] == 123
    assert result["items"][0]["categories"]


def test_catalog_is_read_only_about_upstream_code():
    source = open("scout/catalog.py", encoding="utf-8").read()
    assert "git clone" not in source.lower()
    assert "subprocess" not in source
