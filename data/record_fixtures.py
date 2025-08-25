# data/record_fixtures.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


# Always place the fixture under the project root ./data/
# Using Path.cwd() avoids Windows drive/UNC mismatches that Streamlit’s watcher can hit.
FIXTURE_PATH: Path = (Path.cwd() / "data" / "products_fixture.json").resolve()

def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Tiny safe fallback so mock mode never crashes if the file doesn't exist yet.
SAMPLE_FIXTURE: Dict[str, Any] = {
    "version": 1,
    "created_at": "1970-01-01T00:00:00Z",
    "data": {
        # Example grouped payload (match your UI shape: {group_name: [products...]})
        "Exemplo": [
            {
                "id": "S1",
                "title": "Calça Slim Azul",
                "price": "R$ 199",
                "brand": "Demo",
                "image": "",
                "url": "#",
            },
            {
                "id": "S2",
                "title": "Calça Reta Preta",
                "price": "R$ 179",
                "brand": "Demo",
                "image": "",
                "url": "#",
            },
        ]
    },
}


def record_fixture(payload: Dict[str, Any]) -> Path:
    """
    Overwrite data/products_fixture.json with the exact dict your UI will render.
    The file format stays boring:
        {
          "version": 1,
          "created_at": "...UTC...",
          "data": { ...your grouped products dict... }
        }

    Raises:
        ValueError: if payload is not a non-empty dict
        OSError: if the file cannot be written
    """
    if not isinstance(payload, dict) or not payload:
        raise ValueError("record_fixture: 'payload' must be a non-empty dict")

    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)

    blob = {
        "version": 1,
        "created_at": _now_utc_iso(),
        "data": payload,
    }

    # Simple atomic-ish write: write to temp then replace.
    tmp_path = FIXTURE_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(FIXTURE_PATH)

    return FIXTURE_PATH


def load_fixture() -> Dict[str, Any]:
    """
    Load data/products_fixture.json. If it doesn't exist or is invalid,
    return a tiny built-in sample so the app keeps running.

    Returns:
        Dict[str, Any]: a dict with keys: version, created_at, data (dict)
    """
    try:
        if FIXTURE_PATH.exists():
            text = FIXTURE_PATH.read_text(encoding="utf-8")
            blob = json.loads(text)
            # Minimal validation
            if isinstance(blob, dict) and isinstance(blob.get("data"), dict):
                return blob
    except Exception:
        # Fall through to sample on any parse/IO error
        pass

    # Ensure the sample carries a fresh timestamp to avoid confusion in logs
    sample = dict(SAMPLE_FIXTURE)
    sample["created_at"] = _now_utc_iso()
    return sample


__all__ = ["record_fixture", "load_fixture", "FIXTURE_PATH"]
