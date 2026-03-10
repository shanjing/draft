# MCP Server Operations Runbook

## Overview

Draft's MCP server exposes document search, semantic retrieval, and RAG Q&A to any MCP-compliant client. It runs as a separate process from the UI server (port 8059 vs 8058) and can be started independently.

Two transports are supported:


| Transport           | Use case                                | Auth                    |
| ------------------- | --------------------------------------- | ----------------------- |
| **stdio**           | Claude Desktop, local trusted tools     | None (process-isolated) |
| **Streamable HTTP** | Remote agents, Docker, SRE agents, curl | Bearer token            |


---

## Prerequisites

```bash
# Python 3.11 or 3.12 (3.14+ not supported)
python --version

# Install dependencies (includes mcp>=1.0)
pip install -r requirements.txt

# Verify MCP package is available
python -c "from mcp.server.fastmcp import FastMCP; print('ok')"

# Verify draft_mcp loads cleanly
python -c "from draft_mcp.server import mcp; print([t.name for t in mcp._tool_manager.list_tools()])"
# → ['search_docs', 'retrieve_chunks', 'get_document', 'list_documents', 'list_sources', 'query_docs']
```

The MCP server requires the same `~/.draft/` data directory used by the UI. If Draft is already set up and indexed, the MCP server is ready to run.

---

## Configuration

All configuration is in `.env` at the repo root (same file as the UI). Copy `.env.example` if starting fresh.

### MCP-specific variables


| Variable            | Default        | Purpose                                                                                                |
| ------------------- | -------------- | ------------------------------------------------------------------------------------------------------ |
| `DRAFT_MCP_TOKEN`   | auto-generated | Bearer token for HTTP transport. If unset, a random token is printed to stderr on startup.             |
| `MCP_LOG_JSON`      | unset          | Set to `1` to emit structured JSON log lines instead of plain text (affects both stderr and log file). |
| `OTEL_SERVICE_NAME` | `draft-mcp`    | OTel service name for traces and metrics.                                                              |


### Log file

The server always writes logs to `~/.draft/draft-mcp.log` in addition to stderr. No configuration required — the file is created automatically on first run.

```bash
tail -f ~/.draft/draft-mcp.log
```

With `MCP_LOG_JSON=1` the file contains one JSON object per line:

```json
{"ts": 1741442324.1, "levelname": "INFO", "message": "ok", "tool": "retrieve_chunks", "duration_ms": 41.2, "status": "ok"}
```

### LLM variables (required only for `query_docs`)


| Variable             | Purpose                                   |
| -------------------- | ----------------------------------------- |
| `DRAFT_LLM_PROVIDER` | `ollama` | `claude` | `gemini` | `openai` |
| `OLLAMA_MODEL`       | e.g. `qwen3:8b` (if provider is ollama)   |
| `ANTHROPIC_API_KEY`  | Required if provider is `claude`          |
| `GEMINI_API_KEY`     | Required if provider is `gemini`          |
| `OPENAI_API_KEY`     | Required if provider is `openai`          |


### DRAFT_HOME

The server resolves `DRAFT_HOME` from the environment (defaults to `~/.draft`). If you run the server as a different user or in Docker, set this explicitly.

```bash
DRAFT_HOME=/path/to/.draft python scripts/serve_mcp.py
```

---

## Running Modes

### 1. Local daemon — `draft.sh mcp` (recommended for local use)

`draft.sh` is the unified local process manager for the UI and MCP server. It handles PID tracking, force-kill on restart/stop, and combined status.

```bash
./draft.sh mcp start             # HTTP daemon, port 8059, background
./draft.sh mcp start --log-json  # same, with JSON-format logs
./draft.sh mcp stop              # stop (SIGTERM → SIGKILL → port sweep)
./draft.sh mcp restart           # stop then start
./draft.sh mcp start --stdio     # stdio transport (foreground)
./draft.sh mcp logs              # tail ~/.draft/draft-mcp.log
./draft.sh status                # show state of both UI and MCP
```

### 2. stdio (Claude Desktop / local)

```bash
./draft.sh mcp start --stdio     # via draft.sh (recommended)
# or directly:
python scripts/serve_mcp.py --stdio
```

- Reads JSON-RPC from stdin, writes to stdout
- No auth — the process boundary is the security perimeter
- Started and managed by the MCP client (e.g. Claude Desktop launches and owns the process)
- Logs go to stderr and `~/.draft/draft-mcp.log`

### 3. HTTP daemon (foreground / scripting)

```bash
python scripts/serve_mcp.py
```

- Streamable HTTP on `0.0.0.0:8059`
- Bearer token auth on all requests except `/health`
- Token printed to stderr if `DRAFT_MCP_TOKEN` is not set

### 4. HTTP daemon with JSON logging

Logs are always written to `~/.draft/draft-mcp.log`. Setting `MCP_LOG_JSON=1` switches both stderr and the log file to JSON format:

```bash
./draft.sh mcp start --log-json   # via draft.sh (recommended)
# or directly:
MCP_LOG_JSON=1 python scripts/serve_mcp.py
```

Each tool call emits one JSON line to `~/.draft/draft-mcp.log`:

```json
{"ts": 1741442324.1, "levelname": "INFO", "message": "ok", "tool": "retrieve_chunks", "duration_ms": 41.2, "status": "ok"}
```

### 5. Kubernetes / Helm (local Kubernetes or cloud)

(Production grade K8 operation guide will be provided for GKE/EKS)

The Helm chart at `kubernetes/draft/` deploys the MCP server to any Kubernetes cluster.

**Prerequisites:** Helm 3, `draft:latest` image accessible to all cluster nodes.

**Load image into local Kubernetes** (when the image is not in a registry):

```bash
# Save image to tar
docker save draft:latest -o /tmp/draft-latest.tar

# kind: kind load docker-image draft:latest

# Local Kubernetes cluster (multi-node) — copy tar to each node and import:
#   for node in <worker-1> <worker-2>; do
#     scp /tmp/draft-latest.tar ${node}:/tmp/draft-latest.tar
#     ssh $node "sudo ctr -n k8s.io images import /tmp/draft-latest.tar"
#   done
```

**Install:**

```bash
# Extract the token from .env and run the upgrade
MCP_TOKEN=$(grep DRAFT_MCP_TOKEN .env | cut -d '=' -f2) && \
helm install draft ./kubernetes/draft \
  --namespace draft --create-namespace \
  --set image.pullPolicy=Never \
  --set mcp.token="$MCP_TOKEN" \
  --set hfCache.hostPath=/path/to/ai_models     # omit if downloading from HF Hub
```

**Verify:**

```bash
kubectl get pods -n draft
kubectl port-forward svc/draft 8059:8059 -n draft
curl http://localhost:8059/health
# → {"status": "ok", "llm_ready": ..., "index_ready": ...}
```

**Bootstrap DRAFT_HOME (sources and docs)**  
The pod’s PVC starts empty: no `sources.yaml` and no `.doc_sources/`. So `list_sources` and `retrieve_chunks` will be empty until you supply sources and content.

- **Option A — Helm values (recommended):** Copy `kubernetes/draft/values.mcp.yaml` to `kubernetes/draft/values.local.yaml` (gitignored), fill in your real host paths, and deploy with both overlays: `helm upgrade draft ./kubernetes/draft -n draft -f kubernetes/draft/values.mcp.yaml -f kubernetes/draft/values.local.yaml`. `sourcesConfig` is the YAML body for `sources.yaml` (repos and their container-side `source` paths). `docSources` mounts host paths read-only into the pod; each `source` in `sourcesConfig` must match a `mountPath`. The chart mounts `sources.yaml` from a ConfigMap and the doc dirs from hostPath. No pull in-pod; the indexer reads mounted docs directly. See `kubernetes/draft/values.yaml` for all options.
- **Option B — Manual:** Create `sources.yaml` and `.doc_sources/` (or run `pull`) inside the pod or via a Job that uses the same PVC, then run the RAG indexer in the pod. See `docs/container_orchestration.md` for disk layout and `scripts/pull.py` for pull behavior.

After bootstrap, run the indexer so `index_ready` is true and `retrieve_chunks` returns results:

```bash
kubectl -n draft exec deployment/draft -- python -c "
from scripts.index_for_ai import main
main(['--profile', 'quick'])
"
```

**Configure LLM after install:**

```bash
helm upgrade draft ./kubernetes/draft --namespace draft \
  --reuse-values \
  --set env.llmProvider=claude \
  --set env.llmModel=claude-sonnet-4-6 \
  --set secrets.anthropicApiKey="sk-ant-..."
```

**Uninstall:**

```bash
helm uninstall draft --namespace draft
kubectl delete namespace draft   # also deletes the PVC
```

See `docs/container_orchestration.md` for the full Kubernetes reference, all Helm values, and OTel configuration.

---

### 6. Docker (HTTP)

No docker-compose exists yet; run directly from the same image as the UI:

```bash
# Build (same Dockerfile, same image)
docker build -t draft .

# Run MCP server (port 8059)
docker run -d \
  --name draft-mcp \
  -p 8059:8059 \
  -v ~/.draft:/root/.draft \
  --env-file .env \
  --env-file .env.docker \
  draft \
  python scripts/serve_mcp.py

# Logs
docker logs -f draft-mcp

# Stop
docker stop draft-mcp && docker rm draft-mcp
```

> **Note:** If using Ollama on the host, `.env.docker` sets `OLLAMA_HOST=http://host.docker.internal:11434`. On Linux replace with `http://172.17.0.1:11434` or use `--network=host`.

---

## Kubernetes Operations

Complete SRE runbook for managing Draft in Kubernetes: config changes, deploy, index, and verify.

**Files involved:**

| File | Purpose | Committed? |
|------|---------|-----------|
| `kubernetes/draft/values.yaml` | Default values — do not edit for deployments | Yes |
| `kubernetes/draft/values.mcp.yaml` | `sourcesConfig` only — container-side source paths. Safe to commit; no host paths. | Yes |
| `kubernetes/draft/values.local.yaml` | Local cluster behaviour + host paths: `image.pullPolicy`, `hfCache.hostPath`, `env.hfHubOffline`, `docSources`. Gitignored; lives next to `values.mcp.yaml`. | No (gitignored) |

**Why two files:** Helm arrays don't merge — a later `-f` file fully replaces an earlier array. `values.mcp.yaml` owns the pod's view (`sourcesConfig` — container paths, safe to commit). `values.local.yaml` owns the host's view (`docSources` — real host paths) plus local cluster settings (`image.pullPolicy: Never`, pre-cached HF models). Neither is redundant; together they produce a complete config.

---

### Helm values reference

#### `values.yaml` — defaults (all environments)

| Value | Default | Description |
|-------|---------|-------------|
| `replicaCount` | `1` | Number of pod replicas. Keep at 1 — the PVC is ReadWriteOnce. |
| `image.repository` | `draft` | Image name for local clusters; full registry path for cloud (e.g. `gcr.io/my-project/draft`). |
| `image.tag` | `latest` | Image tag. Pin to a SHA or semver in production. |
| `image.pullPolicy` | `IfNotPresent` | Cloud default. Set `Never` (local: no registry) or `Always` (CI/CD with mutable tag) in `values.local.yaml`. |
| `mcp.port` | `8059` | Port the MCP HTTP server listens on inside the container. Must match `service.port`. |
| `mcp.token` | `""` | Bearer token for MCP auth. Auto-generated at startup if empty (printed to stderr). Set a stable value so it survives restarts. Generate with `openssl rand -base64 32`. |
| `mcp.existingSecret` | `""` | Name of a pre-existing Kubernetes Secret with key `DRAFT_MCP_TOKEN`. Use for GitOps / external secret managers. Overrides `mcp.token`. |
| `draftHome` | `/data/draft` | `DRAFT_HOME` inside the container. All app state lives here. Must match the PVC mount path. |
| `persistence.enabled` | `true` | Create a PVC for `DRAFT_HOME`. Set `false` only for quick ephemeral tests. |
| `persistence.storageClass` | `""` | StorageClass for the PVC. Empty = cluster default (local-path for kind; gp2/pd-ssd for cloud). |
| `persistence.size` | `2Gi` | PVC size. Increase to 5–10 Gi if you have many sources or larger embedding models. |
| `persistence.accessMode` | `ReadWriteOnce` | Standard for single-replica. Change only with a multi-replica + shared-storage setup. |
| `sourcesConfig` | `""` | YAML body for `sources.yaml`, injected via ConfigMap and mounted at `DRAFT_HOME/sources.yaml`. Set in `values.mcp.yaml`, not here. |
| `docSources` | `[]` | List of `{name, hostPath, mountPath}`. Each entry creates a read-only hostPath volume in the pod. **Arrays do not merge across `-f` files** — define the full list in one file (`values.local.yaml`). |
| `hfCache.hostPath` | `""` | Host node path to mount as the HuggingFace model cache (`DRAFT_HOME/.cache/huggingface`). Empty = models download to PVC on first use. Set in `values.local.yaml` for local clusters. |
| `env.hfHubOffline` | `"0"` | `"1"` blocks all HF Hub network access (use when all models are pre-cached). `"0"` allows downloads at runtime. |
| `env.llmProvider` | `""` | LLM provider for AI Q&A: `claude`, `gemini`, `openai`, `ollama`. Empty = AI Q&A disabled. |
| `env.llmModel` | `""` | Model name for the chosen provider (e.g. `claude-sonnet-4-6`, `gpt-4o`, `qwen3:8b`). |
| `secrets.anthropicApiKey` | `""` | Anthropic API key. Required when `env.llmProvider=claude`. Pass via `--set` at deploy time. |
| `secrets.geminiApiKey` | `""` | Google AI API key. Required when `env.llmProvider=gemini`. |
| `secrets.openaiApiKey` | `""` | OpenAI API key. Required when `env.llmProvider=openai`. |
| `otel.serviceName` | `draft-mcp` | Service name tag on all traces and metrics (`OTEL_SERVICE_NAME`). |
| `otel.otlpEndpoint` | `""` | OTLP HTTP collector endpoint. Empty = console exporter (output to pod logs or file). |
| `otel.metricsLog` | `stdout` | Console exporter destination: `stdout` (pod logs, recommended) or a file path on the PVC. |
| `service.type` | `ClusterIP` | Kubernetes Service type. Use `ClusterIP` + `kubectl port-forward` for local access. |
| `service.port` | `8059` | Service port. Must match `mcp.port`. |
| `resources` | `{}` | CPU/memory requests and limits. Recommended: `memory >= 1Gi` (embedding model ~500 MB + app). |
| `nodeSelector` | `{}` | Constrain pod to nodes with specific labels. |
| `tolerations` | `[]` | Allow pod to schedule on tainted nodes. |
| `affinity` | `{}` | Node/pod affinity and anti-affinity rules. |

#### `values.local.yaml` — local cluster overrides (gitignored)

This file is never committed. It holds everything that is specific to your machine or local cluster.

| Value | Example | Description |
|-------|---------|-------------|
| `image.pullPolicy` | `Never` | Required for kind/k3s/minikube — image is loaded locally, no registry. Use `Always` or `IfNotPresent` for cloud. |
| `hfCache.hostPath` | `/Users/you/ai_models` | Absolute path on the host node to a pre-downloaded HuggingFace model cache. Mounted over `DRAFT_HOME/.cache/huggingface`. Models needed: `sentence-transformers/all-MiniLM-L6-v2` (~90 MB) and `cross-encoder/ms-marco-MiniLM-L-6-v2` (~67 MB). |
| `env.hfHubOffline` | `"1"` | Set `"1"` when `hfCache.hostPath` is populated — blocks HF Hub network access and prevents startup delays. |
| `docSources[].name` | `runbooks` | Kubernetes volume name — unique, lowercase, no underscores. Used internally; not visible to the app. |
| `docSources[].hostPath` | `/Volumes/External/docs/runbooks` | Absolute path on the **host node** to the document directory. Must exist before the pod starts. |
| `docSources[].mountPath` | `/mnt/docs/runbooks` | Path **inside the container** where the directory appears. Must exactly match the corresponding `source:` entry in `values.mcp.yaml` `sourcesConfig`. |

---

### Local Kubernetes (Mac Mini / kind / on-prem)

#### First-time setup

```bash
# 1. Build image
docker build -t draft:latest .

# 2. Load image into local cluster (kind is required, brew install kind)
kind load docker-image draft:latest
# For other local clusters: scp the tar to each node and import with ctr

# 3. Create kubernetes/draft/values.local.yaml (gitignored — never committed)
#    Local cluster behaviour + host-specific paths. Three categories:
#      image.pullPolicy  — Never: image only exists locally (kind load), no registry
#      hfCache.hostPath  — pre-downloaded models on the host; avoids re-downloading at startup
#      env.hfHubOffline  — "1": block HF Hub network access (all models are pre-cached)
#      docSources        — real host paths for each document directory
#    (values.mcp.yaml holds sourcesConfig — the container-side source paths, committed.)
cat > kubernetes/draft/values.local.yaml << 'EOF'
# Local image loaded via: kind load docker-image draft:latest
# Never pull from a registry — the image only exists locally.
image:
  pullPolicy: Never

# Pre-downloaded HuggingFace models on the host node.
# Mounted into the pod so models are available immediately without downloading.
hfCache:
  hostPath: /Users/you/ai_models   # adjust to your actual models directory

# Models are pre-cached on the host — disable HF Hub network access.
env:
  hfHubOffline: "1"

# Host-path mounts for document source directories.
# mountPath must match the source paths in kubernetes/draft/values.mcp.yaml sourcesConfig.
docSources:
  - name: runbooks
    hostPath: /Volumes/External/draft_mcp_doc/runbooks
    mountPath: /mnt/docs/runbooks
  - name: engineering
    hostPath: /Volumes/External/draft_mcp_doc/engineering
    mountPath: /mnt/docs/engineering
  - name: others
    hostPath: /Volumes/External/draft_mcp_doc/others
    mountPath: /mnt/docs/others
EOF
# Adjust hostPath values to match your actual directories.

# 4. Install
helm install draft ./kubernetes/draft \
  --namespace draft --create-namespace \
  --set mcp.token="$(openssl rand -base64 32)" \
  -f kubernetes/draft/values.mcp.yaml \
  -f kubernetes/draft/values.local.yaml
# image.pullPolicy=Never, hfCache.hostPath, and hfHubOffline are set in values.local.yaml

# 5. Verify pod is running
kubectl get pods -n draft
kubectl logs deployment/draft -n draft | tail -20
```

#### Updating source paths or adding a new doc directory

```bash
# 1. Edit kubernetes/draft/values.mcp.yaml — add the new repo entry to sourcesConfig
# 2. Edit kubernetes/draft/values.local.yaml — add the corresponding docSources entry with the real hostPath
# 3. Upgrade
helm upgrade draft ./kubernetes/draft -n draft \
  -f kubernetes/draft/values.mcp.yaml \
  -f kubernetes/draft/values.local.yaml

# 4. Confirm sources.yaml is correct inside the pod
kubectl -n draft exec deployment/draft -- cat /data/draft/sources.yaml

# 5. Confirm the new directory is visible
kubectl -n draft exec deployment/draft -- ls /mnt/docs/<new-source> | head -10
```

#### Applying changes to Draft Kubernetes deployment

After editing any values file, re-apply with `helm upgrade`. Any change to volumes (`hfCache.hostPath`, `docSources`) or env vars triggers an automatic pod restart.

**Local Kubernetes (kind / on-prem)** — edit `values.local.yaml` then:

```bash
helm upgrade draft ./kubernetes/draft -n draft \
  -f kubernetes/draft/values.mcp.yaml \
  -f kubernetes/draft/values.local.yaml
```

**Cloud (GKE / EKS / AKS)** — pass changed values as `--set` flags or update `values.mcp.yaml`, then:

```bash
helm upgrade draft ./kubernetes/draft -n draft \
  --reuse-values \
  --set image.tag=<new-tag> \        # if deploying a new image
  -f kubernetes/draft/values.mcp.yaml
```

**Verify after upgrade:**

```bash
# Pod restarted and is running
kubectl get pods -n draft

# Confirm env vars applied
kubectl -n draft exec deployment/draft -- env | grep -E 'HF_HUB|LLM|DRAFT'

# Confirm hfCache volume is mounted (local only)
kubectl get pod -n draft -o jsonpath='{.items[0].spec.volumes}' | python3 -m json.tool | grep -A3 hfcache
```

#### Updating the LLM provider or API key

```bash
helm upgrade draft ./kubernetes/draft -n draft \
  --reuse-values \
  --set env.llmProvider=claude \
  --set env.llmModel=claude-sonnet-4-6 \
  --set secrets.anthropicApiKey="sk-ant-..."
```

#### Rebuilding the RAG index

Run after any new `.md` files are added to a mounted directory, or after changing the embed model.

```bash
# Quick rebuild (daily / after new docs added)
kubectl -n draft exec deployment/draft -- \
  python scripts/index_for_ai.py --profile quick

# Deep rebuild (weekly / after embed model change)
kubectl -n draft exec deployment/draft -- \
  python scripts/index_for_ai.py --profile deep

# Expected output: "Indexed N chunks."  (N > 0 means success)
```

#### Rolling restart (pick up ConfigMap changes without helm upgrade)

```bash
kubectl rollout restart deployment/draft -n draft
kubectl rollout status deployment/draft -n draft
```

#### Verify and test

```bash
# 1. Health check (unauthenticated)
kubectl -n draft port-forward svc/draft 8059:8059 &
curl http://localhost:8059/health
# → {"status": "ok", "llm_ready": true, "index_ready": true, "version": "1.0"}
# index_ready must be true before clients call retrieve_chunks

# 2. Get the MCP token and establish session
TOKEN=$(kubectl -n draft get secret draft -o jsonpath='{.data.DRAFT_MCP_TOKEN}' | base64 -d)
BASE="http://localhost:8059/mcp"
HEADERS=(-H "Authorization: Bearer $TOKEN" \
         -H "Content-Type: application/json" \
         -H "Accept: application/json, text/event-stream")

SESSION=$(curl -si -X POST "$BASE" "${HEADERS[@]}" \
  -d '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"sre-test","version":"1.0"}}}' \
  | grep -i "mcp-session-id" | awk '{print $2}' | tr -d '\r')
echo "Session: $SESSION"

# 3. List sources — confirms sources.yaml is mounted and parsed
curl -s -X POST "$BASE" "${HEADERS[@]}" -H "Mcp-Session-Id: $SESSION" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_sources","arguments":{}}}' \
  | grep '^data:' | cut -c7- | python3 -m json.tool
# Expect: runbooks, engineering, others each with doc_count > 0

# 4. Semantic search — confirms vector index is built
curl -s -X POST "$BASE" "${HEADERS[@]}" -H "Mcp-Session-Id: $SESSION" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"retrieve_chunks","arguments":{"query":"deployment runbook","top_k":3,"rerank":true}}}' \
  | grep '^data:' | cut -c7- | python3 -m json.tool
# Expect: chunks with repo/path/text/score. If IndexNotReady, rebuild index first.
```

#### Uninstall

```bash
helm uninstall draft -n draft
kubectl delete namespace draft    # also deletes the PVC (vector store, HF cache)
```

---

### Cloud Kubernetes (GKE / EKS / AKS)

> Production-grade GKE/EKS guide is forthcoming. The steps below cover the key differences from local Kubernetes.

#### Key differences from local

| Concern | Local Kubernetes | Cloud Kubernetes |
|---------|-----------------|-----------------|
| Image delivery | `kind load` / node import | Push to registry (ECR, GCR, Artifact Registry) |
| Doc sources | `hostPath` volumes on the node | CSI driver PV (e.g. Mountpoint for S3) or pre-populated PVC |
| `image.pullPolicy` | `Never` (local image) | `Always` or `IfNotPresent` |
| HF model cache | `hfCache.hostPath` on node | PVC (pre-populate or allow download at startup) |
| Token storage | `--set mcp.token=...` | External Secret (AWS Secrets Manager, GCP Secret Manager) via `mcp.existingSecret` |

#### Image: build and push to registry

```bash
# Build
docker build -t <registry>/draft:latest .

# Push
docker push <registry>/draft:latest

# Update values (or set in values file)
helm upgrade draft ./kubernetes/draft -n draft \
  --set image.repository=<registry>/draft \
  --set image.tag=latest \
  --set image.pullPolicy=Always \
  -f kubernetes/draft/values.mcp.yaml \
  -f kubernetes/draft/values.local.yaml
```

#### Doc sources: CSI-backed volumes (no code change)

For S3 or other cloud storage, mount the bucket as a filesystem using a CSI driver. The app sees it as a local path — `sources.yaml` and app code are unchanged.

```yaml
# kubernetes/draft/values.local.yaml — cloud variant (replace hostPath with PVC backed by CSI driver)
# docSources is left empty; volumes are defined manually or via a PV/PVC

# 1. Install Mountpoint for Amazon S3 CSI driver (or equivalent for GCS/Azure Blob)
# 2. Create a PersistentVolume + PersistentVolumeClaim bound to your S3 bucket
# 3. Add a volumeMount + volume to the pod via a custom values overlay
```

The `sourcesConfig` in `values.mcp.yaml` stays identical — source paths like `/mnt/docs/runbooks` still work, regardless of whether the backing store is a host directory or an S3 CSI mount.

#### Deploy

```bash
# Install
helm install draft ./kubernetes/draft \
  --namespace draft --create-namespace \
  --set image.repository=<registry>/draft \
  --set image.pullPolicy=Always \
  --set mcp.existingSecret=draft-mcp-secret \   # pre-created Secret with DRAFT_MCP_TOKEN
  --set env.llmProvider=claude \
  --set env.llmModel=claude-sonnet-4-6 \
  --set secrets.anthropicApiKey="sk-ant-..." \
  --set persistence.storageClass=<your-storageclass> \
  --set persistence.size=4Gi \
  -f kubernetes/draft/values.mcp.yaml \
  -f kubernetes/draft/values.local.yaml

# Upgrade (after image push or config change)
helm upgrade draft ./kubernetes/draft -n draft \
  --reuse-values \
  -f kubernetes/draft/values.mcp.yaml \
  -f kubernetes/draft/values.local.yaml
```

#### Rebuild index (same as local)

```bash
kubectl -n draft exec deployment/draft -- \
  python scripts/index_for_ai.py --profile quick
```

#### Verify (same as local, different access method)

In cloud, use an Ingress or LoadBalancer instead of `port-forward`:

```bash
# Get external endpoint
kubectl -n draft get svc draft

# Or if behind an Ingress:
curl https://<your-ingress-host>/health
# → {"status": "ok", "llm_ready": true, "index_ready": true, "version": "1.0"}
```

---

## Stopping the Server

```bash
# Local daemon (started with draft.sh):
./draft.sh mcp stop

# By process name (fallback):
pkill -f "serve_mcp.py"

# Docker:
docker stop draft-mcp

# Kubernetes:
helm uninstall draft --namespace draft
```

stdio processes are managed by the MCP client — Claude Desktop stops them automatically.

---

## Health & Status Verification

The `/health` endpoint is unauthenticated and is the primary liveness/readiness check.

```bash
curl http://localhost:8059/health
```

```json
{
  "status": "ok",
  "llm_ready": true,
  "index_ready": true,
  "version": "1.0"
}
```


| Field         | Meaning                                                            |
| ------------- | ------------------------------------------------------------------ |
| `status`      | Always `"ok"` if the process is alive                              |
| `llm_ready`   | LLM provider is configured in `.env` (`query_docs` will work)      |
| `index_ready` | Vector store exists and is non-empty (`retrieve_chunks` will work) |


If `index_ready` is `false`, run a rebuild before clients call `retrieve_chunks`:

```bash
python scripts/index_for_ai.py --profile quick
```

---

## Client Integration

### Claude Desktop (stdio)

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "draft": {
      "command": "python",
      "args": ["/path/to/draft/scripts/serve_mcp.py", "--stdio"],
      "env": {
        "DRAFT_HOME": "/Users/yourname/.draft"
      }
    }
  }
}
```

Restart Claude Desktop. In any conversation, Draft's tools will appear in the tool picker. The `answer_from_docs` prompt is available under the prompts menu.

### HTTP client (any agent / curl)

**Step 1: Get the token**

```bash
# From .env
grep DRAFT_MCP_TOKEN .env

# Or read from startup log if auto-generated
python scripts/serve_mcp.py 2>&1 | head -5
# [draft-mcp] No DRAFT_MCP_TOKEN set. Generated token for this session:
#   <TOKEN>
```

**Step 2: Set the token persistently**

```bash
echo "DRAFT_MCP_TOKEN=your-token-here" >> .env
```

**Step 3: Initialize a session**

The Streamable HTTP transport requires an `initialize` handshake. The server returns an `Mcp-Session-Id` header that must be included in all subsequent requests.

```bash
TOKEN=$(grep DRAFT_MCP_TOKEN .env | cut -d= -f2)
BASE="http://localhost:8059/mcp"
HEADERS=(-H "Authorization: Bearer $TOKEN" \
         -H "Content-Type: application/json" \
         -H "Accept: application/json, text/event-stream")

SESSION=$(curl -si -X POST "$BASE" "${HEADERS[@]}" \
  -d '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' \
  | grep -i "mcp-session-id" | awk '{print $2}' | tr -d '\r')

echo "Session: $SESSION"
```

**Step 4: Make tool calls**

All tool calls go to `POST http://localhost:8059/mcp` with the session ID header. Responses are Server-Sent Events (SSE); pipe through `grep '^data:' | cut -c7-` to extract the JSON payload.

---

## Testing

### Full Test Suite

A full test suite is in `tests/test_mcp.py`.

```bash
source .venv/bin/activate
pytest tests/test_mcp.py -v
```

### Quick Individual Tests Setup (run once per shell session)

```bash
TOKEN=$(grep DRAFT_MCP_TOKEN .env | cut -d= -f2)
BASE="http://localhost:8059/mcp"
HEADERS=(-H "Authorization: Bearer $TOKEN" \
         -H "Content-Type: application/json" \
         -H "Accept: application/json, text/event-stream")

SESSION=$(curl -si -X POST "$BASE" "${HEADERS[@]}" \
  -d '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' \
  | grep -i "mcp-session-id" | awk '{print $2}' | tr -d '\r')

echo "Session: $SESSION"
```

---

### Test 1 — List available sources

Verifies the server is running, auth works, and `sources.yaml` is read correctly.

```bash
curl -s -X POST "$BASE" "${HEADERS[@]}" -H "Mcp-Session-Id: $SESSION" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "list_sources",
      "arguments": {}
    }
  }' | grep '^data:' | cut -c7- | python3 -m json.tool
```

If `SESSION` is empty, the `initialize` call failed — check the token and that the server is running. If the server returns 500, restart the MCP server after code changes; ensure `DRAFT_HOME` (or default `~/.draft`) has `sources.yaml`.

**Expected response:**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "[{\"name\": \"draft\", \"source\": \".\", \"url\": null, \"doc_count\": 12}, ...]"
      }
    ],
    "isError": false
  }
}
```

The `text` field contains a JSON-encoded list of repo objects. If `doc_count` is 0 for all repos, run `python scripts/pull.py` first.

---

### Test 2 — Semantic search for a concept

Verifies the vector index is built and `retrieve_chunks` returns ranked results.

```bash
curl -s -X POST "$BASE" "${HEADERS[@]}" -H "Mcp-Session-Id: $SESSION" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "retrieve_chunks",
      "arguments": {
        "query": "how to check the high-level status of the InferenceService and view the rollout status of the underlying predictor deployment?",
        "top_k": 3,
        "rerank": true
      }
    }
  }' | grep '^data:' | cut -c7- | python3 -m json.tool
```

**Expected response** (abbreviated):

```json
{
    "jsonrpc": "2.0",
    "id": 2,
    "result": {
        "content": [
            {
                "type": "text",
                "text": "{\n  \"repo\": \"runbooks\",\n  \"path\": \"Inference_runbook.md\",\n  \"heading\": \"Deployment and rollout\",\n  \"text\": \"Each model is an **InferenceService**; KServe creates a **Deployment** and **Service** for the predictor. Check InferenceService `.status.conditions` for Ready, and the underlying Deployment rollout status. Stuck or failed rollouts appear here.\\n\\n**Commands**\\n\\n```bash\\n# List InferenceServices and high-level status\\nkubectl get inferenceservice -n inference\\n\\n# InferenceService conditions and status (replace <model-name> with e.g. qwen3-8b)\\nkubectl describe inferenceservice <model-name> -n inference\\n\\n# Underlying Deployments (KServe names them <model-name>-predictor)\\nkubectl get deployment -n inference\\n\\n# Rollout status for a predictor Deployment (replace <model-name> with actual name)\\nkubectl rollout status deployment/<model-name>-predictor -n inference\\n\\n# ReplicaSets and desired/current replicas\\nkubectl get replicaset -n inference -l neural-gate/role=model-server\\n```\\n\\n---\",\n  \"score\": 7.6109\n}"
            },
```

Each chunk has `repo`, `path`, `heading`, `text`, `score`, `start_line`, `end_line`. The client LLM uses these chunks to write its own synthesized answer.

**If `isError: true` with `IndexNotReady`:**

```bash
python scripts/index_for_ai.py --profile quick
# Then retry
```

---

### Test 3 — Auth rejection

Confirms the middleware is active.

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -X POST http://localhost:8059/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{}'
# → 401

curl -s -o /dev/null -w "%{http_code}" \
  -X POST http://localhost:8059/mcp \
  -H "Authorization: Bearer wrong-token" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{}'
# → 401
```

---

## Tool Reference (Client Quick Card)


| Tool              | When to call                               | Key parameters                    |
| ----------------- | ------------------------------------------ | --------------------------------- |
| `list_sources`    | Always first — understand what repos exist | none                              |
| `search_docs`     | Keyword / exact phrase lookup              | `query`, `limit=20`               |
| `retrieve_chunks` | Conceptual / semantic questions (primary)  | `query`, `top_k=5`, `rerank=true` |
| `get_document`    | Read a full document by path               | `repo`, `path`                    |
| `list_documents`  | Browse what files exist in a repo          | `repo`                            |
| `query_docs`      | Non-LLM clients wanting a complete answer  | `question`                        |


**Decision guide for LLM clients:**

```
Do I know the exact document I need?
  → get_document(repo, path)

Do I have a keyword to search for?
  → search_docs(query) to find paths, then get_document if needed

Do I have a question or concept?
  → retrieve_chunks(query, top_k=5)   ← use chunks as your context, synthesize yourself

Am I a non-LLM client that needs a complete answer?
  → query_docs(question)
```

---

## Best Practices

### For operators

**Set a persistent token.** A random token changes on every restart, breaking any clients configured with the old value.

```bash
# Generate once and store
python -c "import secrets; print(secrets.token_urlsafe(32))"
# → paste into .env: DRAFT_MCP_TOKEN=<value>
```

**Keep the vector index current.** When new docs are pulled (`scripts/pull.py`), rebuild the index:

```bash
python scripts/index_for_ai.py --profile quick   # fast, good for daily updates
python scripts/index_for_ai.py --profile deep    # thorough, run weekly or after large ingestions
```

**Run behind a reverse proxy for TLS in production.** The server binds to `0.0.0.0:8059` with no TLS. For anything beyond a local network, add nginx or Caddy in front:

```nginx
location /mcp/ {
    proxy_pass http://127.0.0.1:8059/;
}
```

**Use JSON logs for production.** `MCP_LOG_JSON=1` writes machine-parseable JSON lines to `~/.draft/draft-mcp.log`, which can be tailed or forwarded to log aggregators (Loki, CloudWatch, Datadog):

```bash
MCP_LOG_JSON=1 python scripts/serve_mcp.py
# Logs land in ~/.draft/draft-mcp.log automatically
```

**stdio for local, HTTP for remote.** Don't expose the HTTP server on a public interface without a token and ideally TLS. stdio is always safe — it never opens a port.

### For LLM clients / agents

**Call `list_sources` once at session start**, not on every query. Cache the result.

**Use `retrieve_chunks` as the primary tool.** `search_docs` is complementary for keyword recall but has no semantic understanding. `query_docs` adds a second LLM call with no benefit if you're already an LLM.

**Include `repo` and `path` in your citations.** Both fields are present in every chunk. Cite as `repo/path` or link to the doc by path. This is the contract between Draft and its clients.

**Handle `IndexNotReady` gracefully.** If `retrieve_chunks` returns `IndexNotReady`, surface it to the user rather than silently falling back to `search_docs` only — it means the semantic index is missing, which affects answer quality significantly.

---

## Troubleshooting


| Symptom                              | Likely cause                    | Fix                                                                             |
| ------------------------------------ | ------------------------------- | ------------------------------------------------------------------------------- |
| `ImportError: No module named 'mcp'` | SDK not installed               | `pip install "mcp>=1.0"`                                                        |
| `IndexNotReady` on `retrieve_chunks` | Vector store not built          | `python scripts/index_for_ai.py --profile quick`                                |
| `LLMNotConfigured` on `query_docs`   | No provider in `.env`           | Set `DRAFT_LLM_PROVIDER` and matching API key                                   |
| `SourceNotFound` on `get_document`   | Repo name wrong                 | Call `list_sources` to get exact names                                          |
| `401 Unauthorized`                   | Token mismatch                  | Check `DRAFT_MCP_TOKEN` in `.env`; restart server after changing                |
| `doc_count: 0` in `list_sources`     | Docs not pulled                 | Run `python scripts/pull.py`                                                    |
| Empty `retrieve_chunks` results      | Index empty or query too narrow | Try `search_docs` first; rebuild index with `--profile deep`                    |
| Claude Desktop shows no tools        | stdio process not starting      | Check `claude_desktop_config.json` path; run the command manually to see stderr |


