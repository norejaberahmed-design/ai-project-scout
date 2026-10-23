import io
import json
import time
import unittest
import urllib.error
from email.message import Message
from unittest.mock import patch

import github_api


class FakeResponse:
    def __init__(self, body=b'{"ok": true}', headers=None, status=200):
        self._body = body
        self.headers = Message()
        for key, value in (headers or {}).items():
            self.headers[key] = str(value)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self._body[:size]


class GitHubApiTests(unittest.TestCase):
    def setUp(self):
        with github_api._cache_lock:
            github_api._cache.clear()

    def test_success_sends_auth_only_from_environment_and_caches_etag(self):
        captured = {}

        def opener(request, timeout):
            captured["headers"] = dict(request.header_items())
            return FakeResponse(b'{"items": []}', {"ETag": '"abc"'})

        with patch.dict("os.environ", {"GITHUB_TOKEN": "fake-test-token"}):
            result = github_api.request_json(
                "https://api.github.com/search/repositories?q=skills",
                opener=opener,
            )
        self.assertEqual(result, {"items": []})
        self.assertEqual(captured["headers"].get("Authorization"), "Bearer fake-test-token")
        with github_api._cache_lock:
            self.assertTrue(any(key.startswith("https://api.github.com/search/repositories?q=skills|") for key in github_api._cache))

    def test_transient_503_retries_with_bounded_deterministic_backoff(self):
        calls = []
        sleeps = []

        def opener(request, timeout):
            calls.append(request.full_url)
            if len(calls) == 1:
                raise urllib.error.HTTPError(request.full_url, 503, "busy", Message(), io.BytesIO(b""))
            return FakeResponse()

        result = github_api.request_json(
            "https://api.github.com/repos/example/project",
            opener=opener,
            sleeper=sleeps.append,
            jitter=lambda: 0,
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(calls), 2)
        self.assertEqual(sleeps, [1.0])

    def test_rate_limit_does_not_retry_before_long_reset_and_reports_resume_time(self):
        headers = Message()
        headers["X-RateLimit-Remaining"] = "0"
        headers["X-RateLimit-Reset"] = str(1_700_000_100)
        request_url = "https://api.github.com/search/repositories?q=skills"

        def opener(request, timeout):
            raise urllib.error.HTTPError(request_url, 403, "rate limited", headers, io.BytesIO(b""))

        sleeps = []
        with self.assertRaisesRegex(RuntimeError, "resume after"):
            github_api.request_json(
                request_url,
                opener=opener,
                sleeper=sleeps.append,
                clock=lambda: 1_700_000_000,
                max_wait_seconds=8,
            )
        self.assertEqual(sleeps, [])

    def test_secondary_limit_honors_retry_after_with_fake_clock(self):
        headers = Message()
        headers["Retry-After"] = "2"
        calls = []

        def opener(request, timeout):
            calls.append(1)
            if len(calls) == 1:
                raise urllib.error.HTTPError(request.full_url, 429, "secondary limit", headers, io.BytesIO(b""))
            return FakeResponse()

        sleeps = []
        result = github_api.request_json(
            "https://api.github.com/repos/example/project",
            opener=opener,
            sleeper=sleeps.append,
            clock=lambda: 1_700_000_000,
            jitter=lambda: 0,
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(sleeps, [2.0])

    def test_etag_is_sent_and_cached_body_is_reused_on_304(self):
        url = "https://api.github.com/repos/example/project"
        calls = []

        def opener(request, timeout):
            calls.append(dict(request.header_items()))
            if len(calls) == 1:
                return FakeResponse(b'{"revision": "abc"}', {"ETag": '"revision-1"'})
            self.assertEqual(calls[-1].get("If-none-match"), '"revision-1"')
            raise urllib.error.HTTPError(url, 304, "not modified", Message(), io.BytesIO(b""))

        first = github_api.request_json(url, opener=opener)
        second = github_api.request_json(url, opener=opener)
        self.assertEqual(first, {"revision": "abc"})
        self.assertEqual(second, first)
        self.assertEqual(len(calls), 2)

    def test_non_github_or_http_url_is_refused(self):
        with self.assertRaisesRegex(ValueError, "Only HTTPS GitHub API"):
            github_api.request_json("http://api.github.com/repos/example/project")
        with self.assertRaisesRegex(ValueError, "Only HTTPS GitHub API"):
            github_api.request_json("https://example.org/")

    def test_unauthorized_is_not_retried(self):
        calls = []

        def opener(request, timeout):
            calls.append(1)
            raise urllib.error.HTTPError(request.full_url, 401, "unauthorized", Message(), io.BytesIO(b""))

        with self.assertRaisesRegex(RuntimeError, "HTTP 401"):
            github_api.request_json(
                "https://api.github.com/repos/example/project",
                opener=opener,
                sleeper=lambda _: self.fail("401 must not sleep or retry"),
            )
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
