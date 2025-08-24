# streamlit_app.py
# Split version: exact UI/strings preserved from original; only moves are imports.
# No refactors beyond importing helpers and product renderer.

from typing import Dict, List, Any
import time
import uuid

import streamlit as st

from streamlit_client import stream_user_query
from streamlit_persistence import ensure_tables

from utils.streamlit_utils import format_context_summary, group_products
from streamlit_products import render_grouped_products

# --------------------------- constants ---------------------------------------
MAX_PRODUCTS = 15

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

# --------------------------- helpers (unchanged) ------------------------------

def _reset_session_for_run(q: str):
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.last_query = q
    st.session_state.logs = ["### Processando sua solicitação."]
    st.session_state.products = {}
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
