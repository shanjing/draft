# RAG Operations

How to build the RAG index, ask questions, and run end-to-end tests. Includes model choices (defaults and Qwen3 pairs G/L/S).

---

## Default models

Index profiles control embedding model and chunking. The reranker (cross-encoder) is shared unless overridden.

| Profile | Embedding model | Reranker |
|---------|-----------------|----------|
| **quick** | `sentence-transformers/all-MiniLM-L6-v2` | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| **deep** | `nomic-ai/nomic-embed-text-v1.5` | `cross-encoder/ms-marco-MiniLM-L-6-v2` |

- **quick** — Faster indexing, smaller chunks (1600 chars).
- **deep** — Higher quality, larger chunks (2400 chars), requires `trust_remote_code` for nomic.

Override via `.env`: `DRAFT_EMBED_MODEL`, `DRAFT_CROSS_ENCODER_MODEL`.

Note: for most Macbooks, Mac Mini and PCs, use this set of default model.

---

## Qwen3 pairs (G, L, S)

When using **Ollama** with all four Qwen3 models installed, you can choose from three preset pairs. No Hugging Face download.

**Four Qwen3 models:**

| Role | 8B | 0.6B |
|------|----|------|
| **Embedding** | `qwen3-embedding:8b` | `qwen3-embedding:0.6b` |
| **Reranker** | `dengcao/Qwen3-Reranker-8B:Q3_K_M` | `dengcao/Qwen3-Reranker-0.6B:Q8_0` |

**Preset pairs:**

| Choice | Embed | Reranker | Use case |
|--------|-------|----------|----------|
| **G (Gold)** | 8B | 0.6B | Best balance: strong retrieval, fast rerank |
| **L (8B+8B)** | 8B | 8B | Highest quality, slower |
| **S (0.6B+0.6B)** | 0.6B | 0.6B | Fastest, lowest resource use |

Setup (`./setup.sh`) detects when all four are present and offers G/L/S. Set `DRAFT_EMBED_PROVIDER=ollama` and `DRAFT_RERANK_PROVIDER=ollama` in `.env` when using these.

---

## CLI commands

### Build RAG index

```bash
python scripts/index_for_ai.py [--profile quick|deep] [-v]
```

- `--profile quick` — Default; faster indexing.
- `--profile deep` — Higher quality (nomic embed, larger chunks).
- `-v` / `--verbose` — Show embed model and progress.

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
| `-p` / `--pair` | Model pair: default/d (sentence-transformers), G (Gold), L (8B+8B), S (0.6B+0.6B). Default: `default`. |
| `-q` / `--query` | Question to ask (default: "What is this project about?") |
| `--rebuild` | Rebuild index from sources.yaml before retrieval (default: use existing index) |
| `--profile quick\|deep` | Index profile when building (default: quick) |
| `-v` / `--verbose` | Show models, build/rerank details, and citation scores |

Examples:

```bash
# Use existing index, default pair (sentence-transformers)
python tests/test_pipeline.py -q "what is vault" -v

# Gold pair (Ollama, no HF download)
python tests/test_pipeline.py -p G -q "what is vault" -v

# 8B+8B or 0.6B+0.6B
python tests/test_pipeline.py -p L -q "what is vault" -v
python tests/test_pipeline.py -p S -q "what is vault" -v

# Rebuild index then run retrieval
python tests/test_pipeline.py -p G --rebuild -q "what is vault" -v
```

Run from the draft repo root.
