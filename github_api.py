"""Bounded, rate-aware GitHub JSON client shared by discovery adapters.

The helper preserves failures as failures: a failed request is never converted into
an empty result set. It retries only eligible transient/rate-limit responses and
never sleeps beyond the configured operational wait budget.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from threading import Lock
from typing import Callable

MAX_ATTEMPTS = 3
MAX_WAIT_SECONDS = 8.0
MAX_RESPONSE_BYTES = 1_250_000
RETRYABLE_HTTP = {500, 502, 503, 504}
_cache: dict[str, tuple[str, dict]] = {}
_cache_lock = Lock()


def _retry_after(headers, now: float) -> float | None:
    raw = headers.get("Retry-After") if headers else None
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        try:
            target = parsedate_to_datetime(str(raw)).timestamp()
            return max(0.0, target - now)
        except (TypeError, ValueError, OverflowError):
            return None


def _reset_delay(headers, now: float) -> float | None:
    raw = headers.get("X-RateLimit-Reset") if headers else None
    try:
        return max(0.0, float(raw) - now)
    except (TypeError, ValueError):
        return None


def _retry_delay(headers, status: int, now: float, attempt: int, jitter: Callable[[], float]) -> float | None:
    if status in {403, 429}:
        # Primary quota exhausted: wait for documented reset. Secondary limits
        # normally provide Retry-After; without guidance, fail closed.
        remaining = headers.get("X-RateLimit-Remaining") if headers else None
        retry_after = _retry_after(headers, now)
        if remaining == "0":
            return _reset_delay(headers, now)
        if retry_after is not None:
            return retry_after
        return None
    if status in RETRYABLE_HTTP:
        return min(2.0 ** attempt, MAX_WAIT_SECONDS) + max(0.0, min(0.5, jitter()))
    return None


def request_json(
    url: str,
    *,
    timeout: float = 12,
    opener: Callable = urllib.request.urlopen,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.time,
    jitter: Callable[[], float] = random.random,
    max_wait_seconds: float = MAX_WAIT_SECONDS,
    max_attempts: int = MAX_ATTEMPTS,
) -> dict:
    """GET a bounded JSON response with conditional requests and bounded retries."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "api.github.com":
        raise ValueError("Only HTTPS GitHub API URLs are permitted.")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "AI-Project-Scout/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = "Bearer " + token
    # Keep cached representations isolated by credential context without retaining
    # the token itself in the cache key or logs.
    cache_key = url + "|" + hashlib.sha256(token.encode("utf-8")).hexdigest()
    with _cache_lock:
        cached = _cache.get(cache_key)
    if cached:
        headers["If-None-Match"] = cached[0]

    attempts = max(1, min(int(max_attempts), MAX_ATTEMPTS))
    for attempt in range(attempts):
        req = urllib.request.Request(url, headers=headers)
        try:
            response = opener(req, timeout=timeout)
            with response:
                status = getattr(response, "status", 200)
                response_headers = response.headers
                if status == 304:
                    if cached:
                        return dict(cached[1])
                    raise RuntimeError("GitHub returned 304 without a cached representation.")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise RuntimeError("GitHub response exceeded the configured size limit.")
            try:
                data = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                raise RuntimeError("GitHub returned invalid JSON.") from None
            if not isinstance(data, dict):
                raise RuntimeError("GitHub returned an unexpected response.")
            etag = response_headers.get("ETag") if response_headers else None
            if etag:
                with _cache_lock:
                    _cache[cache_key] = (etag, dict(data))
            return data
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            response_headers = exc.headers
            if status == 304 and cached:
                return dict(cached[1])
            now = clock()
            delay = _retry_delay(response_headers, status, now, attempt, jitter)
            if delay is None:
                raise RuntimeError(f"GitHub API returned HTTP {status}.") from None
            if attempt + 1 >= attempts:
                if status in {403, 429}:
                    reset = _reset_delay(response_headers, now)
                    retry_after = _retry_after(response_headers, now)
                    wait = reset if reset is not None else retry_after
                    if wait is not None:
                        retry_at = datetime.fromtimestamp(now + wait, timezone.utc).isoformat()
                        raise RuntimeError(f"GitHub rate limit reached; resume after {retry_at}.") from None
                raise RuntimeError(f"GitHub API returned transient HTTP {status}; retry budget exhausted.") from None
            if delay > max_wait_seconds:
                retry_at = datetime.fromtimestamp(now + delay, timezone.utc).isoformat()
                raise RuntimeError(f"GitHub rate limit/transient wait exceeds {max_wait_seconds:g}s; resume after {retry_at}.") from None
            sleeper(delay)
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt + 1 >= attempts:
                raise RuntimeError("GitHub API is unreachable after bounded retries.") from None
            delay = min(2.0 ** attempt, max_wait_seconds) + max(0.0, min(0.5, jitter()))
            if delay > max_wait_seconds:
                raise RuntimeError("GitHub API is unreachable; retry budget exceeds operational wait policy.") from None
            sleeper(delay)
        except OSError:
            if attempt + 1 >= attempts:
                raise RuntimeError("GitHub API transport failed after bounded retries.") from None
            delay = min(2.0 ** attempt, max_wait_seconds) + max(0.0, min(0.5, jitter()))
            if delay > max_wait_seconds:
                raise RuntimeError("GitHub API transport failed; retry budget exceeds operational wait policy.") from None
            sleeper(delay)
    raise RuntimeError("GitHub request ended without a response.")
