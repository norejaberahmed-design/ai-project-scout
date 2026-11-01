"""Offline regression tests for the standalone Atlas application."""
import json

from atlas import app as atlas_app


def test_health_creates_configured_cache_directory(tmp_path, monkeypatch):
    db_path = tmp_path / "nested" / "atlas.sqlite3"
    monkeypatch.setattr(atlas_app, "DB_PATH", str(db_path))

    response = atlas_app.app.test_client().get("/api/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "ok",
        "app": "Atlas AI",
        "database": "ok",
    }
    assert db_path.exists()


def test_categories_exposes_nine_supported_lanes():
    response = atlas_app.app.test_client().get("/api/categories")

    assert response.status_code == 200
    categories = response.get_json()
    assert len(categories) == 9
    assert {item["id"] for item in categories} == set(atlas_app.CATEGORIES)


def test_discovery_caches_github_response_and_closes_database(tmp_path, monkeypatch):
    db_path = tmp_path / "cache" / "atlas.sqlite3"
    monkeypatch.setattr(atlas_app, "DB_PATH", str(db_path))
    calls = []

    payload = {
        "total_count": 1,
        "items": [{
            "id": 77,
            "name": "demo-agent",
            "full_name": "sample/demo-agent",
            "description": "A public AI agent project",
            "html_url": "https://github.com/sample/demo-agent",
            "stargazers_count": 42,
            "language": "Python",
            "updated_at": "2026-10-01T00:00:00Z",
            "license": {"spdx_id": "MIT"},
            "topics": ["ai-agent"],
            "forks_count": 3,
            "open_issues_count": 1,
            "archived": False,
            "owner": {"login": "sample"},
        }],
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, timeout))
        return FakeResponse()

    monkeypatch.setattr(atlas_app.urllib.request, "urlopen", fake_urlopen)
    client = atlas_app.app.test_client()

    first = client.get("/api/discover?q=agent&category=all")
    second = client.get("/api/discover?q=agent&category=all")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.get_json()["items"][0]["full_name"] == "sample/demo-agent"
    assert first.get_json()["cached"] is False
    assert second.get_json()["cached"] is True
    assert len(calls) == 1
    assert db_path.exists()


def test_invalid_category_falls_back_to_all_without_external_call(tmp_path, monkeypatch):
    monkeypatch.setattr(atlas_app, "DB_PATH", str(tmp_path / "atlas.sqlite3"))

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"total_count": 0, "items": []}'

    monkeypatch.setattr(
        atlas_app.urllib.request, "urlopen", lambda request, timeout: FakeResponse()
    )
    response = atlas_app.app.test_client().get("/api/discover?category=not-a-category")

    assert response.status_code == 200
    assert response.get_json()["total"] == 0
