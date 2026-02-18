# How the LLM's TPM Was Accidentally Maxed Out — And How It Was Fixed

**A case study in agent architecture: when session.state and tool returns dump 500KB of base64 into every prompt.**

---

## The Problem That Was Easy to Miss

MarginCall is a multi-agent stock analysis system. It fetches price data, financials, technical charts, sentiment, options, Reddit posts, and news. It synthesizes everything into a polished report. It works — until API bills climb, responses slow down, and rate limits are hit.

The cause was: **100–500KB of base64-encoded chart images** were being sent to the LLM on every run. Twice.

This document describes how that was found and fixed in **MarginCall**, an open-source stock research agent built with the Google Agent Development Kit (ADK).

---

## The Setup: A Pipeline of Agents

MarginCall uses a **SequentialAgent** pipeline:

```
stock_analysis_pipeline
├── stock_data_collector   → fetches 10 tools (price, financials, technicals, options, Reddit, news...)
├── report_synthesizer     → reads session.state.stock_data, produces structured JSON report
└── presenter              → formats the report for display
```

Data flows via **session.state** and **output_key**. The `stock_data_collector` is instructed to:

> Store results in session.state (output_key=stock_data):
> ```json
> {
>   "ticker": {
>     "price": <fetch_stock_price result>,
>     "financials": <fetch_financials result>,
>     "technicals": <fetch_technicals_with_chart result>,  // ← the culprit
>     "cnn_fear_greed": ...,
>     "vix": ...,
>     ...
>   }
> }
> ```

The `report_synthesizer` reads `session.state.stock_data` and produces the final report. Simple enough.

---

## The Original (Non-Ideal) Implementation

### What the Original Code Did

`fetch_technicals_with_chart` is a composite tool that:

1. Fetches RSI, MACD, SMA indicators
2. Generates two Plotly charts (1-year daily, 90-day daily)
3. Renders each chart as PNG, base64-encodes it
4. Returns the full result including those base64 strings

```python
# Simplified original flow
chart_result = await generate_trading_chart(ticker, timeframe)
# chart_result = {
#   "status": "Chart generated...",
#   "image_base64": "iVBORw0KGgoAAAANSUhEUgAACWAAA..."  # 50–200KB each
# }

result["charts"][timeframe] = {
    "label": "1-Year Daily",
    "result": chart_result["status"],
    "image_base64": chart_result["image_base64"],  # ← returned as-is
}
# Cached and returned to the agent
return validated  # Full payload, including base64
```

Two charts × ~100–200KB each ≈ **200–400KB** of base64 text per analysis.

### Where It Went Wrong

In ADK (and most agent frameworks), two things happen:

1. **Tool results become `function_response`**  
   When `stock_data_collector` calls `fetch_technicals_with_chart`, the tool's return value is sent back to the LLM as a `function_response` so it can "see" the result and decide what to do next. That return value included the full base64.

2. **Session state is injected into the next agent's context**  
   The `report_synthesizer` receives `session.state` as part of its prompt. Since `stock_data` contained the full technicals (including base64 charts), the LLM got the same bloat again.

So the charts were sent to the LLM **at least twice** per run:

| Step | Recipient | Data |
|------|-----------|------|
| 1 | stock_data_collector | Full tool response with base64 |
| 2 | report_synthesizer | session.state.stock_data with base64 |

With the other tool results (financials, options, Reddit, news) the pipeline was easily hitting **300–500KB+** of input tokens per run. That is expensive, slow, and often unnecessary. The report synthesizer only needs **indicators and signals** (e.g. "RSI 33.8, bearish MACD"), not the raw chart pixels.

---

## The Impact

- **TPM (tokens per minute) limits** — Large prompts consume quota faster
- **Latency** — More input tokens → longer processing
- **Cost** — Input tokens are billed; 500KB ≈ 125K+ tokens
- **Context dilution** — The model wastes capacity on pixels instead of analysis

---

## The Fix

Three changes were made.

### 1. Strip Base64 Before Returning to the Agent

`fetch_technicals_with_chart` now:

- Caches the **full** result (with base64) for the frontend's `/api/charts` endpoint
- Returns a **stripped** copy to the agent — chart metadata (label, status) but no `image_base64`

```python
def _strip_chart_base64(charts: dict) -> dict:
    """Remove image_base64 from chart entries so they are not sent to the LLM."""
    if not charts:
        return charts
    stripped = {}
    for k, v in charts.items():
        if isinstance(v, dict):
            stripped[k] = {kk: vv for kk, vv in v.items() if kk != "image_base64"}
        else:
            stripped[k] = v
    return stripped

# After caching the full result...
to_return = dict(validated)
if "charts" in to_return:
    to_return["charts"] = _strip_chart_base64(to_return["charts"])
return to_return  # Agent sees this — no base64
```

### 2. Return Status-Only from Chart Generation (When Using ADK Artifacts)

`generate_trading_chart` now:

- Saves charts to **ADK artifacts** when `tool_context` is present (for ADK Ib UI)
- Returns **status-only** (no `image_base64`) when using the artifact path
- The caller (`fetch_technicals_with_chart`) loads the PNG from the artifact for the cache when needed

```python
# When tool_context present: save to ADK artifacts
await tool_context.save_artifact(png_filename, png_part)
# Return status-only; fetch_technicals loads artifact for cache
return {
    "status": f"Chart generated for {ticker}. Inline: {png_filename}; Interactive: {html_filename}",
}
```

Artifacts are stored separately and **do not** go to the LLM. Only the tool's return value does — and that return is kept small.

### 3. Keep Full Data in Cache for the Frontend

The frontend still gets charts via `/api/charts`:

```python
# server.py
@charts_router.get("/charts")
async def get_charts(ticker: str):
    data = await cache.get_json(cache_key)  # Full data with base64
    # ... extract charts for frontend display
    return {"charts": out}
```

The cache stores the full result. The agent never sees it. Best of both worlds.

---

## Data Flow After the Fix

```
generate_trading_chart
├── ADK path: save_artifact(html, png) → return status-only
└── CLI path: save to .tmp → return status + base64 (for cache)

fetch_technicals_with_chart
├── Receives chart result (status-only or status+base64)
├── If status-only: load_artifact() to get base64 for cache
├── Cache full result (with base64) for /api/charts
└── Return STRIPPED result (no base64) to agent

stock_data_collector
└── Receives stripped technicals → stores in session.state

report_synthesizer
└── Reads session.state.stock_data → indicators/signals only, no pixels
```

---

## Key Takeaways

1. **Tool return values go to the LLM** — Whatever the tools return becomes part of the conversation. Keep it lean.

2. **Session state goes to the next agent** — If storing large blobs in `session.state`, they will be in the next agent's prompt. Prefer references (filenames, cache keys) over raw data.

3. **Artifacts ≠ context** — ADK's `save_artifact` stores binaries separately. They do not bloat the LLM unless the code explicitly passes them. Use artifacts for generated files; use status strings for tool returns.

4. **Cache for consumers, strip for the model** — Cache the full payload for APIs and UIs. Return a trimmed version to the agent.

5. **The report synthesizer did not need the charts** — It only needed RSI, MACD, SMA signals. Pixels were being sent for no reason. The design question is: *what does the model actually need?*

---

## Before and After

| Metric | Before | After |
|--------|--------|-------|
| Chart data to LLM | ~200–400KB base64 | 0 (metadata only) |
| Total stock_data size | ~300–500KB | ~20–50KB |
| TPM impact | High | Much lower |
| Charts in ADK Ib UI | Yes (artifacts) | Yes |
| Charts in custom frontend | Yes (/api/charts) | Yes |

---

## Where to Look in the Repo

MarginCall is open source. The relevant code lives in:

- `agent_tools/fetch_technicals_with_chart.py` — stripping logic, cache vs return
- `agent_tools/generate_trading_chart.py` — status-only returns, artifact saving
- `stock_analyst/sub_agents/stock_data_collector/agent.py` — pipeline definition
- `stock_analyst/sub_agents/report_synthesizer/agent.py` — consumes session.state

Running a stock analysis and checking the logs shows cache hits, stripped payloads, and no base64 in the agent context.

---

*When building agent systems with rich tool outputs, auditing what actually reaches the model pays off — for TPM and for cost.*
