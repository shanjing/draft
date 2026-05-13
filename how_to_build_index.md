# How to Build the Search Indexes

Draft maintains two independent indexes:

- **FTS (full-text search)** — Whoosh index under `.search_index/`, used by the search bar.
- **RAG (embeddings)** — ChromaDB vector store under `~/.draft/.vector_store/`, used by Ask (AI).

They are rebuilt independently. The table below shows which actions trigger each.

## What triggers each index

| Action | FTS rebuilt | RAG rebuilt |
|---|:---:|:---:|
| Pull (`/api/pull`) | ✅ | ❌ |
| Reindex (`/api/reindex`) | ✅ | ❌ |
| Add source | ✅ | ✅ |
| Remove source | ✅ | ✅ |
| Delete vault file | ✅ | ✅ |
| Rebuild RAG index button (`/api/reindex_ai`) | ❌ | ✅ |

## Rebuilding FTS

**From the UI:** click the **Pull ↻** button in the sidebar toolbar. This pulls latest docs and rebuilds the FTS index.

**Via API:**
```bash
curl -X POST http://localhost:8058/api/reindex
```

**Note:** `scripts/pull.py` run directly from the CLI does **not** rebuild the FTS index — only the server's `/api/pull` handler does.

## Rebuilding RAG (embeddings)

**From the UI:** open the **Ask (AI)** panel, expand **Models**, and click **Rebuild RAG index**.

**Via API:**
```bash
curl -X POST http://localhost:8058/api/reindex_ai \
  -H 'Content-Type: application/json' \
  -d '{}'
```

**Via CLI (recommended for large corpora):**
```bash
python scripts/index_for_ai.py
```

The CLI script reads `DRAFT_EMBED_MODEL` from `.env` to select the embedding model. Use `-v` for verbose output with a progress bar.

## When to rebuild

- **After editing docs outside the UI** (e.g. directly editing files under `~/.draft/.doc_sources/`): run Pull to refresh FTS, and Rebuild RAG index to refresh embeddings.
- **After changing `DRAFT_EMBED_MODEL` in `.env`**: rebuild RAG — the old embeddings used a different model and results will be stale.
- **After a fresh clone / new install**: run Pull once (builds FTS), then rebuild RAG index before using Ask (AI).
- **FTS only stale** (search returns old results): use the Pull button or `POST /api/reindex`.
- **Ask (AI) only stale** (answers miss recent docs): use the Rebuild RAG index button or `scripts/index_for_ai.py`.
