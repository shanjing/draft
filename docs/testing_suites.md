## Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

- **test_ask.py** — Ask API (**POST /api/ask**, SSE stream), LLM status.
- **test_search.py** — Search API, tree (includes vault).
- **test_components.py** — Chunking, ingest (**build_index**), **ai_engine** (**retrieve**, **_env_strip**).
- **test_otel.py** — OpenTelemetry (OTel): **lib/otel.py** (no-op tracer/meter, `get_tracer`/`get_meter`, `configure_otel`), **lib/metrics.py** (all `record_*` functions), **mcp/instrumentation.py** (`instrument_tool_call`, `request_id_var`), and **ai_engine** (ask_stream with OTel no-op path). All tests run without the opentelemetry-sdk installed. One test builds the RAG index and is marked `slow`; skip with **`pytest tests/test_otel.py -m 'not slow'`** for a fast run.
- **test_ask_curl.sh** — Manual curl test against a running server; run with **`bash tests/test_ask_curl.sh [BASE_URL]`**.

Integration test against a live server: **`pytest tests/test_integration_curl.py -m integration`** (server must be running on 8058).

### Pipeline test (4 model pairs)

**test_pipeline.py** — Standalone CLI to build the RAG index from **sources.yaml** and run retrieval. Supports 4 model pairs via `-p`/`--pair`:

| Pair | Embed | Reranker | Notes |
|------|-------|----------|-------|
| default/d | sentence-transformers (profile) | ms-marco-MiniLM-L-6-v2 | Hugging Face |
| G (Gold) | qwen3-embedding:8b | Qwen3-Reranker-0.6B | Ollama, best balance |
| L | qwen3-embedding:8b | Qwen3-Reranker-8B | Ollama, highest quality |
| S | qwen3-embedding:0.6b | Qwen3-Reranker-0.6B | Ollama, fastest |

```bash
# Full pipeline (default pair = sentence-transformers)
.venv/bin/python tests/test_pipeline.py -q "your question" -v

# Gold pair (Ollama, no HF download)
.venv/bin/python tests/test_pipeline.py -p G -q "your question" -v

# 8B+8B or 0.6B+0.6B
.venv/bin/python tests/test_pipeline.py -p L -q "your question" -v
.venv/bin/python tests/test_pipeline.py -p S -q "your question" -v

# Rebuild index before retrieval
.venv/bin/python tests/test_pipeline.py -p G --rebuild -q "your question" -v

# Deep profile (for default pair)
.venv/bin/python tests/test_pipeline.py -p default --profile deep -v
```

Options: `-p`/`--pair` (default, d, G, L, S), `-q`/`--query`, `--rebuild`, `--profile`, `-v`/`--verbose`. Run from the draft repo root.
