# llm/bench.py
import sys, time, json, csv, yaml
from pathlib import Path
from datetime import datetime

from utils import llm_utils
from utils.llm_utils import execute_prompt, last_input_tokens, last_output_tokens, last_cost


# ---- simple config you can edit in PyCharm ----
BASE_DIR = Path(__file__).resolve().parent
MODELS_YAML  = BASE_DIR / "models.yaml"
QUERIES_PATH = BASE_DIR / "queries.csv"
OUTPUT_DIR   = BASE_DIR

# Always use these two prompts
PINNED_PROMPTS = [
    BASE_DIR.parent / "prompts/prompt_0_attribute_selection.txt",
    BASE_DIR.parent / "prompts/prompt_context_analyzer.txt",
]

# Fallback glob if a pinned file is missing
PROMPTS_GLOB = str(BASE_DIR.parent / "prompts/*.txt")


def load_yaml(p: Path):
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def load_lines(p: Path):
    with p.open("r", encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]

def soft_json_ok(text: str):
    try:
        json.loads(text)
        return True, ""
    except Exception as e:
        return False, str(e)[:200]

def ensure_model_in_llm_utils(alias: str, cfg: dict):
    """Best-effort: if llm_utils.MODELS has this alias, update creds/routes.
    If not, create a minimal entry so execute_prompt(api_model=alias) can resolve."""
    model_map = getattr(llm_utils, "MODELS", None)
    if model_map is None:
        return
    entry = model_map.get(alias, {})
    # Common fields people wire up in routers; harmless if unused
    entry.update({
        "api_key": cfg.get("api_key"),
        "base_url": cfg.get("base_url"),
        "model_id": cfg.get("model_id", alias),
        "defaults": cfg.get("defaults", {}),
    })
    model_map[alias] = entry

def compute_cost(in_tok, out_tok, pricing):
    if in_tok is None or out_tok is None or not pricing:
        return None
    pi = float(pricing.get("input", 0.0))
    po = float(pricing.get("output", 0.0))
    return (in_tok / 1e6) * pi + (out_tok / 1e6) * po

def write_xlsx(rows, out_path: Path):
    try:
        from openpyxl import Workbook
    except ImportError:
        raise SystemExit("openpyxl not installed. Run: pip install openpyxl")
    wb = Workbook()
    ws = wb.active
    ws.title = "bench"
    headers = ["model","prompt_file","query","latency_ms","input_tokens","output_tokens","cost_usd","quality_ok","quality_reason"]
    ws.append(headers)
    for r in rows:
        ws.append([r.get(h) for h in headers])
    wb.save(out_path)

def normalize_models(cfg: dict):
    out = []
    # flat shape: models: {alias: {...}}
    flat = (cfg.get("models") or {})
    if flat:
        out.extend(flat.items())

    # hierarchical shape: providers: {prov: {base_url, api_key, defaults, models:[...]}}
    for prov, pcfg in (cfg.get("providers") or {}).items():
        p_base = pcfg.get("base_url")
        p_key = pcfg.get("api_key")
        p_def = pcfg.get("defaults") or {}
        for m in pcfg.get("models") or []:
            alias = m.get("alias") or m.get("model_id")
            merged = {
                **m,
                "base_url": m.get("base_url", p_base),
                "api_key": m.get("api_key", p_key),
                "defaults": {**p_def, **(m.get("defaults") or {})},
            }
            out.append((alias, merged))
    return out

def resolve_prompt_files():
    files = [Path(p) for p in PINNED_PROMPTS if Path(p).exists()]
    if len(files) == len(PINNED_PROMPTS):
        return files
    missing = [str(p) for p in PINNED_PROMPTS if not Path(p).exists()]
    if missing:
        print(f"Warning: missing pinned prompts, falling back to glob: {missing}")
    return sorted((BASE_DIR.parent).glob("prompts/*.txt"))

def _val(x):
    try:
        return x() if callable(x) else x
    except Exception:
        return None

def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cfg = load_yaml(MODELS_YAML)
    models = normalize_models(cfg)
    queries = load_lines(QUERIES_PATH)
    prompt_files = resolve_prompt_files()

    if not models: raise SystemExit("No models in models.yaml")
    if not queries: raise SystemExit("No queries in queries.csv")
    if not prompt_files: raise SystemExit(f"No prompts matched: {PROMPTS_GLOB}")

    results = []
    for alias, mcfg in models:
        ensure_model_in_llm_utils(alias, mcfg)
        defaults = (mcfg.get("defaults") or {})
        for p in prompt_files:
            p_str = str(p)
            for q in queries:
                t0 = time.perf_counter()
                try:
                    resp = execute_prompt(
                        api_model=alias,
                        prompt_file=p_str,
                        user_query=q,
                        **defaults
                    )
                except Exception as e:
                    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                    err = f"{type(e).__name__}: {e}"
                    results.append({
                        "model": alias, "prompt_file": p_str, "query": q,
                        "latency_ms": latency_ms, "input_tokens": None, "output_tokens": None,
                        "cost_usd": None, "quality_ok": False, "quality_reason": f"call_failed: {err}"
                    })
                    print(f"[{alias}] {p.name} | {latency_ms} ms | CALL FAIL: {err}")
                    continue

                latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                text = resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False)
                ok, reason = soft_json_ok(text)

                in_tok = _val(getattr(llm_utils, "last_input_tokens", None))
                out_tok = _val(getattr(llm_utils, "last_output_tokens", None))
                last_cost_val = _val(getattr(llm_utils, "last_cost", None))

                pricing = mcfg.get("pricing_per_million") or mcfg.get("cost_per_million")
                cost = last_cost_val if isinstance(last_cost_val, (int, float)) else compute_cost(in_tok, out_tok,
                                                                                                  pricing)

                results.append({
                    "model": alias,
                    "prompt_file": p_str,
                    "query": q,
                    "latency_ms": latency_ms,
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                    "cost_usd": round(cost, 6) if isinstance(cost, (int, float)) else None,
                    "quality_ok": ok,
                    "quality_reason": "" if ok else reason
                })
                print(f"[{alias}] {p.name} | {latency_ms} ms | JSON {'OK' if ok else 'FAIL'}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUTPUT_DIR / f"bench_results_{ts}.xlsx"
    write_xlsx(results, out_path)
    print(f"Saved: {out_path}")

if __name__ == "__main__":
    run()
