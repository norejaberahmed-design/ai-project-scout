import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import api_server


class ApiHttpIntegrationTests(unittest.TestCase):
    def setUp(self):
        api_server.REQUEST_TIMES.clear()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.AgentHandler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, path, method="GET", payload=None, headers=None):
        headers = dict(headers or {})
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(self.base + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=3) as response:
                raw = response.read()
                return response.status, json.loads(raw.decode("utf-8")), response.headers
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            return exc.code, json.loads(raw.decode("utf-8")), exc.headers

    def test_health_endpoint_reports_configuration_without_exposing_secrets(self):
        with patch.dict(os.environ, {}, clear=True):
            status, body, headers = self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")
        self.assertFalse(body["web_search_configured"])
        self.assertFalse(body["model_configured"])
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertNotIn("key", json.dumps(body).lower())

    def test_chat_returns_answer_and_sources_through_real_http_handler(self):
        search = {"provider": "Tavily", "results": [
            {"title": "Official docs", "url": "https://example.org/docs",
             "snippet": "Official evidence", "source": "Tavily"}
        ], "coverage_note": "Only public indexed results."}
        with patch.dict(os.environ, {
            "SCOUT_LLM_API_KEY": "test-only-key",
            "SCOUT_LLM_MODEL": "test-model",
        }, clear=True), patch("api_server.search_web", return_value=search), \
             patch("api_server.generate_answer", return_value="هذه إجابة اختبارية مدعومة بمصدر.") as generate:
            status, body, headers = self.request(
                "/api/chat", method="POST", payload={"question": "اختبر البحث"},
                headers={"Origin": "https://norejaberahmed-design.github.io"}
            )
        self.assertEqual(status, 200)
        self.assertIn("إجابة اختبارية", body["answer"])
        self.assertEqual(body["sources"][0]["url"], "https://example.org/docs")
        self.assertEqual(body["coverage_note"], "Only public indexed results.")
        self.assertEqual(headers["Access-Control-Allow-Origin"],
                         "https://norejaberahmed-design.github.io")
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        generate.assert_called_once()

    def test_search_endpoint_does_not_require_model_and_returns_search_results(self):
        result = {"query": "public sources", "provider": "Tavily", "results": [],
                  "result_count": 0, "coverage_note": "public only"}
        with patch("api_server.search_web", return_value=result) as search:
            status, body, _ = self.request("/api/search", method="POST",
                                           payload={"query": "public sources"})
        self.assertEqual(status, 200)
        self.assertEqual(body["provider"], "Tavily")
        search.assert_called_once_with("public sources")

    def test_disallowed_origin_is_rejected(self):
        status, body, _ = self.request(
            "/api/search", method="POST", payload={"query": "test"},
            headers={"Origin": "https://untrusted.example"}
        )
        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "Origin not allowed")

    def test_wrong_content_type_and_oversized_body_are_rejected(self):
        status, _, _ = self.request("/api/search", method="POST", payload={"query": "test"},
                                    headers={"Content-Type": "text/plain"})
        self.assertEqual(status, 415)
        large_payload = {"question": "x", "extra": "z" * (api_server.MAX_BODY_BYTES + 10)}
        status, _, _ = self.request("/api/chat", method="POST", payload=large_payload)
        self.assertEqual(status, 413)

    def test_chat_reports_missing_model_configuration_before_search(self):
        with patch.dict(os.environ, {}, clear=True), patch("api_server.search_web") as search:
            status, body, _ = self.request("/api/chat", method="POST",
                                           payload={"question": "hello"})
        self.assertEqual(status, 503)
        self.assertIn("SCOUT_LLM_API_KEY", body["error"])
        search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
