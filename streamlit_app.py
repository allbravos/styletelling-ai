# streamlit_app.py
# Split version: exact UI/strings preserved from original; only moves are imports.
# No refactors beyond importing helpers and product renderer.
import hashlib
from typing import Dict, List, Any
import time
import uuid
from streamlit_orchestrator import stream_user_query, fetch_results_for_prewarm, render_dev_sidebar
from streamlit_persistence import ensure_tables
from utils.streamlit_utils import format_context_summary, group_products, reset_session_for_run
from streamlit_products import render_grouped_products
import streamlit as st

from config.config import MAX_PRODUCTS, USE_CACHE, DEV_MODE, PAGE_TITLE, PAGE_ICON, LAYOUT, RECORD_CACHE
from data.cache_runtime import read_rows, canonicalize_query, build_envelope, write_cache, CACHE_DIR, load_index, get_cached_result

# --------------------------- page setup & state -------------------------------
st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout=LAYOUT)
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

if DEV_MODE:
    render_dev_sidebar()

# --------------------------- helpers (unchanged) ------------------------------

def _render_logs():
    if st.session_state.logs:
        logs_area.markdown("\n\n".join(st.session_state.logs))


def _render_results():
    with results_area.container():
        render_grouped_products(st.session_state.products)


def _handle_stream(q: str):
    import hashlib

    if USE_CACHE and q:
        key = canonicalize_query(q)
        cached_payload = get_cached_result(key, CACHE_INDEX)
        if cached_payload is not None:
            # Stable result-set id for this exact query (same across reruns)
            st.session_state.result_set_id = hashlib.sha1(key.encode()).hexdigest()[:10]

            st.session_state.products = cached_payload
            total = sum(len(v) for v in st.session_state.products.values())
            st.session_state.logs.append("⚡ Resultado do cache")
            st.session_state.logs.append(f"\n---\n**Tempo total:** ~0s • Itens retornados: {total}")
            _render_logs()
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

                    # Set stable result-set id now that the batch is ready
                    key_for_id = canonicalize_query(q)
                    st.session_state.result_set_id = hashlib.sha1(key_for_id.encode()).hexdigest()[:10]

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
                                        "backend_version": "styletelling-stream-2025-08-25"
                                    },
                                )
                                write_cache(filename, env)
                            except Exception as _cache_err:
                                st.session_state.logs.append(f"_Cache write falhou: {_cache_err}_")

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
    reset_session_for_run(query.strip())
    _render_logs()
    _handle_stream(query.strip())

elif retry_clicked:
    q = st.session_state.last_query
    reset_session_for_run(q)
    _render_logs()
    _handle_stream(q)

# Single-pass render (prevents duplicate widget keys)
if st.session_state.logs:
    _render_logs()
if st.session_state.products:
    _render_results()
