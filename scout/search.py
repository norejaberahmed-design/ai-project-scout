"""Web search adapters: Tavily when configured, otherwise a no-key DuckDuckGo fallback."""
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
        results.append({"title":str(item.get("title") or url)[:250],"url":url,
            "snippet":str(item.get("content") or item.get("body") or "")[:1200],
            "published_date":str(item.get("published_date") or item.get("date") or "")[:40]})
        if len(results) >= count:
            break
    return results

def web_search(query: str, max_results: int | None = None) -> list[dict]:
    query = query.strip()
    if not query or len(query) > 500:
        raise ValueError("query must contain 1–500 characters")
    count = max_results or int_setting("SCOUT_SEARCH_MAX_RESULTS", 5, 1, 8)
    timeout = int_setting("SCOUT_REQUEST_TIMEOUT", 25, 5, 60)
    api_key = setting("TAVILY_API_KEY")
    if api_key:
        try:
            response = requests.post("https://api.tavily.com/search",
                json={"api_key":api_key,"query":query,"search_depth":"advanced",
                      "max_results":count,"include_answer":False,"include_raw_content":False},
                timeout=timeout)
            if response.status_code >= 400:
                raise SearchError(f"SEARCH_PROVIDER_ERROR: search provider returned HTTP {response.status_code}.")
            return _normalize(response.json().get("results",[]),count)
        except SearchError:
            raise
        except requests.Timeout as exc:
            raise SearchError("SEARCH_TIMEOUT: web search did not respond in time.") from exc
        except requests.RequestException as exc:
            raise SearchError("SEARCH_NETWORK_ERROR: unable to reach the web search provider.") from exc
        except ValueError as exc:
            raise SearchError("SEARCH_INVALID_RESPONSE: search provider returned invalid data.") from exc
    try:
        with DDGS(timeout=min(timeout, 20)) as client:
            return _normalize(client.text(query, max_results=count, safesearch="moderate"),count)
    except Exception as exc:
        raise SearchError("SEARCH_FALLBACK_ERROR: free web search failed; check network access or configure TAVILY_API_KEY.") from exc
