# Changelog — feat/enhance_RAG

Detailed change log for the RAG enhancement branch (vs `main`). Use this for release notes or review.

---

## Summary

This branch adds cross-encoder reranking, Ollama-based embedding/reranking, a dedicated Ask CLI, configurable model pairs (G/L/S), and UI improvements for the Ask (AI) panel (model display, citations with scores, resizable layout, loading indicator). It also enforces **HF_HUB_OFFLINE=1** and documents **Privacy** so Draft can run fully locally.

---

## 1. RAG pipeline and models

### 1.1 Cross-encoder reranking

- **lib/ai_engine.py**
  - Introduced **reranking** step: after vector search, chunks are scored with a cross-encoder and trimmed to top-N for the LLM.
  - New constants: `RETRIEVAL_TOP_K = 10`, `RERANK_TOP_N = 3`, `CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"`.
  - `_get_cross_encoder_model()` reads `DRAFT_CROSS_ENCODER_MODEL` from env; cross-encoder is loaded and cached via `_get_cross_encoder()`.
  - **Ollama rerank:** when `DRAFT_RERANK_PROVIDER=ollama`, reranking uses `lib.ollama_embed.rerank` (Ollama `/api/rerank`). On Ollama failure (e.g. 404), no fallback to Hugging Face — rerank is skipped and chunks get placeholder scores so the pipeline stays local.
  - `retrieve()` now returns more candidates (top_k=10 by default); `rerank()` reduces to top 3 for context.

### 1.2 Ollama embedding and reranking

- **lib/ollama_embed.py** (new)
  - `embed(model_name, texts, batch_size=1)`: calls Ollama `/api/embeddings`, returns list of embedding vectors for use with ChromaDB.
  - `rerank(model_name, query, documents, top_n=3)`: calls Ollama `/api/rerank`, returns list of `{index, document, score}`; normalized for downstream.
  - `is_ollama_embed_model(name)`: detects Ollama embedding model names for provider selection.

- **lib/ai_engine.py**
  - `retrieve()` checks `DRAFT_EMBED_PROVIDER` (from collection metadata or env). When `ollama`, uses `lib.ollama_embed.embed` for the query and Chroma’s `query(query_embeddings=..., include=[...])`; otherwise uses SentenceTransformer.
  - Rerank step uses Ollama when `DRAFT_RERANK_PROVIDER=ollama` and the configured cross-encoder model name is an Ollama reranker.

### 1.3 Ask stream: models event and citations with scores

- **lib/ai_engine.py**
  - **`ask_stream()`** now yields:
    - **`("models", {...})`** — `embed_model`, `cross_encoder_model`, `llm_model` (resolved from `.env` / provider). Emitted **after** retrieval and rerank, **before** any text or error, so UI/CLI can show “Models” even when there are no chunks.
    - **`("citations", list)`** — each citation includes `score` when rerank produced one (and optional `start_line`, `end_line`, `snippet`).
  - **`_build_citations()`** copies `score` from reranked chunks into citation dicts.
  - LLM model resolution moved earlier so the `models` payload is complete before the empty-chunk check.

### 1.4 Ingest and indexing

- **lib/ingest.py**
  - **HF_HUB_OFFLINE:** `os.environ.setdefault("HF_HUB_OFFLINE", "1")` at top so Hugging Face uses only local/cached assets unless overridden.
  - Progress/logging now uses `lib.log.get_logger(__name__)` and `log.info()` instead of `print()` for consistency with CLI/UI (e.g. `index_for_ai -v` output in system console).
  - No functional change to chunking or Chroma write logic.

---

## 2. CLI and configuration

### 2.1 Ask CLI

- **scripts/ask.py** (new)
  - `ask.py -q "question" [--debug]`: runs RAG (retrieve → rerank → LLM) and prints answer + citations.
  - Loads `.env` from repo root; sets `HF_HOME` to repo `.cache/huggingface` and **`HF_HUB_OFFLINE=1`** by default.
  - Handles SSE-style events from `ask_stream()`: prints **Models** (embed, encoder, LLM), then streamed answer, then **---** and numbered citations with **`[score: x]`** and line ranges when available.
  - Exits with clear error if LLM is not configured.

### 2.2 Index script

- **scripts/index_for_ai.py**
  - Loads `.env`; sets **`HF_HUB_OFFLINE=1`** after `load_dotenv` so indexing is offline by default.
  - No other behavior change.

### 2.3 Embed/config writer

- **scripts/setup_embed_config.py** (new, used by setup.sh)
  - Writes/updates **`.env`** with: `DRAFT_EMBED_MODEL`, `DRAFT_CROSS_ENCODER_MODEL`, `DRAFT_EMBED_PROVIDER`, `DRAFT_RERANK_PROVIDER`.
  - **HF_HUB_OFFLINE:** Ensures **`HF_HUB_OFFLINE=1`** is present in `.env` (adds or overwrites existing line) so RAG stays local.

### 2.4 Environment and dependencies

- **.env.example**
  - Added **`HF_HUB_OFFLINE=1`** and a short comment that Hugging Face runs offline (no network for models).

- **requirements.txt**
  - Grouped into Utilities, RAG, AI; pinned/raised versions where needed.
  - **sentence-transformers** ≥ 4.37.0; **transformers** ≥ 4.51.0 and **tokenizers** ≥ 0.13.2 for Qwen3 embed/reranker support.
  - **numpy** kept `<2` for Chroma/PyTorch compatibility.

---

## 3. Setup script (embed/cross-encoder and LLM)

- **setup.sh**
  - **show_current_state():** Shows **Embed** and **Cross-encoder** from `.env` when present; RAG index line no longer says “freshly baked”.
  - **do_config_embed_flow()** (new): Interactive flow to choose embedding and cross-encoder:
    - If Ollama is available, suggests Qwen3 pairs (Gold: 8b embed + 0.6B reranker; 8B+8B; 0.6B+0.6B) and can pull them.
    - Options: default (sentence-transformers), or Ollama G/L/S. Writes choices via `scripts/setup_embed_config.py` and sets **`HF_HUB_OFFLINE=1`** in `.env`.
  - Main menu extended so “Configure embedding and cross-encoder” can be run; LLM config and RAG index build unchanged in spirit but run after embed config when chosen.
  - No change to sources.yaml or vault handling.

---

## 4. Tests

- **tests/test_pipeline.py** (new)
  - Standalone CLI: build index (optional) and run one Ask. Supports **4 model pairs** via **`-p`/`--pair`**:
    - **default** / **d**: sentence-transformers (embed from `--profile`), cross-encoder `ms-marco-MiniLM-L-6-v2`.
    - **G** (Gold), **L** (8B+8B), **S** (0.6B+0.6B): Ollama embed + reranker; no Hugging Face download when run with Ollama.
  - **`--rebuild`**: rebuilds index from sources.yaml; **default is no rebuild** (use existing index).
  - Sets **`HF_HUB_OFFLINE=1`** after loading `.env`. Output format aligned with `ask.py`: Models (embed, encoder, LLM), then answer, then citations with `[score: x]`.
  - Run from repo root; uses `DRAFT_HOME`/sources.yaml.

- **tests/test_ask.py**
  - Covers **POST /api/ask** (SSE stream) and LLM-ready check; may assert on `models` event and citation structure.

- **tests/test_components.py**
  - **ai_engine:** Asserts that `ask_stream()` yields a **`models`** event (with `embed_model`, `cross_encoder_model`, `llm_model`) even when there are no chunks (then an error event). Ensures rerank/citations behavior is testable.

---

## 5. UI (Ask panel and layout)

### 5.1 Backend

- **ui/app.py**
  - After `load_dotenv`, sets **`os.environ.setdefault("HF_HUB_OFFLINE", "1")`** so the server runs HF offline by default.
  - **SSE `/api/ask`:** Forwards **`llm_model`** in the **`models`** event payload so the frontend can show Embed, Encoder, and LLM.

### 5.2 Frontend: structure and behavior

- **ui/static/index.html**
  - **Models block:** `#ask-models-wrap` with heading “Models” and `#ask-models` (collapsible via chevron).
  - **Citations block:** `#ask-citations-wrap` with heading and `#ask-citations`.
  - **Layout:** Main content wrapped in `.content-wrapper`; **resize handle** `.content-resize` for horizontal resizing of the reading panel. **Ask AI** panel has vertical resize handle `.ask-ai-resize`.
  - **Loading:** `#ask-loading-dots` (three dots) for “waiting for retrieval/LLM” state.
  - Removed footer “Model Used” toggle; Models section is always in DOM but can be collapsed.

- **ui/static/app.js**
  - **Models event:** Fills `#ask-models` with embed, encoder, and LLM; shows the section; supports collapse/expand (chevron, `ask-models-collapsed`).
  - **Citations event:** Renders each citation with rank, **rerank score `[x]`**, repo/path, heading, line range, and snippet; uses `.ask-citation-link` for doc links.
  - **Resize:** `initContentResize()` (horizontal) and `initAskAiResize()` (vertical); persist sizes in localStorage where applicable.
  - **Loading:** Show `#ask-loading-dots` when a question is sent; hide on first `text` or `error` or on stream end.
  - “Index:” label kept in front of Quick rebuild / Deep rebuild.

- **ui/static/style.css**
  - **Models:** `.ask-models-wrap`, `.ask-models-heading`, chevron (▼/▲ when collapsed), `.ask-models-row`, `.ask-models-label`, `.ask-models-value`.
  - **Citations:** `.ask-citations-wrap`, `.ask-citation-item`, `.ask-citation-header`, `.ask-citation-rank`, `.ask-citation-score-label`/`.ask-citation-score-value`, `.ask-citation-link`, `.ask-citation-heading`, `.ask-citation-meta`; card-like layout.
  - **Loading:** `.ask-loading-dots`, `.ask-dot`, `@keyframes ask-dot-blink` (red/yellow/green, staggered).
  - **Layout:** `.content-wrapper`, `.content-resize`, `.ask-ai-resize`; Ask panel flex and max-height/overflow for scroll.
  - **Ask hint row:** `.ask-ai-hint-row` for alignment.

---

## 6. Logging

- **lib/log.py**
  - **get_logger(name):** Returns a logger for the given module (e.g. `get_logger(__name__)`).
  - **configure():** Configures the **root** logger (not only `draft`), so all lib and app loggers propagate; optional format argument.
  - **configure_cli(level):** Uses message-only format for CLI scripts so that subprocess output (e.g. `index_for_ai -v`) stays clean in the system console.
  - **logger** remains as the app-level convenience logger.

---

## 7. Documentation

- **docs/RAG_operations.md** (new)
  - Default models (quick/deep profiles, cross-encoder).
  - Qwen3 pairs (G, L, S): which models, env vars, use cases.
  - CLI: **Build index** (`index_for_ai.py`), **Ask** (`ask.py`), **Pipeline test** (`test_pipeline.py` with `-p`, `--rebuild`, `--profile`). Documents output format (Models, answer, citations with scores).

- **docs/testing-suites.md**
  - Added **Pipeline test** subsection: table of pairs (default, G, L, S), example commands, options (`-p`, `-q`, `--rebuild`, `--profile`, `-v`).

- **README.md**
  - **Start the UI:** Option A (daemon `start.sh`, port), Option B (foreground `serve.py`, port).
  - **Privacy:** New section — Draft sets **`HF_HUB_OFFLINE=1`** in `.env` and in code; local LLM (Ollama) keeps everything on-device; cloud LLM is optional; recommendation to use Ollama + HF_HUB_OFFLINE for maximum privacy.
  - **Using setup.sh:** Five steps (environment, sources.yaml, add sources, configure LLM, build RAG index); mention of embed/cross-encoder and G/L/S; pointer to `docs/RAG_operations.md`.
  - **References:** Renamed from “Engineering”; table of design/operations docs (storage, core, design principles, intelligence layer, RAG design, **RAG operations**, local oracle, testing suites).

---

## 8. Other

- **.claude/settings.json**
  - New or updated Claude Code project settings (if present).

---

## Files changed (overview)

| Area        | Files |
|------------|--------|
| RAG core   | lib/ai_engine.py, lib/ingest.py, lib/ollama_embed.py (new) |
| CLI        | scripts/ask.py (new), scripts/index_for_ai.py, scripts/setup_embed_config.py (new) |
| Setup      | setup.sh |
| Config     | .env.example, requirements.txt |
| Logging    | lib/log.py |
| Tests      | tests/test_pipeline.py (new), tests/test_ask.py, tests/test_components.py |
| UI         | ui/app.py, ui/static/index.html, ui/static/app.js, ui/static/style.css |
| Docs       | README.md, docs/RAG_operations.md (new), docs/testing-suites.md |
| Other      | .claude/settings.json (new) |

---

## Suggested commit strategy

See **COMMIT_MESSAGES.md** for one-commit and multi-commit message options.
