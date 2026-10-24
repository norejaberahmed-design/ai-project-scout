"""Real web search adapter with bounded, normalized citations."""
import requests
from .config import int_setting, setting

class SearchError(RuntimeError):
    pass

def web_search(query: str, max_results: int | None = None) -> list[dict]:
    query = query.strip()
    if not query or len(query) > 500:
        raise ValueError("query must contain 1–500 characters")
    api_key = setting("TAVILY_API_KEY")
    if not api_key:
        raise SearchError("SEARCH_NOT_CONFIGURED: set TAVILY_API_KEY on the server to enable web search.")
    count = max_results or int_setting("SCOUT_SEARCH_MAX_RESULTS", 5, 1, 8)
    try:
        response = requests.post("https://api.tavily.com/search",
            json={"api_key": api_key, "query": query, "search_depth": "advanced",
                  "max_results": count, "include_answer": False, "include_raw_content": False},
            timeout=int_setting("SCOUT_REQUEST_TIMEOUT", 25, 5, 60))
        if response.status_code >= 400:
            raise SearchError(f"SEARCH_PROVIDER_ERROR: search provider returned HTTP {response.status_code}.")
        payload = response.json()
        results, seen = [], set()
        for item in payload.get("results", []):
            url = str(item.get("url", "")).strip()
            if not url.startswith(("https://", "http://")) or url in seen:
                continue
            seen.add(url)
            results.append({"title": str(item.get("title") or url)[:250], "url": url,
                "snippet": str(item.get("content") or "")[:1200],
                "published_date": str(item.get("published_date") or "")[:40]})
            if len(results) >= count:
                break
        return results
    except SearchError:
        raise
    except requests.Timeout as exc:
        raise SearchError("SEARCH_TIMEOUT: web search did not respond in time.") from exc
    except requests.RequestException as exc:
        raise SearchError("SEARCH_NETWORK_ERROR: unable to reach the web search provider.") from exc
    except ValueError as exc:
        raise SearchError("SEARCH_INVALID_RESPONSE: search provider returned invalid data.") from exc
