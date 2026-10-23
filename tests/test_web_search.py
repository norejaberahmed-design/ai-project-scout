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

    def test_missing_key_uses_general_web_search_fallback(self):
        fallback = {"query": "test", "provider": "DuckDuckGo",
                    "results": [{"title": "Source", "url": "https://example.org", "snippet": "Evidence"}],
                    "result_count": 1, "coverage_note": "general web"}
        with patch.dict("os.environ", {}, clear=True), patch("web_search._search_duckduckgo", return_value=fallback) as search:
            result = web_search.search_web("test", api_key="")
        self.assertEqual(result["provider"], "DuckDuckGo")
        search.assert_called_once_with("test", 20)

    def test_duckduckgo_parser_extracts_search_results(self):
        page = """
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fguide">A useful guide</a>
        <div class="result__snippet">Public web evidence and examples</div>
        """
        parser = web_search._DuckDuckGoParser()
        parser.feed(page)
        self.assertEqual(parser.results[0]["title"], "A useful guide")
        self.assertEqual(parser.results[0]["url"], "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fguide")
        self.assertIn("Public web evidence", parser.results[0]["snippet"])

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
        self.assertIn("لا تشمل كل الإنترنت", result["coverage_note"])
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode())
        self.assertEqual(payload["query"], "public AI tools")
        self.assertEqual(payload["api_key"], "test-key")
        self.assertFalse(payload["include_raw_content"])

    @patch("web_search.urllib.request.urlopen")
    def test_tavily_failure_falls_back_to_general_web_search(self, urlopen):
        import urllib.error
        urlopen.side_effect = urllib.error.HTTPError(
            "https://api.tavily.com/search", 401, "unauthorized", {}, None
        )
        fallback = {"query": "test", "provider": "DuckDuckGo",
                    "results": [{"title": "Source", "url": "https://example.org", "snippet": "Evidence"}],
                    "result_count": 1, "coverage_note": "general web"}
        with patch("web_search._search_duckduckgo", return_value=fallback):
            result = web_search.search_web("test", api_key="do-not-leak-this")
        self.assertEqual(result["provider"], "DuckDuckGo")
        self.assertIn("fallback_note", result)
        self.assertNotIn("do-not-leak-this", str(result))

    @patch("web_search._search_tavily")
    def test_tutorial_queries_add_youtube_sources_near_front(self, search_tavily):
        search_tavily.side_effect = [
            {"query": "AI agent skills tutorial", "provider": "Tavily", "results": [
                {"title": "Web result " + str(i), "url": "https://example.org/" + str(i),
                 "snippet": "Evidence", "source": "Tavily"} for i in range(8)
            ], "result_count": 8, "coverage_note": "public web"},
            {"query": "AI agent skills tutorial", "provider": "Tavily", "results": [
                {"title": "Video tutorial", "url": "https://www.youtube.com/watch?v=abc123",
                 "snippet": "Video evidence", "source": "Tavily"}
            ], "result_count": 1, "coverage_note": "public web"},
        ]
        result = web_search.search_web("AI agent skills tutorial", api_key="test-key")
        self.assertEqual(result["youtube_search"], "searched")
        self.assertEqual(result["results"][4]["url"], "https://www.youtube.com/watch?v=abc123")
        self.assertEqual(result["results"][4]["source"], "YouTube-focused discovery")
        self.assertEqual(result["result_count"], 9)


if __name__ == "__main__":
    unittest.main()
