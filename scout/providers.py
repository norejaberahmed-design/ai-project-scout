"""OpenAI-compatible model provider adapter."""
import requests
from .config import int_setting, setting

class ProviderError(RuntimeError):
    pass

def chat_completion(messages: list[dict], timeout: int | None = None) -> str:
    api_key = setting("SCOUT_LLM_API_KEY")
    model = setting("SCOUT_LLM_MODEL")
    url = setting("SCOUT_LLM_API_URL", "https://openrouter.ai/api/v1/chat/completions")
    if not api_key or not model:
        raise ProviderError("MODEL_NOT_CONFIGURED: set SCOUT_LLM_API_KEY and SCOUT_LLM_MODEL on the server.")
    try:
        response = requests.post(url, headers={"Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "temperature": 0.2},
            timeout=timeout or int_setting("SCOUT_REQUEST_TIMEOUT", 25, 5, 60))
        if response.status_code >= 400:
            raise ProviderError(f"MODEL_PROVIDER_ERROR: provider returned HTTP {response.status_code}.")
        answer = response.json()["choices"][0]["message"]["content"]
        if not isinstance(answer, str) or not answer.strip():
            raise ProviderError("MODEL_EMPTY_RESPONSE: provider returned no text.")
        return answer.strip()
    except ProviderError:
        raise
    except requests.Timeout as exc:
        raise ProviderError("MODEL_TIMEOUT: the model provider did not respond in time.") from exc
    except requests.RequestException as exc:
        raise ProviderError("MODEL_NETWORK_ERROR: unable to reach the model provider.") from exc
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ProviderError("MODEL_INVALID_RESPONSE: provider returned an unsupported response.") from exc
