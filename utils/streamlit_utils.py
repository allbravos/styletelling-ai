# utils/streamlit_utils.py
from collections import OrderedDict
from typing import Dict, List, Any
from io import BytesIO
import streamlit as st
import uuid
import requests
from PIL import Image, ImageDraw, ImageFont

from config.config import MAX_PRODUCTS


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
                "image_file": p.get("image_file"),
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


def reset_session_for_run(q: str):
    st.session_state.session_id = str(uuid.uuid4())  # keep if used elsewhere
    st.session_state.last_query = q
    st.session_state.logs = ["### Processando sua solicitação."]
    st.session_state.products = {}
    st.session_state.result_set_id = None

    _prefixes = (
        "submitted_", "need_comment_", "details_", "error_",
        "like_", "dislike_", "confirm_", "cancel_",
        "d_", "d_send_", "d_cancel_",
        "open_dialog_",
    )
    keys_to_clear = [k for k in list(st.session_state.keys()) if k.startswith(_prefixes)]
    for k in keys_to_clear:
        st.session_state.pop(k, None)

    st.session_state.pop("_card_occurrence_counter", None)


@st.cache_data(show_spinner=False, ttl=3600)
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


def inject_discreet_link_css_once():
    """Style popover trigger to look like a subtle text link."""
    flag = "_desc_link_css_v1"
    if not st.session_state.get(flag):
        st.markdown(
            """
            <style>
              .desc-trigger button {
                background: none !important;
                border: none !important;
                padding: 0 !important;
                margin: 2px 0 0 0 !important;
                text-decoration: underline;
                font-size: 0.85rem;
                opacity: 0.7;
              }
              .desc-trigger button:hover {
                opacity: 1;
                text-decoration: underline;
              }
            </style>
            """,
            unsafe_allow_html=True,
        )
        st.session_state[flag] = True
