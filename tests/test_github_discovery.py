import base64
import unittest
from unittest.mock import patch

import github_discovery


class GitHubDiscoveryTests(unittest.TestCase):
    def test_repository_url_parser_rejects_non_repository_routes(self):
        self.assertEqual(github_discovery.repository_from_url("https://github.com/openai/openai"),
                         ("openai", "openai"))
        self.assertEqual(github_discovery.repository_from_url("github.com/openai/openai.git"),
                         ("openai", "openai"))
        self.assertIsNone(github_discovery.repository_from_url("https://github.com/openai/openai/issues/4"))
        self.assertIsNone(github_discovery.repository_from_url("https://example.org/openai/openai"))

    @patch("github_discovery.request_json")
    def test_repository_inspection_is_read_only_and_summarizes_evidence(self, request_json):
        readme = "# Demo\nThis project provides an AI agent.\n"
        request_json.side_effect = [
            {"full_name": "demo/agent", "html_url": "https://github.com/demo/agent",
             "description": "A test agent", "language": "Python", "stargazers_count": 42,
             "pushed_at": "2026-10-01T00:00:00Z", "license": {"spdx_id": "MIT"},
             "default_branch": "main"},
            {"tree": [{"type": "blob", "path": "pyproject.toml"},
                      {"type": "blob", "path": "tests/test_agent.py"},
                      {"type": "blob", "path": ".github/workflows/ci.yml"}]},
            {"encoding": "base64", "content": base64.b64encode(readme.encode()).decode()},
        ]
        result = github_discovery.inspect_repository("https://github.com/demo/agent")
        self.assertEqual(result["url"], "https://github.com/demo/agent")
        self.assertIn("License: MIT", result["snippet"])
        self.assertIn("pyproject.toml", result["snippet"])
        self.assertIn("README excerpt (untrusted text)", result["snippet"])
        self.assertIn("code was not run", result["snippet"])
        self.assertEqual(request_json.call_count, 3)

    @patch("github_discovery.request_json")
    def test_repository_search_returns_only_bounded_metadata(self, request_json):
        request_json.return_value = {"items": [
            {"full_name": "demo/tool", "html_url": "https://github.com/demo/tool",
             "description": "AI tool", "language": "Python", "stargazers_count": 5,
             "pushed_at": "2026-10-01T00:00:00Z", "license": {"spdx_id": "MIT"}}
        ]}
        results = github_discovery.search_repositories("discover AI agent tools")
        self.assertEqual(len(results), 1)
        self.assertIn("Metadata only", results[0]["snippet"])
        self.assertNotIn("source_code", results[0])
        self.assertIn("per_page=5", request_json.call_args.args[0])

    @patch("github_discovery.inspect_repository")
    def test_explicit_repository_url_triggers_inspection(self, inspect):
        inspect.return_value = {"title": "repo"}
        self.assertEqual(github_discovery.discover_github("Analyze https://github.com/demo/tool"),
                         [{"title": "repo"}])
        inspect.assert_called_once_with("https://github.com/demo/tool")

    @patch("github_discovery.search_repositories")
    def test_project_discovery_is_skipped_for_unrelated_chat(self, search):
        self.assertEqual(github_discovery.discover_github("What is 2 plus 2?"), [])
        search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
