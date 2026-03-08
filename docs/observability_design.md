# Observability Design (Draft)

This document is the **main observability reference** for Draft. It defines how pipeline signals, LLM metrics, and audit logs work together. RAG and MCP observability are summarized in [RAG_design.md](RAG_design.md) and [MCP_design.md](MCP_design.md) respectively; this doc is the source of truth for detail.

---

## Design principles

Draft is an LLM application (RAG + MCP) typically deployed as a single container or on a single host. The operationally interesting questions are all at the LLM and pipeline layer — not the infrastructure layer. Infrastructure monitoring (CPU, memory, uptime) is covered by the host OS or container runtime; the application's job is to expose LLM-level signals.

**Single observability stack: OpenTelemetry.** OTel covers all three pillars:

| Layer | Role | Answers |
|-------|------|---------|
| **OTel Metrics** | Quantitative LLM and pipeline signals | *"How is the system performing?"* — token usage, request counts, latency distributions, error rates per stage. |
| **OTel Traces** | Causal pipeline signals | *"Where did this request go wrong and why?"* — request flow, latency breakdown per stage (retrieval, rerank, LLM, tool boundary). |
| **Structured logs** | Audit and debugging | *"What exactly happened in this request?"* — who, what, when, request_id, status, error_type; searchable and correlatable with traces. |

**Why not Prometheus/Grafana as a separate layer?** Prometheus is a valid OTel metrics export *target*, not a separate stack. If a Prometheus scrape endpoint is ever needed (e.g. for an existing SRE stack), the OTel Prometheus exporter adds it without changing instrumentation. Using `prometheus_client` directly would lock instrumentation to one backend; the OTel Metrics SDK keeps it portable.

**Why not infrastructure monitoring in the app?** For a single-process deployment, CPU/memory/uptime are observable from the host without application instrumentation. The health endpoint (`GET /health`) covers operational liveness checks.

**Exporter strategy:** Console exporter by default (no OTLP endpoint). Metrics default to `~/.draft/otel_metrics.log` (or `$DRAFT_HOME/otel_metrics.log`); set `DRAFT_OTEL_METRICS_LOG=stdout` for terminal output. Spans go to stdout unless OTLP is used. Switch to OTLP for any production backend (Grafana Cloud, Honeycomb, Datadog, self-hosted Jaeger/Tempo) by setting `OTEL_EXPORTER_OTLP_ENDPOINT` — no instrumentation changes required.

**GenAI semantic conventions:** Use OTel GenAI semconv (`gen_ai.*` attribute names) from the start. This ensures compatibility with off-the-shelf GenAI dashboards and avoids a custom-to-standard migration later.

---

## Scope in Draft

- **RAG:** The pipeline (retrieve → rerank → generate) is the primary instrumentation target. Every RAG call — from UI, MCP, or CLI — produces the same metrics and traces. This is where the LLM-level signals live.
- **MCP:** Tool calls are instrumented at the boundary (request_id, tool name, transport). When the tool is `query_docs`, RAG child spans and metrics appear under the tool span via OTel context propagation.
- **Health endpoint:** `GET /health` → `{"status": "ok", "llm_ready": true, "index_ready": true, "version": "..."}`. Used by Docker `HEALTHCHECK` and simple liveness checks. Independent of the OTel stack.

---

## OTel setup: `lib/otel.py`

Single module that configures both the TracerProvider and MeterProvider. OTel is **optional**: when the SDK is installed and configured at process start, real providers are used; otherwise no-op. No hard dependency in lib for core RAG to run.

**Contents:**
- `configure_otel(service_name, otlp_endpoint=None)` — initializes TracerProvider and MeterProvider. If `otlp_endpoint` is set (or `OTEL_EXPORTER_OTLP_ENDPOINT` env var), uses OTLP exporter; otherwise uses console exporter. Console metrics default to `~/.draft/otel_metrics.log` (or `$DRAFT_HOME/otel_metrics.log`); set `DRAFT_OTEL_METRICS_LOG=stdout` for stdout, or a path. On `ImportError` (SDK not installed): no-op.
- `shutdown_otel()` — force_flush and shutdown the global TracerProvider and MeterProvider so the final metric batch is exported on exit. Entry points call it in cleanup (lifespan shutdown, finally, atexit).
- `get_tracer(name, version)` — returns real tracer if configured, else no-op tracer.
- `get_meter(name, version)` — returns real meter if configured, else no-op meter.
- No-op implementations (`_NoopTracer`, `_NoopSpan`, `_NoopMeter`, etc.) so call sites need no `if otel_enabled` guards.

**Who calls `configure_otel` and `shutdown_otel`:** UI (`ui/app.py` lifespan), CLI (`scripts/ask.py`), and MCP server (`scripts/serve_mcp.py`) call `configure_otel()` at startup **by default** (service name from `OTEL_SERVICE_NAME` or a default per entry point). They call `shutdown_otel()` on exit (lifespan after yield, `finally` in ask.py, `atexit` in serve_mcp.py). Tests run the no-op path unless they explicitly call `configure_otel`.

---

## Application of OTel: RAG metrics (Phase 1)

**Where:** `lib/ai_engine.py` via `lib/otel.py`. Metrics are defined once and recorded when `ask_stream` completes each stage.

**Metric instruments** (OTel Metrics SDK, GenAI semconv where applicable):

| Instrument | Name | Type | Key attributes |
|------------|------|------|----------------|
| LLM token usage | `gen_ai.client.token.usage` | Histogram | `gen_ai.system`, `gen_ai.request.model`, `gen_ai.token.type` (input\|output) |
| LLM operation latency | `gen_ai.client.operation.duration` | Histogram | `gen_ai.system`, `gen_ai.request.model`, `gen_ai.operation.name` (chat\|embeddings) |
| Retrieval latency | `rag.retrieval.duration` | Histogram | `rag.embed_model`, `rag.top_k` |
| Rerank latency | `rag.rerank.duration` | Histogram | `rag.reranker_model` |
| RAG request count | `rag.requests` | Counter | `status` (ok\|error), `error_type` |
| Chunks retrieved | `rag.chunks.retrieved` | Histogram | — |

**`lib/metrics.py` (new):** Defines all instruments using `get_meter()` from `lib/otel.py`. Exposes thin record functions:
- `record_rag_request(status, error_type=None)` — overall RAG request duration is in `gen_ai.client.operation.duration`, not in this counter.
- `record_retrieval(duration_sec, embed_model, top_k, chunk_count)`
- `record_rerank(duration_sec, reranker_model)`
- `record_llm_tokens(input_tokens, output_tokens, system, model)` — defined but **not yet called**; deferred until streaming providers expose token counts (see below).
- `record_llm_duration(duration_sec, system, model, operation)`

This is the **single source of truth** for what we expose and what SLIs are built from. If `opentelemetry-sdk` is not installed, all record functions are no-ops via `get_meter()`.

**SLIs documented in `lib/metrics.py`:**
- RAG availability: `rate(rag.requests{status="ok"}) / rate(rag.requests)`
- RAG p99 latency: histogram quantile on `gen_ai.client.operation.duration`
- Token consumption trend: sum of `gen_ai.client.token.usage` over time — **deferred.** Instrument exists but `record_llm_tokens` is not called; streaming responses do not surface token counts from all providers. To make this SLI operational, add provider-specific handling (e.g. Anthropic `stream.get_final_message().usage`, OpenAI `stream.usage`) or document as future work.

---

## Application of OTel: RAG traces (Phase 2)

**Where:** `lib/ai_engine.py`, same entry point as metrics.

**Spans:**

- One parent span `rag.ask` for the full RAG call.
- Child spans:
  - `rag.retrieval` — query to top-k chunks. Attributes: `rag.embed_model`, `rag.top_k`, `rag.chunk_count`.
  - `rag.rerank` — cross-encoder rerank. Attributes: `rag.reranker_model`, `rag.chunk_count`.
  - `rag.generation` — build context, call LLM, stream response. Attributes: `gen_ai.system`, `gen_ai.request.model`, `gen_ai.response.model`.

**Generator span lifecycle:** The `rag.generation` span must close even if the consumer disconnects mid-stream. Use `try/finally` inside the generator:

```python
with tracer.start_as_current_span("rag.generation") as span:
    try:
        for chunk in llm_stream():
            yield chunk
    except GeneratorExit:
        span.set_status(StatusCode.ERROR, "client_disconnected")
        raise
    finally:
        pass  # span closes via context manager __exit__
```

**Span naming:** Use fixed span names (`rag.retrieval`, `mcp.tool`) — not dynamic names like `mcp.tool.{tool_name}`. Put the variable value in an attribute (`mcp.tool = "query_docs"`). Dynamic span names fragment traces in backends that group by name.

**On exception:** Record on span (`span.record_exception(e)`), set status ERROR, do not swallow.

---

## Application of OTel: MCP (Phase 3)

**Status:** Instrumentation is built and wired (`mcp/instrumentation.py`, `lib/metrics.py` MCP instruments, `serve_mcp.py` startup). The MCP server itself is currently a stub: `serve_mcp.py` exits when `mcp.server` is not importable, so Phase 3 is **wired but inactive** until a real MCP server exists. HTTP request ID propagation (middleware setting `request_id_var` from `Mcp-Session-Id`) is tracked as TODO for when the HTTP server is implemented.

**Where:** `mcp/` — single instrumentation point in the tool dispatcher (`mcp/instrumentation.py`). Every tool call is wrapped once; no per-tool decorators.

**Metrics and spans per tool call:**

- Metrics: `mcp.tool.calls` counter (`tool`, `transport`, `status`), `mcp.tool.duration` histogram (`tool`). Recorded in `lib/metrics.py` alongside RAG metrics.
- One span per tool call: `mcp.tool`. Attributes: `mcp.tool` (name), `request_id`, `mcp.transport` (http\|stdio).
- When the tool is `query_docs`: OTel context propagates so `rag.ask` and children attach under the `mcp.tool` span.

**Request ID propagation:**

- `contextvars.ContextVar` set at request start.
- HTTP: set from `Mcp-Session-Id` header in middleware (or generate UUID).
- Stdio: generate UUID when the request is received.
- Dispatcher reads context var when starting the span and emitting the structured log line.

**Structured logs (MCP):**

- One JSON log line per tool call: `ts`, `request_id`, `tool`, `transport`, `duration_ms`, `status`, `message`; on error add `error_type`.
- Format: JSON lines when `--log-json` or `MCP_LOG_JSON=1` (flag takes precedence over env); plain text otherwise.
- `lib/log.py`: add `configure_json(level)` and a minimal JSON formatter. No new dependency.

**Startup:** `serve_mcp.py` calls `configure_json()` when `--log-json`; calls `configure_otel(service_name=...)` at startup by default and registers `shutdown_otel` with `atexit`.

---

## Implementation plan

### Dependencies

Optional OTel (e.g. `requirements-otel.txt`):
```
opentelemetry-api
opentelemetry-sdk
opentelemetry-exporter-otlp-proto-http
```
Core Draft and all tests run **without** these installed.

### Phase 1 — RAG metrics

1. `lib/otel.py`: no-op tracer + meter, `get_tracer()`, `get_meter()`, `configure_otel()` (console exporter default, OTLP when env set).
2. `lib/metrics.py`: all metric instruments (GenAI semconv + RAG custom); thin record functions; SLI documentation.
3. `lib/ai_engine.py`: call record functions at end of each stage in `ask_stream`.
4. `ui/app.py`, `scripts/ask.py`, `scripts/serve_mcp.py`: call `configure_otel` at startup by default; call `shutdown_otel` on exit (lifespan, finally, atexit).

### Phase 2 — RAG traces

1. `lib/ai_engine.py`: wrap `ask_stream` in `rag.ask` parent span + `rag.retrieval`, `rag.rerank`, `rag.generation` child spans; handle generator lifecycle; record exceptions.
2. No new files; uses `lib/otel.py` already in place.

### Phase 3 — MCP

1. `mcp/instrumentation.py`: request_id context var, dispatcher wraps each tool call with span + metrics + structured log line.
2. `lib/metrics.py`: add MCP metric instruments.
3. `lib/log.py`: `configure_json()` and JSON formatter.
4. `serve_mcp.py`: call `configure_json` and `configure_otel` at startup.

### File and change summary

| Item | Action |
|------|--------|
| requirements-otel.txt | New: optional OTel + OTLP exporter deps. |
| lib/otel.py | No-op tracer + meter, `get_tracer()`, `get_meter()`, `configure_otel()`, `shutdown_otel()`. Console metrics default to `otel_metrics.log` under DRAFT_HOME. |
| lib/metrics.py | New: all metric instruments (GenAI semconv), record functions, SLI docs. |
| lib/ai_engine.py | Phase 1: record metrics per stage. Phase 2: add spans. |
| lib/log.py | Phase 3: `configure_json()` and JSON formatter. |
| ui/app.py, scripts/ask.py, scripts/serve_mcp.py | Call `configure_otel` at startup by default; call `shutdown_otel` on exit. |
| mcp/instrumentation.py | Phase 3: request_id var, dispatcher wrap (span + metrics + log). |
| mcp/serve_mcp.py | Phase 3: `configure_json`, `configure_otel` at startup, `atexit.register(shutdown_otel)`. |

### Verification

- **Without OTel installed:** all paths run unchanged (no-op). No test changes needed.
- **With OTel, console exporter:** `ask_stream` emits metrics (default: `~/.draft/otel_metrics.log`) and a trace with `rag.ask → rag.retrieval, rag.rerank, rag.generation` (spans to stdout unless OTLP). With the SDK installed, run `scripts/ask.py` or the UI; no env var required for OTel to run.
- **With OTLP:** set `OTEL_EXPORTER_OTLP_ENDPOINT`; same instrumentation routes to any backend.
- **Generator disconnect:** verify `rag.generation` span closes on `GeneratorExit` (simulate by disconnecting SSE client mid-stream).

---

## Summary

| Question | Signal | Layer |
|----------|--------|-------|
| Is the system healthy? | `GET /health` endpoint | Operational (host/container) |
| How is the system performing? | OTel Metrics (GenAI semconv) | LLM + pipeline |
| Where did this request go wrong and why? | OTel Traces (`rag.*`, `mcp.tool`) | Pipeline |
| What exactly happened in this request? | Structured logs (JSON, request_id) | MCP tool calls; RAG on demand |

Prometheus/Grafana are not a separate layer. If a Prometheus scrape endpoint is needed, add the OTel Prometheus exporter — instrumentation is unchanged. The OTel OTLP exporter routes to any backend (Grafana Cloud, Honeycomb, Datadog, Jaeger) via config, not code changes.
