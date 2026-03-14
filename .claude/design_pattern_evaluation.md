# Design Pattern Evaluation

Assessment of how closely Draft aligns with textbook design across three dimensions.
Evaluated 2026-03-13 on branch `onnx_migration`.

---

## 1. Infrastructure Optimization — 85%

| Pattern | Status |
|---|---|
| Multi-stage Docker build | ✓ |
| CPU-only inference | ✓ |
| Non-root container user (`app`, UID 1000) | ✓ |
| Framework-agnostic inference (ONNX Runtime) | ✓ |
| Model volume separation from image (hostPath mount) | ✓ |
| Helm chart with per-env value overrides | ✓ |
| K8s liveness/readiness probes (`/health`) | ✓ |
| Cold-start init container (index-builder) | ✓ |
| INT8 quantization | not yet |
| Distroless / minimal runtime image | long-term |

**Gap:** INT8 quantization is the one remaining Phase 2 item — documented in `notes/onnxruntime_optimization.md`, not yet applied. Would reduce ONNX model files from ~173 MB to ~46 MB combined and give 3–4× CPU speedup over FP32 PyTorch.

---

## 2. MCP Engineering Pattern — 90%

| Pattern | Status |
|---|---|
| Retrieval-first: `retrieve_chunks` primary, `query_docs` for non-LLM only | ✓ |
| Transport duality: stdio (local/trusted) + Streamable HTTP (remote/auth) | ✓ |
| Auth at transport layer, not tool layer (`BearerTokenMiddleware`) | ✓ |
| Direct `lib/` import — no internal HTTP round-trip to UI server | ✓ |
| Typed tool signatures + structured error types (`IndexNotReady`, etc.) | ✓ |
| Health endpoint for K8s probes (`/health` → `llm_ready`, `index_ready`) | ✓ |
| OTel span per tool call (`mcp.tool.<name>`) with `request_id` | ✓ |
| Resource URIs (`draft://sources`, `draft://doc/`) + `answer_from_docs` prompt | ✓ |
| Read-only MCP surface (admin ops CLI/UI only) | ✓ |
| Rate limiting on HTTP transport | missing |

The key design decision — `retrieve_chunks` returns raw chunks for the client LLM to synthesize rather than calling `query_docs` which would double-infer — is precisely what the MCP spec intends and what most implementations miss.

**Gap:** No rate limiting on the HTTP transport. Textbook production MCP would throttle per-token or per-IP.

---

## 3. RAG Design and Implementation — 75%

| Pattern | Status |
|---|---|
| Two-stage retrieval: bi-encoder (embed) → cross-encoder (rerank) | ✓ |
| AST-based Python chunking (not regex) | ✓ |
| Source-line metadata for code citations (`start_line`, `end_line` in Chroma) | ✓ |
| Strict context-only system prompt | ✓ |
| Streamed LLM response (SSE) | ✓ |
| Provider-agnostic LLM (Ollama / Claude / Gemini / OpenAI / unified endpoint) | ✓ |
| `.env` as source of truth for all model config (embed + rerank) | ✓ |
| OTel spans for retrieval / rerank / generation with latency metrics | ✓ |
| Hybrid retrieval (vector + BM25 fusion) | missing |
| Incremental index updates | missing |
| Heading text prepended to chunk embedding input | missing |
| Chunk overlap for Python (code) | partial |

**Primary gap:** Hybrid retrieval. Draft has both ChromaDB (vector) and Whoosh (FTS) but they run in separate code paths — `retrieve_chunks` is vector-only, `search_docs` is FTS-only. Textbook RAG fuses both at retrieval time (reciprocal rank fusion or score normalization) then reranks the merged set. This significantly improves recall on exact-match queries (function names, error codes, config keys) where vector similarity underperforms.

**Secondary gaps:**
- Full index rebuild on every run — acceptable for small private doc sets but not production scale.
- Heading not prepended to chunk text before embedding — reduces retrieval quality when queries match section titles rather than body content.

---

## Summary

```
Infrastructure:  ████████░░  85%  — ONNX done; INT8 quantization remaining
MCP pattern:     █████████░  90%  — textbook architecture; rate limiting missing
RAG:             ███████░░░  75%  — core solid; hybrid retrieval is the key gap
```

The MCP layer is the strongest dimension — the retrieval-first design and transport/auth layering match the spec intent closely. Infrastructure is well-optimized with the ONNX migration complete. RAG is functional and well-instrumented; the Whoosh+ChromaDB split being unmerged is the clearest distance from a textbook production design.

### Priority order for closing gaps

1. **Hybrid retrieval** (RAG) — fuse Whoosh BM25 + Chroma vector at `retrieve()` before reranking; highest impact on answer quality
2. **INT8 quantization** (infra) — `onnxruntime.quantization.quantize_dynamic`; straightforward, ~4× CPU speedup
3. **Rate limiting** (MCP) — middleware on the Starlette app; low effort, production necessity
4. **Heading prepend** (RAG) — prepend `heading + "\n"` to chunk text before embedding; one-line change in ingest, requires index rebuild
