"""Environment-backed configuration. Never expose secret values to clients."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_DIR = ROOT / "skills" / "active"
PROPOSED_DIR = ROOT / "skills" / "proposed"
SITE_DIR = ROOT / "site"

def setting(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()

def int_setting(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(setting(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))

def allowed_origins() -> set[str]:
    raw = setting("SCOUT_ALLOWED_ORIGINS", "http://127.0.0.1:8080,http://localhost:8080")
    return {item.strip().rstrip("/") for item in raw.split(",") if item.strip()}
