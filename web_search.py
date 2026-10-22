"""Server-side general web search adapter using Tavily.

Set TAVILY_API_KEY in the server environment. Never place this secret in the static
GitHub Pages frontend. Search results are evidence leads and must be cited/verified.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

API_URL = "https://api.tavily.com/search"
MAX_QUERY_CHARS = 500
MAX_RESULTS = 8


def search_web(query: str, api_key: str | None = None, timeout: int = 20) -> dict:
    query = " ".join((query or "").split()).strip()
    if not query:
        raise ValueError("أدخل سؤالًا أو عبارة للبحث.")
    if len(query) > MAX_QUERY_CHARS:
        raise ValueError(f"Query is limited to {MAX_QUERY_CHARS} characters.")
    key = api_key or os.getenv("TAVILY_API_KEY")
    if not key:
        raise RuntimeError("البحث العام غير مهيأ: أضف TAVILY_API_KEY إلى أسرار الخادم.")
    payload = json.dumps({
        "api_key": key,
        "query": query,
        "search_depth": "basic",
        "topic": "general",
        "max_results": MAX_RESULTS,
        "include_answer": False,
        "include_raw_content": False,
    }).encode("utf-8")
    request = urllib.request.Request(API_URL, data=payload, method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json",
        "User-Agent": "AI-Project-Scout/0.3",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(1_000_000)
    except urllib.error.HTTPError as exc:
        # Do not expose request body, authorization data, or API key in errors.
        raise RuntimeError(f"Web search provider returned HTTP {exc.code}.") from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("Web search provider is unreachable; retry later.") from None
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise RuntimeError("Web search provider returned invalid JSON.") from None
    results = []
    for item in data.get("results", [])[:MAX_RESULTS]:
        url = str(item.get("url", ""))
        title = str(item.get("title", "")).strip()
        if not url.startswith(("https://", "http://")) or not title:
            continue
        results.append({
            "title": title[:300],
            "url": url,
            "snippet": str(item.get("content", ""))[:1500],
            "score": item.get("score"),
            "source": "Tavily",
        })
    return {"query": query, "provider": "Tavily", "results": results,
            "result_count": len(results), "coverage_note":
            "Search results cover the provider's indexed/public web results, not every website or private content."}
