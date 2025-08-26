# streamlit_orchestrator.py
import streamlit as st
from typing import Iterator, Dict, Any
from utils.streamlit_utils import group_products

from config.config import CACHE_DIR
from data.cache_runtime import build_envelope, read_rows, write_cache


def stream_user_query(user_query: str) -> Iterator[Dict[str, Any]]:
    """
    Main interface between the UI and the data source.
    It yields events that drive the Streamlit front-end:
      - {"status": "progress", "message": str}
      - {"status": "context_result", ...}
      - {"status": "intermediate_result", ...}
      - {"status": "final_result", "data": <grouped_products_dict>}
      - {"status": "final_message", "message": str}
    """
    from run_user_query import process_user_query_streaming
    for step in process_user_query_streaming(user_query):
        yield step


def fetch_results_for_prewarm(query: str) -> dict:
    final_payload = None
    for ev in stream_user_query(query):
        status = ev.get("status")
        if status == "final_result":
            data = ev.get("data")
            if isinstance(data, dict):
                final_payload = data
            else:
                final_payload = group_products(data)
            break
        elif status == "error":
            raise RuntimeError(ev.get("message", "Erro ao buscar resultados"))
    if final_payload is None:
        raise RuntimeError("Fluxo terminou sem 'final_result'")
    return final_payload


def render_dev_sidebar():
    with st.sidebar:
        st.markdown("### Cache")
        _overwrite = st.checkbox("Sobrescrever existentes", False)
        _limit = st.number_input("Limite (0 = todos)", min_value=0, value=0, step=1)
        if st.button("🔧 Preaquecer cache agora"):
            _rows = read_rows("data/queries.csv")
            if _limit and _limit > 0:
                _rows = _rows[: int(_limit)]

            prog = st.progress(0.0, text="Preparando…")
            log = st.empty()

            total = len(_rows)
            written = 0
            skipped = 0
            failed = 0

            for i, r in enumerate(_rows, start=1):
                try:
                    # skip if exists and not overwriting
                    path = CACHE_DIR / r.filename
                    if path.exists() and not _overwrite:
                        skipped += 1
                    else:
                        # fetch + write envelope atomically
                        result = fetch_results_for_prewarm(r.query_raw)
                        env = build_envelope(
                            query_raw=r.query_raw,
                            query_norm=r.query_norm,
                            result=result,
                            filename=r.filename,
                            meta_extra={"backend_version": "styletelling-prewarm-ui"},
                        )
                        write_cache(r.filename, env)
                        written += 1

                    prog.progress(i / total, text=f"{i}/{total} • {r.filename}")
                    log.markdown(
                        f"**Último:** `{r.filename}`  \n"
                        f"— *query:* {r.query_raw[:80]}{'…' if len(r.query_raw)>80 else ''}"
                    )
                except Exception as e:
                    failed += 1
                    prog.progress(i / total, text=f"{i}/{total} • erro em {r.filename}")
                    log.markdown(f"**Erro:** `{r.filename}` — {e}")

            st.success(
                f"Preaquecer concluído • total={total} • gravados={written} • pulados={skipped} • falhas={failed}"
            )