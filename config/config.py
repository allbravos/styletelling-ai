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
    Precedence: ENV (<KEY>) -> config.yaml -> default
    Example: _get("MAX_PRODUCTS", 60)
    """
    env_key = key
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


def _resolve_db_path():
    """
    Enhanced database path resolution with multiple fallback locations.
    Tries environment variable first, then searches common locations.
    """
    # Get the project root directory (parent of the config directory)
    PROJECT_ROOT = Path(__file__).parent.parent.resolve()
    DB_FILENAME = "styletelling.sqlite"

    # Check for environment variable first
    env_db_path = _get("DB_PATH")
    if env_db_path and env_db_path != "styletelling.sqlite":  # Not just the default
        if os.path.exists(env_db_path):
            print(f"[CONFIG] Using database path from environment: {env_db_path}")
            return env_db_path
        else:
            print(f"[CONFIG] Environment DB_PATH '{env_db_path}' not found, searching...")

    # Try multiple possible locations for the database file
    POSSIBLE_DB_PATHS = [
        PROJECT_ROOT / DB_FILENAME,  # Standard: project root
        Path.cwd() / DB_FILENAME,  # Current working directory
        Path(__file__).parent / DB_FILENAME,  # config directory (fallback)
        Path(DB_FILENAME),  # Relative to current directory
    ]

    # Find the database file
    for path in POSSIBLE_DB_PATHS:
        if path.exists():
            resolved_path = str(path.resolve())
            print(f"[CONFIG] Found database at: {resolved_path}")
            return resolved_path

    # If no existing database found, use the project root as default
    default_path = str(PROJECT_ROOT / DB_FILENAME)
    print(f"[CONFIG] No existing database found, using default: {default_path}")
    return default_path


# ---- Public values ----
API_KEY: str = _get("API_KEY")

MAX_PRODUCTS: int = _get("MAX_PRODUCTS", 15)
DEV_MODE: bool = _get("DEV_MODE", False)
RECORD_CACHE: bool = _get("RECORD_CACHE", True)
CACHE_DIR: str = _get("CACHE_DIR", "data/cached_queries_v1")
PROMPT_DIR: str = _get("PROMPT_DIR", "prompts/")

# Enhanced database path resolution
DB_PATH: str = _resolve_db_path()

# Print debug info (will be visible in Streamlit logs)
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
print(f"[CONFIG] Project root: {PROJECT_ROOT}")
print(f"[CONFIG] Current working directory: {Path.cwd()}")
print(f"[CONFIG] Final database path: {DB_PATH}")
print(f"[CONFIG] Database exists: {os.path.exists(DB_PATH)}")

# List all files in project root for debugging
if PROJECT_ROOT.exists():
    files_in_root = [f.name for f in PROJECT_ROOT.glob("*") if f.is_file()]
    print(f"[CONFIG] Files in project root: {files_in_root}")

# List all .sqlite files in various locations for debugging
sqlite_files = []
for search_dir in [PROJECT_ROOT, Path.cwd(), Path(__file__).parent]:
    if search_dir.exists():
        found_sqlite = list(search_dir.glob("*.sqlite"))
        if found_sqlite:
            sqlite_files.extend([str(f) for f in found_sqlite])

if sqlite_files:
    print(f"[CONFIG] Found .sqlite files: {sqlite_files}")
else:
    print(f"[CONFIG] No .sqlite files found in searched directories")

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