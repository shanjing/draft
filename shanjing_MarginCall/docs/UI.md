# MarginCall — UI and API reference for frontends

This doc explains how the ADK server exposes the stock report, what the built-in UI does, and how a custom frontend can consume the data. See also `CLAUDE.md` and `README.md` for project context.

---

## ADK dev UI format

The ADK web UI (`adk web`) processes **event content parts**. It is not limited to one format:

| Part type            | How it’s shown |
|----------------------|----------------|
| **text**             | Rendered as Markdown (when the content is valid markdown) |
| **functionCall** / **functionResponse** | Collapsible tool blocks |
| **inlineData**       | Binary (images, files) |

In MarginCall, the **presenter** currently outputs plain text with Unicode box-drawing and emoji — not full markdown (no `#` headers, no `**bold**`). So the dev UI effectively shows that text as-is. If the presenter emitted real markdown (e.g. `[title](url)` for links), the ADK UI would render it.

---

## What ADK sends over the wire

The project has **two layers** of report data:

### Layer 1: Structured JSON — `report_synthesizer`

- Uses **output_schema=StockReport** (Pydantic schema in `agent_tools/schemas.py`).
- Output is stored in **session.state["stock_report"]**.
- This is the canonical structured data (ticker, rating, sentiment, financials, options, news, reddit, etc.).

### Layer 2: Formatted text — `presenter`

- Reads `session.state` (including `stock_report`) and is instructed to render a plain-text report.
- Output goes to **event.content.parts[0].text** and, via `output_key="presentation"`, to **session.state["presentation"]**.
- This is what users see in the ADK dev UI and CLI.

---

## ADK FastAPI server endpoints

The server is built with `google.adk.cli.fast_api.get_fast_api_app` (see `server.py`). It exposes:

| Endpoint      | Response format                    | Use case              |
|---------------|------------------------------------|------------------------|
| **POST /run** | JSON array of Event objects        | Single batch response  |
| **POST /run_sse** | SSE stream (`data: {event_json}\n\n`) | Real-time streaming |

**Request body** (both endpoints) includes at least:

- `appName` — e.g. your app name
- `userId`, `sessionId` — identity and session
- `newMessage` — e.g. `{ "role": "user", "parts": [{ "text": "Analyze AAPL" }] }`

For full request/response details and optional flags (e.g. `streaming`), see the [ADK API Server Guide](https://github.com/google/adk-docs/blob/main/docs/runtime/api-server.md) (or your local `adk-docs/docs/runtime/api-server.md`).

### Event shape (simplified)

Each event in the stream or in the `/run` array looks roughly like:

```json
{
  "invocationId": "e-...",
  "author": "presenter",
  "content": {
    "parts": [{ "text": "..." }],
    "role": "model"
  },
  "actions": {
    "stateDelta": { "presentation": "..." },
    "artifactDelta": {}
  },
  "turnComplete": true
}
```

- **content.parts[].text** — the formatted report (or any model text).
- **actions.stateDelta** — session state updates (e.g. `presentation`); to get the full **stock_report**, your frontend typically needs to read **session state** after the run (e.g. via a GET session or equivalent if the server exposes it).

---

## Building a custom frontend

You do **not** need to use the presenter’s text for a rich UI.

1. **Read session.state["stock_report"]** after the pipeline completes. That is the full **StockReport** as structured JSON (ticker, company_intro, financials, sentiment, options_analysis, news_articles, reddit_posts, rating, conclusion, etc.).
2. **Render it yourself** — React components, charts, tables, HTML, etc. Use the schema in `agent_tools/schemas.py` as the contract.

The **presenter** is mainly for text-only interfaces (CLI, ADK dev UI). A custom frontend should consume **StockReport** from session state and implement its own layout and formatting.

To do that, ensure your client can obtain session state after a run (e.g. a GET session endpoint or state included in the API response), so you can read `session.state["stock_report"]` reliably.
