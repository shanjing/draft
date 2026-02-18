**Testing layers**

There are two layers of tests: **infrastructure** (fast, no LLM) and **agentic** (evals that call the model). In CI/CD, run infrastructure tests in the main build; run agentic evals in a separate job or gate (e.g. with API key, or on schedule). Decoupling them keeps the build fast and makes both layers more productive. Agentic evals also support **model selection**: run the same eval set against different LLMs to compare routing, trajectory, and response quality before committing to a model.

**Infrastructure / application build**

- Smoke test (check_env.py): agent wiring, imports, config validation
- Unit tests (pytest): schemas, cache, tools, truncation — runs offline, no API keys
- Manual integration: `python -m main run -i "analyze GOOGL"` — verifies full pipeline (often run by hand or in a separate release check)

**Agentic / LLM evaluation**

- **Agent evals (ADK):** test files (`.test.json`) under `evals/`; criteria via `evals/test_config.json`; run via pytest `tests/test_agent_evals.py` (marked `integration`, needs API key), CLI `adk eval stock_analyst evals/`, or `adk web` Eval tab. To skip evals: `pytest -m "not integration"`. See **docs/AIEvalsPlan.md**.
- Future: rubric-based report quality, token budget assertions, user simulation (conversation scenarios)