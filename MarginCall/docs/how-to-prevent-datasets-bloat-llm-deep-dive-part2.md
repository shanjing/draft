# How to Prevent Datasets Bloat LLM, Part 2 — A Deep Dive

**Technical deep dive: two-layer remediation (schema + truncation), inline signals, observability, and best practices in MarginCall.**

---

**Part 1** ([How to Prevent Datasets Bloat LLM, Part 1](how-to-prevent-datasets-bloat-llm-deep-dive-part1.md)) covered stripping chart base64 from tool returns. **Part 2** (this document) addresses *all* remaining sources of context bloat. Those are unbounded strings from Reddit, search results, financials, and malformed API responses. The document describes the problem, the risk matrix, the two-layer fix (Pydantic schema checks plus a last-resort truncation pass), how the LLM is informed when data was shortened, logging, and takeaways.

---

## 1. Problems and Goals

### The Problem

This issue appears in **all agentic patterns**, especially multi-agent workflows. Whenever data is passed to the next hop — from a tool to an agent, or from one agent to another — unbounded payloads can blow context and cost. It is not specific to MarginCall. It is a factor to consider in any agent design where tool results or agent outputs feed the next step.

In MarginCall, tool outputs are merged into `session.state` (e.g. `stock_data`) and passed to the report synthesizer. If any tool returns unbounded or unexpectedly large strings, then:

- **Token count explodes** — e.g. a single Reddit post body with 70K characters of `\n` can blow the prompt to 70K+ tokens.
- **Downstream validation fails** — the report synthesizer expects a single JSON object; if the model’s reply is cut off mid-string, `StockReport.model_validate_json(...)` raises and the run fails.
- **Cost and latency** — larger context means higher TPM usage and slower responses (as in Part 1).

Relying on *prompt instructions* alone (e.g. “limit to 3 articles, 300 chars”) does not help. The **full** tool response is already in the LLM’s context before the model “decides” to trim. Truncation must happen **at the tool level**, before data is injected into the LLM.

A second issue is **silent truncation**. It is worse than large context. Shortening content without telling the model can lead it to assume it has the full picture and give misleading analysis. The LLM must **always know when it is working with incomplete data**.

### Goals

1. **Cap all bloat-prone sources** — Reddit (titles, snippets, URLs), search results (Brave, Google), `long_business_summary`, and any other unbounded string.
2. **Two layers of defense** — (a) Pydantic schema validators that truncate at the boundary; (b) a recursive “last checkpoint” that caps every string in a tool’s return dict.
3. **Signal truncation to the LLM** — inline markers (e.g. ` [truncated, N chars total]`) and a report-level disclaimer when any source was truncated.
4. **Observability** — log every truncation (dataset, original/truncated size) at INFO, same visibility as cache hits; leave room for future metrics.

---

## 2. Risk Summary: Problematic Areas

The following table lays out the main sources of bloat, typical and worst-case sizes, and how they are mitigated **after** the fixes in this document.

| Source                 | Typical Size | Worst Case | Mitigation Today                                      | Risk  |
|------------------------|-------------|------------|--------------------------------------------------------|-------|
| Chart base64           | 200–400KB   | 500KB      | Stripped (fixed) — see [Part 1](how-to-prevent-datasets-bloat-llm-deep-dive-part1.md) | Low   |
| long_business_summary | 1.8KB       | 3KB        | Capped at 500 chars + ` [truncated]` in `fetch_financials` | Low   |
| Brave search results  | 5KB         | 15KB+      | Pydantic (10 results, 2KB/field); response cap 50KB; inline signal | Low   |
| Google search results | 1.5KB       | 3KB        | Result cap 10; 2KB/field; response cap 50KB; inline signal | Low   |
| Reddit post titles    | 600B        | 2KB        | Pydantic 2KB + fetch_reddit 500B; inline signal       | Low   |
| Reddit snippets       | 1.3KB       | 70KB+      | 500B in fetch_reddit + Pydantic 2KB; inline signal     | Low   |
| All other tools       | <500B each  | <1KB each  | `truncate_strings_for_llm` last checkpoint            | Low   |

*Original “before” view: long_business_summary had no mitigation (High risk); Brave/Google had “soft LLM instruction only” (High/Medium); Reddit titles had none (Medium). All are now addressed with schema + truncation + signals.*

---

## 3. Proposed Fixes: Two Layers of Remediation

Two complementary layers are used so that even if one is bypassed (e.g. a new field, or a bug), the other still bounds size.

### Layer 1: Schema check (Pydantic)

- **Where:** `agent_tools/tool_schemas.py` (and tool-level caps before building the model).
- **What:** For bloat-prone tools (Reddit, Brave search), the **return contract** is a Pydantic model. Each string field has a `field_validator(mode="before")` that calls `truncate_string_to_bytes(value, max_bytes, context="ModelName.field")`. Result count is also capped (e.g. `BraveSearchResult.results` limited to 10).
- **Why:** The schema is the single source of truth for “max size per field.” Validation runs as soon as the tool builds the model (e.g. `RedditPostsResult(...)`), so invalid or oversized data is normalized before it is cached or returned.

### Layer 2: Size truncate (last checkpoint)

- **Where:** `tools/truncate_for_llm.py`; every tool that returns a dict calls it before returning.
- **What:** `truncate_strings_for_llm(obj, max_bytes=2000, tool_name="...")` recursively walks dicts/lists and replaces any string longer than `max_bytes` with a fixed message: `"value exceeds size limit ({size} bytes, max {max_bytes}) [content truncated for context limit]"`. Returns `(result, any_truncated)`.
- **Why:** Catches anything that slips past the schema (e.g. a new field, a different code path, or malformed API data). Acts as a global size guard so no single string can blow the context.

Flow for a tool like `fetch_reddit`:

1. Build list of post dicts (fetch_reddit already caps snippet/title/url in code).
2. Build `RedditPostsResult(posts=all_posts, ...)` → Pydantic validators truncate any over-size string.
3. `out = result.model_dump()`.
4. `result, any_truncated = truncate_strings_for_llm(out, tool_name="fetch_reddit")`.
5. `result["truncation_applied"] = get_tool_truncation_occurred() or any_truncated`.
6. Return `result`.

---

## 4. Details of Each Fix (with Code Snippets)

### 4.1 Central truncation and inline signal — `tools/truncate_for_llm.py`

**Constants and context var:**

```python
MAX_STRING_BYTES = 2000
MAX_RESPONSE_STRING_BYTES = 50_000
OVER_LIMIT_TEMPLATE = "value exceeds size limit ({size} bytes, max {max_bytes}) [content truncated for context limit]"

_truncation_occurred: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "truncation_occurred", default=False
)
```

The context var is set to `True` whenever `truncate_string_to_bytes` or `_truncate_string` actually truncates. Tools that need to expose `truncation_applied` call `reset_tool_truncation_occurred()` at start and `get_tool_truncation_occurred()` at end so the flag reflects only that tool’s run (and is async-safe).

**Per-field truncation with inline “N chars total” signal:**

```python
def truncate_string_to_bytes(
    s: str,
    max_bytes: int = MAX_STRING_BYTES,
    suffix: str = "...",
    context: str | None = None,
    include_size_signal: bool = True,
) -> str:
    # ...
    if len(encoded) <= max_bytes:
        return s
    signal_tail = f" [truncated, {len(s)} chars total]" if include_size_signal else ""
    # Reserve space for suffix + signal; truncate content to fit
    reserve = len(suffix_b) + (len(signal_b) if include_size_signal else 0)
    allowed = encoded[: max_bytes - reserve]
    truncated = allowed.decode("utf-8", errors="ignore").rstrip() + suffix + signal_tail
    _set_truncation_occurred()
    logger.info(
        "Truncation: dataset=%s original_bytes=%s truncated_bytes=%s",
        context or "unknown", len(encoded), truncated_size,
    )
    return truncated
```

So the LLM sees e.g. `"Apple announced a major partnership with... [truncated, 847 chars total]"` and knows content was shortened.

**Recursive last checkpoint (replacement message, no inline N):**

```python
def _truncate_string(s: str, max_bytes: int, path: str, tool_name: str | None) -> tuple[str, bool]:
    if len(encoded) <= max_bytes:
        return s, False
    msg = OVER_LIMIT_TEMPLATE.format(size=len(encoded), max_bytes=max_bytes)
    _set_truncation_occurred()
    logger.info("Truncation: dataset=%s original_bytes=%s truncated_bytes=%s", dataset, ...)
    return msg, True
```

Used inside `truncate_strings_for_llm()` when walking dicts/lists; the replacement message already states that content was truncated.

### 4.2 Pydantic schema checks — Reddit and Brave (`agent_tools/tool_schemas.py`)

**Reddit:** Each string field has its own validator with a clear `context` for logs:

```python
class RedditPostEntry(BaseModel):
    subreddit: str = Field(...)
    title: str = Field(...)
    url: str = Field(...)
    snippet: str = Field(default="", ...)

    @field_validator("snippet", mode="before")
    @classmethod
    def truncate_snippet(cls, v: str) -> str:
        if isinstance(v, str):
            return truncate_string_to_bytes(v, MAX_STRING_BYTES, context="RedditPostEntry.snippet")
        return v
    # same for subreddit, title, url
```

`RedditPostsResult` has a validator for `message`. All call `truncate_string_to_bytes`, so they get the inline ` [truncated, N chars total]` and set the context var.

**Brave search:** `BraveSearchEntry` (title, url, description) and `BraveSearchResult` (results capped at 10):

```python
BRAVE_SEARCH_FIELD_MAX_BYTES = 2000
BRAVE_SEARCH_MAX_RESULTS = 10

class BraveSearchEntry(BaseModel):
    title: str = Field(default="")
    url: str = Field(default="")
    description: str = Field(default="")

    @field_validator("description", mode="before")
    @classmethod
    def truncate_description(cls, v: str) -> str:
        if isinstance(v, str):
            return truncate_string_to_bytes(v, BRAVE_SEARCH_FIELD_MAX_BYTES, context="BraveSearchEntry.description")
        return v or ""
```

`BraveSearchResult` has a validator on `results` that slices to `BRAVE_SEARCH_MAX_RESULTS`.

### 4.3 Tool-level caps and last checkpoint — `fetch_reddit`, `fetch_financials`, `google_custom_search`

**fetch_reddit:** Reset context var, build result via Pydantic, then run last checkpoint and set `truncation_applied`:

```python
reset_tool_truncation_occurred()
# ... build all_posts with _snippet_from_selftext (500B), title/url caps ...
out = RedditPostsResult(status="success", ticker=ticker_upper, posts=all_posts, ...).model_dump()
result, any_truncated = truncate_strings_for_llm(out, tool_name="fetch_reddit")
result["truncation_applied"] = get_tool_truncation_occurred() or any_truncated
return result
```

**fetch_financials — long_business_summary:** Cap in the tool before building the model, with logging:

```python
LONG_BUSINESS_SUMMARY_MAX_CHARS = 500
LONG_BUSINESS_SUMMARY_TRUNCATED_SUFFIX = " [truncated]"

# In the loop that fills data from info:
if out_key == "long_business_summary" and isinstance(val, str):
    original_len = len(val)
    if original_len > LONG_BUSINESS_SUMMARY_MAX_CHARS:
        val = val[:LONG_BUSINESS_SUMMARY_MAX_CHARS].rstrip() + LONG_BUSINESS_SUMMARY_TRUNCATED_SUFFIX
        logger.info(
            "Truncation: dataset=fetch_financials.long_business_summary original_chars=%s truncated_chars=%s",
            original_len, len(val),
        )
data[out_key] = val
```

**google_custom_search:** Same pattern as Brave: cap items to 10, truncate title/url/snippet per item with `truncate_string_to_bytes(..., context="google_custom_search.snippet")` etc., then cap the full response string with `truncate_string_to_bytes(out, MAX_RESPONSE_STRING_BYTES, ..., context="google_custom_search.response", include_size_signal=False)`.

---

## 5. LLM Behavior When Detecting Truncated Datasets

Silent truncation is avoided in two ways.

### 5.1 Inline signal in content

- **Per-field truncation:** The model sees text like `"... [truncated, 847 chars total]"` at the end of a snippet or description. It knows that (1) content was shortened, and (2) the original length, so it can qualify its analysis (e.g. “based on the excerpt provided”) or suggest following the link.
- **Replacement message:** When `truncate_strings_for_llm` replaces a whole string, the value is `"value exceeds size limit (X bytes, max Y) [content truncated for context limit]"`. The model clearly sees that the field was truncated for context limits.

### 5.2 Report-level disclaimer

- **Flag:** Tools that can truncate (e.g. Reddit) set `truncation_applied: true` on their return. That flows into `session.state.stock_data.ticker.reddit` (or news, depending on how the collector merges).
- **Schema:** The report schema includes an optional `content_disclaimer: str | None`. The report_synthesizer prompt instructs: if `reddit.truncation_applied` is true, or news/source content contains `"value exceeds size limit"` or `"response truncated"`, set `content_disclaimer` to the exact paragraph: *“The content is reduced by AI from its original size, please follow the link to check the original content. This may also affect the accuracy of the analysis, remember this is for entertainment only.”*
- **Behavior:** The LLM (report_synthesizer) therefore (1) sees truncated content with inline markers, (2) sees the `truncation_applied` flag or truncation phrases, and (3) outputs the disclaimer in the report so end users are informed.

---

## 6. Observability: Logging and Future Metrics

### 6.1 Logging (current)

Every truncation is logged at **INFO** with the same logger as cache (`tools.logging_utils.logger`), so it appears in the same system logs as “Cache HIT” / “Cache PUT.”

**Format:**

- From `truncate_string_to_bytes`:  
  `Truncation: dataset=<context> original_bytes=<N> truncated_bytes=<M>`
- From `_truncate_string`:  
  `Truncation: dataset=<tool_name.path> original_bytes=<N> truncated_bytes=<M>`
- From `fetch_financials` (long_business_summary):  
  `Truncation: dataset=fetch_financials.long_business_summary original_chars=<N> truncated_chars=<M>`

**Examples:**

```
Truncation: dataset=RedditPostEntry.snippet original_bytes=70000 truncated_bytes=2003
Truncation: dataset=brave_search.response original_bytes=55000 truncated_bytes=50000
Truncation: dataset=fetch_financials.long_business_summary original_chars=1800 truncated_chars=512
```

So there is full visibility on *what* was truncated and *how much*.

### 6.2 Metrics (proposal)

To detect regressions and tune limits:

- **Counters:** e.g. `truncation_events_total{dataset="RedditPostEntry.snippet"}` incremented on each truncation.
- **Size histograms:** e.g. `truncation_original_bytes` / `truncation_truncated_bytes` per dataset (or per tool).
- **Session-level:** After `stock_data_collector` writes to `session.state.stock_data`, log or emit `stock_data_bytes = len(json.dumps(stock_data))` so alerts can fire if it crosses a threshold (e.g. > 50KB).

Logging gives immediate visibility; metrics would allow dashboards and SLOs (e.g. “truncation rate per tool,” “p99 session state size”).

---

## 7. Best Practices and Key Takeaways

### 7.1 Truncate at the source

- Do not rely on prompt instructions to “limit to N items” or “keep summaries short.” The full tool response is already in context. Enforce limits **in the tool** (and in the schema) before the return is cached or written to session state.

### 7.2 Always signal truncation

- Prefer **inline signals** (` [truncated, N chars total]`) and a **report-level disclaimer** over silent truncation. The model and the user should know when content was reduced so analysis can be qualified and links recommended.

### 7.3 Two layers

- **Schema (Pydantic):** Defines the contract and normalizes at construction time; good for known bloat-prone fields and result counts.
- **Last checkpoint (`truncate_strings_for_llm`):** Catches unknowns and malformed data; keeps the overall return dict bounded. Use both.

### 7.4 Context var for “truncation happened”

- Pydantic validators cannot add a new field to the tool return. A **context var** (`_truncation_occurred`) lets both validators and `truncate_strings_for_llm` set a single “truncation happened” flag per tool run, which the tool then exposes as `truncation_applied` for the report.

### 7.5 Log every truncation

- Log dataset/path and original/truncated sizes at INFO so truncation is as visible as cache hits and limits can be debugged and tuned without guessing.

### 7.6 Principle

- **“The LLM should always know when it’s working with incomplete data.”** Silent truncation is worse than large context: with large context the answer can still be accurate; with silent truncation the model may confidently rely on missing information.

---

## Summary

- **Problems:** Unbounded tool returns (Reddit, search, long_business_summary, etc.) blow token count and can break report validation; silent truncation misleads the model.
- **Goals:** Cap all bloat sources at the tool/schema level, use two layers (schema + last checkpoint), and signal truncation to the LLM and user.
- **Risk table:** Updated so every previously high/medium risk source has a concrete mitigation (schema + truncation + signals).
- **Implementation:** `tools/truncate_for_llm.py` (inline signal, replacement message, context var, logging); Pydantic validators in `tool_schemas.py` for Reddit and Brave; tool-level caps in fetch_financials and google_custom_search; report `content_disclaimer` and prompt instructions.
- **Observability:** INFO logs for every truncation; proposal for counters/histograms and session state size.
- **Takeaways:** Truncate at source; always signal; use two layers; use a context var for the truncation flag; log everything; never truncate silently.

Together with [Part 1](how-to-prevent-datasets-bloat-llm-deep-dive-part1.md) (chart base64 stripping), the two parts give a complete approach to preventing dataset bloat from reaching the LLM while keeping the model and users informed when content was reduced.

---

**DISCLAIMER** — Issue discovery, solution design, core implementation, and testing are by the author. Most routine code was written with AI assistance or pair programming and was fully verified or edited by the author.
