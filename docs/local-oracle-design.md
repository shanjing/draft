# Design: The Local Oracle

A RAG-based “Sam Rogers” style assistant over your private draft docs: sharp, direct, contextually aware, and without sending your notes to a public training set.

---

## Goals

- **Answer questions** using only the content of your mirrored `.md` files.
- **Cite sources**: every answer links back to the original docs (and ideally to sections).
- **No leakage**: support a fully local path (embeddings + LLM) so nothing leaves your machine; optionally use Claude API for higher quality.
- **Fits the existing stack**: build on draft’s pull → local files → web UI and re-use the doc viewer and tree.

---

## Architecture Overview

```
                    ┌─────────────────┐
                    │  sources.yaml   │
                    │  pull.py        │
                    └────────┬────────┘
                             │ sync .md
                             ▼
                    ┌─────────────────┐
                    │  draft/.doc_    │
                    │  sources/<repo>  │
                    │  *.md files     │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
  │ Whoosh       │   │ Chunking +   │   │ FastAPI UI   │
  │ (existing)   │   │ Embeddings   │   │ (existing)   │
  └──────────────┘   └──────┬───────┘   └──────┬───────┘
                            │                  │
                            ▼                  │
                     ┌──────────────┐         │
                     │ Vector store │         │
                     │ (Chroma/     │         │
                     │  FAISS)      │         │
                     └──────┬───────┘         │
                            │                  │
                            ▼                  ▼
                     ┌──────────────────────────────┐
                     │  lib/ai_engine.py             │
                     │  Semantic search → LLM        │
                     │  (Claude API or local Qwen)   │
                     └──────────────┬───────────────┘
                                    │
                                    ▼
                     ┌──────────────────────────────┐
                     │  Draft Chat UI               │
                     │  Ask question → streamed      │
                     │  answer + citation links      │
                     └──────────────────────────────┘
```

---

## Phase 1: Ingestion & Vectorization (“Brain” Setup)

### Scope

Turn the existing `draft/.doc_sources/<repo>/*.md` corpus into a queryable vector index without changing how files are synced.

### Chunking

- **Unit**: Logical segments by **header** and **paragraph**. Do not split mid-sentence.
- **Size**: Cap chunk size (e.g. 512–1024 tokens or ~2–4k chars). If a section is larger, split by subheadings or paragraphs.
- **Overlap**: Optional small overlap (e.g. one paragraph or ~50 tokens) so context isn’t lost at boundaries.
- **Metadata per chunk**: `repo`, `path` (relative to repo), `heading` or `chunk_id`, and optionally `start_line` so citations can point to a section.

Store the exact chunk text in the index (or a stable reference) so retrieval can return snippets and build citation payloads without re-reading files.

### Embeddings

- **Model**: Use a lightweight local model, e.g. **nomic-embed-text** (or another sentence-transformers-style model). Run on CPU or GPU; no external API.
- **Input**: Chunk text (and optionally heading) concatenated. Normalize whitespace and strip pure code blocks if desired to avoid noisy embeddings.

### Vector Store

- **Options**: **ChromaDB** (simpler metadata + filtering) or **FAISS** (lighter; store metadata in parallel and join after search).
- **Location**: Under the draft root, e.g. `.vector_store/` or `draft/.chroma/`, so it stays next to the docs and can be gitignored.
- **Schema**: At least `(id, text, embedding, repo, path, heading_or_id)`. Optional: `source_path` for a direct link.

### Ingestion Pipeline (recommended)

- **Do not** extend `pull.py` with embedding logic. Keep pull as sync-only.
- Add a **separate ingestion step** (e.g. `scripts/index_for_ai.py` or a small `lib/ingest.py`):
  - Reads from the same `draft/.doc_sources/<repo>/` layout.
  - Applies the same logical “which files to include” as the rest of draft (e.g. exclude top-level README, CLAUDE.md, etc. if desired).
  - Chunks → embeds → writes to the vector store.
- **Trigger**: Run after pull (e.g. from UI “Pull” success callback, or manually). Optionally: “Reindex for AI” in the UI that calls this step.
- **Idempotency**: Rebuild the index from scratch on each run (or support clear + re-add) so the store always reflects current `draft/.doc_sources/` contents.

---

## Phase 2: Retrieval & LLM (“Reasoning” Layer)

### Module

- **Location**: `lib/ai_engine.py` (or `ui/ai_engine.py` if UI-owned). Depends only on the vector store path and draft root; no dependency on FastAPI.

### Semantic Search

- **Input**: User question string.
- **Steps**:
  1. Embed the question with the same model used for ingestion.
  2. Query the vector store for top-k (e.g. **top-3** to start) most similar chunks.
  3. Return for each: `repo`, `path`, `heading_or_id`, `text` (snippet), and a stable link (e.g. `#heading` or line range if supported later).

### Optional: Hybrid Retrieval

- Combine **vector similarity** with **keyword search** (e.g. existing Whoosh index).
- Merge or rerank (e.g. reciprocal rank fusion or a tiny cross-encoder) so exact matches (e.g. project names) are not missed. Can be added in a later iteration.

### LLM Integration

- **Providers**:
  - **Claude (API)**: Claude 3.5 Sonnet (or current default). Best quality; request/response go over the network; no training on your data if you don’t log full context.
  - **Local (Ollama)**: e.g. **Qwen-2.5-Coder-32B** (or another instruction model). Zero data leave the machine.
- **Prompt design**:
  - **System**: “You are a direct, precise assistant. Answer only using the provided context. If the answer is not in the context, say you don’t know. Do not guess or use external knowledge.”
  - **User (or assistant)**: Include the retrieved chunks as the only allowed source, then the user question.
- **Output**: Plain text answer (for streaming) plus a **structured list of citations** (repo, path, heading/link) derived from the chunks that were sent to the LLM.

### API Contract (to be implemented in FastAPI)

- **Endpoint**: e.g. `POST /api/ask` or `POST /api/chat` with body `{ "query": "..." }`.
- **Response**: Streamed via **Server-Sent Events (SSE)**:
  - Events: text deltas (and optionally “citation” events if you want to stream them incrementally).
  - Final payload (or last event): list of citations `[{ "repo", "path", "heading", "url" }]` where `url` is the same as the existing doc viewer (e.g. `#/doc/repo/path` or `/api/doc/repo/path`).

---

## Phase 3: Draft Chat UI (“User” Layer)

### Placement

- **Chat interface**: A **sidebar** or **overlay** “Ask a question” so the user can keep the tree and current doc in view while querying the oracle.
- Re-use the existing doc viewer: citation links open the same document (and optionally scroll to a heading when supported).

### Behaviour

- **Input**: Text box (and optional “Ask” button). Submit sends the query to the retrieval + LLM pipeline.
- **Streaming**: Consume SSE from `POST /api/ask`; append tokens to the chat answer area so the reply “types out” in real time.
- **Citations**: Render each source as a link (e.g. `repo/path` or “Heading in path”) that:
  - Opens the existing doc view (same route as tree clicks).
  - Optionally includes a fragment (e.g. `#section`) for future scroll-to-section.

### State

- **Minimal**: One question → one answer + list of citations. No need for multi-turn history in the first version unless desired; if added, keep history in the client or pass last N turns in the API.

---

## Implementation Order

1. **Phase 1**: Add `docs/`, then implement chunking + embeddings + vector store in a separate script/module; run it after pull and optionally expose “Reindex for AI” in the UI.
2. **Phase 2**: Implement `lib/ai_engine.py` (retrieve + LLM), then FastAPI `POST /api/ask` with SSE and citation list.
3. **Phase 3**: Add the chat sidebar/overlay, wire it to `/api/ask`, and render streamed text + citation links.

---

## Dependencies (to add as needed)

- Embeddings: `sentence-transformers` (or direct `nomic-embed`) + PyTorch.
- Vector store: `chromadb` or `faiss-cpu` (+ numpy).
- LLM: `anthropic` for Claude; `ollama` or direct HTTP for local.
- FastAPI: SSE is built-in (`StreamingResponse` with `text/event-stream`).

---

## Out of Scope (for this design)

- Multi-turn conversation memory.
- Training or fine-tuning on your data.
- MCP server or other agent protocols (separate doc if needed).
- Authentication (assume local / trusted use for the oracle).

---

## Is Draft ready to use?

- **Without AI (no local LLM):** Yes. The  UI (tree, doc viewer, Pull, Add source, full-text Whoosh search) works. Run `./setup.sh` then `python scripts/serve.py`; open http://localhost:8058.
- **With Ask (AI) — needs two things:**
  1. **AI index:** Run `python scripts/index_for_ai.py` once (and after Pull). Requires **Python 3.11 or 3.12**; ChromaDB does not support Python 3.14+ yet. The script downloads the embedding model (nomic-embed-text) on first run.
  2. **LLM:** Either set **ANTHROPIC_API_KEY** (Claude) or run **Ollama** locally. For Ollama, the default model is **qwen3:8b**. Pull it once: `ollama run qwen3:8b`. Override with env: `OLLAMA_MODEL=qwen2.5-coder:32b` (or another model).

**Quick test with Ollama (qwen3:8b):**

```bash
# Terminal 1: start Ollama and pull model (once)
ollama run qwen3:8b

# Terminal 2: from draft repo (use Python 3.11/3.12 venv for indexing)
python3.12 -m venv .venv312 && .venv312/bin/pip install -r requirements.txt
.venv312/bin/python scripts/index_for_ai.py -v
.venv312/bin/python scripts/serve.py
# Open http://localhost:8058 → Ask (AI) → type a question
```

If you only have Python 3.14, the index script and `/api/ask` will fail until ChromaDB supports 3.14; the rest of Draft (tree, search, pull, add source) still works.

## Implementation Notes

- **Python**: ChromaDB has compatibility issues with Python 3.14+ (Pydantic v1). Use Python 3.11 or 3.12 for `index_for_ai.py` and for the app if you use Ask (AI).
- **First run**: `scripts/index_for_ai.py` downloads the embedding model (nomic-embed-text) on first run; ensure network access.
- **Ollama model**: Default is `qwen3:8b`. Set `OLLAMA_MODEL` to use another model (e.g. `qwen2.5-coder:32b`).

## Document History

- Initial design: Local Oracle (RAG over draft docs, citations, optional local LLM).
- Implemented: Phase 1–3 (lib/chunking, lib/ingest, lib/ai_engine, scripts/index_for_ai.py, POST /api/ask, POST /api/reindex_ai, Ask AI sidebar UI).
