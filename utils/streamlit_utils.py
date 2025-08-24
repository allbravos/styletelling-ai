# utils/streamlit_utils.py
from collections import OrderedDict
from typing import Dict, List, Any
from io import BytesIO

import streamlit as st
import requests
from PIL import Image, ImageDraw, ImageFont

# Keep this constant here so the default value in group_products remains identical
MAX_PRODUCTS = 15  # global cap across categories


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
