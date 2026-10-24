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

    @patch("web_search._request")
    def test_bing_rss_fallback_parses_only_http_source_links(self, request):
        request.return_value = b"""<?xml version="1.0"?>
        <rss><channel>
          <item><title>Useful documentation</title><link>https://example.org/docs</link><description>Public evidence</description></item>
          <item><title>Unsafe link</title><link>javascript:alert(1)</link><description>Ignore</description></item>
        </channel></rss>"""
        result = web_search._search_bing_rss("test", timeout=3)
        self.assertEqual(result["provider"], "Bing RSS")
        self.assertEqual(result["result_count"], 1)
        self.assertEqual(result["results"][0]["url"], "https://example.org/docs")
        request.assert_called_once()

    @patch("web_search._search_bing_rss")
    @patch("web_search._search_duckduckgo")
    def test_public_search_tries_bing_when_duckduckgo_fails(self, duckduckgo, bing):
        duckduckgo.side_effect = RuntimeError("blocked")
        bing.return_value = {
            "query": "test", "provider": "Bing RSS",
            "results": [{"title": "Source", "url": "https://example.org", "snippet": "Evidence"}],
            "result_count": 1, "coverage_note": "public web",
        }
        result = web_search._search_public_web("test", timeout=4)
        self.assertEqual(result["provider"], "Bing RSS")
        self.assertIn("fallback_note", result)
        duckduckgo.assert_called_once_with("test", 4)
        bing.assert_called_once_with("test", 4)

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
        result = web_search.search_web("  public science results  ", api_key="test-key")
        self.assertEqual(result["query"], "public science results")
        self.assertEqual(result["result_count"], 1)
        self.assertEqual(result["results"][0]["url"], "https://example.org/a")
        self.assertIn("لا تشمل كل الإنترنت", result["coverage_note"])
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode())
        self.assertEqual(payload["query"], "public science results")
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
    def test_skill_queries_do_not_trigger_video_search(self, search_tavily):
        search_tavily.return_value = {
            "query": "agent skills", "provider": "Tavily",
            "results": [{"title": "Skill guide", "url": "https://example.org/skills",
                         "snippet": "Evidence", "score": 0.9}],
            "result_count": 1, "coverage_note": "public web",
        }
        result = web_search.search_web("agent skills", api_key="test-key")
        self.assertEqual(result["result_count"], 1)
        self.assertNotIn("youtube_search", result)
        search_tavily.assert_called_once_with("agent skills", "test-key", 20)



    def test_build_research_queries_is_bounded_and_keeps_original_first(self):
        queries = web_search.build_research_queries("How do Python AI agents work?")
        self.assertEqual(queries[0], "How do Python AI agents work?")
        self.assertGreaterEqual(len(queries), 2)
        self.assertLessEqual(len(queries), web_search.MAX_RESEARCH_QUERIES)
        self.assertTrue(all(len(query) <= web_search.MAX_QUERY_CHARS for query in queries))

    @patch("web_search.search_web")
    def test_research_mode_deduplicates_results_and_reports_real_query_coverage(self, search):
        def fake_search(query, api_key=None, timeout=20):
            if query == "compare AI agents":
                url = "https://example.org/shared"
            else:
                url = "https://example.org/" + str(len(query))
            return {
                "query": query,
                "provider": "Mock public web",
                "results": [
                    {"title": "Evidence " + str(len(query)), "url": url,
                     "snippet": "Search provider result", "source": "Mock public web"}
                ],
                "result_count": 1,
                "coverage_note": "bounded test evidence",
            }
        search.side_effect = fake_search
        result = web_search.search_web_research("compare AI agents", max_queries=3)
        self.assertTrue(result["research_mode"])
        self.assertEqual(result["queries"][0], "compare AI agents")
        self.assertLessEqual(len(result["queries"]), 3)
        urls = [item["url"] for item in result["results"]]
        self.assertEqual(len(urls), len(set(urls)))
        self.assertGreaterEqual(search.call_count, 2)
        self.assertIn("بحث معمق محدود", result["coverage_note"])

    def test_research_mode_rejects_empty_query(self):
        with self.assertRaises(ValueError):
            web_search.build_research_queries("   ")


if __name__ == "__main__":
    unittest.main()
