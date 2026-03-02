# Agentic RAG Design

## Problem

The current `/api/ask` pipeline always runs RAG — every query hits ChromaDB retrieval and cross-encoder reranking regardless of whether the question needs documentation. The system prompt hard-restricts the LLM to "answer only from context," making it useless for general questions, reasoning, or anything not in the indexed docs.

## Solution

Add an **agentic router** — a fast LLM call before the pipeline that classifies each query as `"rag"` or `"direct"`. If `"direct"`, skip retrieval and answer from general knowledge (still framed as a docs assistant). The routing decision is shown in the UI.

---

## Architecture

```
USER QUERY
    ↓
route_query(query)        ← fast LLM call → "rag" | "direct"
    ↓
yield ("route", {mode, reason})   ← new SSE event
    ↓
  "rag" branch                    "direct" branch
    ↓                                 ↓
retrieve → rerank             skip retrieval
    ↓                                 ↓
build context                 DIRECT_SYSTEM_PROMPT
    ↓                                 ↓
SYSTEM_PROMPT                 _ask_direct()
    ↓                                 ↓
yield text + citations         yield text only (no citations)
```

---

## Prompts

### Router prompt (`ROUTER_PROMPT`)

Used for the classification call. Expects a JSON response.

```
You are a query router for a private documentation assistant.
Classify the user's question. Reply with JSON only, no other text:
{"mode": "rag", "reason": "one sentence"}
  OR
{"mode": "direct", "reason": "one sentence"}

Use "rag" when the question asks about specific project details, code, configs,
APIs, architecture, or anything that requires looking up in docs.
Use "direct" when the question is general knowledge, reasoning, math,
writing, or a meta-question that does not need private docs.

Question: {query}
```

### Direct system prompt (`DIRECT_SYSTEM_PROMPT`)

Used when the router chooses the direct path. The LLM is still framed as a docs assistant but is free to use general knowledge.

```
You are a helpful assistant embedded in a private documentation system.
This question can be answered from general knowledge — no specific docs are needed.
Be concise and practical.
```

---

## SSE Event Contract

The existing event types (`models`, `text`, `citations`, `error`) are unchanged. One new event type is added:

| Event | Payload | When |
|-------|---------|------|
| `route` | `{mode: "rag"\|"direct", reason: str}` | Always, fires first |
| `models` | `{embed_model, cross_encoder_model, llm_model}` | Always |
| `text` | `str` | Streamed LLM response fragments |
| `citations` | `list` | RAG mode only (empty list in direct mode) |
| `error` | `str` | On failure |

---

## Implementation Plan

### `lib/prompts.py`
- Add `ROUTER_PROMPT` (classification prompt with `{query}` placeholder)
- Add `DIRECT_SYSTEM_PROMPT` (general-knowledge fallback prompt)

### `lib/ai_engine.py`

**1. Extract `_resolve_llm() -> (provider, model)`**

Refactor the provider/model detection logic currently inline in `ask_stream()` (lines 340–367) into a standalone helper. This is required because `route_query()` needs to know which LLM to call before the rest of the pipeline runs. No behavior change — pure refactor.

**2. Add `route_query(query, provider, model) -> (mode, reason)`**

- Makes a **non-streaming** LLM call using the configured provider
- Parses the JSON response for `mode` and `reason`
- Defaults to `("rag", "fallback")` on any parse or call failure (conservative)
- One implementation per provider, reusing existing client setup patterns

**3. Add `_ask_direct(query, provider, model)` generator**

- Skips retrieve/rerank entirely
- Uses `DIRECT_SYSTEM_PROMPT` as system prompt, raw `query` as user content
- Reuses existing `_stream_claude/gemini/openai/ollama()` functions
- Yields `("text", str)` only — no citations

**4. Modify `ask_stream()`**

```
1. _resolve_llm()                          → (provider, model)
2. route_query(query, provider, model)     → (mode, reason)
3. yield ("route", {mode, reason})
4. yield ("models", {...})                 # unchanged
5. if mode == "direct":
       yield from _ask_direct(...)
       return                              # no citations yielded
6. else:  # "rag"
       ... existing pipeline unchanged
```

### `ui/app.py`

Add `"route"` handling in the `event_stream()` generator:

```python
elif kind == "route":
    yield f"data: {json.dumps({'type': 'route', 'mode': payload['mode'], 'reason': payload['reason']})}\n\n"
```

### `ui/static/index.html`

Add routing indicator element inside `.ask-ai-body`, before `#ask-answer`:

```html
<div id="ask-route" class="ask-route hidden"></div>
```

### `ui/static/app.js`

- Grab `routeEl` in setup
- Clear it at the start of each `runAsk()`
- Handle the `"route"` event in `handleEvent()`:

```javascript
} else if (data.type === 'route') {
    routeEl.textContent = data.mode === 'rag' ? '→ Docs' : '→ Direct';
    routeEl.className = 'ask-route ask-route-' + data.mode;
    routeEl.classList.remove('hidden');
}
```

### `ui/static/style.css`

```css
.ask-route {
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.03em;
  margin-bottom: 0.4rem;
  opacity: 0.75;
}
.ask-route-rag    { color: var(--accent); }
.ask-route-direct { color: var(--fg-muted); }
```

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Router LLM | Same as configured LLM | No extra setup; classification is a single cheap call |
| Router failure | Default to `"rag"` | Conservative — better to over-retrieve than miss docs |
| Direct mode scope | General knowledge, docs-aware tone | User wants LLM to be helpful but stay in character |
| Citations in direct mode | None | No retrieval = nothing to cite |
| User override | None (fully agentic) | Keeps UX simple; override can be added later if needed |
| UI indicator | Small `→ Docs` / `→ Direct` label | Transparency without clutter |

---

## Verification

1. Start the server: `python scripts/serve.py`
2. Ask a **docs question** (e.g. *"How does the pull pipeline work?"*) → expect `→ Docs`, citations shown
3. Ask a **general question** (e.g. *"What is a cross-encoder?"*) → expect `→ Direct`, no citations
4. Ask an **ambiguous question** (e.g. *"What models are supported?"*) → observe routing decision
5. Simulate router failure (bad LLM config) → confirm fallback to RAG, no crash
6. Open browser DevTools → Network → confirm `route` event fires before `text` events in the SSE stream
