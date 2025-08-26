# data/cache_runtime.py
import csv
import json
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Callable, Tuple
from config.config import CACHE_DIR

NORM_VERSION = "v1"
CACHE_DIR = Path(CACHE_DIR)

# ----------------
# Normalization
# ----------------

def canonicalize_query(text: str) -> str:
    """Return canonical form of a query string for cache matching."""
    text = unicodedata.normalize("NFKC", text).casefold()
    text = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
    text = " ".join(text.strip().split())
    text = re.sub(r"[^a-z0-9 ]+", "", text)
    return text.strip()


def validate_filename(name: str) -> bool:
    """Filename rules: allowed chars, .json ending, length, safe path."""
    if len(name) > 80:
        return False
    if not name.endswith(".json"):
        return False
    if name.startswith(".") or ".." in name:
        return False
    if not re.match(r"^[A-Za-z0-9._-]+\.json$", name):
        return False
    return True


# ----------------
# CSV loading
# ----------------

@dataclass(frozen=True)
class QueryRow:
    line_no: int
    query_raw: str
    query_norm: str
    filename: str  # exactly as in CSV


def read_rows(csv_path: str) -> List[QueryRow]:
    """
    Read queries.csv -> list[QueryRow].
    Validates filename rules and uniqueness (canonical key and filename).
    """
    rows: List[QueryRow] = []
    seen_keys: Dict[str, int] = {}
    seen_files: Dict[str, int] = {}

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):  # start=2 for header
            raw_query = (row.get("query") or "").strip()
            filename = (row.get("file") or "").strip()
            if not raw_query or not filename:
                raise ValueError(f"Row {i}: empty query or file")

            if not validate_filename(filename):
                raise ValueError(f"Row {i}: invalid filename '{filename}'")

            key = canonicalize_query(raw_query)

            if key in seen_keys:
                raise ValueError(
                    f"Row {i}: duplicate canonical key '{key}' "
                    f"(first seen at row {seen_keys[key]})"
                )
            if filename in seen_files:
                raise ValueError(
                    f"Row {i}: duplicate file name '{filename}' "
                    f"(first seen at row {seen_files[filename]})"
                )

            seen_keys[key] = i
            seen_files[filename] = i
            rows.append(QueryRow(i, raw_query, key, filename))

    return rows


def load_index(csv_path: str) -> Dict[str, str]:
    """
    Load queries.csv into {canonical_key -> file}.
    Raises ValueError on duplicates or invalid rows.
    """
    rows = read_rows(csv_path)
    index = {r.query_norm: r.filename for r in rows}
    print(f"Loaded {len(index)} queries from {csv_path}")
    return index


# ----------------
# Cache read/write
# ----------------

def _ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def build_envelope(
    *,
    query_raw: str,
    query_norm: str,
    result: dict,
    filename: str,
    meta_extra: Optional[dict] = None,
) -> dict:
    meta = {
        "source": "prewarm_from_file",
        "file": filename,
        "norm_version": NORM_VERSION,
    }
    if meta_extra:
        meta.update(meta_extra)

    return {
        "query_raw": query_raw,
        "query_norm": query_norm,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "meta": meta,
        "result": result,
    }


def write_cache(filename: str, envelope: dict) -> Path:
    """
    Atomically write envelope to CACHE_DIR/filename and re-open to validate JSON.
    Returns the full path.
    """
    _ensure_cache_dir()
    path = CACHE_DIR / filename
    tmp = path.with_suffix(path.suffix + ".tmp")

    # Basic sanity before writing
    if envelope.get("query_norm") and not isinstance(envelope.get("result"), dict):
        raise ValueError("Envelope missing or invalid 'result' dict")

    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(envelope, f, ensure_ascii=False, separators=(",", ":"), indent=2)

    os.replace(tmp, path)

    # Re-open to ensure valid JSON (and catch partial writes on weird FS)
    with open(path, "r", encoding="utf-8") as f:
        json.load(f)

    return path


def get_cached_result(canonical_key: str, index: Dict[str, str]) -> Optional[dict]:
    """
    Return envelope['result'] if cached; otherwise None.
    Treat JSON/IO errors as a cache miss.
    """
    filename = index.get(canonical_key)
    if not filename:
        return None

    path = CACHE_DIR / filename
    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            envelope = json.load(f)
        # sanity: norm matches key (best-effort)
        if envelope.get("query_norm") != canonical_key:
            # still return it—it’s a cache, not sacred scripture
            return envelope.get("result")
        return envelope.get("result")
    except Exception:
        # treat as miss; logging can be added by caller
        return None


# ----------------
# Prewarm runner
# ----------------

def prewarm_from_csv(
    csv_path: str,
    fetch_results: Callable[[str], dict],
    *,
    overwrite: bool = False,
    limit: Optional[int] = None,
    meta_extra: Optional[dict] = None,
) -> Tuple[int, int, int]:
    """
    Precompute cache files for all rows in queries.csv using fetch_results(query_raw).

    Returns (total, written, skipped)
    - total: number of rows considered
    - written: number of files written (or overwritten)
    - skipped: existing files skipped because overwrite=False
    """
    rows = read_rows(csv_path)
    _ensure_cache_dir()

    total = 0
    written = 0
    skipped = 0

    for r in rows:
        if limit is not None and total >= limit:
            break
        total += 1

        path = CACHE_DIR / r.filename
        if path.exists() and not overwrite:
            skipped += 1
            continue

        # Fetch and write
        result = fetch_results(r.query_raw)  # <-- your existing function
        envelope = build_envelope(
            query_raw=r.query_raw,
            query_norm=r.query_norm,
            result=result,
            filename=r.filename,
            meta_extra=meta_extra,
        )
        write_cache(r.filename, envelope)
        written += 1

    print(
        f"Prewarm done: total={total}, written={written}, skipped={skipped}, "
        f"cache_dir={CACHE_DIR}"
    )
    return total, written, skipped


# ----------------
# CLI dry-run
# ----------------

if __name__ == "__main__":
    csv_file = Path(__file__).parent / "queries.csv"
    idx = load_index(str(csv_file))
    # preview a few keys
    for k, v in list(idx.items())[:5]:
        print(f"{k} -> {v}")
