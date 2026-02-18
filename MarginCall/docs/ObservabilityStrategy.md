# Observability Strategy

This document covers the monitoring and observability design for MarginCall — what is monitored, what ADK provides natively, and how each layer is implemented.

The core thesis: **an LLM agent pipeline has the same observability requirements as any distributed system** (latency, error rates, resource consumption, throughput) **plus LLM-specific concerns** (token cost, context window pressure, hallucination guardrails, cache economics). Both layers are instrumented.

---

## 1. What Needs to Be Monitored

### Application Layer (MarginCall tools and infrastructure)

| Metric | Why it matters | Current status |
|--------|---------------|----------------|
| **Cache hit/miss rate** | Each cache miss triggers an external API call + downstream LLM processing. Target: 80%+ hit rate. | **Prometheus:** `margincall_cache_ops_total{operation,result}` + per-run logging via `@cached` decorator |
| **Tool execution latency** | Identifies slow external dependencies (yfinance, Reddit, CNN). | **Prometheus:** `margincall_tool_duration_seconds{tool_name}` + per-run via `RunSummaryCollector` |
| **Tool error rate** | A failing tool degrades report quality. Persistent failures need alerting. | **Prometheus:** `margincall_tool_errors_total{tool_name}` + logged via `log_tool_error()` |
| **Truncation events** | Signals that upstream data is growing — early warning for token budget pressure. | **Prometheus:** `margincall_truncation_total{tool_name}` + per-tool `_truncation_occurred` context var |
| **Cache entry count / TTL distribution** | Monitors cache growth and staleness. | Available via `get_stats()` on cache backend |
| **Run wall-clock time** | End-to-end latency from user query to response. | **Prometheus:** `margincall_run_duration_seconds` histogram + `RunSummaryCollector.total_seconds()` |

### Agent/LLM Layer (ADK provides this)

| Metric | Why it matters | ADK support |
|--------|---------------|-------------|
| **Input/output tokens per LLM call** | Direct cost driver. A single bloated tool response can 5x the token bill. | Built-in: `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` in OTEL spans |
| **LLM call latency** | Distinguishes slow tools from slow model inference. | Built-in: `generate_content` spans with duration |
| **Agent invocation count** | Tracks how many agent hops a query requires. Runaway loops = cost explosion. | Built-in: `invoke_agent` spans per agent |
| **Tool call count per agent** | Validates that the pipeline calls expected tools. Missing tools = incomplete data. | Built-in: `execute_tool` spans with `gen_ai.tool.name` |
| **LLM error rate** | API failures, timeouts, rate limits from the model provider. | Built-in: span status + `on_model_error_callback` |
| **Finish reasons** | Distinguishes normal completions from length cutoffs or safety filters. | Built-in: `gen_ai.response.finish_reasons` in spans |

### Infrastructure Layer (standard)

| Metric | Why it matters | Current status |
|--------|---------------|----------------|
| **HTTP request latency (p50/p95/p99)** | User-facing SLA. FastAPI middleware. | Not yet instrumented (Phase 2) |
| **Active SSE connections** | Monitors frontend load on log streaming. | **Prometheus:** `margincall_active_sse_connections` gauge |
| **SQLite cache DB size** | Prevents disk exhaustion on long-running instances. | Not yet instrumented (Phase 2) |
| **Process memory / CPU** | Standard container health. Prometheus `process_*` metrics come free. | **Auto-exposed** by `prometheus_client` default collectors |

---

## 2. What ADK Currently Offers

*(ADK API details below — callback names, span attributes, env vars — should be confirmed against the `adk-python` / `adk-docs` version when implementing.)*

### 2.1 Built-in OpenTelemetry Instrumentation

ADK (v1.21.0+) instruments every agent run with OpenTelemetry spans automatically. No application code needed — these spans exist when ADK's runner is used:

**Span hierarchy per request:**
```
invoke_agent (root agent)
  └─ generate_content {model}          ← LLM call with token counts
       └─ execute_tool {tool_name}     ← tool execution
  └─ invoke_agent (sub-agent)          ← pipeline agent
       └─ generate_content {model}
            └─ execute_tool ...
```

**Attributes on each span:**

| Span | Attributes |
|------|-----------|
| `invoke_agent` | `gen_ai.agent.name`, `gen_ai.agent.description`, `gen_ai.conversation_id` |
| `generate_content` | `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.response.finish_reasons` |
| `execute_tool` | `gen_ai.tool.name`, `gen_ai.tool.description`, `gen_ai.tool.type`, function_call_id |

**Source:** `google.adk.telemetry.tracing` module.

### 2.2 Callback Hooks

ADK exposes callbacks at every boundary — these are the integration points for custom Prometheus metrics:

```python
Agent(
    name="stock_analyst",
    before_agent_callback=on_agent_start,       # agent lifecycle
    after_agent_callback=on_agent_end,
    before_model_callback=on_model_start,       # LLM calls (access to LlmRequest)
    after_model_callback=on_model_end,          # LLM responses (access to LlmResponse with token counts)
    before_tool_callback=on_tool_start,         # tool execution
    after_tool_callback=on_tool_end,
    on_model_error_callback=on_model_error,     # LLM failures
    on_tool_error_callback=on_tool_error,       # tool failures
)
```

**What's available in callbacks:**
- `callback_context.invocation_id` — correlates all events in a single run
- `callback_context.session.id` — session-level correlation
- `LlmResponse.usage_metadata.prompt_token_count` / `candidates_token_count`
- `tool_context.agent_name`, `tool_context.function_call_id`

### 2.3 OTLP Export (Environment-Driven)

ADK's `telemetry.setup` module auto-configures exporters via standard OTEL env vars:

```bash
# Generic OTLP endpoint (works with any collector)
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# Or split by signal type
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://localhost:4317
OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://localhost:4317
OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=http://localhost:4317
```

Set these env vars and ADK exports its built-in spans to any OTLP-compatible collector (OpenTelemetry Collector, Grafana Alloy, Datadog Agent, etc.).

### 2.4 Google Cloud Native Export

For GCP deployments, ADK provides direct integration:

```python
from google.adk.telemetry.google_cloud import get_gcp_exporters

exporters = get_gcp_exporters(
    enable_cloud_tracing=True,      # → Cloud Trace
    enable_cloud_metrics=True,      # → Cloud Monitoring
    enable_cloud_logging=True,      # → Cloud Logging
)
```

Also available via CLI: `adk deploy cloud_run --trace_to_cloud`.

### 2.5 BigQuery Analytics Plugin

Enterprise-grade event logging for offline analysis:

```python
from google.adk.plugins.bigquery_agent_analytics_plugin import BigQueryAgentAnalyticsPlugin

plugin = BigQueryAgentAnalyticsPlugin(project="my-project", dataset="agent_analytics")
runner = Runner(agents=[root_agent], plugins=[plugin])
```

Captures every event (LLM calls, tool executions, agent lifecycle) with full schema: timestamps, token usage, latency, trace IDs, content payloads. Useful for cost analysis and quality evaluation over time, not real-time monitoring.

---

## 3. Current Implementation

MarginCall has run-scoped observability built into the application layer. This foundation has been **formalized into Prometheus metrics** (see Section 4) while preserving the original per-run logging unchanged:

### 3.1 RunSummaryCollector (`tools/logging_utils.py`)

Collects per-run data during `execute_agent_stream()`:

```
============================================================
RUN SUMMARY
============================================================
Model: gemini-2.5-flash
Total execution time: 45.32 s
- Tools / agents invoked (with duration):
  - fetch_stock_price (stock_data_collector) 2.15 s (cache hit)
  - fetch_reddit (stock_data_collector) 8.47 s
  - fetch_vix (stock_data_collector) 1.89 s (cache hit)
- Tool executions (run context; cache hit / executed / error):
  - fetch_stock_price: cache hit
  - fetch_reddit: executed
  - fetch_vix: cache hit
- Tools not invoked this run:
  - brave_search: not seen in root event stream; not in run registry
============================================================
```

**Data sources:** `record_event()` for timing, `_from_cache` flag for cache detection, `run_context` registry for execution status, session events for agent tracking.

### 3.2 Structured Logging Functions (`tools/logging_utils.py`)

| Function | Level | Format |
|----------|-------|--------|
| `log_tool_error(tool, msg)` | WARNING | `[MarginCall] type=tool_error tool={tool} message={msg}` |
| `log_agent_failure(agent, type, msg)` | ERROR | `[MarginCall] type={type} agent={agent} message={msg}` |
| `log_llm_error(msg)` | ERROR | `[MarginCall] type=llm_error message={msg}` |

### 3.3 Cache Backend Logging (`tools/cache/sqlite_backend.py`)

Every cache operation is logged:
- `Cache HIT: AAPL:price:2026-02-16`
- `Cache PUT: AAPL:price:2026-02-16 (TTL=900s)`
- `Cache MISS: AAPL:price:2026-02-16`
- `Cache INVALIDATE ticker=AAPL, deleted=5 entries`
- `Cache PURGE: removed 12 expired entries`

### 3.4 Truncation Tracking (`tools/truncate_for_llm.py`)

Per-tool context variable flags when content was shortened:
```
Truncation: dataset=fetch_reddit.posts[0].snippet original_bytes=4200 truncated_bytes=500
```

Tools set `result["truncation_applied"] = True` so the LLM knows data was cut.

### 3.5 SSE Log Streaming (`server.py`)

Real-time log delivery to the frontend:
- Thread-safe queue collects log records from all threads
- Async broadcast consumer pushes to connected SSE clients
- 400-line circular replay buffer for late-joining clients
- Heartbeat every 250ms prevents browser timeout

---

## 4. Implementation Status

### Phase 1: Prometheus `/metrics` Endpoint — IMPLEMENTED

**Dependency:** `prometheus_client>=0.21.0` (in `requirements.txt`).

**Metrics endpoint:** `GET /metrics` on the FastAPI server returns `prometheus_client.generate_latest()` in standard Prometheus text exposition format.

**Central definitions:** All metric objects live in `tools/metrics.py` — single source of truth. The module is import-guarded: if `prometheus_client` is not installed, `METRICS_ENABLED = False` and the app runs without metrics (no crashes, no side effects).

**10 metrics exposed:**

| Metric | Type | Labels | Instrumentation point |
|--------|------|--------|----------------------|
| `margincall_tool_calls_total` | Counter | `tool_name`, `cache_hit` | `tools/cache/decorators.py` → `_record_tool_run()` |
| `margincall_tool_duration_seconds` | Histogram | `tool_name` | `tools/cache/decorators.py` → `_record_tool_duration()` |
| `margincall_tool_errors_total` | Counter | `tool_name` | `tools/cache/decorators.py` → `_record_tool_run()` (when `error` is not None) |
| `margincall_cache_ops_total` | Counter | `operation`, `result` | `tools/cache/sqlite_backend.py` → `_inc_cache_metric()` in `get()`, `put()`, `invalidate_ticker()` |
| `margincall_truncation_total` | Counter | `tool_name` | `tools/truncate_for_llm.py` → `_inc_truncation_metric()` after each `_set_truncation_occurred()` |
| `margincall_run_duration_seconds` | Histogram | — | `tools/runner_utils.py` → `execute_agent_stream()` finally block |
| `margincall_runs_total` | Counter | `status` | `tools/runner_utils.py` → status set per exception type (success/timeout/llm_error/agent_error) |
| `margincall_llm_tokens_total` | Counter | `direction`, `model` | `stock_analyst/agent.py` → `_after_model_callback` extracts `usage_metadata` |
| `margincall_llm_call_duration_seconds` | Histogram | `model` | `stock_analyst/agent.py` → `_before_model_callback` + `_after_model_callback` pair |
| `margincall_active_sse_connections` | Gauge | — | `server.py` → inc on SSE connect, dec in generator finally block |

**Histogram bucket ranges:**
- `tool_duration_seconds`: 0.1, 0.5, 1, 2, 5, 10, 15, 30, 60s (tool calls range from sub-second cache hits to 30s+ API calls)
- `run_duration_seconds`: 1, 5, 10, 20, 30, 45, 60, 90, 120, 180, 300s (full pipeline runs typically 20-90s)
- `llm_call_duration_seconds`: 0.5, 1, 2, 5, 10, 20, 30, 60s (model inference typically 2-15s)

**Files modified:**

| File | What was added |
|------|---------------|
| `tools/metrics.py` (**new**) | All 10 metric definitions with import guard |
| `tools/cache/decorators.py` | `_record_tool_run()` increments `tool_calls_total` + `tool_errors_total`; new `_record_tool_duration()` records histogram; timing via `time.perf_counter()` around function calls |
| `tools/cache/sqlite_backend.py` | `_inc_cache_metric()` helper called in `get()` (hit/miss), `put()` (ok), `invalidate_ticker()` (ok) |
| `tools/truncate_for_llm.py` | `_inc_truncation_metric()` called after every `_set_truncation_occurred()` |
| `tools/runner_utils.py` | `_run_status` variable tracks outcome through try/except/finally; metrics recorded in finally block |
| `stock_analyst/agent.py` | `_before_model_callback` stores start time in ContextVar; `_after_model_callback` records tokens + latency; both added to root agent |
| `server.py` | `GET /metrics` endpoint; SSE gauge inc/dec in `log_stream()` |

**Design pattern:** Every instrumentation point uses lazy `try/except` imports so metrics are additive — removing `prometheus_client` from requirements silently disables all metrics without breaking any existing functionality.

### Phase 2: OTEL Collector + Distributed Tracing — PLANNED

**Goal:** Export ADK's built-in spans to an OpenTelemetry Collector, which fans out to Prometheus (metrics) and Tempo/Jaeger (traces). This provides the full request waterfall: user query → supervisor → pipeline → tools → external APIs.

**Prerequisites:** `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-grpc` (not yet in requirements).

**Architecture:**

```
MarginCall (FastAPI + ADK)
  │
  │  OTLP/gRPC (port 4317)
  v
OpenTelemetry Collector
  ├──→ Prometheus (metrics, port 9090)
  ├──→ Tempo or Jaeger (traces, port 3200/16686)
  └──→ Loki (logs, optional, port 3100)
         │
         v
      Grafana (dashboards + trace explorer)
```

**Configuration:**

```bash
# .env additions
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=margincall
```

ADK auto-exports its spans when these env vars are set. No code changes needed for the built-in agent/LLM/tool spans.

**OTEL Collector config (`otel-collector.yaml`):**
```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

exporters:
  prometheus:
    endpoint: 0.0.0.0:8889
  otlp/tempo:
    endpoint: tempo:4317
    tls:
      insecure: true

service:
  pipelines:
    metrics:
      receivers: [otlp]
      exporters: [prometheus]
    traces:
      receivers: [otlp]
      exporters: [otlp/tempo]
```

**What this unlocks:**
- Waterfall trace view: see exactly where time is spent (LLM inference vs. tool execution vs. data fetching)
- Token cost attribution: which agent/tool combination consumes the most tokens
- Error correlation: trace a failed run from the user query through to the specific external API that timed out
- Latency heatmaps across runs

### Phase 3: GCP Cloud Operations (Production) — PLANNED

**Goal:** For Cloud Run deployment, use GCP-native exporters instead of self-hosted collector.

```python
# server.py or startup hook
from google.adk.telemetry.google_cloud import get_gcp_exporters

if os.getenv("GOOGLE_CLOUD_PROJECT"):
    get_gcp_exporters(
        enable_cloud_tracing=True,
        enable_cloud_metrics=True,
        enable_cloud_logging=True,
    )
```

- **Cloud Trace** replaces Tempo/Jaeger — same waterfall view, zero infrastructure
- **Cloud Monitoring** replaces Prometheus — auto-scales, no storage management
- **Cloud Logging** replaces Loki — structured logs with trace correlation

---

## 5. Grafana Dashboard Design

### Pre-Provisioned: MarginCall Overview — IMPLEMENTED

A single consolidated dashboard is auto-provisioned at `observability/grafana/dashboards/margincall-overview.json` (UID: `margincall-overview`). It covers health, cost, and tool performance in one view — 14 panels:

| Panel | PromQL | Visualization |
|-------|--------|--------------|
| Run Success Rate | `sum(rate(margincall_runs_total{status="success"}[5m])) / clamp_min(sum(rate(margincall_runs_total[5m])), 1)` | Gauge (green >95%, yellow >80%, red below) |
| Cache Hit Rate | `sum(rate(margincall_cache_ops_total{result="hit"}[5m])) / clamp_min(sum(rate(margincall_cache_ops_total{operation="get"}[5m])), 1)` | Gauge (target >80%) |
| Active SSE Connections | `margincall_active_sse_connections` | Stat |
| Total Runs | `sum(margincall_runs_total)` | Stat |
| Run Latency p50/p95/p99 | `histogram_quantile(0.50/0.95/0.99, ...)` on `run_duration_seconds_bucket` | Time series |
| LLM Tokens/min | `sum by (direction) (rate(margincall_llm_tokens_total[5m]) * 60)` | Stacked area |
| Tool Calls by Tool | `sum by (tool_name) (rate(margincall_tool_calls_total[5m]))` | Stacked time series |
| Tool Errors by Tool | `sum by (tool_name) (rate(margincall_tool_errors_total[5m]))` | Bar chart |
| Tool Latency p95 | `histogram_quantile(0.95, ...) by (le, tool_name)` on `tool_duration_seconds_bucket` | Time series |
| Cache Operations/min | `sum by (operation, result) (rate(margincall_cache_ops_total[5m]) * 60)` | Stacked time series |
| Truncation Events/min | `sum by (tool_name) (rate(margincall_truncation_total[5m]) * 60)` | Time series |
| LLM Call Latency p50/p95 | `histogram_quantile(...)` on `llm_call_duration_seconds_bucket` | Time series |
| Runs by Status | `sum by (status) (rate(margincall_runs_total[5m]))` | Stacked time series |
| Cache Hit vs Miss by Tool | `sum by (tool_name, cache_hit) (rate(margincall_tool_calls_total[5m]))` | Stacked time series |

### Future: Dedicated Dashboards (split when needed)

As usage grows, consider splitting into focused dashboards:

- **Agent Health** — run success/latency/errors (operational on-call view)
- **Cost & Tokens** — token rates, cache savings, truncation frequency (cost engineering)
- **Tool Performance** — per-tool latency/errors/cache behavior (debugging)

### Future: Trace Explorer (Phase 2)

Grafana's Tempo data source provides:
- Search by trace ID, agent name, or tool name
- Waterfall view of full request lifecycle
- Span-level token counts and latency
- Error highlighting in trace view

---

## 6. Alerting Rules

| Alert | Condition | Severity |
|-------|-----------|----------|
| High error rate | `rate(margincall_tool_errors_total[5m]) > 0.1` | Warning |
| Run timeout spike | `rate(margincall_runs_total{status="timeout"}[5m]) > 0.05` | Warning |
| Cache hit rate drop | `cache_hit_rate < 0.6` for 10 minutes | Warning |
| Token cost spike | `rate(margincall_llm_tokens_total[1h]) > threshold` | Critical |
| LLM provider errors | `rate(margincall_runs_total{status="llm_error"}[5m]) > 0.1` | Critical |
| Tool consistently failing | `margincall_tool_errors_total{tool="X"}` increase > 5 in 10m | Warning |

---

## 7. Token Budget Monitoring — Why Truncation Is Not an Antipattern

A note on the truncation metrics: monitoring `truncation_events_total` is not about limiting the AI. It's about **managing the signal-to-noise ratio of LLM inputs** — analogous to monitoring payload sizes for any metered API.

What truncation prevents:
- **Cost blowup** — The TPM bloat incident sent 300-500KB per run (125K+ tokens). After truncation: 20-50KB (15-30K tokens). See [TPM Bloat Fix](how-we-fixed-llm-tpm-bloat-from-session-state.md).
- **Lost-in-the-middle degradation** — LLMs demonstrably pay less attention to content in the middle of long contexts. Less noise = better reasoning.
- **Rate limit pressure** — Fewer tokens per request = more requests per minute within provider TPM limits.

What truncation does NOT do:
- It never cuts the user's query
- It never removes data the LLM needs for reasoning (structured metadata is preserved)
- Tools set `truncation_applied: true` so the LLM knows data was shortened and won't hallucinate missing sections

Monitoring truncation frequency indicates when upstream data sources are growing — an early warning to review field caps or add a summarization pass before it becomes a cost problem.

---

## 8. Operations Guide

### 8.1 Local Development (no Docker for MarginCall)

Run MarginCall locally and only containerize the monitoring stack:

```bash
# 1. Start MarginCall
source .venv/bin/activate
cd MarginCall
uvicorn server:app --host 0.0.0.0 --port 8080

# 2. Verify metrics are exposed
curl -s localhost:8080/metrics | head -20
# Should show margincall_* metrics plus default process_* and python_* collectors

# 3. Start Prometheus + Grafana (update target to host.docker.internal)
#    Edit observability/prometheus.yml: targets: ["host.docker.internal:8080"]
docker compose -f docker-compose.observability.yml up prometheus grafana -d

# 4. Access dashboards
#    Prometheus targets: http://localhost:9090/targets (verify "margincall" is UP)
#    Grafana:            http://localhost:3000 (admin / margincall)
```

### 8.2 Full Stack (Docker)

Run everything in containers:

```bash
docker compose -f docker-compose.observability.yml up -d

# Services:
#   MarginCall:  http://localhost:8080
#   Prometheus:  http://localhost:9090
#   Grafana:     http://localhost:3000 (admin / margincall)
```

The Grafana dashboard "MarginCall Overview" is auto-provisioned on first start. No manual import needed.

### 8.3 Verifying Metrics

After running at least one agent query, verify each metric layer:

```bash
# Tool layer: should see tool_name labels for each tool that ran
curl -s localhost:8080/metrics | grep margincall_tool_calls_total

# Cache layer: should see get/hit, get/miss, put/ok
curl -s localhost:8080/metrics | grep margincall_cache_ops_total

# Run layer: should see status="success" (or error type)
curl -s localhost:8080/metrics | grep margincall_runs_total

# LLM layer: should see direction="input" and "output" with token counts
curl -s localhost:8080/metrics | grep margincall_llm_tokens_total

# Truncation: only appears after a tool truncates data
curl -s localhost:8080/metrics | grep margincall_truncation_total

# SSE gauge: reflects currently connected log stream clients
curl -s localhost:8080/metrics | grep margincall_active_sse_connections
```

### 8.4 Metric Storage and Retention

Metrics flow through three layers:

```
MarginCall process (in-memory, resets on restart)
    │
    │  GET /metrics  (scraped every 15s)
    v
Prometheus TSDB  (prometheus_data volume, 7-day retention)
    │
    │  PromQL queries on demand
    v
Grafana  (no metric storage — queries Prometheus live)
```

- **In-process counters/histograms** are ephemeral. Process restart resets them to zero. This is expected — Prometheus stores the time series and uses `rate()` / `increase()` functions that handle counter resets gracefully.
- **Prometheus retention** is set to 7 days (`--storage.tsdb.retention.time=7d`). Adjust in `docker-compose.observability.yml` if needed.
- **Grafana data volume** stores only dashboard configs and user preferences, not metric data.

### 8.5 Metrics Without prometheus_client

The import guard in `tools/metrics.py` means uninstalling `prometheus_client` silently disables all metrics:

```python
try:
    from prometheus_client import Counter, Gauge, Histogram
    METRICS_ENABLED = True
except ImportError:
    METRICS_ENABLED = False
```

Every instrumentation point checks `METRICS_ENABLED` before recording. The app runs identically with or without the library — no performance overhead, no errors, no behavior change.

### 8.6 Adding a New Metric

1. Define the metric in `tools/metrics.py` inside the `if METRICS_ENABLED:` block.
2. At the instrumentation point, use the guarded import pattern:
   ```python
   try:
       from tools.metrics import METRICS_ENABLED
       if METRICS_ENABLED:
           from tools.metrics import your_new_metric
           your_new_metric.labels(...).inc()
   except Exception:
       pass
   ```
3. Add a Grafana panel to `observability/grafana/dashboards/margincall-overview.json` (or create a new dashboard JSON in the same directory — it's auto-discovered).
4. If the metric warrants an alert, add a rule to Section 6.

### 8.7 Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `curl /metrics` returns 501 | `prometheus_client` not installed | `pip install prometheus_client>=0.21.0` |
| Prometheus target shows DOWN | MarginCall not reachable from Prometheus container | Check network config; for local dev, use `host.docker.internal:8080` as target |
| Metrics all zero after a run | Metrics module not imported at runtime | Verify `python -c "from tools.metrics import METRICS_ENABLED; print(METRICS_ENABLED)"` prints `True` |
| LLM token metrics missing | `after_model_callback` not firing | Verify `stock_analyst/agent.py` has `after_model_callback=_after_model_callback` on root agent; check if sub-agent LLM calls also need callbacks |
| Grafana shows "No data" | Prometheus hasn't scraped yet or time range too narrow | Wait 15-30s, check Prometheus `/targets`, widen Grafana time range |
| Dashboard panels show "datasource not found" | Grafana provisioning didn't load | Verify `observability/grafana/provisioning/` is mounted; restart Grafana container |

### 8.8 Cloud Deployment

#### AWS (ECS / EKS)

**ECS with Amazon Managed Prometheus (AMP):**
- Add Prometheus as a sidecar container in the task definition
- Configure `remote_write` in `prometheus.yml` to push to AMP endpoint
- Connect Amazon Managed Grafana to AMP as data source
- Import the same `margincall-overview.json` dashboard

**EKS with kube-prometheus-stack:**
```yaml
# ServiceMonitor for auto-discovery
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: margincall
spec:
  selector:
    matchLabels:
      app: margincall
  endpoints:
    - port: http
      path: /metrics
      interval: 15s
```

#### GCP (Cloud Run)

Use ADK's native exporters (zero infrastructure):

```python
# In server.py startup or lifespan hook
import os
if os.getenv("GOOGLE_CLOUD_PROJECT"):
    from google.adk.telemetry.google_cloud import get_gcp_exporters
    get_gcp_exporters(
        enable_cloud_tracing=True,   # → Cloud Trace
        enable_cloud_metrics=True,   # → Cloud Monitoring
        enable_cloud_logging=True,   # → Cloud Logging
    )
```

For custom Prometheus metrics, Cloud Monitoring's **Managed Prometheus** can scrape the `/metrics` endpoint — same PromQL queries, same dashboard JSON.

#### Portability

The `/metrics` endpoint and metric names are standard Prometheus. The same PromQL queries and Grafana dashboard JSON work across local Docker, AWS, and GCP — only the scrape target configuration changes.

---

## References

- [Cache Strategy](CacheStrategy.md) — Cache backend design, TTL tiers, migration path
- [TPM Bloat Fix](how-we-fixed-llm-tpm-bloat-from-session-state.md) — Base64 chart incident and fix
- [Token Bloat Prevention](how-to-prevent-datasets-bloat-llm-deep-dive-part1.md) — Systematic LLM context management
- [Error Handling Plan](ErrorHandlingLoggingPlan.md) — Structured logging patterns
- ADK Telemetry: `google.adk.telemetry.tracing` / `google.adk.telemetry.setup`
- ADK Callbacks: `google.adk.agents.callback_context`
- ADK Cloud Trace: `google.adk.telemetry.google_cloud`
