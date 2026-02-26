# RAG Design Principles

A local RAG-based assistant over your private docs and code — answers from your content only, with citations that link to the source and show relevant snippets (including code).

---

## Goals

- **Answer questions** using only the content of your collected files (docs and code).
- **Cite sources** — every answer links back to the original doc or file; for code, show file path, line range, and a snippet.
- **No leakage** — support a fully local path (embeddings + LLM) so nothing leaves your machine; optionally use Claude, Gemini, or OpenAI for higher quality.
- **Code-aware** — index both markdown and Python (and optionally other code) so questions like “how does X work?” or “what is the testing strategy?” can surface both docs and source.

---

## Architecture Overview

```
                    ┌─────────────────┐
                    │  sources.yaml   │  (source of truth for repos)
                    │  (DRAFT_HOME)   │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
  ┌──────────────┐   ┌──────────────────┐   ┌──────────────┐
  │ vault/       │   │ effective roots  │   │ FastAPI UI   │
  │ *.md, *.py   │   │ (local path or   │   │ (existing)   │
  │              │   │  .clones/<name>) │   │              │
  └──────┬───────┘   └────────┬─────────┘   └──────┬───────┘
         │                    │ *.md, *.py          │
         └────────────────────┼────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ lib/ingest.py   │
                    │ collect_chunks  │  ← sources.yaml + get_effective_repo_root
                    │ .md → chunk_    │
                    │   markdown      │
                    │ .py → chunk_    │
                    │   python (ast)  │
                    └────────┬────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ Chroma vector   │  (id, text, embedding, repo, path, heading,
                    │ store           │   start_line?, end_line?)
                    └────────┬────────┘
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
         ▼                    ▼                    ▼
  ┌──────────────┐   ┌─────────────────┐   ┌──────────────┐
  │ Whoosh       │   │ lib/ai_engine   │   │ Doc viewer   │
  │ (full-text   │   │ retrieve() →    │   │ (tree, open  │
  │  search)     │   │ LLM → citations │   │  .md / .py)  │
  └──────────────┘   └────────┬────────┘   └──────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ Ask UI          │  Streamed answer + citations
                    │ (snippet + link │  (repo/path, lines X–Y, <pre> snippet)
                    │  for code)      │
                    └─────────────────┘
```

---

## RAG Design in Detail

### 1. Source of truth and content roots

- **Repos**: Listed in **sources.yaml** (path: `DRAFT_HOME/sources.yaml`). Each entry has a **name** and **source** (local path or GitHub URL). Ingestion does **not** copy files; it reads from **effective roots**:
  - **Local source** → resolved path (absolute or relative to draft root).
  - **GitHub source** → `DRAFT_HOME/.clones/<name>` (clone/pull managed by pull).
- **Vault**: Fixed directory `DRAFT_HOME/vault/`; always walked for `.md` and `.py` in addition to repos.
- **File exclusions**: Same as the rest of Draft (e.g. README.md, CLAUDE.md, `.venv`, `.git`, `__pycache__`, paths in `.gitignore`). Applied in ingest so indexed content matches what the UI and search see.

### 2. Chunking strategy

Two chunkers live in **lib/chunking.py**; ingest chooses by file extension.

- **Markdown (chunk_markdown)**  
  - Split by **`##` / `###`** headers into sections; within each section, split by paragraphs with a **chunk size cap** (~2400 chars by default) and optional **paragraph overlap** (e.g. 1 paragraph) to avoid hard cuts at boundaries.  
  - **Metadata per chunk**: `repo`, `path`, `heading` (section title), `chunk_index`. No line numbers (optional for future).

- **Python (chunk_python)**  
  - Uses the **ast** module (no regex) so decorators and multiline signatures are handled correctly.  
  - **Units**: Top-level `def` / `async def` → one chunk per function. Top-level `class` → one chunk if small; otherwise one chunk per **method** (heading `ClassName.method_name`) plus one for class-level code. Module-level code (imports, constants, `if __name__`) → one chunk with heading `"<module>"`.  
  - **Metadata per chunk**: `repo`, `path`, `heading` (e.g. function or class name), `chunk_index`, **start_line**, **end_line** (1-based).  
  - **Oversized blocks**: If a function or class body exceeds the cap, stored text is truncated (with `"\n..."`) but **start_line** / **end_line** are unchanged so citations still point at the full range.  
  - **Parse errors**: Whole file is emitted as a single chunk with heading `"<module>"` and line range 1–N.

Chunk metadata is stored in Chroma so retrieval can return both text and (for code) line range for citations.

### 3. Embeddings and vector store

- **Model**: Configurable per **index profile** (e.g. `quick`: smaller/faster model; `deep`: nomic-embed-text for higher quality). Stored in collection metadata so the same model is used at query time.
- **Input**: Chunk text only (heading can be included in the stored text for context). No separate field for “heading” in the embedding input in the current design.
- **Store**: **ChromaDB** under draft root (e.g. `.vector_store/`). Schema: document id, embedding, **metadata** (`repo`, `path`, `heading`, optional `start_line`, `end_line`), and stored document text.
- **Rebuild**: Index is rebuilt from scratch on each run (no incremental update). Ensures the store matches current vault + effective roots.

### 4. Retrieval (lib/ai_engine)

- **Input**: User query string.
- **Steps**:  
  1. Embed the query with the same model as the collection (from collection metadata; fallback for older collections).  
  2. Query Chroma for **top-k** (e.g. 5) most similar chunks.  
  3. Return for each: `repo`, `path`, `heading`, `text`, and when present **start_line**, **end_line** (from metadata).
- **No hybrid retrieval yet**: Pure vector search. Whoosh is used elsewhere for full-text search in the UI; combining the two (e.g. rerank or fusion) is a possible extension.

### 5. Citation building (with code snippets)

Citations are built **at query time** in **lib/ai_engine** (e.g. `_build_citations`) so the UI can show both links and, for code, a short snippet.

- **Payload per citation**: `repo`, `path`, `heading`, and when the chunk has line range: **start_line**, **end_line**, **snippet** (exact lines from the file).
- **Snippet resolution**:  
  - **Vault**: File path is `get_vault_root() / path`.  
  - **Repo**: File path is `get_effective_repo_root(name, source, draft_root) / path`; `source` comes from **sources.yaml** (parsed once per request).  
  - Read the file from disk, slice `lines[start_line - 1 : end_line]`, set **snippet** (and **start_line** / **end_line**) on the citation. If the file is missing, leave snippet empty but keep line range so the UI can still show “file X, lines Y–Z”.
- **Prompt**: The system prompt instructs the model to cite file and line range when referring to code; the UI then shows that range and the resolved snippet.

### 6. LLM and API

- **Providers**: Local (Ollama), Claude, Gemini, OpenAI. Provider and model are chosen via env (e.g. `DRAFT_LLM_PROVIDER`, `OLLAMA_MODEL`, `CLOUD_AI_MODEL`).
- **Strict context-only**: The model is instructed to answer only from the provided context (retrieved chunks) and to cite doc/section or file and line range when relevant.
- **Endpoint**: `POST /api/ask` with body `{ "query": "..." }`. Response is **SSE**: events `text`, `citations`, `error`. Citations are a list of objects with `repo`, `path`, `heading`, and optionally `start_line`, `end_line`, `snippet`.

### 7. Ask UI and doc viewer

- **Streaming**: The client consumes SSE and appends text deltas to the answer area.
- **Citations**: Each citation is rendered as a link (e.g. `repo/path` or `repo/path (lines X–Y)` for code) that opens the **doc viewer**. For citations with **snippet**, a `<pre>` block below the link shows the code snippet.
- **Doc viewer**: Serves both `.md` and `.py` (and other allowed types). So “View source” for a code citation opens the actual file (e.g. `.py`) in the same viewer. Optional future: fragment or query param to scroll to a line.

---

## Ingestion pipeline (scripts/index_for_ai.py + lib/ingest)

- **Entry point**: `scripts/index_for_ai.py` (CLI with click: `--profile quick|deep`, `-v`). Can be triggered from the UI via “Reindex for AI” (runs the script as a subprocess).
- **Flow**:  
  1. **collect_chunks(draft_root)** uses **sources.yaml** (get_sources_yaml_path + parse_sources_yaml) to get repo list; for each repo, get effective root (get_effective_repo_root); also walk vault (get_vault_root). For each `.md` and `.py` file passing should_include and not in gitignore, read content and call **chunk_markdown** or **chunk_python**. Return one flat list of Chunks.  
  2. **build_index(draft_root)** calls collect_chunks, loads the embedding model for the chosen profile, embeds in batches, and writes to Chroma (ids, embeddings, documents, metadatas). For code chunks, metadatas include **start_line** and **end_line**.
- **Idempotency**: Each run rebuilds the collection (delete + create). No incremental index.

---

## Operations

### Rebuild RAG index (admin / CLI)

The vector index is rebuilt only on demand. Use the CLI from the **draft repo root**:

```bash
# Quick (default) — smaller, faster embedding model
python scripts/index_for_ai.py

# Explicit profile: quick or deep
python scripts/index_for_ai.py --profile quick
python scripts/index_for_ai.py --profile deep

# Verbose progress
python scripts/index_for_ai.py --profile deep -v
```

- **quick**: Lighter model, faster; good for iteration.
- **deep**: Higher-quality embeddings (e.g. nomic-embed-text); better retrieval for nuanced questions.

The same script is triggered from the UI via **Ask (AI)** → “Quick rebuild” or “Deep rebuild (nomic)” (POST `/api/reindex_ai` with `mode: "quick"` or `"deep"`). Setup can also run it once at the end of configuration.

---

## Implementation order (reference)

1. **Ingestion**: Chunking (markdown then Python), collect_chunks from vault + effective roots, build_index → Chroma.
2. **Retrieval and LLM**: lib/ai_engine (retrieve, ask_stream, citation building with snippet), POST /api/ask with SSE.
3. **UI**: Ask panel, streamed answer, citation links + snippet block; doc viewer allows .py.

---

## Dependencies

- Embeddings: `sentence-transformers` (+ PyTorch).
- Vector store: `chromadb`.
- LLM: `anthropic`, `openai`, `google-generativeai`; Ollama via HTTP.
- FastAPI: SSE via `StreamingResponse` with `text/event-stream`.

---

## Document history

- Initial design: Local Oracle (RAG over draft docs, citations, optional local LLM).
- Implemented: Phase 1–3 (chunking, ingest, ai_engine, index_for_ai, POST /api/ask, Ask UI).
- Extended: Code-aware RAG — chunk_python (ast), .py in ingest and Chroma, start_line/end_line in metadata; citations with snippet resolution from vault/repo roots; doc viewer and Ask UI support .py and show line range + snippet.
