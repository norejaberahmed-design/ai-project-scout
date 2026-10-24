"""Server-side configuration for OpenAI-compatible LLM providers.

Keys are read only from environment variables. Provider IDs are allowlisted; users cannot
supply arbitrary URLs, preventing the chat endpoint from becoming an SSRF proxy.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

PROVIDERS = {
    "openai": {
        "label": "ChatGPT / OpenAI",
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "key_envs": ("SCOUT_OPENAI_API_KEY", "OPENAI_API_KEY"),
        "model_envs": ("SCOUT_OPENAI_MODEL", "OPENAI_MODEL"),
        "default_model": "gpt-4.1-mini",
    },
    "deepseek": {
        "label": "DeepSeek",
        "endpoint": "https://api.deepseek.com/chat/completions",
        "key_envs": ("SCOUT_DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY"),
        "model_envs": ("SCOUT_DEEPSEEK_MODEL", "DEEPSEEK_MODEL"),
        "default_model": "deepseek-chat",
    },
    "gemini": {
        "label": "Google Gemini",
        "endpoint": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "key_envs": ("SCOUT_GEMINI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"),
        "model_envs": ("SCOUT_GEMINI_MODEL", "GEMINI_MODEL"),
        "default_model": "gemini-2.5-flash",
    },
    "openrouter": {
        "label": "OpenRouter",
        "endpoint": "https://openrouter.ai/api/v1/chat/completions",
        "key_envs": ("SCOUT_OPENROUTER_API_KEY", "OPENROUTER_API_KEY"),
        "model_envs": ("SCOUT_OPENROUTER_MODEL", "OPENROUTER_MODEL"),
        "default_model": "",
    },
}

ALIASES = {"chatgpt": "openai", "gpt": "openai", "google": "gemini", "google-gemini": "gemini"}


def _first_env(names: tuple[str, ...]) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def normalize_provider(provider: str | None) -> str:
    requested = (provider or os.getenv("SCOUT_DEFAULT_PROVIDER", "") or "legacy").strip().lower()
    requested = ALIASES.get(requested, requested)
    if requested not in {*PROVIDERS, "legacy"}:
        raise ValueError("مزود النموذج غير معروف. اختر openai أو deepseek أو gemini أو openrouter.")
    return requested


def provider_config(provider: str | None = None) -> dict:
    """Return endpoint, key and model for one provider; never expose this object to clients."""
    name = normalize_provider(provider)
    if name == "legacy":
        key = os.getenv("SCOUT_LLM_API_KEY", "").strip()
        model = os.getenv("SCOUT_LLM_MODEL", "").strip()
        endpoint = os.getenv("SCOUT_LLM_API_URL", "https://openrouter.ai/api/v1/chat/completions").strip()
        label = "مزود متوافق مع OpenAI (الإعداد القديم)"
    else:
        item = PROVIDERS[name]
        key = _first_env(item["key_envs"])
        model = _first_env(item["model_envs"]) or item["default_model"]
        endpoint = item["endpoint"]
        label = item["label"]
    parsed = urlparse(endpoint)
    if endpoint and (parsed.scheme != "https" or not parsed.netloc):
        raise RuntimeError("عنوان مزود النموذج يجب أن يستخدم HTTPS.")
    return {"id": name, "label": label, "api_key": key, "model": model,
            "endpoint": endpoint, "configured": bool(key and model)}


def list_provider_status() -> list[dict]:
    """Safe client-facing status: no keys, endpoint credentials, or private values."""
    items = []
    for name in ("openai", "deepseek", "gemini", "openrouter", "legacy"):
        try:
            config = provider_config(name)
        except (ValueError, RuntimeError):
            config = {"id": name, "label": name, "configured": False}
        items.append({"id": config["id"], "label": config["label"],
                      "configured": bool(config["configured"])})
    return items


def any_provider_configured() -> bool:
    return any(item["configured"] for item in list_provider_status())
