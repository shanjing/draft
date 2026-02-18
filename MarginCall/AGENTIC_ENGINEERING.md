# Agentic Engineering: Designing LLM Agent Systems That Work

This document describes how MarginCall approaches the core design challenges of building production agentic systems. It is organized around six failure modes that are common in LLM agent projects — not as a checklist, but as the lens through which every design decision in this codebase was made.

The companion document **[ENGINEERING.md](ENGINEERING.md)** covers the infrastructure that supports these agent design decisions — caching, observability, deployment, resilience. The two are inseparable: agent design dictates what the infrastructure must provide, and infrastructure constraints shape what the agents can do.

---

## 1. Context Window Is the Agent's Working Memory

The context window is not a technical detail to worry about later. It is the agent's working memory — everything it knows, everything it reasons over. Blow it, and the agent gets dumber, slower, and more expensive simultaneously.

### How MarginCall manages it

**Three-layer truncation pipeline.** Every tool output passes through progressive size reduction before reaching the LLM:

```
External API response (unbounded)
  → Pydantic field validators (per-field byte caps at schema layer)
  → truncate_strings_for_llm() (recursive walk, MAX_STRING_BYTES=2000 per field)
  → base64 stripping (charts cached for frontend, metadata-only to LLM)
  → LLM receives lean, structured payload
```

This is defense in depth. The schema layer catches oversized fields even if the tool function forgot to truncate. The recursive truncator catches anything the schema missed. The base64 strip prevents the single largest payload category (chart images) from ever entering the context.

**Transparency, not silence.** When content is truncated, the system doesn't hide it. A context variable (`_truncation_occurred`) flags the event, tools set `truncation_applied: true` in their return, and the report synthesizer's prompt explicitly instructs: if truncation occurred, include a disclaimer. The LLM knows its input was shortened and adjusts its reasoning accordingly — it won't hallucinate details from content it never saw.

**Output key isolation.** Each pipeline agent writes to a single `output_key` in `session.state`. The downstream agent reads only that key, not the full conversation history of the previous agent. This is the most underrated context management technique in ADK — it means the report synthesizer sees `stock_data` (the collector's structured output), not the collector's 10 tool calls, 10 tool responses, and internal reasoning.

**The lesson that made this non-negotiable:** Early in development, a single tool (`fetch_technicals_with_chart`) returned 200-400KB of base64-encoded chart images to the LLM. This data was duplicated in `session.state` for the next agent. Total input per run: ~125K tokens. The fix — cache full payloads for the frontend, return metadata-only to the agent — dropped token cost to ~15-30K per run. Documented in [how-we-fixed-llm-tpm-bloat-from-session-state.md](docs/how-we-fixed-llm-tpm-bloat-from-session-state.md).

---

## 2. Start Simple, Earn Complexity

A common failure mode in agent projects is reaching for multi-hop reasoning, memory systems, and complex orchestration before validating that a simpler approach works. Complexity is not a feature — it is a cost you pay on every debug session, every new contributor's ramp-up, and every production incident.

### How MarginCall keeps it simple

**The pipeline is three agents in a line.** The core of the system is a `SequentialAgent` — fetch data, analyze it, present it. No loops, no conditional routing, no retry chains. The data collector fetches everything, the synthesizer reads from state and produces a structured report, the presenter formats it. Each agent does one thing.

**SQLite, not Redis.** The cache backend is SQLite in WAL mode. For a single-instance local agent, this is correct. The abstract `CacheBackend` interface exists so Redis can slot in when multi-instance deployment requires it — but it hasn't been built yet because it isn't needed yet. The migration path is designed, not implemented.

**No framework beyond ADK.** MarginCall doesn't use LangChain, LlamaIndex, or a custom orchestrator. Google ADK provides agents, tools, sequential pipelines, and session state. That's sufficient. The `@cached` decorator, the `run_context` registry, and the `RunSummaryCollector` are the only custom infrastructure — each under 250 lines, each solving a specific problem that ADK doesn't cover.

**One config file, one env file.** Model selection, cache backend, timeouts — all resolved at import time from `tools/config.py` and `.env`. No YAML hierarchies, no feature flags, no runtime config reloading.

The rule: don't build Phase 2 infrastructure during Phase 1 development. Design for it (interfaces, key formats, env vars), but don't implement it until the simpler version is proven insufficient.

---

## 3. Agents vs. Workflows — Use LLMs Only Where You Need Judgment

An agent (LLM decides what to do) is more flexible but slower, more expensive, and less predictable than a workflow (code decides what to do). The design question for every step: does this require *judgment*, or just *execution*?

### MarginCall's split

**Workflow: the pipeline itself.** `stock_analysis_pipeline` is a `SequentialAgent` — a deterministic three-step workflow. Data collection always precedes analysis, which always precedes presentation. No LLM decides this ordering. It's hardcoded because it's always correct.

```python
stock_analysis_pipeline = SequentialAgent(
    name="stock_analysis_pipeline",
    sub_agents=[stock_data_collector, report_synthesizer, presenter],
)
```

**Agent: the root supervisor.** The root `stock_analyst` uses the LLM to classify user intent: full research (→ pipeline), casual chat (→ respond directly), cache refresh (→ invalidate then pipeline), single-tool queries (→ call one tool). This routing requires understanding natural language — "give me fresh numbers on META" maps to path C (invalidate + re-run), not path A (cached analysis). A keyword-based router would miss the nuance.

**Agent: the data collector.** `stock_data_collector` is an `LlmAgent` with 10 tools and a `BuiltInPlanner`. For a full analysis, it calls all 10 tools. But users sometimes ask for partial data ("just financials and Reddit"), and the LLM's planner handles that routing without a branching decision tree. The prompt instructs parallel grouping for the common all-tools case, so even when the LLM decides, it decides efficiently.

**LLM as computation: synthesizer and presenter.** These agents have no tools — the LLM *is* the tool. The synthesizer reads structured data and produces a structured report (applying the 60/40 weighting rule). The presenter reads the report and formats it for display. There's no simpler way to do "read 10 data sources and write an investment thesis" than giving it to a language model with a schema.

**The agent-as-tool pattern.** The entire pipeline is wrapped as `AgentTool(agent=stock_analysis_pipeline)` in the root agent's toolbox. This means the root agent's LLM call decides *whether* to run the pipeline, but the pipeline execution itself is deterministic. Judgment at the boundary, workflow inside.

---

## 4. Structured Output Over String Parsing

Parsing LLM text output with regex is the #1 source of silent failures in agent systems. The LLM adds a newline, changes a word, wraps output in markdown fences, and the parser breaks. The fix is to never parse in the first place.

### How MarginCall avoids it

**`output_schema` on the synthesizer.** The report synthesizer uses `output_schema=StockReport` — a Pydantic model with typed fields, validators, and constraints. ADK enforces this: the LLM must produce valid JSON matching the schema, or the response is rejected and retried. No regex, no `json.loads()` on raw text, no string splitting.

```python
report_synthesizer = LlmAgent(
    output_schema=StockReport,  # Pydantic model — enforced by ADK
    output_key="stock_report",
)
```

**Two-schema architecture.** Tool return values and LLM output values use separate schema files:

| Layer | File | What it validates |
|-------|------|-------------------|
| Tool data | `agent_tools/tool_schemas.py` | Raw data from yfinance, Reddit, CNN — field types, value ranges |
| LLM output | `agent_tools/schemas.py` | Analyzed StockReport — ratings, summaries, recommendations |

If yfinance changes a field name, only `tool_schemas.py` changes. If the report format evolves, only `schemas.py` changes. Decoupled contracts, not a monolith.

**Validation as guardrails, not parsing.** Pydantic validators enforce invariants the LLM might violate:
- `ge=0` on stock prices — a negative price is always wrong
- `ge=0, le=100` on Fear & Greed scores — if the API returns garbage, reject it
- Field-level `max_length` and byte-cap validators — truncation happens at the schema layer before the data reaches the LLM

**Tool outputs are dicts, never strings.** Every tool function returns `Result(...).model_dump()` (success) or `{"status": "error", "error_message": "..."}` (failure). The consuming agent reads structured fields, not text.

**State-based communication.** Agents exchange data through `session.state` using `output_key`, not by parsing each other's text output. The synthesizer reads `session.state["stock_data"]` — a typed dict — not the data collector's natural language response.

---

## 5. Agents Need a Plan Before They Act

An agent without a plan will call tools randomly, repeat failed actions, and waste tokens discovering what it should have known upfront. Planning is not overhead — it is cost control.

### How MarginCall builds planning in

**`BuiltInPlanner` on the data collector.** The most tool-heavy agent uses ADK's native planner with thinking enabled:

```python
stock_data_collector = LlmAgent(
    planner=BuiltInPlanner(
        thinking_config=ThinkingConfig(include_thoughts=True)
    ),
    ...
)
```

The model reasons about which tools to call and in what order *before* making the first function call. For a full analysis, the prompt reinforces this with explicit parallel grouping:

```
Group 1 (parallel): fetch_stock_price, fetch_financials, fetch_technicals, fetch_earnings_date
Group 2 (parallel): fetch_cnn_greedy, fetch_vix, fetch_stocktwits, fetch_options, fetch_reddit
Group 3: news_fetcher (agent tool)
```

This is prompt-level planning combined with model-level planning. The LLM doesn't discover the tool list through exploration — it knows the tools, the grouping, and the expected output structure before it starts.

**Structured decision tree on the root agent.** The root agent's instruction is a classification prompt with seven explicit paths (A-G), each with routing rules and examples. The LLM doesn't "figure out" what to do — it matches the user's request to a pre-defined path and executes it. This is planning encoded in the prompt, not left to model improvisation.

**Report synthesizer uses a decision matrix.** The 60/40 weighting rule is an explicit algorithm in the prompt — a lookup table mapping (market sentiment × stock performance) to recommendation. The LLM follows a prescribed analytical process rather than freestyling a recommendation. The weighting percentages are loaded from `report_rules.json`, making the algorithm tunable without prompt changes.

**Graceful degradation on missing data.** The synthesizer's prompt includes explicit instructions for handling missing or errored data sources: use defaults, lower confidence, add disclaimers. This is a pre-planned failure mode — the agent knows what to do when tools fail before any tool has been called.

---

## 6. Evaluation Is Not Optional — W.I.P.

Unit tests verify that tools return the right shape. Schema tests verify that Pydantic catches bad data. Cache tests verify that TTL works. But none of these test the thing that makes this an agent system: *does the LLM produce good analysis?*

### What exists today

**83 unit tests** covering tool functions (mocked externals), schema validation (field constraints, truncation), cache operations (put/get/TTL/invalidate), config resolution (cloud/local model selection), and truncation behavior (recursive dict/list, UTF-8 safety). All offline, all fast (<5s), all deterministic.

**Structural validation** via `check_env.py` — agent names match directories, imports resolve, sub-agents match config. Catches wiring bugs at startup, not at query time.

**RunSummaryCollector** — per-run observability showing which tools ran, which were skipped, cache hit rates, and duration. This is operational visibility, not quality evaluation, but it catches a class of bugs (tool not called, unexpected cache miss) that pure unit tests miss.

### What's being built

The gap is clear: there is no automated evaluation of LLM output quality. A prompt change to the report synthesizer could silently degrade recommendations, and no test would catch it. This is the next engineering priority.

The planned approach:
- **Golden eval set** — Known ticker data → expected report quality assertions (rating direction, required sections present, weighting rule applied correctly)
- **Deterministic checks** — Schema compliance, field completeness, confidence range, truncation disclaimers present when expected
- **LLM-as-judge** — Rubric-based grading of report quality against reference outputs
- **Regression detection** — Run evals on prompt changes before merging

This section will be updated as the evaluation framework is implemented.

---

## How These Constraints Connect

These six concerns are not independent. They form a dependency chain:

```
Context management (1) ←── enables ──→ Simple solutions (2)
        │                                      │
        │ (lean context means                  │ (simple pipeline means
        │  cheaper LLM calls)                  │  fewer agent decisions)
        v                                      v
Planning (5) ←──── enables ────→ Agents vs. workflows (3)
        │                                      │
        │ (planned execution means             │ (clear boundaries mean
        │  predictable tool usage)             │  predictable outputs)
        v                                      v
Structured output (4) ←── validates ──→ Evaluation (6)
```

Context management keeps costs low enough to run evals. Simple architecture keeps the eval surface small. Structured output makes evaluation deterministic rather than subjective. And evaluation closes the loop — proving the agents actually work.

The infrastructure described in **[ENGINEERING.md](ENGINEERING.md)** — caching, observability, resilience — exists to serve these agent design requirements. The 3-tier cache exists because context management (1) demands that tool outputs be bounded and repeatable. Prometheus metrics exist because planning (5) and evaluation (6) require visibility into what the agents actually did. The tools-never-raise pattern exists because agents need structured failure modes (4), not stack traces.

---

## References

- [ENGINEERING.md](ENGINEERING.md) — Infrastructure: cache, observability, deployment, resilience
- [Observability Strategy](docs/ObservabilityStrategy.md) — Prometheus metrics, Grafana dashboards, operations guide
- [TPM Bloat Fix](docs/how-we-fixed-llm-tpm-bloat-from-session-state.md) — Context window incident and fix
- [Token Bloat Prevention](docs/how-to-prevent-datasets-bloat-llm-deep-dive-part1.md) — Systematic context management
- [Cache Strategy](docs/CacheStrategy.md) — How infrastructure supports context and cost control

---

Built by **[Shan Jing](https://www.linkedin.com/in/shanjing/)** — SRE/Cloud Architect turned agentic systems engineer. The thesis: agents are distributed systems, and building them requires both AI intuition and infrastructure discipline.
