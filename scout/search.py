"""General web search with Tavily primary and DuckDuckGo fallback."""
import requests
from ddgs import DDGS
from .config import int_setting, setting


class SearchError(RuntimeError):
    pass


def _normalize(items, count: int) -> list[dict]:
    results, seen = [], set()
    for item in items:
        url = str(item.get("url") or item.get("href") or "").strip()
        if not url.startswith(("https://", "http://")) or url in seen:
            continue
        seen.add(url)
        results.append({
            "title": str(item.get("title") or url)[:250],
            "url": url,
            "snippet": str(item.get("content") or item.get("body") or "")[:1200],
            "published_date": str(item.get("published_date") or item.get("date") or "")[:40],
        })
        if len(results) >= count:
            break
    return results


def _duckduckgo(query: str, count: int, timeout: int) -> list[dict]:
    with DDGS(timeout=min(timeout, 20)) as client:
        return _normalize(client.text(query, max_results=count, safesearch="moderate"), count)


def web_search(query: str, max_results: int | None = None) -> list[dict]:
    """Search the public web; try the configured provider, then a no-key fallback.

    An empty list is a real empty result set. If every available provider fails,
    raise SearchError rather than fabricating results.
    """
    query = query.strip()
    if not query or len(query) > 500:
        raise ValueError("query must contain 1–500 characters")
    count = max_results or int_setting("SCOUT_SEARCH_MAX_RESULTS", 5, 1, 8)
    timeout = int_setting("SCOUT_REQUEST_TIMEOUT", 25, 5, 60)
    api_key = setting("TAVILY_API_KEY")
    failures = []

    if api_key:
        try:
            response = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key, "query": query, "search_depth": "advanced",
                    "max_results": count, "include_answer": False, "include_raw_content": False,
                },
                timeout=timeout,
            )
            if response.status_code >= 400:
                failures.append(f"Tavily HTTP {response.status_code}")
            else:
                data = response.json()
                if not isinstance(data, dict) or not isinstance(data.get("results", []), list):
                    failures.append("Tavily returned an invalid result format")
                else:
                    results = _normalize(data.get("results", []), count)
                    if results:
                        return results
                    failures.append("Tavily returned no usable results")
        except requests.Timeout:
            failures.append("Tavily timed out")
        except requests.RequestException:
            failures.append("Tavily network error")
        except ValueError:
            failures.append("Tavily returned invalid JSON")

    try:
        results = _duckduckgo(query, count, timeout)
        if results:
            return results
        failures.append("DuckDuckGo returned no usable results")
    except Exception as exc:
        failures.append(f"DuckDuckGo failed ({type(exc).__name__})")

    detail = "; ".join(failures) if failures else "No search provider is available"
    raise SearchError(
        "SEARCH_UNAVAILABLE: no web search provider returned results. "
        "Check backend internet access or configure TAVILY_API_KEY. " + detail
    )
