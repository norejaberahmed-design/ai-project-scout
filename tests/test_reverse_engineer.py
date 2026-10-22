import unittest

from reverse_engineer import analyze_snapshot, inspect_candidates


class ReverseEngineerTests(unittest.TestCase):
    def test_architecture_and_risk_are_reported_without_claiming_integration(self):
        meta = {
            "html_url": "https://github.com/example/agent",
            "description": "AI tool server",
            "stargazers_count": 42,
            "language": "Python",
            "license": {"spdx_id": "MIT"},
            "default_branch": "main",
            "pushed_at": "2026-10-01T00:00:00Z",
        }
        tree = {"tree": [
            {"path": "src/main.py", "type": "blob"},
            {"path": "pyproject.toml", "type": "blob"},
            {"path": ".github/workflows/test.yml", "type": "blob"},
            {"path": "scripts/install.sh", "type": "blob"},
        ]}
        result = analyze_snapshot("example/agent", meta, tree,
            "# Agent\n\nThis MCP server exposes tool calling and a FastAPI API.\n" * 20,
            {"pyproject.toml": "[project]\nname='agent'\n"})
        self.assertIn("MCP / tool server", [x["capability"] for x in result["architecture_signals"]])
        self.assertIn("src/main.py", result["entrypoint_candidates"])
        self.assertEqual(result["decision"], "manual_review_required")
        self.assertEqual(result["license_decision"], "review_terms_and_attribution_before_reuse")
        self.assertTrue(result["risk_flags"])

    def test_inspector_uses_bounded_read_only_requests(self):
        calls = []
        def fake_fetch(url):
            calls.append(url)
            if url.endswith("/repos/example/agent"):
                return {"html_url": "https://github.com/example/agent", "default_branch": "main",
                        "license": {"spdx_id": "UNKNOWN"}}
            if "/git/trees/" in url:
                return {"tree": [{"path": "README.md", "type": "blob", "sha": "abc"}]}
            if url.endswith("/git/blobs/abc"):
                import base64
                return {"encoding": "base64", "content": base64.b64encode(b"# Small\n").decode()}
            raise AssertionError("unexpected endpoint " + url)
        report = inspect_candidates({"candidates": [{"repository": "example/agent"}]}, fetcher=fake_fetch, limit=1)
        self.assertEqual(report["analyzed_count"], 1)
        self.assertEqual(report["results"][0]["license_decision"], "do_not_copy_until_license_verified")
        self.assertTrue(all(url.startswith("https://api.github.com/") for url in calls))
        self.assertEqual(report["mode"], "read_only_public_source_static_recon")


if __name__ == "__main__":
    unittest.main()
