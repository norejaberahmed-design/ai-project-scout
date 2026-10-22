import json
import unittest
from unittest.mock import patch

import web_search


class WebSearchTests(unittest.TestCase):
    def test_empty_query_is_rejected_before_network(self):
        with self.assertRaises(ValueError):
            web_search.search_web("  ", api_key="test-key")

    def test_long_query_is_rejected(self):
        with self.assertRaises(ValueError):
            web_search.search_web("x" * (web_search.MAX_QUERY_CHARS + 1), api_key="test-key")

    def test_missing_key_is_reported_without_network(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "TAVILY_API_KEY"):
                web_search.search_web("test", api_key="")

    @patch("web_search.urllib.request.urlopen")
    def test_search_returns_bounded_source_links_and_coverage_note(self, urlopen):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, limit):
                self.asserted_limit = limit
                return json.dumps({"results": [
                    {"title": "Source A", "url": "https://example.org/a", "content": "Evidence", "score": 0.9},
                    {"title": "Bad URL", "url": "javascript:alert(1)", "content": "Ignore"},
                    {"title": "", "url": "https://example.org/no-title", "content": "Skip"},
                ]}).encode()
        urlopen.return_value = Response()
        result = web_search.search_web("  public AI tools  ", api_key="test-key")
        self.assertEqual(result["query"], "public AI tools")
        self.assertEqual(result["result_count"], 1)
        self.assertEqual(result["results"][0]["url"], "https://example.org/a")
        self.assertIn("not every website", result["coverage_note"])
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode())
        self.assertEqual(payload["query"], "public AI tools")
        self.assertEqual(payload["api_key"], "test-key")
        self.assertFalse(payload["include_raw_content"])

    @patch("web_search.urllib.request.urlopen")
    def test_provider_error_does_not_disclose_secret(self, urlopen):
        import urllib.error
        urlopen.side_effect = urllib.error.HTTPError(
            "https://api.tavily.com/search", 401, "unauthorized", {}, None
        )
        with self.assertRaises(RuntimeError) as caught:
            web_search.search_web("test", api_key="do-not-leak-this")
        self.assertNotIn("do-not-leak-this", str(caught.exception))
        self.assertIn("HTTP 401", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
