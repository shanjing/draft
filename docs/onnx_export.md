# ONNX Export and Deployment

Operational guide for exporting PyTorch models to ONNX format and running Draft with the ONNX provider — no PyTorch required at runtime.

**Why:** Replacing `sentence-transformers` (PyTorch) with `onnxruntime` cuts the Docker image from ~1.78 GB to ~724 MB and halves memory usage. The models are exported once on a dev machine and mounted at runtime; the image stays lean and model updates don't require a rebuild.

See [container_optimization.md](container_optimization.md) for the full design rationale.

---

## Prerequisites

The export script requires PyTorch and runs on a dev machine — not inside the Docker image. Draft's `.venv` already includes everything needed:

```
torch, transformers, onnx   ← export-time only
onnxruntime, tokenizers     ← runtime (already in the image)
```

---

## Step 1: Export models

Run once from the draft repo root. Output goes to any directory on the host — the models are mounted into Docker/K8s at runtime.

```bash
.venv/bin/python scripts/export_onnx.py --output-dir /path/to/onnx_models
```

Output layout:

```
/path/to/onnx_models/
├── embed/                          # sentence-transformers/all-MiniLM-L6-v2
│   ├── model.onnx                  # 86.8 MB
│   ├── tokenizer.json
│   ├── tokenizer_config.json
│   ├── special_tokens_map.json
│   └── vocab.txt
└── rerank/                         # cross-encoder/ms-marco-MiniLM-L-6-v2
    ├── model.onnx                  # 86.8 MB
    ├── tokenizer.json
    ├── tokenizer_config.json
    ├── special_tokens_map.json
    └── vocab.txt
```

To export only one model:

```bash
.venv/bin/python scripts/export_onnx.py --output-dir /path/to/onnx_models --embed-only
.venv/bin/python scripts/export_onnx.py --output-dir /path/to/onnx_models --rerank-only
```

---

## Step 2: Rebuild the RAG index with ONNX embeddings

The vector index must be built with the same embedding provider used at query time. If your existing index was built with the HF provider, rebuild it:

```bash
# Add to .env (or export for the session):
DRAFT_EMBED_PROVIDER=onnx
DRAFT_ONNX_EMBED_DIR=/path/to/onnx_models/embed
DRAFT_ONNX_RERANK_DIR=/path/to/onnx_models/rerank

python scripts/index_for_ai.py --profile quick
```

---

## Step 3: Run Docker with ONNX

The ONNX image (`ONNX_ONLY=1` build) has no PyTorch. Activate ONNX via a separate env override file so the main `.env` stays unchanged for local dev:

```bash
# Create once — one line, no secrets
echo 'DRAFT_EMBED_PROVIDER=onnx' > .env.docker
```

Run the container:

```bash
docker run --rm \
  --env-file .env.docker \
  -v ~/.draft:/home/app/.draft \
  -v $(pwd)/.env:/app/.env:ro \
  -v /path/to/onnx_models:/app/onnx_models:ro \
  <image-id>
```

- `--env-file .env.docker` — sets `DRAFT_EMBED_PROVIDER=onnx`; takes precedence over the mounted `.env`
- `-v ~/.draft:/home/app/.draft` — mounts to the `app` user's home (not `/root`); writable so the MCP server can write `draft-mcp.log` there
- `-v .env` — LLM keys and other config (unchanged for local dev)
- `-v onnx_models` — model files; the image already has `DRAFT_ONNX_EMBED_DIR=/app/onnx_models/embed` and `DRAFT_ONNX_RERANK_DIR=/app/onnx_models/rerank` baked in as defaults, so no `-e` flags needed for those

To run a one-off query for testing:

```bash
docker run --rm \
  --env-file .env.docker \
  -v ~/.draft:/home/app/.draft \
  -v $(pwd)/.env:/app/.env:ro \
  -v /path/to/onnx_models:/app/onnx_models:ro \
  <image-id> \
  python scripts/ask.py --show-prompt -q "what is RAG"
```

---

## Kubernetes (Helm)

Set `env.embedProvider` and `onnxModels.hostPath` in `values.local.yaml`:

```yaml
env:
  embedProvider: "onnx"

onnxModels:
  # Path to the onnx_models/ directory on the K8s node
  # Must contain embed/ and rerank/ subdirectories
  hostPath: /path/on/node/onnx_models
```

The Helm chart mounts this path to `/app/onnx_models` inside the pod (matching the `DRAFT_ONNX_EMBED_DIR` / `DRAFT_ONNX_RERANK_DIR` defaults from the Dockerfile) and injects `DRAFT_EMBED_PROVIDER=onnx` via ConfigMap. No image changes needed.

Deploy as usual:

```bash
helm upgrade --install draft ./kubernetes/draft -n draft --create-namespace \
  -f kubernetes/draft/values.mcp.yaml \
  -f kubernetes/draft/values.local.yaml
```

---

## Environment variables

| Variable | Default (in image) | Description |
|---|---|---|
| `DRAFT_EMBED_PROVIDER` | *(unset — falls back to hf)* | Set to `onnx` to activate ONNX Runtime |
| `DRAFT_ONNX_EMBED_DIR` | `/app/onnx_models/embed` | Path to embedding model dir (`model.onnx` + `tokenizer.json`) |
| `DRAFT_ONNX_RERANK_DIR` | `/app/onnx_models/rerank` | Path to cross-encoder model dir |
| `DRAFT_ONNX_RERANK_MODEL` | *(unset)* | Display name override for the ONNX reranker; defaults to `cross-encoder/ms-marco-MiniLM-L-6-v2` |

---

## Building the ONNX image

```bash
# ONNX-only (no PyTorch, ~724 MB):
docker build --build-arg ONNX_ONLY=1 -t draft:onnx .

# Standard (PyTorch included, ~1.78 GB):
docker build -t draft:pytorch .
```

---

## Verification

Expected output from `ask.py --show-prompt`:

```
Models: embed=sentence-transformers/all-MiniLM-L6-v2, encoder=cross-encoder/ms-marco-MiniLM-L-6-v2, LLM=...
```

Key things to confirm:
1. `encoder` shows `ms-marco-MiniLM-L-6-v2` — confirms ONNX rerank path is active
2. No `sentence_transformers` or `torch` import errors — confirms PyTorch is not loaded
3. OTel spans `rag.retrieval` and `rag.rerank` both show `status_code: UNSET` (no errors)
4. Citations returned with ranking scores in the `[-10, +10]` range typical for ms-marco
