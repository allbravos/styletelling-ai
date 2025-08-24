# streamlit_client.py
from typing import Iterator, Dict, Any

def stream_user_query(user_query: str) -> Iterator[Dict[str, Any]]:
    """
    Thin wrapper around your existing streaming pipeline that yields dicts.
    Expected events include: progress, context_result, intermediate_result,
    final_result, and final_message. Adjust import below to match your codebase.
    """
    from run_user_query import process_user_query_streaming  # adjust if needed
    for step in process_user_query_streaming(user_query):
        yield step
