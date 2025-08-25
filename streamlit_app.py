# streamlit_app.py
# Split version: exact UI/strings preserved from original; only moves are imports.
# No refactors beyond importing helpers and product renderer.

from typing import Dict, List, Any
import time
import uuid

import streamlit as st

from data.cache_runtime import (
    read_rows,
    canonicalize_query,
    build_envelope,
    write_cache,
    CACHE_DIR,
    load_index,          # <-- add
    get_cached_result,   # <-- add
)
from streamlit_client import stream_user_query, DATA_MODE, RECORD_FIXTURES, RECORD_CACHE
from streamlit_persistence import ensure_tables
from data.record_fixtures import record_fixture

from utils.streamlit_utils import format_context_summary, group_products
from streamlit_products import render_grouped_products

# --------------------------- constants ---------------------------------------
MAX_PRODUCTS = 15
USE_CACHE: bool = True
SHOW_CACHE_TOOLS = False
# --------------------------- page setup & state -------------------------------
st.set_page_config(page_title="Styletelling – Streamlit", layout="wide")
ensure_tables()

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "last_query" not in st.session_state:
    st.session_state.last_query = ""
if "logs" not in st.session_state:
    st.session_state.logs: List[str] = []
if "products" not in st.session_state:
    # grouped dict: {category: [products]}
    st.session_state.products: Dict[str, List[Dict[str, Any]]] = {}

st.set_page_config(page_title="Styletelling – Streamlit", layout="wide")
ensure_tables()

try:
    CACHE_INDEX = load_index("data/queries.csv")
except Exception:
    CACHE_INDEX = {}

# --------------------------- header & inputs ---------------------------------
st.title("🛍️ Styletelling — Assistente de Moda")
st.write("Descreva a ocasião ou estilo. Eu busco e mostro até 15 produtos.")

query = st.text_area(
    "O que você está procurando?",
    placeholder="Ex: Viagem de verão para cidade litorânea com amigos",
    height=80,
)
col_run, col_retry = st.columns([1, 1])
run_clicked = col_run.button("Buscar", type="primary")
retry_clicked = col_retry.button("Repetir última busca", disabled=not st.session_state.last_query)

logs_area = st.empty()
results_area = st.empty()

# --------------------------- sidebar ------------------------------
def _fetch_results_for_prewarm(query: str) -> dict:
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

if SHOW_CACHE_TOOLS:
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
                        result = _fetch_results_for_prewarm(r.query_raw)
                        env = build_envelope(
                            query_raw=r.query_raw,
                            query_norm=r.query_norm,
                            result=result,
                            filename=r.filename,
                            meta_extra={
                                "backend_version": "styletelling-prewarm-ui",
                                "mode": DATA_MODE,
                            },
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

# --------------------------- helpers (unchanged) ------------------------------

def _reset_session_for_run(q: str):
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.last_query = q
    st.session_state.logs = ["### Processando sua solicitação."]
    st.session_state.products = {}
    st.session_state.fixture_saved = False
    # also clear per-product transient states from any previous run
    keys_to_clear = [
        k for k in list(st.session_state.keys())
        if any(
            k.startswith(prefix) for prefix in (
                "submitted_", "need_comment_", "details_", "error_",
                "like_", "dislike_", "confirm_", "cancel_",
                "d_", "d_send_", "d_cancel_",
                "open_dialog_",  # ensure dialog flags are cleared
            )
        )
    ]
    for k in keys_to_clear:
        st.session_state.pop(k, None)


def _render_logs():
    if st.session_state.logs:
        logs_area.markdown("\n\n".join(st.session_state.logs))


def _render_results():
    with results_area.container():
        render_grouped_products(st.session_state.products)

def _handle_stream(q: str):

    if USE_CACHE and q:
        key = canonicalize_query(q)
        cached_payload = get_cached_result(key, CACHE_INDEX)
        if cached_payload is not None:
            st.session_state.products = cached_payload
            total = sum(len(v) for v in st.session_state.products.values())
            st.session_state.logs.append("⚡ Resultado do cache")
            st.session_state.logs.append(f"\n---\n**Tempo total:** ~0s • Itens retornados: {total}")
            _render_logs()
            _render_results()
            return

    with st.spinner("Encontrando os melhores produtos…"):
        try:
            start = time.time()
            for step in stream_user_query(q):
                status = step.get("status")
                if status == "progress":
                    msg = step.get("message") or ""
                    if msg:
                        st.session_state.logs.append(msg)
                        _render_logs()

                elif status == "context_result":
                    ctx = step.get("data") or {}
                    summary = format_context_summary(ctx)
                    if summary:
                        st.session_state.logs.append(f"**Contexto:** {summary}")
                        _render_logs()

                elif status == "intermediate_result":
                    _type = step.get("type")
                    data = step.get("data") or []
                    if _type == "attributes" and data:
                        st.session_state.logs.append(f"**Atributos selecionados:** {', '.join(data)}")
                        _render_logs()
                    elif _type == "categories" and data:
                        st.session_state.logs.append(f"**Categorias sugeridas:** {', '.join(data)}")
                        _render_logs()

                elif status == "final_result":
                    final_results = step.get("data") or {}
                    st.session_state.products = group_products(final_results, cap=MAX_PRODUCTS)

                    if USE_CACHE and RECORD_CACHE:
                        key = canonicalize_query(q)
                        filename = CACHE_INDEX.get(key)
                        if filename:
                            try:
                                env = build_envelope(
                                    query_raw=q,
                                    query_norm=key,
                                    result=st.session_state.products,
                                    filename=filename,
                                    meta_extra={
                                        "backend_version": "styletelling-stream-2025-08-25",
                                        "mode": DATA_MODE,
                                    },
                                )
                                write_cache(filename, env)
                            except Exception as _cache_err:
                                st.session_state.logs.append(f"_Cache write falhou: {_cache_err}_")

                    # Save a single-file fixture with the exact payload the UI will render.
                    # Only in real mode, only once per rerun, and only if enabled.
                    if (
                            DATA_MODE.lower() == "real"
                            and RECORD_FIXTURES
                            and st.session_state.products
                            and not st.session_state.get("fixture_saved", False)
                    ):
                        try:
                            record_fixture(st.session_state.products)
                            st.session_state.fixture_saved = True
                            st.session_state.logs.append("_Fixture salva em `data/products_fixture.json`._")
                        except Exception as _rec_err:
                            st.session_state.logs.append(f"_Não foi possível salvar a fixture: {_rec_err}_")

                    took = round(time.time() - start, 2)
                    total = sum(len(v) for v in st.session_state.products.values())
                    st.session_state.logs.append(f"\n---\n**Tempo total:** {took}s • Itens retornados: {total}")
                    _render_logs()

                elif status == "final_message":
                    msg = step.get("message") or ""
                    if msg:
                        st.session_state.logs.append(msg)
                        _render_logs()

                if not st.session_state.products:
                    results_area.info("Buscando…")
        except Exception as e:
            st.session_state.logs.append(f"❌ Erro: {e}")
            _render_logs()

# --------------------------- actions & rendering ------------------------------
if run_clicked and query.strip():
    _reset_session_for_run(query.strip())
    _render_logs()
    _handle_stream(query.strip())

elif retry_clicked:
    q = st.session_state.last_query
    _reset_session_for_run(q)
    _render_logs()
    _handle_stream(q)

# Single-pass render (prevents duplicate widget keys)
if st.session_state.logs:
    _render_logs()
if st.session_state.products:
    _render_results()
