# streamlit_app.py
import uuid
import time
from collections import OrderedDict
from typing import Dict, List, Any, Iterator
from io import BytesIO

import streamlit as st

# NEW: lightweight image fetch + placeholder
import requests
from PIL import Image, ImageDraw, ImageFont

from streamlit_client import stream_user_query
from streamlit_persistence import ensure_tables, save_feedback

MAX_PRODUCTS = 15  # global cap across categories

# --------------------------- helpers: data & grouping ---------------------------
def format_context_summary(ctx: Dict[str, Any]) -> str:
    if not ctx:
        return ""
    occ = ctx.get("occasion") or {}
    weather = ctx.get("weather") or {}
    parts = []
    occ_bits = []
    if occ.get("event"):
        occ_bits.append(f"Evento: **{occ['event']}**")
    if occ.get("dress_code"):
        occ_bits.append(f"Estilo: **{occ['dress_code']}**")
    if occ.get("activity"):
        occ_bits.append(f"Atividade: **{occ['activity']}**")
    if occ_bits:
        parts.append(" | ".join(occ_bits))
    if weather.get("climate"):
        emoji = "☀️" if weather["climate"] == "Hot" else "❄️" if weather["climate"] == "Cold" else "🌤️"
        parts.append(f"Clima: {emoji} **{weather['climate']}**")
    return " • ".join(parts)


def group_products(final_results: Dict[str, List[Dict[str, Any]]], cap: int = MAX_PRODUCTS) -> Dict[str, List[Dict[str, Any]]]:
    """Ordered grouping by category with a global cap and dedupe by product_id."""
    grouped: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
    seen = set()
    total = 0
    for cat, items in (final_results or {}).items():
        bucket: List[Dict[str, Any]] = []
        for p in items or []:
            pid = p.get("product_id")
            if not pid or pid in seen:
                continue
            seen.add(pid)
            bucket.append({
                "product_id": pid,
                "name": p.get("name"),
                "price": p.get("price"),
                "relevance_score": p.get("relevance_score"),
                "image_url": p.get("image_url"),
                "category": cat,
                "description": p.get("description", ""),
            })
            total += 1
            if total >= cap:
                break
        if bucket:
            grouped[cat] = bucket
        if total >= cap:
            break
    return grouped


# --------------------------- helpers: images -----------------------------------
@st.cache_data(show_spinner=False)
def _fetch_image_bytes(url: str | None, timeout: float = 5.0) -> bytes | None:
    """Try to fetch bytes for an image URL. Return None on any failure."""
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.ok and resp.content:
            return resp.content
    except Exception:
        pass
    return None


@st.cache_data(show_spinner=False)
def _placeholder_bytes(size=(600, 600)) -> bytes:
    """Generate a neutral placeholder image as bytes (PNG)."""
    w, h = size
    img = Image.new("RGB", (w, h), color=(242, 242, 242))  # light gray
    draw = ImageDraw.Draw(img)
    # Simple icon-ish box
    margin = int(min(w, h) * 0.1)
    draw.rectangle([margin, margin, w - margin, h - margin], outline=(200, 200, 200), width=4)
    # Optional: faint text
    text = "sem imagem"
    try:
        # If default fonts unavailable, PIL will raise — we just skip text if so
        font = ImageFont.load_default()
        tw, th = draw.textsize(text, font=font)
        draw.text(((w - tw) / 2, (h - th) / 2), text, fill=(180, 180, 180), font=font)
    except Exception:
        pass
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _render_image(p: Dict[str, Any]):
    """Render product image with graceful fallback to a placeholder."""
    raw = _fetch_image_bytes(p.get("image_url"))
    if not raw:
        raw = _placeholder_bytes()
    st.image(BytesIO(raw), use_container_width=True)


# --------------------------- helpers: feedback & UI ----------------------------
def _persist_feedback(pid: str, rating: str, p: Dict[str, Any], details: str | None):
    details = (details or "").strip() or None
    save_feedback(
        user_query=st.session_state.last_query,
        product_id=pid,
        product_name=p.get("name") or "",
        category=p.get("category") or "",
        rating=rating,
        details=details,
        session_id=st.session_state.session_id,
    )
    st.toast(f"Feedback registrado: {rating}")


# Modal dialog for mandatory comment on negative feedback (open/close via flag)
@st.dialog("Conte rapidamente o que não funcionou")
def _dislike_dialog(pid: str, p: Dict[str, Any], base: str):
    details_key = f"d_{base}"
    st.markdown("**Explique o que não funcionou:** _relevância, preço, imagem, ajuste, etc._")
    st.text_area("Comentário obrigatório", key=details_key, label_visibility="collapsed", height=120)
    c1, c2 = st.columns([1, 1], gap="small")
    with c1:
        if st.button("Enviar", key=f"d_send_{base}", use_container_width=True):
            details = (st.session_state.get(details_key) or "").strip()
            if not details:
                st.warning("O comentário é obrigatório.")
            else:
                _persist_feedback(pid, "Não Gostei", p, details=details)
                st.session_state[f"submitted_{base}"] = True
                # cleanup and close dialog
                st.session_state.pop(details_key, None)
                st.session_state.pop(f"open_dialog_{base}", None)  # NEW: close flag
                st.rerun()
    with c2:
        if st.button("Cancelar", key=f"d_cancel_{base}", use_container_width=True):
            # cleanup and close dialog without saving
            st.session_state.pop(details_key, None)
            st.session_state.pop(f"open_dialog_{base}", None)  # NEW: close flag
            st.rerun()


def _render_product_card(p: Dict[str, Any]):
    pid = p["product_id"]
    cat = (p.get("category") or "").replace(" ", "_")
    base = f"{pid}_{cat}_{st.session_state.session_id}"

    # IMAGE: now uses robust renderer with placeholder
    _render_image(p)

    st.markdown(f"**{p.get('name','')}**")

    price = p.get("price") or ""
    score = p.get("relevance_score")
    cat = p.get("category") or ""
    st.caption(f"ID: `{pid}` • {cat} • Score: {score}")
    if price:
        st.write(price)

    # Per-product state
    submitted_key = f"submitted_{base}"
    submitted = st.session_state.get(submitted_key, False)

    # If the dialog should be open (from a prior click), render it first and stop
    if st.session_state.get(f"open_dialog_{base}"):
        _dislike_dialog(pid, p, base)
        return

    if submitted:
        st.success("Feedback enviado")
        return

    cols = st.columns(2, gap="small")
    with cols[0]:
        if st.button("👍 Gostei", key=f"like_{base}", use_container_width=True):
            # clear any leftover dialog flag just in case
            st.session_state.pop(f"open_dialog_{base}", None)
            _persist_feedback(pid, "Gostei", p, details=None)
            st.session_state[submitted_key] = True
            return
    with cols[1]:
        if st.button("👎 Não gostei", key=f"dislike_{base}", use_container_width=True):
            st.session_state[f"open_dialog_{base}"] = True
            st.rerun()
            return


def render_grouped_products(grouped: Dict[str, List[Dict[str, Any]]]):
    if not grouped:
        st.info("Nenhum produto encontrado. Tente refinar a descrição.")
        return
    for cat, products in grouped.items():
        st.subheader(f"{cat} · {len(products)}")
        cols_per_row = 3
        for i, p in enumerate(products):
            if i % cols_per_row == 0:
                row = st.columns(cols_per_row, gap="medium")
            with row[i % cols_per_row]:
                _render_product_card(p)


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
                "open_dialog_",  # NEW: ensure dialog flags are cleared
            )
        )
    ]
    for k in keys_to_clear:
        st.session_state.pop(k, None)


def _render_logs():
    logs_area.markdown("\n\n".join(st.session_state.logs))


def _render_results():
    with results_area.container():
        render_grouped_products(st.session_state.products)


def _handle_stream(q: str):
    with st.spinner("Encontrando os melhores produtos…"):
        try:
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
                    elif _type == "categories" and data:
                        st.session_state.logs.append(f"**Categorias sugeridas:** {', '.join(data)}")
                    _render_logs()

                elif status == "final_result":
                    final_results = step.get("data") or {}
                    st.session_state.products = group_products(final_results, cap=MAX_PRODUCTS)
                    took = round(time.time() - _start, 2)
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
    _start = time.time()
    _handle_stream(query.strip())

elif retry_clicked:
    q = st.session_state.last_query
    _reset_session_for_run(q)
    _render_logs()
    _start = time.time()
    _handle_stream(q)

# Single-pass render (prevents duplicate widget keys)
if st.session_state.logs:
    _render_logs()
if st.session_state.products:
    _render_results()
