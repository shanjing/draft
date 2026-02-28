# Commit messages — feat/enhance_RAG

Use one of the options below depending on whether you want a single commit or a logical split.

---

## Option A: Single commit (all changes)

**Subject (≤72 chars):**

```
feat(rag): rerank, Ollama embed/rerank, Ask CLI, model display, HF offline, UI tweaks
```

**Full message (body):**

```
feat(rag): rerank, Ollama embed/rerank, Ask CLI, model display, HF offline, UI tweaks

RAG pipeline:
- Add cross-encoder reranking (retrieve top-K, rerank to top-N for LLM).
- Support Ollama for embedding and reranking via lib/ollama_embed; no HF
  fallback when Ollama rerank fails (keeps pipeline local).
- Emit ("models", {embed_model, cross_encoder_model, llm_model}) from
  ask_stream before text/error; citations include rerank score.

CLI and config:
- Add scripts/ask.py: RAG from CLI (-q "question", --debug); prints Models
  then answer then citations with [score: x].
- Add scripts/setup_embed_config.py: write DRAFT_EMBED_*, DRAFT_RERANK_*,
  and HF_HUB_OFFLINE=1 to .env. setup.sh gains embed/cross-encoder flow (G/L/S).
- Set HF_HUB_OFFLINE=1 in .env.example and in code (ingest, app, ask, index_for_ai,
  test_pipeline) so Hugging Face stays offline by default.

Tests:
- Add tests/test_pipeline.py: -p/--pair (default, G, L, S), --rebuild,
  same output style as ask.py. Extend test_ask and test_components for
  models event and citations.

UI:
- Ask panel: show Models (embed, encoder, LLM) with collapse; citations
  with rerank score [x], repo/path, snippet; loading dots (red/yellow/green);
  resizable content area and Ask AI panel.
- README: Start the UI (daemon/foreground), Privacy (HF_HUB_OFFLINE, local LLM),
  Using setup.sh, References table.

Docs: docs/RAG_operations.md (defaults, G/L/S, CLI), testing-suites pipeline
section; requirements.txt versions and grouping; lib/log get_logger, configure_cli.
```

---

## Option B: Multiple logical commits

Use these in order so history stays coherent.

---

### Commit 1 — RAG: cross-encoder rerank and Ollama embed/rerank

**Subject:**

```
feat(rag): add cross-encoder rerank and Ollama embed/rerank support
```

**Body:**

```
- Retrieve top-K (10), rerank with cross-encoder or Ollama to top-N (3).
- lib/ollama_embed: embed(), rerank(), is_ollama_embed_model().
- ai_engine: _get_cross_encoder_model(), rerank(); Ollama rerank on
  failure skips rerank (no HF fallback). Citations include score.
- requirements: sentence-transformers, transformers, tokenizers for
  Qwen3; numpy <2.
```

**Files (conceptual):** lib/ai_engine.py, lib/ollama_embed.py (new), lib/ingest.py (logging only if you want it here), requirements.txt.

---

### Commit 2 — Ask stream: models event and citations

**Subject:**

```
feat(rag): emit models event and citations with scores from ask_stream
```

**Body:**

```
- Yield ("models", {embed_model, cross_encoder_model, llm_model}) after
  rerank, before text/error, so UI/CLI can show Models even with no chunks.
- _build_citations includes score; ask_stream yields ("citations", list).
- test_components: expect models event before error when no chunks.
```

**Files:** lib/ai_engine.py, tests/test_components.py.

---

### Commit 3 — CLI: ask.py, index_for_ai, setup_embed_config, .env

**Subject:**

```
feat(cli): add ask.py, setup_embed_config, HF_HUB_OFFLINE in .env
```

**Body:**

```
- scripts/ask.py: -q "question" [--debug], prints Models then answer then
  citations with [score: x]. HF_HOME and HF_HUB_OFFLINE=1.
- scripts/setup_embed_config.py: write DRAFT_EMBED_*, DRAFT_RERANK_*,
  HF_HUB_OFFLINE=1 to .env. Called by setup.sh for embed/cross-encoder.
- scripts/index_for_ai.py: set HF_HUB_OFFLINE=1 after load_dotenv.
- .env.example: add HF_HUB_OFFLINE=1.
```

**Files:** scripts/ask.py (new), scripts/setup_embed_config.py (new), scripts/index_for_ai.py, .env.example.

---

### Commit 4 — setup.sh embed/cross-encoder flow

**Subject:**

```
feat(setup): embed and cross-encoder config flow with G/L/S presets
```

**Body:**

```
- do_config_embed_flow: suggest Qwen3 pairs, offer Ollama pull; write
  choices via setup_embed_config.py. show_current_state shows Embed and
  Cross-encoder from .env.
```

**Files:** setup.sh.

---

### Commit 5 — Pipeline test and test updates

**Subject:**

```
test: add test_pipeline.py with pair/rebuild, update test_ask and test_components
```

**Body:**

```
- tests/test_pipeline.py: -p/--pair (default, G, L, S), --rebuild,
  HF_HUB_OFFLINE=1; output matches ask.py (Models, answer, citations).
- test_ask: POST /api/ask, models/citations as needed.
- test_components: models event when no chunks.
```

**Files:** tests/test_pipeline.py (new), tests/test_ask.py, tests/test_components.py.

---

### Commit 6 — UI: models, citations, resize, loading

**Subject:**

```
feat(ui): Ask panel models/citations, resize handles, loading dots
```

**Body:**

```
- Models section (collapsible) with embed, encoder, LLM; citations with
  score [x], repo/path, snippet. app.py forwards llm_model in models event.
- Content area and Ask AI panel resizable; loading dots (red/yellow/green).
- index.html, app.js, style.css.
```

**Files:** ui/app.py, ui/static/index.html, ui/static/app.js, ui/static/style.css.

---

### Commit 7 — Logging and ingest default

**Subject:**

```
chore: get_logger, configure_cli, HF_HUB_OFFLINE default in ingest
```

**Body:**

```
- lib/log: get_logger(name), configure() on root logger, configure_cli()
  for message-only CLI output.
- lib/ingest: setdefault HF_HUB_OFFLINE=1; use get_logger for progress.
```

**Files:** lib/log.py, lib/ingest.py.

---

### Commit 8 — Docs and README

**Subject:**

```
docs: RAG_operations, testing-suites, README Privacy and setup
```

**Body:**

```
- docs/RAG_operations.md: default models, G/L/S, CLI (index, ask, pipeline).
- docs/testing-suites.md: pipeline test section with pairs and examples.
- README: Start the UI, Privacy (HF_HUB_OFFLINE, local LLM), Using setup.sh,
  References table.
```

**Files:** docs/RAG_operations.md (new), docs/testing-suites.md, README.md.

---

### Commit 9 — Other

**Subject:**

```
chore: add .claude/settings.json
```

**Body:** (optional) Add or update Claude Code project settings.

**Files:** .claude/settings.json.

---

## One-liner for Option A (copy-paste)

```text
feat(rag): rerank, Ollama embed/rerank, Ask CLI, model display, HF offline, UI tweaks

RAG pipeline: cross-encoder rerank; Ollama embed/rerank (no HF fallback); models event and citations with score. CLI: ask.py, setup_embed_config, HF_HUB_OFFLINE in .env and code. Setup: embed flow G/L/S. Tests: test_pipeline -p/--rebuild. UI: Models/citations, resize, loading dots. Docs: RAG_operations, Privacy, setup.
```
