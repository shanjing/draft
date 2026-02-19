# Engineering: Infrastructure Design for a Multi-Agent LLM System

This document covers the architecture and infrastructure decisions behind MarginCall — a multi-agent stock research system built on Google ADK (Agent Development Kit).

The engineering reflects an SRE/cloud architect's perspective: LLM calls are treated as metered, unreliable external dependencies — the same way you'd treat a database or third-party API at scale. Every design decision here maps to a core infrastructure concern: **cost control, observability, resilience, data fidelity, and horizontal scalability.**

---

## 1. Architecture

Supervisor → sequential pipeline → agent-as-tool nesting:

```
    ┌─────────────────────────────────────────────────────────┐
    │ stock_analyst (root)                                    │
    │ tools: stock_analysis_pipeline, invalidate_cache        │
    └───────────────────────────┬─────────────────────────────┘
                                │
                                v
    ┌─────────────────────────────────────────────────────────┐
    │ stock_analysis_pipeline (sequential)                    │
    └───────────────────────────┬─────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        v                       v                       v
    ┌───────────────┐     ┌───────────────┐     ┌──────────────┐
    │stock_data_    │ ──> │report_        │ ──> │ presenter    │
    │collector      │     │synthesizer    │     │ (no tools)   │
    │               │     │ (no tools)    │     └──────────────┘
    │ 9 function    │     │               │
    │ tools +       │     └───────────────┘
    │ AgentTool(    │
    │ news_fetcher) │
    └───────┬───────┘
            │
            v
    ┌───────────────┐
    │ news_fetcher  │
    │ google_search │
    │ | brave_search│
    └───────────────┘
```

**Why this pattern:**

- **Isolation of concerns** — Each agent has a single responsibility. `stock_data_collector` fetches; `report_synthesizer` analyzes; `presenter` formats. A failure in one stage doesn't corrupt the others.
- **Independent replaceability** — Swap `news_fetcher` from Google Search to Brave Search by changing one env var. The pipeline doesn't know or care.
- **Data flow via `session.state` and `output_key`** — Agents communicate through a shared state dict, not direct calls. This is the same decoupling pattern as message queues in distributed systems — producers and consumers don't need to know about each other.
- **Agent-as-tool** — The entire pipeline is wrapped as an `AgentTool` in the root agent's toolbox. The root agent decides *when* to invoke the pipeline (research queries) vs. handle directly (chat, cache stats). This is routing, not orchestration.

---

## 2. Cost Engineering — LLM as a Metered Resource

LLM API calls are the most expensive dependency in this system. At scale, uncontrolled token usage is the equivalent of unoptimized database queries — it will bankrupt you before you notice.

### 3-Tier Cache

Cache TTLs map to **data volatility**, not arbitrary intervals:

| Tier | TTL | Data type | Rationale |
|------|-----|-----------|-----------|
| `TTL_REALTIME` | 15 min | Stock price | Changes every minute during market hours |
| `TTL_INTRADAY` | 4 hours | VIX, sentiment, Reddit, CNN Fear & Greed | Shifts throughout the day but not per-minute |
| `TTL_DAILY` | 24 hours | Financials, technicals, earnings dates | Quarterly data, doesn't change intraday |

Expected cache hit rate: **80%+** for repeat queries within a session. Each cache hit avoids both the external API call (yfinance, Reddit) AND the downstream LLM processing of that data.

### Token Budget Management

Every tool output passes through a truncation pipeline before reaching the LLM:

```
Tool output → Pydantic field validators (per-field byte caps)
           → truncate_strings_for_llm() (recursive, replaces oversized strings)
           → base64 stripping (charts stored in cache, metadata-only to LLM)
           → LLM receives lean payload
```

- **`MAX_STRING_BYTES = 2000`** per field — A Reddit post body doesn't need 70KB of newlines in the LLM context.
- **`SNIPPET_MAX_BYTES = 500`** for Reddit snippets — Enough for the LLM to understand sentiment, not enough to blow the token budget.
- **Context variable tracking** — Each tool run sets a `truncation_occurred` flag so the return value can signal that content was shortened. The LLM knows data was truncated and doesn't hallucinate missing sections.

### The TPM Bloat Incident

Early in development, `fetch_technicals_with_chart` returned **200-400KB of base64-encoded chart images** to the LLM. This data was sent twice: once as the tool response, once in `session.state` for the next agent. Total input per run: **300-500KB** (~125K tokens).

The fix: cache the full payload (with base64) for the frontend API, but return a **stripped copy** to the agent with metadata only. The report synthesizer needs "RSI 33.8, bearish MACD" — not chart pixels.

| Metric | Before | After |
|--------|--------|-------|
| Chart data to LLM | ~200-400KB base64 | 0 (metadata only) |
| Total stock_data size | ~300-500KB | ~20-50KB |
| Token cost per run | ~125K+ input tokens | ~15-30K input tokens |

Full write-up: [docs/how-to-prevent-datasets-bloat-llm-deep-dive-part1.md](docs/how-to-prevent-datasets-bloat-llm-deep-dive-part1.md)

---

## 3. Schema Contracts — Data Fidelity at Agent Boundaries

### Two-Layer Schema Architecture

```
External APIs → tool functions → tool_schemas.py (raw data contracts)
                                        ↓
                              session.state (validated data)
                                        ↓
                              report_synthesizer → schemas.py (LLM output contracts)
                                        ↓
                              Structured StockReport (validated)
```

| Layer | File | Purpose |
|-------|------|---------|
| Tool schemas | `agent_tools/tool_schemas.py` | What tool functions return — raw data from yfinance, Reddit, CNN |
| LLM schemas | `agent_tools/schemas.py` | What the LLM produces — analyzed StockReport with ratings, sentiment |

**Why separate:** Same reason you separate API request/response DTOs from database models. If a yfinance field changes, only the tool schema changes. If the report format changes, only the LLM schema changes. Coupling them leads to cascading breakage.

### Validation as a Guardrail

- **Pydantic `field_validator`** on `RedditPostEntry` — truncates title, URL, snippet at the schema layer. Even if the tool function misses a truncation, the schema catches it. Defense in depth.
- **`ge=0` on price fields** — A negative stock price is always a bug, caught before it reaches the LLM.
- **`ge=0, le=100` on CNN Fear & Greed score** — If the API returns garbage, Pydantic rejects it.
- **`output_schema=StockReport`** on `report_synthesizer` — The LLM is forced to produce structured output matching the schema. No freetext parsing, no regex extraction.

---

## 4. Cache System — Pluggable Backend, Cloud-Ready

### Abstract Interface

```python
class CacheBackend(ABC):
    async def get(self, key: str) -> bytes | None: ...
    async def put(self, key: str, data: bytes, ttl_seconds: int, ...) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def invalidate_ticker(self, ticker: str) -> int: ...
    async def purge_expired(self) -> int: ...
    async def get_stats(self) -> dict: ...
```

Tool functions call `cache.get()` and `cache.put()`. They never touch SQLite directly. Backend is selected by one env var (`CACHE_BACKEND=sqlite`).

### Key Format

```
{TICKER}:{data_type}:{YYYY-MM-DD}
AAPL:price:2026-02-16
:vix:2026-02-16          (market-wide, no ticker)
```

Works identically as a SQLite primary key, Redis key, or GCS object name. No migration friction.

### Migration Path

| Phase | Backend | When | What changes |
|-------|---------|------|-------------|
| Now | SQLite | Local dev, single instance | Current implementation |
| Phase 2 | Redis (Memorystore) | Multi-instance Cloud Run | Swap `CACHE_BACKEND=redis`, implement `RedisCacheBackend` |
| Phase 3 | GCS | Production cloud | Charts/reports to GCS buckets, hot data stays in Redis |
| Phase 4 | Tiered | Scale | Redis for hot (price, sentiment) + GCS for cold (charts, reports) |

### Implementation Details

- **WAL mode** — SQLite journal mode for better concurrent read/write under load.
- **Auto-purge** — Expired entries cleaned every 5 minutes, not on every read.
- **Thread-safe** — `threading.Lock()` with per-call connections. Safe for FastAPI's thread pool.
- **Async interface, sync internals** — The `@cached` decorator bridges async cache methods into sync tool functions using `asyncio.run()` or thread pool executors depending on context.

Full design: [docs/CacheStrategy.md](docs/CacheStrategy.md)

---

## 5. Deployment & Horizontal Scaling

### Stateless Design

No in-memory state between requests. Session data lives in SQLite (local) or can be swapped to an external DB. The application container is disposable — kill it, start another, no data loss.

### Docker

```dockerfile
FROM python:3.13-slim
# Non-root user (security)
RUN adduser --disabled-password --gecos "" myuser
USER myuser
# Single CMD, port from env
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port $PORT"]
```

- Multi-stage build with build deps removed after pip install
- No secrets in image — API keys via `--env-file` at runtime
- Security check: `docker run --rm margincall:latest grep -r "sk-" /app`

### Cloud Run Ready

- Single container, HTTP server (uvicorn/FastAPI)
- Auto-scale 0-to-N based on request concurrency
- `$PORT` from environment (Cloud Run convention)
- No persistent disk required — cache is ephemeral per instance (Redis for shared state at scale)

### Kubernetes Ready

Same image, no changes. Add:
- HPA on request latency or CPU
- ConfigMap/Secret for env vars
- Liveness probe on `/` (FastAPI root)
- Redis sidecar or Memorystore for shared cache

### Environment Abstraction

```bash
# Cloud LLM
CLOUD_AI_MODEL=gemini-2.5-flash

# Local LLM (Ollama)
LOCAL_AI_MODEL=qwen3:8b

# Switch by setting one or the other — no code changes
```

The `tools/config.py` module resolves cloud vs. local at import time. Agents use `model=AI_MODEL` everywhere — never a hardcoded model string.

---

## 6. Observability

Full design and implementation details: [docs/ObservabilityStrategy.md](docs/ObservabilityStrategy.md).

### Prometheus Metrics — Implemented

`GET /metrics` exposes 10 metrics: cache ops, tool calls/duration/errors, truncation events, run duration, runs by status, LLM tokens, LLM call latency, active SSE connections. Defined in `tools/metrics.py` with import guard (graceful no-op if `prometheus_client` is absent).

### Grafana

Pre-provisioned dashboard at `observability/grafana/dashboards/margincall-overview.json` — run success rate, cache hit rate, tool latency/errors, token usage. Use `docker compose -f docker-compose.observability.yml up prometheus grafana` for local monitoring.

### Logging & Streaming

- **Structured logging** — Tool name, cache hit/miss, truncation events (dataset path + byte sizes)
- **SSE log streaming** — 400-line replay buffer, heartbeat to prevent timeout
- **RunSummaryCollector** — Per-run report: tools invoked, duration, cache ratio

### Next Phase

- **OpenTelemetry Collector** — Export ADK spans to Tempo/Jaeger for distributed tracing
- **GCP Cloud Operations** — Native exporters for Cloud Run (Trace, Monitoring, Logging)

---

## 7. Resilience & Error Handling

### Tools Never Raise

Every tool function returns a dict. On success: `{"status": "success", ...}`. On failure: `{"status": "error", "error_message": "..."}`. The agent continues — a failed Reddit fetch doesn't crash the analysis. The report synthesizer works with whatever data is available.

```python
# Pattern used by every tool
try:
    data = fetch_from_external_api(ticker)
    return Result(...).model_dump()
except Exception as e:
    log_tool_error("tool_name", str(e), ticker=ticker)
    return {"status": "error", "error_message": str(e)}
```

### Multi-Endpoint Fallback

CNN Fear & Greed fetcher tries two API endpoints sequentially. If the first is blocked or down, the second is attempted before returning an error. Same pattern applies to news fetching (Google Search → Brave Search fallback via MCP).

### Timeout Management

| Scope | Default | Config |
|-------|---------|--------|
| Per external HTTP call | 10s | Hardcoded per tool (appropriate for market data APIs) |
| Per LLM completion | 120s | `REQUEST_TIMEOUT_SECONDS` env var |
| Per full agent run | 300s | `RUNNER_TIMEOUT_SECONDS` env var (0 = no limit) |

### Fail Fast

API key validation happens at **setup time** (`setup.sh` / `setup.ps1`), not at first agent run. A bad key is caught immediately with a clear error message and retry prompt — not 5 minutes into a pipeline run with a cryptic 401.

---

## 8. Testing

### Unit Tests (83 tests, <5s, no API keys)

| Suite | Tests | Covers |
|-------|-------|--------|
| `test_schemas.py` | 15 | Pydantic validation, field constraints, truncation validators |
| `test_cache.py` | 15 | SQLite put/get/TTL/invalidate/purge/stats, NoOp backend |
| `test_truncation.py` | 14 | String truncation, recursive dict/list, UTF-8 safety, context vars |
| `test_tools.py` | 19 | All tool functions (mocked externals), helper function logic |
| `test_config.py` | 7 | Env parsing, cloud/local model selection |

All external dependencies (yfinance, requests, LLM) are mocked. Tests run offline with zero configuration.

### Structural Validation

`check_env.py` verifies agent wiring at startup:
- Root agent directory and `.name` match
- Sub-agent directories exist and match `SUB_AGENTS` config
- All imports resolve (config, tools, sub-agents)

### Integration (Manual)

```bash
python -m main run -i "tell me about GOOGL" -d -t
```

Full pipeline execution with debug logging and thought traces. Used for manual validation after changes.

---

## 9. What's Next

| Priority | Item | Why |
|----------|------|-----|
| 1 | CI/CD (GitHub Actions) | Lint + test + Docker build + push on every PR |
| 2 | Cloud Run deployment pipeline | Tag-based deploys, zero-downtime |
| 3 | Redis cache backend | Required for multi-instance Cloud Run (shared cache) |
| 4 | OpenTelemetry Collector + tracing | Trace requests through the full agent pipeline (Prometheus + Grafana done) |
| 5 | Parallel tool execution | `stock_data_collector` tools can run concurrently (independent data sources) |

---

## Deep Dives

- [Cache Strategy](docs/CacheStrategy.md) — Pluggable backend design, migration path, schema
- [Observability Strategy](docs/ObservabilityStrategy.md) — Prometheus metrics, Grafana dashboards, OTEL roadmap
- [TPM Bloat Fix](docs/how-we-fixed-llm-tpm-bloat-from-session-state.md) — How base64 charts nearly bankrupted the token budget
- [Token Bloat Prevention](docs/how-to-prevent-datasets-bloat-llm-deep-dive-part1.md) — Systematic approach to LLM context management
- [Error Handling Plan](docs/ERROR_HANDLING_AND_LOGGING_PLAN.md) — Structured logging and error patterns

---

Built by **[Shan Jing](https://www.linkedin.com/in/shanjing/)** — SRE/Cloud Architect. Infrastructure at Tinder and Twitter (multi-region, AWS). Now building and scaling agentic applications.
