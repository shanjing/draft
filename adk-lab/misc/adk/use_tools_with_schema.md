# Using `output_schema` with Tools in Google ADK

## 1. What is `output_schema`?

`output_schema` is a parameter on `LlmAgent` (or its alias `Agent`) that forces the LLM to produce a response conforming to a Pydantic `BaseModel` class.

```python
from pydantic import BaseModel, Field

class BookData(BaseModel):
    title: str = Field(description="Book title.")
    author: str = Field(description="Author name.")
    average_rating: float = Field(ge=1.0, le=5.0, description="Average rating.")

agent = Agent(
    name="my_agent",
    model="gemini-3-pro-preview",
    output_schema=BookData,
    ...
)
```

### Is the output strict JSON?

Yes. When `output_schema` is set, the model is constrained to output **only** valid JSON matching the schema. No free text, no markdown, no commentary — just the JSON object. The Gemini API enforces this at the decoding level via `response_schema`.

### Benefits

- **Type safety**: Pydantic validates field types, constraints (`ge=`, `le=`, `Literal`), and required fields before the data reaches your code.
- **Reliable downstream parsing**: Downstream agents or application code receive a validated `dict`, not a string that might contain malformed JSON.
- **Eliminates prompt fragility**: Without `output_schema`, you rely on instructions like "output ONLY JSON" which the LLM can ignore. With it, the format is enforced by the API.
- **Self-documenting**: The schema class serves as both the contract and the documentation for what the agent produces.

### Use cases

- Agents that produce structured reports (e.g., stock analysis, data summaries)
- Multi-agent pipelines where Agent B needs to read Agent A's output reliably
- Any scenario where downstream code needs to `json.loads()` the result

---

## 2. `output_schema` + `output_key` on the Same Agent

When both are set on the same agent, `output_key` stores the **Pydantic-validated dict** (not raw text) into `session.state`.

Here is the actual ADK source code that handles this (from `llm_agent.py`, lines ~800-813, ADK version 1.21):

```python
if self.output_key:
    result = ''.join(
        part.text
        for part in event.content.parts
        if part.text and not part.thought
    )
    if self.output_schema:
        # Validate JSON against the Pydantic model, then convert to dict
        result = self.output_schema.model_validate_json(result).model_dump(
            exclude_none=True
        )
    event.actions.state_delta[self.output_key] = result
```

The flow:

| Step | What happens |
|------|-------------|
| LLM responds | Raw JSON string: `'{"title": "Dune", "average_rating": 4.5}'` |
| `model_validate_json()` | Pydantic parses and validates types, constraints, required fields |
| `model_dump()` | Converts validated Pydantic model to a Python `dict` |
| `state_delta[output_key]` | Stores the `dict` in `session.state` |

Without `output_schema`, `output_key` stores the **raw text string**. With it, you get a **validated dict** — a significant difference for multi-agent pipelines.

---

## 3. Test Case: Book Search → Recommendation Pipeline

> Reference: `misc/adk/tools_schema.py`

### Schemas

```python
class Review(BaseModel):
    user: str = Field(description="Username of the reviewer.")
    comment: str = Field(description="The review comment.")
    rating: int = Field(ge=1, le=5, description="Rating from 1 to 5 stars.")

class BookData(BaseModel):
    title: str
    author: str
    category: str
    year_published: int
    reviews: list[Review]
    average_rating: float = Field(ge=1.0, le=5.0)

class BookRecommendation(BaseModel):
    title: str
    author: str
    average_rating: float = Field(ge=1.0, le=5.0)
    recommendation: str        # MUST READ, RECOMMENDED, MIXED, or SKIP
    reasoning: str             # 2-3 sentences referencing reviews
    best_for: str              # Target audience
```

### Tool

A `search_book(query)` function that returns one of three fake books with nested review data (author, category, year, and 2 reviews each with user/comment/rating).

### Agent setup

```python
# Agent A: Has BOTH tools and output_schema
book_searcher = Agent(
    tools=[search_book],
    output_schema=BookData,       # Schema enforced
    output_key="book_data",       # Stored as validated dict in session.state
)

# Agent B: Has output_schema only, NO tools
book_recommender = Agent(
    output_schema=BookRecommendation,
    output_key="recommendation",  # Reads book_data from session.state
)

# Pipeline
pipeline = SequentialAgent(sub_agents=[book_searcher, book_recommender])
```

### Results (gemini-3-pro-preview)

| Book | Avg Rating | Recommendation | Correct? |
|------|-----------|----------------|----------|
| Dune | 4.5 | MUST READ | Yes |
| The Great Gatsby | 2.5 | MIXED | Yes |
| Sapiens | 4.0 | RECOMMENDED | Yes |

Key observations:
- `tools` + `output_schema` on the **same agent** worked on `gemini-3-pro-preview` (previously failed on older models).
- `session.state["book_data"]` contained a **validated dict** (not a string), with nested `reviews` as a list of dicts.
- The recommender correctly read the structured data and produced schema-conforming recommendations.
- The LLM correctly computed `average_rating` by averaging review ratings (business logic from instruction, not schema).

---

## 4. LLM Behavior When `output_schema` is Set

### How Gemini handles it

When ADK sends `output_schema` to the Gemini API, two things happen depending on the platform:

**Vertex AI (Gemini 2+):** The schema is sent as `response_schema` in the API request. The model is constrained at the **token decoding level** — it physically cannot generate tokens that violate the schema.

**Google AI (non-Vertex):** ADK uses a workaround. It injects a synthetic tool called `set_model_response` whose input schema matches your Pydantic model, and appends this instruction automatically:

> *"IMPORTANT: You have access to other tools, but you must provide your final response using the set_model_response tool with the required structured format. After using any other tools needed to complete the task, always call set_model_response with your final answer in the specified schema format."*

### How much weight do instructions carry?

| Instruction content | Weight when `output_schema` is set |
|---|---|
| "Output as JSON" / "Match the schema" | **None** — redundant, ADK already enforces this |
| "No commentary, no markdown" | **None** — schema enforcement prevents free text |
| "Calculate X by doing Y" | **Full** — schema defines structure, not computation logic |
| "Use tool Z to fetch data" | **Full** — schema doesn't control tool invocation |
| "If data is missing, use default 0" | **Full** — business rules for edge cases |

**Rule of thumb:** When `output_schema` is set, your instruction should focus on **what values to compute and why** (business logic), not **how to format the output** (structure). The schema handles structure; the instruction handles logic.

---

## 5. Best Practices

### When to use `output_schema`

- **Multi-agent pipelines** where the next agent needs to reliably parse the previous agent's output.
- **API-facing agents** where the response feeds into application code (not shown to a user).
- **Data extraction tasks** where you need specific fields in specific types.

### When NOT to use it

- **Conversational agents** (chatbots, assistants) — free-form text is the point.
- **Agents with `tools`** on older models — Gemini 2.0 and below reject `tools` + `output_schema` together (though Gemini 3+ and Vertex AI support it).
- **Presenter/display agents** — if the agent's job is to render a human-readable report with formatting, emoji, and prose, a schema constrains it unnecessarily.

### Guidelines

1. **Pair with `output_key`** — `output_schema` without `output_key` validates the output but doesn't persist it. Always set both for pipeline agents.

2. **Don't duplicate schema instructions** — If `output_schema=MyModel` is set, do NOT add "output JSON matching MyModel" to the instruction. ADK already handles this. Redundant instructions waste tokens.

3. **Use Field descriptions** — Pydantic `Field(description=...)` values are sent to the model as part of the schema. Write clear descriptions — they guide the LLM on what each field should contain.

4. **Keep schemas flat when possible** — Deeply nested schemas (3+ levels) increase the chance of the LLM making structural errors. If nesting is needed, define each level as its own `BaseModel` class.

5. **Use `Literal` for enums** — For fields with fixed options (e.g., `recommendation: Literal["Buy", "Sell", "Hold"]`), use `Literal` types. The model is constrained to only produce these exact values.

6. **Don't over-schema** — Not every agent needs `output_schema`. The rule: if a human reads the output, skip the schema. If code reads the output, use the schema.

7. **Test with `session.state` inspection** — Always verify the stored value's type (`dict` vs `str`) in session state. A common bug is expecting a dict but getting a string because `output_schema` wasn't set.

---

## 6. Should Tool Functions Share Schemas with the LLM?

**No.** Tool-level schemas and LLM output schemas serve different purposes and should be kept separate.

### Why they differ

| | Tool function return | LLM `output_schema` |
|---|---|---|
| **Producer** | Your Python code | The LLM |
| **Purpose** | Raw data retrieval | Analyzed / summarized output |
| **Content** | Everything the API returns | Curated fields the report needs |
| **Computed fields** | None (raw data) | Yes (`average_rating`, `sentiment_summary`) |
| **Extra metadata** | Often (`status`, `timestamp`, `error`) | Rarely |

Example from our test:

```python
# Tool returns raw data — no computed fields, has extra metadata
def search_book(query: str) -> dict:
    return {"status": "found", "title": "Dune", "reviews": [...]}

# LLM schema has computed fields the tool can't produce
class BookData(BaseModel):
    title: str
    reviews: list[Review]
    average_rating: float  # ← Computed by LLM from review ratings
```

If the tool returned `BookData`, it would need to compute `average_rating` itself — mixing data fetching with analysis logic.

### Real-world example: MarginCall

In our stock analysis project, `fetch_options_analysis()` returns a deeply nested dict with raw data:

```python
{
    "put_call_ratio": {"pcr_volume": 0.495, "total_call_oi": 148000, ...},
    "max_pain": {"strike": 265.0, "distance_pct": 4.95},
    "unusual_activity": {"count": 40, "top_contracts": [...]},
    "implied_volatility": {"iv_mean": 27.45, "hv30": 21.96, ...}
}
```

The `OptionsAnalysis` schema flattens and summarizes this for the report:

```python
class OptionsAnalysis(BaseModel):
    pcr_volume: float           # Flattened from nested dict
    unusual_activity_summary: str  # LLM-generated summary from raw contracts
    options_summary: str         # 2-3 sentence analysis — tool can't write this
```

The tool returns **data**. The schema defines **presentation**. They shouldn't be the same class.

---

## 7. Should Tool Functions Use Schemas At All?

**Yes** — but their own schemas, not the LLM's.

### The problem with bare dicts

Most tool functions today return untyped `dict`:

```python
def fetch_stock_price(ticker: str) -> dict:
    return {"status": "success", "ticker": ticker, "price": current_price}
```

This has real engineering costs:
- **No autocomplete** — IDE can't help; `result["prce"]` is a silent bug
- **No validation** — if `current_price` is `None`, it passes silently and breaks downstream
- **No documentation** — what keys exist? what types? read the function body
- **No refactoring safety** — rename `"price"` to `"current_price"` and nothing warns you

### What tool-level schemas look like

```python
from typing import Literal
from pydantic import BaseModel

class StockPriceResult(BaseModel):
    status: Literal["success", "error"]
    ticker: str
    price: float
    timestamp: str
    error_message: str | None = None

def fetch_stock_price(ticker: str) -> StockPriceResult:
    ...
    return StockPriceResult(
        status="success",
        ticker=ticker,
        price=current_price,     # Pydantic raises immediately if None
        timestamp=current_time,
    )
```

Benefits:
- **Fail fast** — bad data raises at the tool, not 3 agents downstream
- **IDE support** — `result.price` autocompletes, `result.prce` is a red squiggle
- **Type checking** — mypy/pyright catches type mismatches
- **Self-documenting** — the class IS the API contract

### When to add them

Add tool-level schemas when the return shape has **stabilized**. During rapid prototyping, bare dicts are fine for iteration speed. Once a tool's return structure stops changing, formalize it.

### Architecture: two schema layers

```
agent_tools/
├── schemas.py              # LLM output schemas (StockReport, SentimentAnalysis, ...)
├── tool_schemas.py         # Tool return schemas (StockPriceResult, VIXResult, ...)  ✓ IMPLEMENTED
├── fetch_stock_price.py    # Returns StockPriceResult.model_dump()
├── fetch_vix.py            # Returns VIXResult.model_dump()
├── fetch_financials.py     # Returns FinancialsResult.model_dump(exclude_none=True)
├── fetch_options_analysis.py  # Returns OptionsAnalysisResult.model_dump()
└── ...                     # All 8 tool functions validated through schemas
```

- **`schemas.py`** — what the LLM produces (report structure, analyzed output)
- **`tool_schemas.py`** — what tool functions return (raw data contracts)
- No coupling between them. Schema changes in one don't affect the other.

### Summary

| Question | Answer |
|----------|--------|
| Should tools share schemas with `output_schema`? | **No** — different purposes, different layers |
| Should tools use their own schemas? | **Yes** — for validation, IDE support, documentation |
| When to add tool schemas? | When the return shape stabilizes (post-prototyping) |
| Where to put them? | Separate file (`tool_schemas.py`), not in the LLM schemas file |

---

## 8. Pydantic Validation — What's Free vs. What Needs Constraints

When a tool function returns `SchemaClass(...).model_dump()`, Pydantic validates
**at construction time** — before `.model_dump()` is ever called. If the data is
invalid, a `ValidationError` is raised immediately, preventing bad data from
propagating through the pipeline.

### What Pydantic validates automatically (no constraints needed)

These checks happen just by declaring the field type:

| Check | Example | What happens |
|-------|---------|-------------|
| **Type mismatch** | `price="not a number"` on a `float` field | `ValidationError` — wrong type |
| **Missing required field** | Omitting `ticker` when it has no default | `ValidationError` — field required |
| **Nested model structure** | `macd={"line": 1.0}` missing `signal` and `histogram` | `ValidationError` — missing fields in `MACDValues` |
| **None on non-Optional** | `price=None` on a `float` field | `ValidationError` — None not allowed |
| **Wrong collection type** | `expirations_analyzed="2025-01-17"` on a `list[str]` field | `ValidationError` — expected list |

```python
class StockPriceResult(BaseModel):
    price: float          # "hello" → ValidationError (type)
    ticker: str           # omitted  → ValidationError (required)
```

These are **free** — you get them just by using Pydantic. This alone catches a
large class of bugs: typos in field names, `None` leaking from failed API calls,
wrong data shapes from upstream changes.

### What requires explicit constraints

Value **ranges**, **lengths**, and **patterns** are NOT checked automatically.
You must declare them via `Field()` parameters:

| Constraint | Syntax | Use case |
|-----------|--------|----------|
| **Minimum value** | `Field(ge=0)` | Prices, counts, ratios (no negatives) |
| **Maximum value** | `Field(le=100)` | Percentages, scores capped at 100 |
| **Range** | `Field(ge=0, le=100)` | RSI (0-100), confidence percent |
| **Minimum length** | `Field(min_length=1)` | Non-empty ticker strings |
| **Maximum length** | `Field(max_length=10)` | Ticker symbols |
| **Regex pattern** | `Field(pattern=r"^[A-Z]{1,5}$")` | Strict ticker format |
| **Allowed values** | `Literal["Buy", "Sell", "Hold"]` | Enum-like constraints |

```python
class StockPriceResult(BaseModel):
    price: float = Field(..., ge=0)         # -5.0 → ValidationError
    ticker: str = Field(..., min_length=1)   # ""   → ValidationError

class CNNFearGreedResult(BaseModel):
    score: int = Field(..., ge=0, le=100)    # 150  → ValidationError
```

Without `ge=0`, a negative stock price passes silently. Pydantic only checks
that it's a valid `float`, not that it makes business sense.

### When validation fires in the tool pipeline

```
Tool function called
    ↓
Schema constructed: StockPriceResult(ticker="AAPL", price=-5.0)
    ↓                              ← ValidationError raised HERE
.model_dump() called
    ↓
@cached decorator caches result
    ↓
Dict returned to LLM via session.state
```

The error fires **before** the data is cached or sent to the LLM. This is the
key benefit — bad data from an API (yfinance returning `None`, a negative value
from a parsing bug, a missing field after a library update) gets caught at the
source, not 3 agents downstream in the report_synthesizer.

### Practical guidance

| Scenario | Recommendation |
|----------|---------------|
| Field must not be negative | Add `ge=0` |
| Field is a bounded score | Add `ge=0, le=100` |
| Field is a ratio (0-1) | Add `ge=0, le=1` |
| Field is an enum-like string | Use `Literal["A", "B", "C"]` |
| Field can legitimately be None | Use `float \| None = None` (Optional) |
| Field has a known format | Add `pattern=` regex |
| Unsure about valid range | Skip constraints initially, add after observing real data |

**Rule of thumb**: add constraints when you know the valid range. Don't guess —
an overly tight constraint (e.g., `le=1000` on stock price) can break on
legitimate data (BRK.A trades above $600,000). Start with type safety, add
range constraints as you gain confidence in the data boundaries.
