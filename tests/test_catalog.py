"""Offline tests for the GitHub AI ecosystem catalog."""
from scout import catalog


def test_classification_distinguishes_agents_frameworks_and_collections():
    repo = {"name": "demo-agent", "description": "Autonomous AI agent with tools and memory", "topics": []}
    kind, cats, caps, _ = catalog._classify(repo, "This autonomous agent uses browser and Python tools.")
    assert kind == "agent"
    assert "agents" in cats
    assert "browser" in caps

    framework = {"name": "agent-framework", "description": "Framework and SDK for building LLM agents", "topics": []}
    assert catalog._classify(framework, "")[0] == "framework_or_library"

    tutorial = {"name": "awesome-agents", "description": "A tutorial and awesome list of agents", "topics": []}
    assert catalog._classify(tutorial, "")[0] == "tutorial_or_collection"


def test_classification_covers_mcp_inference_and_developer_tools():
    mcp = {"name": "sample-mcp", "description": "Model Context Protocol server exposing tools", "topics": ["mcp"]}
    assert catalog._classify(mcp, "")[0] == "mcp_server_or_tool"

    inference = {"name": "llm-serving", "description": "Fast inference server for local LLM model serving", "topics": []}
    assert catalog._classify(inference, "")[0] == "model_or_inference_tool"

    devtool = {"name": "llm-observability-cli", "description": "Developer tool for LLM tracing and observability", "topics": []}
    assert catalog._classify(devtool, "")[0] == "developer_tool"


def test_discovery_queries_cover_multiple_ai_ecosystem_lanes():
    queries = " ".join(catalog.SEARCH_QUERIES).lower()
    for term in ("agent", "mcp", "rag", "developer tool", "inference", "vector database"):
        assert term in queries
    assert len(catalog.SEARCH_QUERIES) <= catalog.MAX_QUERIES


def test_score_is_bounded():
    repo = {"stargazers_count": 100000, "license": {"spdx_id": "MIT"}, "pushed_at": "2026-01-01"}
    assert 0 <= catalog._score(repo, "agent", "README", [{"claim": "x"}]) <= 100


def test_database_upsert_migrates_and_searches_topics(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "DB_PATH", tmp_path / "catalog.sqlite3")
    repo = {"id": 123, "full_name": "sample/demo-agent", "html_url": "https://github.com/sample/demo-agent",
            "name": "demo-agent", "description": "Autonomous coding agent", "topics": ["ai-agent", "coding"],
            "homepage": "https://example.org", "language": "Python",
            "license": {"spdx_id": "MIT", "name": "MIT License"}, "stargazers_count": 12,
            "forks_count": 1, "open_issues_count": 0, "pushed_at": "2026-10-01T00:00:00Z",
            "default_branch": "main", "archived": False, "fork": False}
    catalog._save(repo, "README autonomous coding agent", "https://github.com/sample/demo-agent/blob/main/README.md")
    catalog._save(repo, "Updated README", "https://github.com/sample/demo-agent/blob/main/README.md")
    result = catalog.list_agents(query="coding")
    assert result["total"] == 1
    assert result["items"][0]["github_id"] == 123
    assert result["items"][0]["categories"]
    assert result["items"][0]["topics"] == ["ai-agent", "coding"]
    assert result["items"][0]["homepage"] == "https://example.org"
    assert result["items"][0]["license_name"] == "MIT License"


def test_catalog_is_read_only_about_upstream_code():
    source = open("scout/catalog.py", encoding="utf-8").read()
    assert "git clone" not in source.lower()
    assert "subprocess" not in source


def test_catalog_api_routes_are_registered_and_catalog_only(tmp_path, monkeypatch):
    import app as webapp
    monkeypatch.setattr(catalog, "DB_PATH", tmp_path / "api-catalog.sqlite3")
    client = webapp.app.test_client()
    page = client.get("/agents")
    assert page.status_code == 200
    assert "دليل أدوات ووكلاء الذكاء الاصطناعي".encode("utf-8") in page.data
    status = client.get("/api/agents/status")
    assert status.status_code == 200
    assert status.json["mode"] == "catalog_only"
    assert status.json["scope"] == "github_open_source_ai_ecosystem"
    assert status.json["database"] == "SQLite"
    listing = client.get("/api/agents")
    assert listing.status_code == 200
    assert listing.json["total"] == 0
