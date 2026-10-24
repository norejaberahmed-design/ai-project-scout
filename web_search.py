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
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

API_URL = "https://api.tavily.com/search"
DUCKDUCKGO_URL = "https://html.duckduckgo.com/html/"
BING_RSS_URL = "https://www.bing.com/search"
MAX_QUERY_CHARS = 500
MAX_RESULTS = 8
MAX_RESPONSE_BYTES = 1_000_000


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


def _search_bing_rss(query: str, timeout: int = 20) -> dict:
    """Second no-key public-web fallback using Bing's RSS results endpoint."""
    url = BING_RSS_URL + "?" + urllib.parse.urlencode({"format": "rss", "q": query})
    raw = _request(url, timeout=timeout, headers={"Accept": "application/rss+xml, application/xml;q=0.9"})
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        raise RuntimeError("Bing returned an unreadable RSS search response.") from None
    results = []
    seen = set()
    for item in root.findall(".//item")[:MAX_RESULTS * 2]:
        title = _clean(item.findtext("title") or "", 300)
        link = (item.findtext("link") or "").strip()
        snippet = _clean(item.findtext("description") or "", 1500)
        parsed = urllib.parse.urlparse(link)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or not title or link in seen:
            continue
        seen.add(link)
        results.append({"title": title, "url": link, "snippet": snippet,
                        "score": None, "source": "Bing"})
        if len(results) >= MAX_RESULTS:
            break
    if not results:
        raise RuntimeError("Bing RSS did not return usable public-web results.")
    return {"query": query, "provider": "Bing RSS", "results": results,
            "result_count": len(results),
            "coverage_note": "بحث عام في نتائج Bing RSS المفهرسة؛ النتائج ليست شاملة وقد تتغير أو تُحجب."}


def _search_public_web(query: str, timeout: int = 20) -> dict:
    """Try independent no-key search providers in order; surface failure only if all fail."""
    failures = []
    for provider, searcher in (("DuckDuckGo", _search_duckduckgo), ("Bing RSS", _search_bing_rss)):
        try:
            result = searcher(query, timeout)
            if result.get("results"):
                if failures:
                    result["fallback_note"] = "تم تجاوز مزود بحث غير متاح: " + ", ".join(failures)
                return result
            failures.append(provider + ": empty results")
        except RuntimeError as exc:
            failures.append(provider + ": " + str(exc)[:180])
    raise RuntimeError("تعذر البحث العام عبر DuckDuckGo وBing RSS: " + " | ".join(failures))


def _search_tavily(query: str, key: str, timeout: int) -> dict:
    parameters = {
        "api_key": key, "query": query, "search_depth": "basic",
        "topic": "general", "max_results": MAX_RESULTS,
        "include_answer": False, "include_raw_content": False,
    }
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
                result = _search_public_web(query, timeout)
                result["fallback_note"] = "تعذر مزود البحث الأساسي؛ استُخدم مزود بحث عام بديل."
            except RuntimeError as fallback_error:
                raise RuntimeError("تعذر البحث عبر Tavily وبدائل البحث العامة: " + str(exc) + " | " + str(fallback_error)) from None
    else:
        result = _search_public_web(query, timeout)

    result["results"] = result["results"][:MAX_RESULTS]
    result["result_count"] = len(result["results"])
    return result

# Multi-query research mode is opt-in so ordinary requests do not multiply search
# provider calls or costs. All variants stay anchored to the user's actual question.
MAX_RESEARCH_QUERIES = 3
MAX_RESEARCH_RESULTS = 12


def build_research_queries(query: str) -> list[str]:
    """Create a small, deterministic set of intent-preserving public-web queries."""
    original = " ".join((query or "").split()).strip()[:MAX_QUERY_CHARS]
    if not original:
        raise ValueError("أدخل سؤالًا أو عبارة للبحث.")
    queries = [original]
    lower = original.lower()
    software_terms = (
        "github", "python", "javascript", "typescript", "api", "code", "coding",
        "software", "library", "framework", "agent", "llm", "open source",
        "برمجة", "كود", "مكتبة", "إطار عمل", "وكيل", "مهارة", "مهارات",
        "تطبيق", "ذكاء اصطناعي",
    )
    recency_terms = (
        "latest", "recent", "today", "current", "2026", "أحدث", "آخر", "حالي",
        "اليوم", "الجديد", "مستجدات",
    )
    if any(term in lower for term in software_terms):
        suffix = "official documentation repository"
    elif any(term in lower for term in recency_terms):
        suffix = "latest updates official sources"
    else:
        suffix = "reliable primary sources"
    second = (original + " " + suffix)[:MAX_QUERY_CHARS].strip()
    if second.casefold() != original.casefold():
        queries.append(second)
    # Third pass looks for corroboration, but remains optional/bounded and
    # never changes the subject of the user's original request.
    third_suffix = "independent evidence comparison"
    third = (original + " " + third_suffix)[:MAX_QUERY_CHARS].strip()
    if third.casefold() not in {item.casefold() for item in queries}:
        queries.append(third)
    return queries[:MAX_RESEARCH_QUERIES]


def search_web_research(query: str, api_key: str | None = None,
                        timeout: int = 12, max_queries: int = MAX_RESEARCH_QUERIES) -> dict:
    """Run a bounded multi-query research pass and deduplicate its real search results."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    queries = build_research_queries(query)
    max_queries = max(1, min(int(max_queries), MAX_RESEARCH_QUERIES))
    queries = queries[:max_queries]
    failures = []
    collected = []
    providers = []
    # At most three independent search requests run concurrently; no page content
    # is executed, and every displayed result comes from a search provider response.
    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        futures = {
            pool.submit(search_web, item, api_key=api_key, timeout=timeout): item
            for item in queries
        }
        for future in as_completed(futures):
            search_query = futures[future]
            try:
                result = future.result()
                provider = str(result.get("provider") or "Public web search")
                if provider not in providers:
                    providers.append(provider)
                for item in result.get("results", []):
                    if not isinstance(item, dict):
                        continue
                    url = str(item.get("url") or "").strip()
                    title = _clean(str(item.get("title") or ""), 300)
                    parsed = urllib.parse.urlparse(url)
                    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not title:
                        continue
                    collected.append({
                        "title": title,
                        "url": url,
                        "snippet": _clean(str(item.get("snippet") or ""), 1500),
                        "score": item.get("score"),
                        "source": str(item.get("source") or provider),
                        "matched_query": search_query,
                    })
            except (RuntimeError, ValueError, OSError) as exc:
                failures.append({"query": search_query, "error": str(exc)[:180]})

    unique = []
    seen = set()
    for item in collected:
        key = item["url"].split("#", 1)[0].rstrip("/").casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    if not unique:
        detail = " | ".join(item["error"] for item in failures[:3])
        raise RuntimeError("لم تُسترجع نتائج بحث قابلة للاستخدام في وضع البحث المعمق." +
                           ((" " + detail) if detail else ""))
    return {
        "query": query,
        "queries": queries,
        "provider": " + ".join(providers),
        "results": unique[:MAX_RESEARCH_RESULTS],
        "result_count": min(len(unique), MAX_RESEARCH_RESULTS),
        "coverage_note": (
            "بحث معمق محدود: نُفذت حتى " + str(len(queries)) +
            " استعلامات ويب مترابطة، ثم أزيلت الروابط المكررة. النتائج من الويب العام المفهرس "
            "وليست تغطية شاملة للإنترنت؛ تحقق من المصادر الأصلية."
        ),
        "research_mode": True,
        "failed_queries": failures,
    }

