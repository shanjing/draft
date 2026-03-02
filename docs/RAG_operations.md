# RAG Operations

How to build the RAG index, ask questions, and run end-to-end tests. Embed and encoder models are configured in setup and stored in `.env`; option 4 (Build RAG index) uses whatever `.env` has.

---

## Default models

| Role | Default |
|------|---------|
| **Embed** | `sentence-transformers/all-MiniLM-L6-v2` (Hugging Face) |
| **Encoder (reranker)** | `cross-encoder/ms-marco-MiniLM-L-6-v2` (Hugging Face only) |

- **Encoder is always Hugging Face** (cross-encoder). Reranking does not use Ollama.
- **Embed** can be Hugging Face or Ollama. If you use an Ollama embed model (e.g. `qwen3-embedding:8b`), set `DRAFT_EMBED_PROVIDER=ollama` in `.env` (setup step 2 does this when you enter a model name without a `/`).

Index profiles (quick/deep) control chunking and batch sizes; the embed/encoder model names come from `.env` (`DRAFT_EMBED_MODEL`, `DRAFT_CROSS_ENCODER_MODEL`). `.env` is the source of truth for these two models globally.

---

## CLI commands

### Build RAG index

```bash
python scripts/index_for_ai.py [--profile quick|deep] [-v]
```

Uses **embed and encoder from `.env`** (set by setup step 2). Option 4 in setup (“Build RAG/index”) runs this with the same .env.

- `--profile quick` — Default; faster indexing, smaller chunks.
- `--profile deep` — Larger chunks; embed model still from `.env`.
- `-v` / `--verbose` — Show embed model, provider, and progress.

Examples:

```bash
python scripts/index_for_ai.py -v
python scripts/index_for_ai.py --profile deep -v
```

### Ask questions (retrieval + LLM)

```bash
python scripts/ask.py -q "your question" [--debug]
```

- `-q` / `--query` — Question (required).
- `--debug` — Log embed model, cross-encoder, rerank scores, and verbose output.

Output: prints **Models** (embed, encoder, LLM), then the answer, then **---** and numbered **citations** with `[score: x]` and optional line ranges.

Requires: built RAG index and LLM config (`OLLAMA_MODEL` or API keys in `.env`).

Examples:

```bash
python scripts/ask.py -q "what is vault"
python scripts/ask.py -q "how does pull work" --debug
```

### End-to-end pipeline test

```bash
python tests/test_pipeline.py [options] [-q "question"] [-v]
```

Runs retrieval + rerank over the **existing index** (no rebuild by default). Same output style as `ask.py`: **Models** (embed, encoder, LLM), answer, then **---** and top-3 **citations** with rerank scores. Use `--rebuild` to build the index from `sources.yaml` first (required on first run or after adding sources).

| Option | Description |
|--------|-------------|
| `-p` / `--pair` | Legacy: default/d (uses .env), G/L/S (overrides for tests). Default: `default`. |
| `-q` / `--query` | Question to ask (default: "What is this project about?") |
| `--rebuild` | Rebuild index from sources.yaml before retrieval (default: use existing index) |
| `--profile quick\|deep` | Index profile when building (default: quick) |
| `-v` / `--verbose` | Show models, build/rerank details, and citation scores |

Examples:

```bash
# Use existing index (embed/encoder from .env)
python tests/test_pipeline.py -q "what is vault" -v

# Rebuild index then run retrieval (uses .env for embed model)
python tests/test_pipeline.py --rebuild -q "what is vault" -v
```

Run from the draft repo root.
