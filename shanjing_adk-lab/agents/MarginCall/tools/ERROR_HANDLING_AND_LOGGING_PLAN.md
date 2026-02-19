# Plan: Exception Handling, Logging, and Timeouts (CLI + UI)

## Goals

- **Classify and log** agent failures, tool errors, 500/API errors, and timeouts in one place.
- **CLI**: Keep and extend current `tools/logging_utils` (and runner) so debug and errors are visible in terminal.
- **UI**: Use the same logging (no click-only) so when the app runs under the ADK web server, errors appear in server logs (stderr) and can be inspected.
- **Timeouts**: Configurable and not too sensitive (e.g. 120s default for LLM calls).

---

## 1. Failure taxonomy

| Type | Source | Example |
|------|--------|--------|
| **Tool error** | Tool returns `status: "error"` or raises | `fetch_reddit` HTTP error, `brave_search` not found |
| **LLM / API error** | LiteLLM or provider | 500 from Ollama, `APIConnectionError`, XML parse error |
| **Timeout** | LLM request or runner | `TimeoutError`, `asyncio.TimeoutError`, provider timeout |
| **Agent failure** | Agent step (e.g. output_schema validation, pipeline step) | report_synthesizer output invalid JSON, presenter gets no `stock_report` |

---

## 2. Where to handle and log

### 2.1 Runner (CLI and UI entry point)

- **Place**: `tools/runner_utils.py` — `execute_agent_stream`.
- **Behavior**:
  - Wrap `runner.run_async(...)` in try/except.
  - On exception:
    - Classify: timeout vs API/connection vs other.
    - Log once with **structured fields** (see §3): `session_id`, `error_type`, `message`, optional `agent_name` if available from event/context.
    - Re-raise so CLI `main.py` can still show a user-facing message and exit 1.
  - Do **not** swallow exceptions; logging is additive.

### 2.2 CLI entry (main.py)

- **Current**: `except Exception as e: ... click.secho(...); if debug: traceback.print_exc()`.
- **Add**: Call `logger.exception(...)` (or equivalent) in the exception path so that **even when not in debug**, a stack trace is written to the log (stderr). This helps both CLI and UI (when UI runs the same app, server stderr gets the trace).

### 2.3 Tools that return `status: "error"`

- **Place**: Individual agent_tools (e.g. `fetch_reddit`, `fetch_financials`, `invalidate_cache`) or a shared helper.
- **Behavior**: When a tool is about to return `{"status": "error", ...}`, log at **WARNING** (or ERROR) with a single line: tool name, ticker/args if any, and short message. Use the same logger as the rest of the app (e.g. `tools.logging_utils.logger` or `tools.debugging_utils`).
- **Optional**: One helper in `tools/debugging_utils.py`, e.g. `log_tool_error(tool_name, message, **kwargs)`, and call it from each tool’s `except` or before `return {"status": "error", ...}`.

### 2.4 Timeouts (don’t be too sensitive)

- **LLM request timeout**: Configure at the **model wrapper** (e.g. LiteLLM) or via env. Suggested default: **120 seconds** for completion calls (report_synthesizer has large context). Env: e.g. `REQUEST_TIMEOUT_SECONDS=120` in `.env`, read in `tools/config.py`, and pass into the LiteLLM client if supported.
- **Runner-level timeout**: Optional: wrap the entire `runner.run_async` in `asyncio.wait_for(..., timeout=...)` with a value **larger** than the LLM timeout (e.g. 300s) so the run doesn’t hang forever. Log on timeout with `error_type=timeout` and `session_id`.
- **Avoid**: Very short per-tool timeouts (e.g. 5s) that could cause false failures under load.

---

## 3. Structured logging format

Use a **consistent prefix or structure** so logs are grep-able and parseable:

- **Suggestion**: `[MarginCall] type=<error_type> agent=<name> tool=<name> session_id=<id> message=<short message>`
- **error_type**: one of `tool_error | llm_error | timeout | agent_error | validation_error`.
- **agent** / **tool**: only when applicable (e.g. for tool errors, set `tool=...`).

Implement in a small **tools/debugging_utils.py** (or under logging_utils):

- `log_agent_failure(agent_name, error_type, message, session_id=None, exc_info=False)`
- `log_tool_error(tool_name, message, session_id=None, **kwargs)`
- `log_llm_error(message, session_id=None, exc_info=True)`  
  Each uses the app’s main logger (e.g. `logging_utils.logger`) and writes a single line (or two with traceback when `exc_info=True`). No `click.secho` in these so that **UI** (server stderr) gets the same lines.

---

## 4. CLI-specific behavior (existing + enhancements)

- **tools/logging_utils.py**:
  - Keep `log_event(event)` and `log_session_state(...)` for **debug** mode (click output).
  - In `log_event`, if `event.error` is present, **also** call `logger.error(...)` with the same message so the error is in the log stream even when not using click (e.g. when run under the UI server).
- **tools/runner_utils.py**:
  - In the `except` block around `runner.run_async`, call the new structured logger (e.g. `log_agent_failure` or `log_llm_error`) with `session_id`, then re-raise.
- **main.py**:
  - In `except Exception`, add `logger.exception("Run failed")` (or equivalent) so stack trace is always in logs; keep `click.secho` for user-facing message.

---

## 5. UI logging

- The **ADK web UI** runs the same app (same `Runner`, same `execute_agent_stream` if that’s what the server uses, or its own loop over the same runner). It does **not** use `click` for output.
- **Strategy**: All failure and error reporting goes through the **logger** (e.g. `logging_utils.logger` or `debugging_utils`). Then:
  - When the app is run via **CLI**, logs go to stderr and the terminal.
  - When the app is run via **ADK web server**, the server’s process stderr captures the same logs (and the server’s own “Error in event_generator” traceback).
- **No separate “UI logging” implementation** is required; ensure no error path relies **only** on `click.secho`, so the UI process still gets the same log lines.

---

## 6. Config (tools/config.py)

- Add optional env:
  - `REQUEST_TIMEOUT_SECONDS`: default `120` (used for LLM completion timeout if the model wrapper supports it).
  - `RUNNER_TIMEOUT_SECONDS`: optional, default `300` or unset (if we add a top-level runner timeout).
- Pass these into the LiteLLM client / runner where applicable.

---

## 7. Implementation order (recommended) — DONE

1. **Extended `tools/logging_utils.py`** with `log_agent_failure`, `log_tool_error`, `log_llm_error` (structured format, logger only).
2. **Added timeout config** in `config.py`: `REQUEST_TIMEOUT_SECONDS` (120), `RUNNER_TIMEOUT_SECONDS` (300); runner uses `asyncio.wait_for` when `RUNNER_TIMEOUT_SECONDS > 0`.
3. **In `runner_utils.execute_agent_stream`**: wrapped stream in try/except + optional `asyncio.wait_for`; on exception, classify (timeout / llm_error / agent_error), call structured logger with `session_id`, re-raise.
4. **In `main.py`**: added `logger.exception(...)` in catch-all except; `logger.warning` for `ValueError`.
5. **In agent_tools**: added `log_tool_error` before error returns in `fetch_financials`, `invalidate_cache`, `fetch_stock_price`; other tools can follow the same pattern.
6. **In `log_event`**: when `event.error` is set, also call `logger.error("[MarginCall] type=agent_error ...")` so UI/server stderr gets it.

---

## 8. What “not too sensitive” for timeouts means

- Use **≥ 120s** for LLM completion (report_synthesizer, presenter).
- Use **≥ 300s** for the full run if a runner-level timeout is added.
- Do **not** reduce existing tool HTTP timeouts (e.g. 10s for Reddit) unless there is a good reason; those are for external APIs, not the LLM.

---

## 9. Summary

| Area | Action |
|------|--------|
| **Exceptions** | Classify in runner (timeout, LLM/API, other); log once with session_id and type; re-raise. |
| **Tool errors** | Log at WARNING when returning `status: "error"` (shared helper or per-tool). |
| **Logging** | One structured format; use logger only (no click-only for errors) so CLI and UI both get logs. |
| **CLI** | Keep click for debug; add logger.exception in main and logger.error in log_event for errors. |
| **UI** | Rely on same logger; ensure server stderr captures it. |
| **Timeouts** | 120s LLM default, 300s runner if used; configurable via env. |
