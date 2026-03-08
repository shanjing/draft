# Observability Implementation Review

**Branch:** `feat/OTel_Observability`
**Files reviewed:** `lib/otel.py`, `lib/metrics.py`, `lib/ai_engine.py`, `lib/log.py`, `scripts/ask.py`, `scripts/serve_mcp.py`, `mcp/instrumentation.py`, `ui/app.py`, `requirements-otel.txt`
**Design references:** `docs/observability_design.md`, `docs/OTel_setup_plan.md`

---

## Summary

The implementation covers Phase 1 (RAG metrics) and Phase 2 (RAG traces) correctly at a structural level, and lays the groundwork for Phase 3 (MCP). The no-op pattern is sound, the span lifecycle for the generator is handled correctly, and all three startup entry points wire up `configure_otel`. However, there are several issues — one critical correctness bug, one spec deviation affecting dashboard compatibility, and a set of gaps/inconsistencies to address before the feature is complete.

---

## Issues

### Critical

**1. Stale meter reference in `lib/metrics.py`**

`lib/metrics.py` captures the meter at module import time:

```python
# lib/metrics.py:15
_METER = get_meter("draft", "1.0.0")
```

`get_meter` returns `_noop_meter` when `_meter` is `None` in `lib/otel.py`. Since `metrics.py` is imported at the top of `lib/ai_engine.py` — which is imported well before any startup hook runs — `_METER` will always be the no-op meter, even after `configure_otel()` is called. All the lazy `_get_*` instrument functions (`_get_rag_requests()`, `_get_gen_ai_token_usage()`, etc.) call `_METER.create_counter(...)` using this stale reference, so they create no-op instruments regardless of OTel being configured.

The lazy-initialization pattern solves a different problem (deferred creation) but not this one. The fix is to call `get_meter(...)` inside each `_get_*` helper at first-call time rather than capturing it once at module level.

---

### Spec deviations

**2. `gen_ai.client.operation.duration` uses wrong unit**

The OTel GenAI semantic conventions specify `gen_ai.client.operation.duration` in **seconds** (`s`). The implementation records it in milliseconds:

```python
# lib/metrics.py:74-76
_gen_ai_operation_duration = _histogram(
    "gen_ai.client.operation.duration", "LLM operation duration (GenAI semconv)", "ms"
)
```

Any off-the-shelf GenAI dashboard (Grafana, Honeycomb, etc.) that relies on the semconv unit will show values three orders of magnitude too large. The custom RAG histograms (`rag.retrieval.duration`, `rag.rerank.duration`, `mcp.tool.duration`) using `ms` are fine since they are not semconv-defined, but `gen_ai.client.operation.duration` must be `s`.

**3. `record_rag_request` signature differs from the design**

The design spec (`observability_design.md`, `lib/metrics.py` section) lists the signature as:
```
record_rag_request(duration_sec, status, error_type=None)
```

The implementation omits `duration_sec`:
```python
# lib/metrics.py:94
def record_rag_request(status: str, error_type: str | None = None) -> None:
```

The overall RAG request duration is captured in `gen_ai.client.operation.duration`, but the `rag.requests` counter carries no latency data, making it impossible to compute per-request duration percentiles from that instrument alone. Whether this is intentional or a spec drift should be clarified and the design doc updated if the simpler signature is preferred.

---

### Missing implementations

**4. Token usage (`record_llm_tokens`) is never called**

`record_llm_tokens` is defined in `metrics.py` and listed in Phase 1 of the design, but it is neither imported nor called in `ai_engine.py`:

```python
# lib/ai_engine.py:25-30 — imports from lib.metrics
from lib.metrics import (
    record_llm_duration,
    record_rag_request,
    record_rerank,
    record_retrieval,
)
```

The streaming providers (`_stream_claude`, `_stream_gemini`, `_stream_openai`, `_stream_openai_compatible`) don't surface token counts from their response objects. This means `gen_ai.client.token.usage` — listed as a Phase 1 SLI instrument — emits nothing. Token consumption trend (one of the three documented SLIs) is therefore not operational.

Capturing token counts from streaming responses requires provider-specific handling (e.g. Anthropic's `stream.get_final_message().usage`, OpenAI's `stream.usage`, etc.) or switching to non-streaming calls for the final usage summary. The gap should be acknowledged or the timeline for it updated.

**5. `gen_span.set_attribute("gen_ai.response.model", ...)` is not in `finally`**

```python
# lib/ai_engine.py:495-497
        if not had_error:
            record_rag_request("ok")
        gen_span.set_attribute("gen_ai.response.model", llm_model)
```

This line is after the streaming loop but outside any `finally` block. If `GeneratorExit` is raised (client disconnects mid-stream), the `except GeneratorExit` block sets status ERROR and re-raises; control never reaches line 497. The `gen_ai.response.model` attribute will be absent on any span that closes due to disconnection. It should be moved into the `finally` block or set before the loop begins.

**6. MCP HTTP request ID propagation not implemented**

`mcp/instrumentation.py` defines `request_id_var` and the design specifies that HTTP transport reads from `Mcp-Session-Id` header in middleware. No HTTP middleware exists in `serve_mcp.py` or `mcp/` to set this var. Currently `request_id_var` will always be `None` for HTTP transport. This is deferred to when the MCP server is built, but it should be tracked explicitly.

---

### Structural observations

**7. Dead code: `_noop_span` function in `lib/otel.py`**

```python
# lib/otel.py:11-14
@contextmanager
def _noop_span(*args: Any, **kwargs: Any):
    """No-op span context manager."""
    yield None
```

This function yields `None`, meaning any call site doing `with _noop_span() as span: span.set_attribute(...)` would raise `AttributeError`. It is never called anywhere — `_NoopTracer.start_as_current_span` correctly yields `_NoopSpan()`. The function should be removed to avoid confusion.

**8. Variable ordering in `lib/otel.py`**

`get_tracer` and `get_meter` are defined at lines 63–70 but reference `_tracer` and `_meter` which are declared at lines 73–74. This works in Python (function bodies evaluate lazily) but the forward reference is confusing for readers. Conventional ordering is: globals first, then functions.

**9. `ui/app.py` uses deprecated `@app.on_event("startup")`**

```python
# ui/app.py:253
@app.on_event("startup")
def _startup():
```

FastAPI deprecated `on_event` in version 0.93 in favour of the `lifespan` context manager. The design doc explicitly says "UI (ui/app.py lifespan)". This is a minor drift but aligns with what the design intended and avoids a FastAPI deprecation warning.

**10. `requirements-otel.txt` has no version pins**

The setup plan specifies `>=1.27.0` for all three packages. The shipped file has bare names with no pins:

```
opentelemetry-api
opentelemetry-sdk
opentelemetry-exporter-otlp-proto-http
```

Without minimum version pins, installations on different machines can produce incompatible combinations. At minimum `>=1.27.0` pins should be added to match the plan.

**11. MCP server is a stub; Phase 3 instrumentation is build-only**

`serve_mcp.py` exits immediately when `mcp.server` is not importable. `mcp/instrumentation.py` is complete but has no callers. This is noted in `serve_mcp.py`'s comment, but the phase completion status should be reflected in the design doc (Phase 3 is "wired but inactive").

---

## What is done well

- **No-op path is correct.** `_NoopTracer`, `_NoopSpan`, `_NoopMeter`, `_NoopCounter`, `_NoopHistogram` all have the right methods; call sites need no `if otel_enabled` guards.
- **Generator span lifecycle is handled correctly.** The `rag.generation` span uses `try/except GeneratorExit/finally` precisely as the design requires. The span will close on both normal exhaustion and client disconnect.
- **Span naming follows the design.** Fixed span names (`rag.ask`, `rag.retrieval`, `rag.rerank`, `rag.generation`, `mcp.tool`) with variable values in attributes — consistent with the "no dynamic span names" principle.
- **MCP instrumentation module is well-structured.** `instrument_tool_call` as a single context manager wrapping the tool call, recording metrics, span, and one structured log line in `finally`, is exactly the "single instrumentation point" the design requires.
- **Structured logging in `lib/log.py` is minimal and correct.** `_JsonFormatter` uses a fixed allowlist of extra keys, avoids new dependencies, and `configure_json()` cleanly replaces any existing handlers.
- **All three entry points wire up `configure_otel`.** `ui/app.py`, `scripts/ask.py`, and `scripts/serve_mcp.py` all check the same env vars (`OTEL_SERVICE_NAME`, `DRAFT_OTEL_ENABLED`) and call `configure_otel` — consistent guard across the codebase.
- **Console exporter is the correct default.** Zero-config, visible in dev logs, switches to OTLP with a single env var.

---

## Areas to update

| # | File | Change needed |
|---|------|---------------|
| 1 | `lib/metrics.py` | Fix stale `_METER` capture: call `get_meter(...)` inside each `_get_*` helper, not at module level |
| 2 | `lib/metrics.py` | Change `gen_ai.client.operation.duration` unit from `"ms"` to `"s"`; convert value in `record_llm_duration` |
| 3 | `lib/ai_engine.py` | Implement token capture in streaming providers and call `record_llm_tokens`, or document as deferred |
| 4 | `lib/ai_engine.py` | Move `gen_span.set_attribute("gen_ai.response.model", llm_model)` into the `finally` block |
| 5 | `lib/otel.py` | Remove the unused `_noop_span` function |
| 6 | `lib/otel.py` | Move `_tracer`/`_meter` declarations above the functions that reference them |
| 7 | `ui/app.py` | Replace `@app.on_event("startup")` with FastAPI `lifespan` context manager |
| 8 | `requirements-otel.txt` | Add `>=1.27.0` version pins to match the setup plan |
| 9 | `docs/observability_design.md` | Clarify Phase 3 status (instrumentation built, MCP server stub only); align `record_rag_request` signature with implementation or revert to spec |
| 10 | `mcp/` | Track HTTP request ID propagation (middleware for `Mcp-Session-Id`) as a TODO for when the MCP server is implemented |

---

## Review Pass 1

**Files changed:** `lib/otel.py`, `lib/metrics.py`, `lib/ai_engine.py`, `scripts/ask.py`, `scripts/serve_mcp.py`, `mcp/instrumentation.py`, `ui/app.py`, `requirements-otel.txt`

### Resolved (8 of 10 original issues)

| # | Issue | Status |
|---|-------|--------|
| 1 | Stale `_METER` capture in `metrics.py` | **Fixed.** Module-level `_METER = get_meter(...)` removed. Each `_get_*` helper now calls `get_meter("draft", "1.0.0")` at first use, so instruments are created only after `configure_otel()` has run. |
| 2 | `gen_ai.client.operation.duration` unit `"ms"` | **Fixed.** Unit changed to `"s"`; `record_llm_duration` now passes `duration_sec` directly without the ×1000 conversion. |
| 4 | `gen_span.set_attribute("gen_ai.response.model", ...)` outside `finally` | **Fixed.** Moved into the `finally` block (`ai_engine.py:495–496`), so the attribute is set even on `GeneratorExit`. |
| 5 | Dead code `_noop_span` function in `otel.py` | **Fixed.** Removed. Only the `_NoopSpan` class remains; `contextmanager` is still present and correctly used by `_NoopTracer.start_as_current_span`. |
| 6 | `_tracer`/`_meter` declared after functions that reference them | **Fixed.** Globals now declared at lines 55–56, before `get_tracer`/`get_meter`. |
| 7 | `ui/app.py` uses deprecated `@app.on_event("startup")` | **Fixed.** Replaced with `@asynccontextmanager _lifespan`; `FastAPI(..., lifespan=_lifespan)` used. Matches the design doc's "lifespan" intent. |
| 8 | `requirements-otel.txt` has no version pins | **Fixed.** All three packages now pinned at `>=1.27.0`. |
| 10 | MCP HTTP request ID propagation untracked | **Addressed.** `mcp/instrumentation.py` now carries an explicit TODO: "When MCP HTTP server is implemented, add middleware that sets request_id_var from the Mcp-Session-Id header." |

### Still open → Resolved in Pass 2

**Issue 3 — `record_rag_request` signature vs design spec (doc-only)** — **Fixed.** `docs/observability_design.md` now shows `record_rag_request(status, error_type=None)` and notes that overall RAG duration is in `gen_ai.client.operation.duration`.

**Issue 4 — Token usage (`record_llm_tokens`) still not called** — **Addressed.** Design doc now states that `record_llm_tokens` is defined but not yet called (deferred); the Token consumption SLI paragraph explicitly marks it deferred and describes what is needed to make it operational. `lib/metrics.py` has a comment above `record_llm_tokens` that it is not called from ai_engine and deferred until streaming providers surface token counts.

---

## Review Pass 2

**Files changed:** `docs/observability_design.md`, `lib/metrics.py`

### Resolved (remaining 2 of 10)

| # | Issue | Status |
|---|-------|--------|
| 3 | `record_rag_request` signature in design doc | **Fixed.** Design doc signature and list updated to match implementation; note added that duration is in `gen_ai.client.operation.duration`. |
| 4 | Token usage not called; SLI appears present | **Addressed.** Design doc: `record_rag_request` and `record_llm_tokens` clarified; Token consumption SLI marked deferred with explanation. Code: comment above `record_llm_tokens` in `lib/metrics.py` states it is not yet called and deferred. |

All items in the "Areas to update" table are now addressed. No open issues remain.

---

## Review Pass 3 — Independent verification

**Verification method:** Fresh read of each changed file against each claimed fix. No code changes made.

| # | Issue | Verified in code |
|---|-------|-----------------|
| 1 | Stale `_METER` capture | ✅ No module-level `_METER`. Every `_get_*` helper calls `get_meter("draft", "1.0.0")` inside the `if … is None` guard. |
| 2 | `gen_ai.client.operation.duration` unit | ✅ `unit="s"` at `lib/metrics.py:84`. `record_llm_duration` passes `duration_sec` directly with no ×1000 conversion. |
| 3 | `record_rag_request` signature in design doc | ✅ `docs/observability_design.md` shows `record_rag_request(status, error_type=None)` with note that duration lives in `gen_ai.client.operation.duration`. |
| 4 | Token usage deferred | ✅ `lib/metrics.py:129` comment: "Not yet called from ai_engine: streaming providers do not surface token counts. Deferred until provider-specific handling exists." Design doc marks Token consumption SLI as deferred with explanation. |
| 5 | `gen_ai.response.model` outside `finally` | ✅ `lib/ai_engine.py:498` (`gen_span.set_attribute("gen_ai.response.model", llm_model)`) is inside the `finally` block that starts at line 495. |
| 6 | MCP request ID propagation | ✅ `mcp/instrumentation.py:10–11` carries the explicit TODO: "When MCP HTTP server is implemented, add middleware that sets request_id_var from the Mcp-Session-Id header." |
| 7 | Dead `_noop_span` function | ✅ Removed. `lib/otel.py` contains only `_NoopSpan` class, `_NoopTracer`, `_NoopMeter`, `_NoopCounter`, `_NoopHistogram`. No `_noop_span` contextmanager. |
| 8 | `_tracer`/`_meter` declared after functions | ✅ Globals at `lib/otel.py:61–62`, before `get_tracer` (line 72) and `get_meter` (line 77). |
| 9 | Deprecated `@app.on_event("startup")` | ✅ `ui/app.py:252` uses `@asynccontextmanager async def _lifespan(app: FastAPI)`. `FastAPI(lifespan=_lifespan)` at line 265. No `on_event` anywhere. |
| 10 | Missing version pins | ✅ `requirements-otel.txt`: all three packages at `>=1.27.0`. |

**Result:** All 10 issues confirmed resolved in live code. No new issues found.
