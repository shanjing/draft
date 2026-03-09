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

### MCP HTTP integration (test_mcp.py)

**test_mcp.py** — Integration tests for the MCP server’s Streamable HTTP transport. The MCP server must be running (e.g. `python scripts/serve_mcp.py`) and **DRAFT_MCP_TOKEN** must be set in the repo root **`.env`** (same as: `TOKEN=$(grep DRAFT_MCP_TOKEN .env | cut -d= -f2)` for curl). Optional: set **MCP_BASE_URL** (default `http://127.0.0.1:8059`) to point at another host/port.

```bash
# Run all MCP integration tests (from repo root, with venv activated)
source .venv/bin/activate
pytest tests/test_mcp.py -v

# Or only MCP tests when running full suite
pytest tests/test_mcp.py -v -m integration
```

If the server is not running, tool tests are skipped with a “not reachable” message. Auth and health tests still run if the server is up.

| Test | Description | Expected |
|------|-------------|----------|
| **test_mcp_list_sources** | POST `tools/call` **list_sources** (no arguments) | **200**; JSON-RPC `result.content[0].text` = JSON array of `{name, source, url?, doc_count?}` |
| **test_mcp_retrieve_chunks** | POST `tools/call` **retrieve_chunks** (`query`, `top_k`, `rerank`) | **200**; JSON-RPC `result.content[0].text` = JSON array of chunk objects (`repo`, `path`, `heading`, `text`, `score`, …) |
| **test_mcp_auth_no_token_returns_401** | POST `/mcp` with no `Authorization` header | **401** |
| **test_mcp_auth_wrong_token_returns_401** | POST `/mcp` with `Authorization: Bearer wrong-token` | **401** |
| **test_mcp_health_unauthenticated** | GET `/health` (no auth) | **200**; JSON `{ "status": "ok", "llm_ready": bool, "index_ready": bool, "version": "1.0" }` |
| **test_mcp_search_docs** | POST `tools/call` **search_docs** (`query`, `limit`) | **200**; JSON-RPC result with content (Whoosh full-text search) |
| **test_mcp_list_documents_requires_repo** | POST `tools/call` **list_documents** (`repo`) | **200**; JSON-RPC `result` or `error` (e.g. repo not in sources) |

**Equivalent curl examples (for manual checks):**

1. **list_sources**
   ```bash
   TOKEN=$(grep DRAFT_MCP_TOKEN .env | cut -d= -f2)
   curl -s -X POST http://localhost:8059/mcp \
     -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_sources","arguments":{}}}' | python -m json.tool
   ```
   Expected: `"result": { "content": [ { "type": "text", "text": "[{\"name\": ...}]" } ], "isError": false }`

2. **retrieve_chunks**
   ```bash
   curl -s -X POST http://localhost:8059/mcp \
     -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"retrieve_chunks","arguments":{"query":"RAG pipeline chunking strategy","top_k":3,"rerank":true}}}' | python -m json.tool
   ```
   Expected: `"result": { "content": [ { "type": "text", "text": "[{\"repo\": ..., \"path\": ..., ...}]" } ], "isError": false }` (or SSE; last `data:` line is the JSON-RPC response).

3. **Auth rejection (401)**
   ```bash
   curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8059/mcp -H "Content-Type: application/json" -d '{}'
   # → 401
   curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8059/mcp -H "Authorization: Bearer wrong-token" -H "Content-Type: application/json" -d '{}'
   # → 401
   ```

Tool tests (list_sources, retrieve_chunks, search_docs, list_documents) require a properly configured server: **sources.yaml** in DRAFT_HOME, and for **retrieve_chunks** a built vector index (`python scripts/index_for_ai.py --profile quick`). If the server returns 500 (e.g. missing config or index), the test fails; fix the server environment and re-run.

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
