# Draft Setup

Setup instructions for all deployment modes. Start with `./setup.sh` for local use; jump to [MCP Server](#mcp-server) for Kubernetes/Docker MCP deployment.

---

## Quick start

```bash
./setup.sh
```

Run from the repo root. Re-run anytime to add sources or change the LLM.

### What setup.sh does

1. **Creates the environment** — `.venv`, installs from `requirements.txt`. Python 3.11 or 3.12. Use `--recreate` to rebuild the venv.
2. **Ensures `~/.draft/sources.yaml`** — copied from `sources.example.yaml` if missing.
3. **Add sources** (option 1) — local path or GitHub URL; runs `pull.py -a` under the hood.
4. **Setup embedding model** (option 2) — HuggingFace or Ollama embed models.
5. **Setup encoder model** (option 3) — cross-encoder for reranking.
6. **Configure LLM for Ask (AI)** (option 4) — Ollama or cloud (Gemini, Claude, OpenAI); writes `.env`.
7. **Build RAG index** (option 5) — quick or deep profile for semantic search and Ask (AI).
8. **Test RAG + LLM** (option 6) — sample Ask to verify the pipeline.
9. **Start UI** (option 7, default).
10. **Run in Docker** (option 8) — builds and runs the container with your data and LLM config.

---

## PKB / BKB

### Start the UI

```bash
./draft.sh ui start             # start on default port 8058 (background)
./draft.sh ui start -p 9000    # custom port
./draft.sh ui stop
./draft.sh ui restart
./draft.sh status               # state of both UI and MCP server
```

Foreground: `source .venv/bin/activate && python scripts/serve.py`

Logs: `~/.draft/.draft-ui.log`

### Data directory (`~/.draft`)

All user data lives under `~/.draft/` (or `$DRAFT_HOME`):

| Path | Contents |
|---|---|
| `~/.draft/sources.yaml` | Source list (gitignored, created from `sources.example.yaml`) |
| `~/.draft/.doc_sources/<name>/` | Pulled `.md` files, one subdir per repo |
| `~/.draft/vault/` | Curated / uploaded docs |
| `~/.draft/.vector_store/` | ChromaDB RAG index |
| `~/.draft/.search_index/` | Whoosh full-text index |

Set `DRAFT_HOME` to use a different root directory.

### Document sources (sources.yaml)

`~/.draft/sources.yaml` lists your doc sources. Each entry has a name (subdir) and a `source` (local path or GitHub URL).

**Add sources:**

```bash
python scripts/pull.py -a ../OtherRepo               # local path
python scripts/pull.py -a https://github.com/owner/repo   # GitHub (API, no clone)
```

Or use `./setup.sh` (option 1) or the UI **Add source** button.

**Pull updates:**

```bash
python scripts/pull.py          # pull all sources (never deletes)
python scripts/pull.py -v       # verbose: show tree and status per repo
```

### RAG index

Semantic search and Ask (AI) require a built vector index:

```bash
python scripts/index_for_ai.py --profile quick   # fast, for new/updated docs
python scripts/index_for_ai.py --profile deep    # re-embeds everything (after model change)
```

Or use the UI **Quick rebuild** / **Deep rebuild** buttons.

### LLM configuration (`.env`)

```bash
# Ollama (local, recommended for privacy)
DRAFT_LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen3:8b

# Cloud providers (one of:)
DRAFT_LLM_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-...

DRAFT_LLM_PROVIDER=gemini
GEMINI_API_KEY=...

DRAFT_LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

No LLM is needed for browsing, search, or pull.

### BKB / Docker

```bash
# Build and run (mounts ~/.draft for sources and vault)
docker build -t draft-ui .
docker run -p 8058:8058 -v ~/.draft:/root/.draft draft-ui

# With LLM config
docker run -p 8058:8058 \
  -v ~/.draft:/root/.draft \
  -v $(pwd)/.env:/app/.env \
  draft-ui

# Ollama on host
docker run -p 8058:8058 \
  -v ~/.draft:/root/.draft \
  -e OLLAMA_HOST=http://host.docker.internal:11434 \
  draft-ui
```

Or use `./setup.sh` option 8.

#### ONNX image (no PyTorch, ~724 MB)

Build the ONNX-only image and run with model files mounted from the host. No PyTorch or sentence-transformers inside the container.

```bash
# Build ONNX image
docker build --build-arg ONNX_ONLY=1 -t draft:onnx .

# Export models once (requires PyTorch on dev machine, output stays on host)
.venv/bin/python scripts/export_onnx.py --output-dir /path/to/onnx_models

# Create env override (one line, no secrets)
echo 'DRAFT_EMBED_PROVIDER=onnx' > .env.docker

# Run
docker run --rm \
  --env-file .env.docker \
  -v ~/.draft:/home/app/.draft \
  -v $(pwd)/.env:/app/.env:ro \
  -v /path/to/onnx_models:/app/onnx_models:ro \
  draft:onnx
```

Full guide: [docs/onnx_export.md](docs/onnx_export.md)

---

## MCP Server

Brief setup for the MCP server. Full operational runbook: **[docs/MCP_operations.md](docs/MCP_operations.md)**.

### Local daemon

```bash
./draft.sh mcp start            # HTTP daemon, port 8059, background
./draft.sh mcp stop
./draft.sh mcp restart
./draft.sh mcp start --stdio    # stdio mode (for manual testing; Claude Desktop/Code spawn the server directly via their config)
./draft.sh mcp logs             # tail MCP log
```

Set `DRAFT_MCP_TOKEN` in `.env` for a stable Bearer token. If unset, a random token is printed to stderr on startup.

### Kubernetes (Helm) — Production Cloud (GKE / EKS / AKS)

```bash
# 1. Build and push image to your registry
docker build -t <registry>/draft:latest .
docker push <registry>/draft:latest

# 2. Create a values overlay for your environment (gitignored)
#    Set image.repository, mcp.token, docSources (CSI-backed volumes), secrets.*

# 3. First-time install
helm install draft ./kubernetes/draft -n draft --create-namespace \
  --set image.repository=<registry>/draft \
  --set image.tag=latest \
  --set mcp.token="$(openssl rand -base64 32)" \
  -f kubernetes/draft/values.mcp.yaml

# Subsequent upgrades
helm upgrade draft ./kubernetes/draft -n draft \
  -f kubernetes/draft/values.mcp.yaml \
  -f kubernetes/draft/values.cloud.yaml    # your cloud-specific overrides

# 4. Expose via LoadBalancer or port-forward
kubectl -n draft get svc draft             # get external IP / port
```

### Kubernetes (Helm) — Local Apple Silicon (minikube / kind)

Requires minikube with the `krunkit` driver (Apple Virtualization Framework) and a wide `--mount-string` so host directories are visible inside the cluster.

```bash
# 1. Create (or recreate) the cluster with host mounts
#    /Volumes/External is shared into the cluster at /mnt/external
minikube start --driver=krunkit \
  --mount-string="/Volumes/External:/mnt/external" \
  --mount

# 2. Build and load image (no registry needed)
docker build -t draft:latest .
minikube image load draft:latest          # or: kind load docker-image draft:latest

# 3. Create kubernetes/draft/values.local.yaml (gitignored)
#    Required keys:
#      image.pullPolicy: Never             # image only exists locally
#      hfCache.hostPath: /mnt/external/huggingface_models
#      env.hfHubOffline: "1"              # models are pre-cached
#      mcp.token: "<openssl rand -base64 32>"   # pin token here
#      docSources:                         # host-path mounts for doc dirs
#        - name: runbooks
#          hostPath: /mnt/external/draft_mcp_doc/runbooks
#          mountPath: /mnt/docs/runbooks

# 4. First-time install
helm install draft ./kubernetes/draft -n draft --create-namespace \
  -f kubernetes/draft/values.mcp.yaml \
  -f kubernetes/draft/values.local.yaml

# Subsequent upgrades (token preserved via values.local.yaml)
helm upgrade draft ./kubernetes/draft -n draft \
  -f kubernetes/draft/values.mcp.yaml \
  -f kubernetes/draft/values.local.yaml

# 5. Port-forward for local access
kubectl -n draft port-forward svc/draft 8059:8059

# 6. Verify
curl http://localhost:8059/health
# → {"status":"ok","index_ready":true,...}
```

Pre-download HuggingFace models on the host (run once):
```bash
pip install sentence-transformers
python -c "
from sentence_transformers import SentenceTransformer, CrossEncoder
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
"
# Models saved to ~/.cache/huggingface — copy or symlink to /Volumes/External/huggingface_models
```

See [MCP operations](docs/MCP_operations.md) for token management, index rebuilds, and troubleshooting.

---

## References

| Doc | Purpose |
|---|---|
| [Engineering](docs/engineering.md) | Design principles, storage, metadata, vault, intelligence layer, implementation order |
| [RAG design](docs/RAG_design.md) | RAG goals, chunking, two-stage retrieval (bi-encoder + cross-encoder), model choices |
| [RAG operations](docs/RAG_operations.md) | Changing embed/encoder models, tests (ask.py, test_pipeline, CI/CD) |
| [MCP design](docs/MCP_design.md) | draft_mcp package, tools, Streamable HTTP + stdio, Bearer auth, resources, prompts |
| [MCP operations](docs/MCP_operations.md) | Runbook: run MCP server, token, config, K8s deployment, testing, troubleshooting |
| [Observability design](docs/observability_design.md) | OTel metrics and traces (RAG + MCP), GenAI semconv, console vs OTLP |
| [OTel walkthrough](docs/OTel_walkthrough.md) | Data-flow walkthrough, metrics log file and env vars |
| [Testing suites](docs/testing_suites.md) | pytest, pipeline test, OTel tests, MCP integration (test_mcp.py), curl integration |
| [ONNX export](docs/onnx_export.md) | Export models to ONNX, Docker + K8s deployment without PyTorch |
