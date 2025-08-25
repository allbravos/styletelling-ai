# streamlit_client.py
from typing import Iterator, Dict, Any

# DATA_MODE: "real" streams from backend, "mock" replays a saved fixture.
# RECORD_FIXTURES: if True in real mode, save latest payload to disk (creates the mocks based on real data)
DATA_MODE: str = "real"         # "real" or "mock"
RECORD_FIXTURES: bool = False
RECORD_CACHE: bool = True


def stream_user_query(user_query: str) -> Iterator[Dict[str, Any]]:
    """
    Main interface between the UI and the data source.
    It yields events that drive the Streamlit front-end:
      - {"status": "progress", "message": str}
      - {"status": "context_result", ...}
      - {"status": "intermediate_result", ...}
      - {"status": "final_result", "data": <grouped_products_dict>}
      - {"status": "final_message", "message": str}

    In mock mode, this bypasses any backend calls and simply loads the
    fixture from data/products_fixture.json (or a built-in sample if missing).
    In real mode, it delegates to the actual streaming generator.
    """
    if DATA_MODE.lower() == "mock":
        from data.record_fixtures import load_fixture

        snap = load_fixture()
        yield {"status": "progress", "message": "(mock) carregando fixture"}
        yield {"status": "final_result", "data": snap.get("data", {})}
        yield {"status": "final_message", "message": "(mock) concluído"}
        return

    # Real mode: forward events from the actual pipeline
    from run_user_query import process_user_query_streaming
    for step in process_user_query_streaming(user_query):
        yield step
