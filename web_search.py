"""General public-web search with Tavily primary and DuckDuckGo HTML fallback.

Search provider output is untrusted evidence, never instructions. No API key is needed
for the fallback, though providers may rate-limit or change their HTML.
"""
from __future__ import annotations

import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

API_URL = "https://api.tavily.com/search"
DUCKDUCKGO_URL = "https://html.duckduckgo.com/html/"
MAX_QUERY_CHARS = 500
MAX_RESULTS = 8
MAX_RESPONSE_BYTES = 1_000_000
YOUTUBE_RESULTS = 4
YOUTUBE_INTENT = re.compile(r"youtube|يوتيوب|فيديو|شرح|tutorial|walkthrough|source code|الكود المصدري|مهارات|skills|agent tools|ai tools|أدوات الذكاء الاصطناعي", re.I)


def _clean(value: str, limit: int = 1500) -> str:
    value = html.unescape(re.sub(r"<[^>]*>", " ", value or ""))
    return " ".join(value.split())[:limit]


class _DuckDuckGoParser(HTMLParser):
    """Extract ordinary result links/snippets, ignoring ads and non-result links."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results: list[dict] = []
        self._current: dict | None = None
        self._capture: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            self._current = {"title": "", "url": attrs.get("href", ""), "snippet": ""}
            self._capture = "title"
            self._text = []
        elif tag in {"a", "div"} and "result__snippet" in classes and self.results:
            self._capture = "snippet"
            self._text = []

    def handle_data(self, data):
        if self._capture:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._capture == "title" and self._current is not None:
            self._current["title"] = _clean(" ".join(self._text), 300)
            self.results.append(self._current)
            self._current = None
            self._capture = None
            self._text = []
        elif tag in {"a", "div"} and self._capture == "snippet" and self.results:
            snippet = _clean(" ".join(self._text), 1500)
            if snippet and not self.results[-1].get("snippet"):
                self.results[-1]["snippet"] = snippet
            self._capture = None
            self._text = []


def _request(url: str, *, data: bytes | None = None, headers: dict | None = None,
             timeout: int = 20) -> bytes:
    request = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET",
        headers={"User-Agent": "Mozilla/5.0 (compatible; AI-Project-Scout/1.0)",
                 "Accept": "text/html,application/json;q=0.9,*/*;q=0.8", **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(MAX_RESPONSE_BYTES)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Search provider returned HTTP {exc.code}.") from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("Search provider is unreachable.") from None


def _search_duckduckgo(query: str, timeout: int = 20) -> dict:
    url = DUCKDUCKGO_URL + "?" + urllib.parse.urlencode({"q": query, "kl": "wt-wt"})
    try:
        raw = _request(url, timeout=timeout)
    except RuntimeError:
        raise
    try:
        document = raw.decode("utf-8", errors="replace")
        parser = _DuckDuckGoParser()
        parser.feed(document)
    except (ValueError, TypeError):
        raise RuntimeError("DuckDuckGo returned an unreadable results page.") from None
    results = []
    seen = set()
    for item in parser.results:
        url = html.unescape(str(item.get("url") or ""))
        title = _clean(str(item.get("title") or ""), 300)
        if url.startswith("//"):
            url = "https:" + url
        parsed = urllib.parse.urlparse(url)
        if "duckduckgo.com" in parsed.netloc.lower():
            target = urllib.parse.parse_qs(parsed.query).get("uddg", [])
            if target:
                url = target[0]
                parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or not title or url in seen:
            continue
        if "duckduckgo.com" in parsed.netloc.lower():
            continue
        seen.add(url)
        results.append({"title": title, "url": url,
                        "snippet": _clean(str(item.get("snippet") or ""), 1500),
                        "score": None, "source": "DuckDuckGo"})
        if len(results) >= MAX_RESULTS:
            break
    if not results:
        raise RuntimeError("لم يُرجع البحث العام نتائج قابلة للاستخدام؛ قد يكون مزود البحث حجب الطلب.")
    return {"query": query, "provider": "DuckDuckGo", "results": results,
            "result_count": len(results),
            "coverage_note": "بحث عام في صفحات الويب المفهرسة عبر DuckDuckGo. النتائج ليست شاملة وقد تتغير أو تُحجب."}


def _search_tavily(query: str, key: str, timeout: int, include_domains: list[str] | None = None) -> dict:
    parameters = {
        "api_key": key, "query": query, "search_depth": "basic",
        "topic": "general", "max_results": YOUTUBE_RESULTS if include_domains else MAX_RESULTS,
        "include_answer": False, "include_raw_content": False,
    }
    if include_domains:
        parameters["include_domains"] = include_domains
    payload = json.dumps(parameters).encode("utf-8")
    raw = _request(API_URL, data=payload, timeout=timeout,
                   headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise RuntimeError("Tavily returned invalid JSON.") from None
    results = []
    for item in data.get("results", [])[:MAX_RESULTS]:
        url = str(item.get("url", ""))
        title = _clean(str(item.get("title", "")), 300)
        parsed_url = urllib.parse.urlparse(url)
        if parsed_url.scheme not in {"https", "http"} or not title:
            continue
        if include_domains:
            hostname = (parsed_url.hostname or "").lower()
            if not any(hostname == domain or hostname.endswith("." + domain) for domain in include_domains):
                continue
        results.append({"title": title, "url": url,
                        "snippet": _clean(str(item.get("content", "")), 1500),
                        "score": item.get("score"), "source": "Tavily"})
    if not results:
        raise RuntimeError("Tavily returned no usable results.")
    return {"query": query, "provider": "Tavily", "results": results,
            "result_count": len(results),
            "coverage_note": "نتائج الويب العامة المفهرسة عبر Tavily؛ لا تشمل كل الإنترنت أو المحتوى الخاص. not every website is indexed."}


def search_web(query: str, api_key: str | None = None, timeout: int = 20) -> dict:
    """Search general public web; prefer Tavily when configured, otherwise use DDG."""
    query = " ".join((query or "").split()).strip()
    if not query:
        raise ValueError("أدخل سؤالًا أو عبارة للبحث.")
    if len(query) > MAX_QUERY_CHARS:
        raise ValueError(f"Query is limited to {MAX_QUERY_CHARS} characters.")
    key = (api_key or os.getenv("TAVILY_API_KEY", "")).strip()
    if key:
        try:
            result = _search_tavily(query, key, timeout)
        except RuntimeError as exc:
            try:
                result = _search_duckduckgo(query, timeout)
                result["fallback_note"] = "تعذر مزود البحث الأساسي؛ استُخدم DuckDuckGo بدلًا منه."
            except RuntimeError:
                raise RuntimeError("تعذر البحث عبر Tavily وDuckDuckGo: " + str(exc)) from None
    else:
        result = _search_duckduckgo(query, timeout)

    # Video/tutorial discovery supplements general-web evidence; it never replaces it.
    result["youtube_search"] = "not_needed"
    if False and YOUTUBE_INTENT.search(query):  # Skill discovery is GitHub-only; never search videos.
        try:
            if key:
                videos = _search_tavily(query, key, timeout, include_domains=["youtube.com", "youtu.be"])
            else:
                videos = _search_duckduckgo("site:youtube.com/watch " + query, timeout)
            existing = {item["url"] for item in result["results"]}
            unique_videos = []
            for item in videos["results"]:
                if item["url"] not in existing:
                    item = dict(item)
                    item["source"] = "YouTube-focused discovery"
                    unique_videos.append(item)
                    existing.add(item["url"])
                if len(unique_videos) >= YOUTUBE_RESULTS:
                    break
            result["results"] = result["results"][:4] + unique_videos + result["results"][4:]
            result["result_count"] = len(result["results"])
            result["provider"] += " + YouTube-focused search"
            result["youtube_search"] = "searched" if unique_videos else "no_results"
        except RuntimeError:
            result["youtube_search"] = "unavailable"
    result["results"] = result["results"][:MAX_RESULTS + YOUTUBE_RESULTS]
    result["result_count"] = len(result["results"])
    return result
