# Plan: AI Evals from Day Zero (Pitfall #6)

This plan addresses the gap “Not starting with AI evals from day zero” by introducing **Google ADK–provided evaluation** using the official evaluate docs and tooling. The full ADK evaluate documentation lives in **`../adk-docs/docs/evaluate/`** (not in this repo); this doc summarizes it and applies it to MarginCall.

---

## 1. ADK evaluate documentation (source of truth)

| Doc | Path | Contents |
|-----|------|----------|
| **Why & how** | `../adk-docs/docs/evaluate/index.md` | Why evaluate agents; two approaches (test file vs evalset); criteria summary; running via web, pytest, CLI |
| **Criteria** | `../adk-docs/docs/evaluate/criteria.md` | All built-in criteria, when to use each, config examples |
| **User simulation** | `../adk-docs/docs/evaluate/user-sim.md` | Conversation scenarios, dynamic user prompts (optional for later) |

**Rules file note:** The current `.cursor/rules/adk-patterns.mdc` does **not** include the full ADK evaluate documentation. It only mentions `adk eval <AGENT> <EVALSET>`. For full details (test file schema, evalset format, criteria, CLI options), use the paths above or the plan below.

---

## 2. ADK-provided tools and conventions

### 2.1 Two ways to run evals (per ADK docs)

1. **Test file approach** (recommended to start)
   - One or more `.test.json` files; each file = one **EvalSet** (one or more eval cases).
   - Fast, good for CI and “unit-test style” agent checks.
   - Schema: Pydantic **EvalSet** / **EvalCase** / **Invocation** (see `adk-python`: `eval_set.py`, `eval_case.py`).
   - Optional: `test_config.json` in the same folder for criteria (defaults: `tool_trajectory_avg_score` 1.0, `response_match_score` 0.8).

2. **Evalset file approach**
   - Single evalset file with multiple sessions; can be more complex and multi-turn.
   - **Caveat:** Evalset-based eval that uses reference responses/tool trajectory can be run locally; **Vertex Gen AI Evaluation Service** is a paid option for richer evals (see index.md).

For “day zero” we use **test files** only (no paid service required).

### 2.2 ADK evaluation entry points

| Tool / method | Use |
|--------------|-----|
| **`AgentEvaluator.evaluate`** (pytest) | `agent_module` = Python module path (e.g. `stock_analyst`); `eval_dataset_file_path_or_dir` = path to a single `.test.json` or a directory that is recursively scanned for `*.test.json`. Loads EvalSet from each file, runs inference, evaluates with criteria from `test_config.json` or default. |
| **`AgentEvaluator.evaluate_eval_set`** | Same idea but you pass an `EvalSet` object and optional `EvalConfig` (e.g. from code). |
| **`adk eval <AGENT_PATH> <EVALSET_FILE_OR_DIR>`** | CLI: `<AGENT_PATH>` = directory containing `__init__.py` that exposes `root_agent` (e.g. `stock_analyst`). Evalset = path to evalset file (or test file). Optional: `--config_file_path`, `--print_detailed_results`. |
| **`adk web`** | Create evals from live sessions (“Add current session”), then run evaluations with configurable criteria in the UI. |

MarginCall’s root agent is in `stock_analyst` (`stock_analyst/__init__.py` → `root_agent`), so:
- **pytest:** `agent_module="stock_analyst"` (run from repo root so `stock_analyst` is importable).
- **CLI:** `adk eval stock_analyst <path_to_test_or_evalset>` (from repo root).

### 2.3 Built-in criteria (use ADK-provided only)

From `../adk-docs/docs/evaluate/criteria.md`:

| Criterion | Reference-based | Use case |
|-----------|-----------------|----------|
| `tool_trajectory_avg_score` | Yes | Regression / workflow: expected tool sequence. Match types: `EXACT`, `IN_ORDER`, `ANY_ORDER`. |
| `response_match_score` | Yes | ROUGE-1 overlap with reference response. |
| `final_response_match_v2` | Yes | LLM-as-judge semantic match to reference. |
| `rubric_based_final_response_quality_v1` | No (rubrics) | Quality when no single reference (e.g. tone, conciseness). |
| `rubric_based_tool_use_quality_v1` | No (rubrics) | Correct tool choice/order by rubric. |
| `hallucinations_v1` | No | Groundedness in context; supports user simulation. |
| `safety_v1` | No | Safety/harmlessness (Vertex; needs GCP). |

**Recommendation from ADK:** For CI/regression use `tool_trajectory_avg_score` and `response_match_score` (fast, predictable). For MarginCall we start with these two; add LLM-judge or rubrics later if needed.

---

## 3. MarginCall-specific plan

### 3.1 Scope (day zero)

- **Root agent routing:** Ensure the root agent chooses the right path (pipeline vs chat vs refresh vs cache stats vs single-tool).
- **Tool trajectory:** For “analyze TICKER” flows, expect `stock_analysis_pipeline` (and optionally correct single-tool calls for Reddit-only, earnings-only, financials-only).
- **Minimal response check:** Either a short reference final response (ROUGE) or a relaxed threshold so we don’t block on wording.

No report-quality or token-budget evals in day zero; those are follow-ups.

### 3.2 Directory layout (use ADK conventions)

- **Eval data:** `evals/` at repo root (or `tests/eval_fixtures/` if you prefer under tests).
- **Test files:** `*.test.json` (each file = one EvalSet; one or more eval cases per file). Filename must end with `.test.json`.
- **Config:** `evals/test_config.json` (optional). If omitted, ADK uses default criteria (tool_trajectory 1.0, response_match 0.8).

### 3.3 Eval cases to add (initial set)

1. **Research / pipeline (A)**  
   - User: e.g. “Tell me about AAPL” or “Analyze GOOGL”.  
   - Expected trajectory: root calls `stock_analysis_pipeline` (and no other root tools).  
   - Match type: `IN_ORDER` or `ANY_ORDER` so we only assert “pipeline was used” (sub-agent tool calls are internal).  
   - Reference final response: short placeholder or skip strict ROUGE (e.g. lower threshold or use only trajectory).

2. **Chat / no tools (B)**  
   - User: “What do you think about the market?” or “How are you?”  
   - Expected trajectory: no tool calls.  
   - Optional: short reference response for `response_match_score`.

3. **Single-tool: Reddit only (E)**  
   - User: “Reddit posts for TSLA.”  
   - Expected trajectory: `fetch_reddit` with appropriate args (e.g. ticker).  
   - Match: `IN_ORDER` or `ANY_ORDER`.

4. **Single-tool: earnings (F)**  
   - User: “When is the next earnings date for AAPL?”  
   - Expected trajectory: `fetch_earnings_date` with ticker.

5. **Single-tool: financials (G)**  
   - User: “Financials for NVDA.”  
   - Expected trajectory: `fetch_financials` with ticker.

6. **Cache stats (D)**  
   - User: “What stocks have we looked at?”  
   - Expected trajectory: `search_cache_stats` (no args).

7. **Refresh (C)**  
   - User: “Refresh AAPL” or “Get me real-time data for TSLA.”  
   - Expected trajectory: `invalidate_cache` then `stock_analysis_pipeline` (order matters → `IN_ORDER`).

Exact `tool_uses` structure must follow ADK’s **Invocation** `intermediate_data.tool_uses`: list of `{ "name": "tool_name", "args": { ... } }` (and optional `id`). Use one invocation per turn; multi-turn can have multiple invocations in one eval case.

### 3.4 test_config.json (ADK-provided criteria)

Example in the same folder as the test files (or parent folder for multi-file):

```json
{
  "criteria": {
    "tool_trajectory_avg_score": {
      "threshold": 1.0,
      "match_type": "IN_ORDER"
    },
    "response_match_score": 0.6
  }
}
```

- Start with `IN_ORDER` for cases where order matters (e.g. refresh); use `ANY_ORDER` for “only these tools must appear.”  
- `response_match_score`: 0.6–0.8 to allow wording variation; tighten later.

### 3.5 Creating test files

- **Option A (recommended):** Run the agent via `adk web`, have a short conversation, then in the UI use **Eval** tab → create or select an eval set → “Add current session” to capture a case. Export or copy the JSON into a `.test.json` and commit under `evals/`.  
- **Option B:** Manually author JSON per ADK schema (see `adk-python`: `eval_set.py`, `eval_case.py`; and sample files under `adk-python/tests/integration/fixture/`).  
- Ensure each file is valid **EvalSet** (eval_set_id, name/description, eval_cases). Each eval case: eval_id, conversation (list of Invocation), session_input (app_name, user_id, state). session_input.app_name must match the app name used at runtime (e.g. from `AGENT_APP_NAME` or `App(name=...)`); use same app_name as in `main.py` / runner so session is compatible.

**If “Add current session” is missing in `adk web`:** (1) **Create or select an eval set first** — the button is often enabled only after you create a new eval set or select one from the list (Eval tab → create/select eval set → then “Add current session”). (2) **Eval extra** — ensure eval dependencies are installed (`pip install "google-adk[eval]"`); without them the Eval tab or add-session API may not work. (3) **Vertex Gen AI Evaluation Service is not required** for adding a session; that paid service is only for running certain evalset-based evaluations in the cloud, not for the local “Add current session” flow.

### 3.6 Running evals

- **pytest (CI):**  
  - From repo root: `pytest tests/test_evals.py -v` (or `tests/integration/test_agent_evals.py`).  
  - Test body: `await AgentEvaluator.evaluate(agent_module="stock_analyst", eval_dataset_file_path_or_dir="evals")`.  
  - This discovers all `*.test.json` under `evals/` and runs them with the config next to the test files.

- **CLI:**  
  - From repo root: `adk eval stock_analyst evals/stock_analyst_routing.test.json --print_detailed_results`  
  - Or a directory: `adk eval stock_analyst evals/` (if CLI supports directory; otherwise point to a single file or list files).

- **Web UI:** Use `adk web` → Eval tab to run evaluations on selected cases with custom thresholds.

### 3.7 Session state (session_input)

For MarginCall, initial state can include `application`, `model_name`, etc., if the runner expects them. Use the same shape as `main.py`’s `initial_state` where relevant. session_input.app_name should match the app name (e.g. from env `AGENT_APP_NAME` or `APP_NAME` in runner_utils). If tests run with a different app name, set it in session_input so the evaluator creates sessions correctly.

---

## 4. Implementation checklist

- [ ] Create `evals/` (or `tests/eval_fixtures/`) and add `test_config.json` with criteria above.
- [ ] Add at least one `.test.json` for pipeline (A) and one for chat (B); optionally one each for (D), (E), (F), (G), (C).
- [ ] Add a pytest test that calls `AgentEvaluator.evaluate(agent_module="stock_analyst", eval_dataset_file_path_or_dir="evals")` (or the chosen path). Mark as integration if it hits the real model/API.
- [ ] Document in `docs/TestingStrategy.md`: eval layer, how to add cases (adk web vs manual), how to run (pytest, adk eval, adk web).
- [ ] Optional: Add a short “Eval” subsection to `.cursor/rules/adk-patterns.mdc` that points to `../adk-docs/docs/evaluate/` and to this plan (`docs/AIEvalsPlan.md`) so future work stays aligned with ADK.

---

## 5. Follow-ups (post–day zero)

- **Report quality:** Use `rubric_based_final_response_quality_v1` or `final_response_match_v2` with a fixed `stock_data` fixture and run report_synthesizer (or full pipeline) to assert structure and key fields.  
- **Token budget:** Custom metric or post-run assertion on token counts (e.g. from run summary / Prometheus) in CI.  
- **User simulation:** For multi-turn flows, add conversation scenarios and use `hallucinations_v1` / `safety_v1` with user simulation (see user-sim.md).  
- **Evalset file:** If we need multi-session or Vertex-backed evals later, add an evalset file and use `adk eval` with that file; keep test files for fast CI.

---

## 6. References

- ADK evaluate index: `../adk-docs/docs/evaluate/index.md`
- ADK criteria: `../adk-docs/docs/evaluate/criteria.md`
- ADK user simulation: `../adk-docs/docs/evaluate/user-sim.md`
- ADK Python EvalSet / EvalCase: `../adk-python/src/google/adk/evaluation/eval_set.py`, `eval_case.py`
- ADK AgentEvaluator: `../adk-python/src/google/adk/evaluation/agent_evaluator.py`
- Sample test files: `../adk-python/tests/integration/fixture/` (e.g. `hello_world_agent/roll_die.test.json`, `home_automation_agent/simple_test.test.json`)
