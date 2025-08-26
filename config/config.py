import os
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None

CFG_FILE = Path(__file__).with_suffix(".yaml")

def _load_yaml():
    if yaml and CFG_FILE.exists():
        with CFG_FILE.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data if isinstance(data, dict) else {}
    return {}

_cfg = _load_yaml()

def _get(key: str, default=None):
    """
    Precedence: ENV (ST_<KEY>) -> config.yaml -> default
    Example: _get("MAX_PRODUCTS", 60)
    """
    env_key = f"ST_{key}"
    if env_key in os.environ:
        val = os.environ[env_key]
        if isinstance(default, bool):
            return str(val).lower() in {"1", "true", "yes", "y"}
        if isinstance(default, int):
            try:
                return int(val)
            except Exception:
                return default
        return val
    if key in _cfg:
        return _cfg[key]
    return default

# ---- Public values ----
API_KEY: str = _get("API_KEY")

MAX_PRODUCTS: int = _get("MAX_PRODUCTS", 15)
DEV_MODE: bool = _get("DEV_MODE", False)
RECORD_CACHE: bool = _get("RECORD_CACHE", True)
DB_PATH: str = _get("DB_PATH", "data/app.sqlite3")
CACHE_DIR: str = _get("CACHE_DIR", "data/cached_queries_v1")
PROMPT_DIR: str = _get("PROMPT_DIR", "prompts/")

# UI
PAGE_TITLE: str = _get("PAGE_TITLE", "Styletelling")
PAGE_ICON: str = _get("PAGE_ICON", "✨")
LAYOUT: str = _get("LAYOUT", "wide")

# Feature toggles
USE_CACHE: bool = _get("USE_CACHE", True)
SHOW_CACHE_TOOLS: bool = _get("SHOW_CACHE_TOOLS", False)

def get_api_key(name: str) -> str | None:
    """
    Look up an API key by name (e.g. 'OPENAI', 'GROQ').
    Precedence: ENV var -> config.yaml -> None.
    ENV convention: <NAME>_API_KEY
    """
    env_key = f"{name.upper()}_API_KEY"
    if env_key in os.environ:
        return os.environ[env_key]
    return _cfg.get(env_key)
