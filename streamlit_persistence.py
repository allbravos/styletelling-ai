# streamlit_persistence.py
import os
from typing import Optional
from utils.database_utils import connect_to_db  # Use centralized connection

_SCHEMA = """
CREATE TABLE IF NOT EXISTS product_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_query TEXT,
    product_id TEXT,
    product_name TEXT,
    category TEXT,
    rating TEXT,
    details TEXT,
    session_id TEXT
);
"""

def _connect():
    """Use centralized connection with additional SQLite optimizations."""
    conn = connect_to_db()
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def ensure_tables() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)

def save_feedback(*, user_query: str, product_id: str, product_name: str, category: str, rating: str, details: Optional[str], session_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO product_feedback
               (user_query, product_id, product_name, category, rating, details, session_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_query, product_id, product_name, category, rating, details, session_id),
        )