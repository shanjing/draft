## Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

- **test_ask.py**: Ask API (POST /api/ask, SSE stream), LLM status.
- **test_search.py**: Search API, tree (includes vault).
- **test_components.py**: Chunking, ingest (build_index), ai_engine (retrieve, _env_strip).
- **tests/test_ask_curl.sh**: Manual curl test against a running server; run with `bash tests/test_ask_curl.sh [BASE_URL]`.

Integration test against a live server: `pytest tests/test_integration_curl.py -m integration` (server must be running on 8058).
