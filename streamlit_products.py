# streamlit_products.py
# Minimal move-only split: product UI + feedback helpers extracted verbatim
# No refactors; keep behavior identical.

from typing import Dict, List, Any
from io import BytesIO

import streamlit as st

from streamlit_persistence import save_feedback
from utils.streamlit_utils import _fetch_image_bytes, _placeholder_bytes, inject_discreet_link_css_once



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
                st.session_state.pop(f"open_dialog_{base}", None)
                st.rerun()
    with c2:
        if st.button("Cancelar", key=f"d_cancel_{base}", use_container_width=True):
            # cleanup and close dialog without saving
            st.session_state.pop(details_key, None)
            st.session_state.pop(f"open_dialog_{base}", None)
            st.rerun()


# Single product card + feedback buttons

def _render_product_card(p: Dict[str, Any]):
    pid = p["product_id"]
    cat = (p.get("category") or "").replace(" ", "_")
    base = f"{pid}_{cat}_{st.session_state.session_id}"

    submitted_key = f"submitted_{base}"
    open_dialog_key = f"open_dialog_{base}"

    # IMAGE
    _render_image(p)

    # Basic info
    st.markdown(f"**{p.get('name','')}**")
    price = p.get("price") or ""
    score = p.get("relevance_score")
    cat_label = p.get("category") or ""
    st.caption(f"ID: `{pid}` • {cat_label} • Score: {score}")
    if price:
        st.write(price)

    desc = (p.get("description") or "").strip()
    if desc:
        inject_discreet_link_css_once()
        st.markdown('<div class="desc-trigger">', unsafe_allow_html=True)
        with st.popover("ver mais..."):  # no key arg in your Streamlit
            st.write(desc)
        st.markdown('</div>', unsafe_allow_html=True)

    # Already submitted?
    if st.session_state.get(submitted_key):
        st.caption("Feedback enviado ✅")
        return

    # Open dislike dialog if flag is set
    if st.session_state.get(open_dialog_key):
        _dislike_dialog(pid, p, base)
        return

    cols = st.columns(2, gap="small")
    with cols[0]:
        if st.button("👍 Gostei", key=f"like_{base}", use_container_width=True):
            # clear any leftover dialog flag just in case
            st.session_state.pop(open_dialog_key, None)
            _persist_feedback(pid, "Gostei", p, details=None)
            st.session_state[submitted_key] = True
            return
    with cols[1]:
        if st.button("👎 Não gostei", key=f"dislike_{base}", use_container_width=True):
            st.session_state[open_dialog_key] = True
            st.rerun()
            return


# Render grouped products in rows with category headers

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
