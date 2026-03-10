# Container orchestration guide for Draft

This guide describes the **infrastructure design** for running Draft in containers (Docker and Kubernetes), how to deploy it, and how models are managed, changed, downloaded, and accessed. The goal is to keep the project **ready for container orchestration**.

## Container image optimization

For detailed guidance on slimming the Docker image, multi-stage builds, virtualenv layout, and model cache handling, see **[Container optimization](container_optimization.md)**.

---

## Infrastructure design for container orchestration

Draft is designed so that **configuration is outside the image** and **models are not baked in**. So you can use Docker and Kubernetes without rebuilding the image when you change models or LLM endpoints.

**How models are managed and changed**

- **Embedding and encoder (reranker):** Model names come from environment configuration (e.g. `.env` or a ConfigMap). The app **re-reads** this configuration on each **reindex**. At Ask time, the embed model comes from the index (collection metadata). If you change `DRAFT_EMBED_MODEL` or `DRAFT_CROSS_ENCODER_MODEL`, you do not need to restart the container or pod; the next **reindex** uses the new model. After changing the embed model, rebuild the RAG index so Ask uses it.
- **LLM (chat):** One **unified endpoint** is used: a single URL (`DRAFT_LLM_ENDPOINT`) that can point to local Ollama, an in-cluster Ollama or gateway, or a public OpenAI-compatible API. If you change the endpoint (e.g. in a ConfigMap), the app points to the new target; the app re-reads env on each Ask. No restart needed.

**How models are downloaded and accessed**

- **Hugging Face** (embed and encoder): Models are **downloaded at runtime** the first time they are needed. They are stored in a cache directory (e.g. `/app/.cache/huggingface` in the container). In Docker you mount a **named volume** for this path so the cache persists across restarts; in Kubernetes you use a **PersistentVolumeClaim**. When you switch to a different embed or encoder model, you do not need to rebuild the image; the new model is downloaded into the same cache volume on first use.
- **Ollama** (LLM and optional embed): The container does not run the model. It sends HTTP requests to an **endpoint** (e.g. `OLLAMA_HOST` or `DRAFT_LLM_ENDPOINT`). That endpoint can be the host (Docker), another container, or a Kubernetes Service. Nothing is downloaded inside the Draft container.

**Why this project is ready for container deployment**

- **Single data root** (`DRAFT_HOME`): All runtime data (sources, vault, pulled docs, vector store at `.vector_store/`) lives under one directory. You mount this directory as a volume. No hardcoded host paths. The RAG index persists in containers because it is stored under `DRAFT_HOME`.
- **Env-driven config:** Embed, encoder, and LLM are configured via environment variables (and optional mounted `.env`). The same image works for local Ollama, in-cluster Ollama, or cloud LLM; you only change env (ConfigMap/Secret).
- **No restart for config changes:** You mount `.env` (Docker) or update ConfigMap/Secret (Kubernetes). The app re-reads on each request. So you can change models and endpoints without restarting the container or pod.
- **Unified LLM endpoint:** One URL (`DRAFT_LLM_ENDPOINT`) plus optional API key supports both Ollama-style and OpenAI-compatible backends. In Kubernetes you can point Draft at any in-cluster or public LLM by updating the endpoint.

The sections below give concrete steps for **Docker** and **Kubernetes**.

---

## Disk space

### Estimated usage

| Volume | Typical | Heavy | Components |
|-------|---------|-------|------------|
| **DRAFT_HOME** | 50–200 MB | up to ~500 MB | sources.yaml, `.doc_sources/`, `vault/`, `.vector_store/`, `.clones/` |
| **HF cache** (under DRAFT_HOME) | 250 MB (quick) / 750 MB (deep) | ~1 GB (both profiles) | Embed models (~90 MB quick, ~550 MB deep), cross-encoder (~90 MB). Stored at `DRAFT_HOME/.cache/huggingface`. Hugging Face checks the cache before downloading. |

### Allocation (2× estimate)

Use **2×** the estimated usage for headroom:

| Volume | Estimate | Allocated (2×) |
|--------|----------|----------------|
| **DRAFT_HOME** (data + HF cache) | 1.5 GB | **4 Gi** |

- **Docker:** Mount `~/.draft` (or your data dir). HF cache is at `DRAFT_HOME/.cache/huggingface`; you do not need a separate volume. The host should have at least **4 GB free** before you run.
- **Kubernetes:** Use one PVC for DRAFT_HOME at **2–4 Gi** (2 Gi default in the Helm chart; increase `persistence.size` if you index many repos or use deep embed models).

---

## Docker deployment guide

### Build the image

From the repo root:

```bash
docker build -t draft-ui .
```

### Run with your data and config

**Minimal:** Use your existing `~/.draft` so the container sees sources and vault.

```bash
docker run -p 8058:8058 -v ~/.draft:/root/.draft draft-ui
```

**With LLM config and host Ollama:** Mount `.env` and set `OLLAMA_HOST` so the container can reach Ollama on the host.

```bash
docker run -p 8058:8058 \
  -v ~/.draft:/root/.draft \
  -v /path/to/draft/repo/.env:/app/.env:ro \
  -e OLLAMA_HOST=http://host.docker.internal:11434 \
  draft-ui
```

Replace `/path/to/draft/repo` with your Draft repo path. Then open http://localhost:8058.

**Using env files (recommended):**

When you use **local Ollama**, create `.env.docker` in the repo with `OLLAMA_HOST=http://host.docker.internal:11434` (or run setup.sh option 6 once). Example:

```bash
docker run -p 8058:8058 \
  -v ~/.draft:/root/.draft \
  --env-file /path/to/draft/repo/.env \
  --env-file /path/to/draft/repo/.env.docker \
  -e DRAFT_HOME=/root/.draft \
  draft-ui
```

If you mount `~/.draft` at `/root/.draft`, you can omit `-e DRAFT_HOME`. If you mount elsewhere (e.g. `/.draft`), set `-e DRAFT_HOME=/.draft`.

### Via setup.sh

Run `./setup.sh` and choose **8) Run Draft in a Docker container**. The script:

- Detects local vs cloud LLM and creates `.env.docker` when you use Ollama.
- Stops any running `draft-ui` container and starts a new one with mounts for **`.env`** and **DRAFT_HOME**. HF cache is at `DRAFT_HOME/.cache/huggingface`; no separate volume.

When you change embed, encoder, or LLM in `.env`, you do not need to restart; the app re-reads on each reindex (and for LLM, on each Ask). After changing the embed model, rebuild the RAG index so it takes effect.

### Configuration summary

See [MCP operations — Configuration](MCP_operations.md#configuration) for the full environment variable reference (`DRAFT_LLM_PROVIDER`, `DRAFT_MCP_TOKEN`, model names, etc.).

**Mounts**

- **DRAFT_HOME:** Mount your data dir (e.g. `~/.draft`) so the app can read and write `sources.yaml`, `.doc_sources/`, `vault/`, `.vector_store/`, and `DRAFT_HOME/.cache/huggingface` (HF models). The host should have about 4 GB free.
- **`.env`:** Mount the repo `.env` at `/app/.env:ro` so config changes (embed/encoder/LLM) take effect without restart.

### Resource and security notes

- **LLM:** When you use Ollama, the LLM runs on the host (or wherever the endpoint points). The container only sends HTTP requests. When you use cloud or an in-cluster gateway, the container only forwards requests.
- **Embed (Ollama):** Same as LLM—HTTP to the endpoint. **Embed (Hugging Face)** and **rerank:** They run inside the container. Models are cached under `DRAFT_HOME/.cache/huggingface`; the app checks the cache before download.
- **Secrets:** Keep API keys in `.env` or use Docker secrets. Do not put them in the image. Use a read-only mount for `.env` when you can.

---

## Kubernetes deployment guide

The Kubernetes deployment uses a **Helm chart** at `kubernetes/draft/`. It deploys the **MCP server** (HTTP transport, port 8059) — Draft's primary programmatic interface for AI clients. No Dockerfile changes are needed; the chart overrides the container command to start the MCP server instead of the UI.

### Prerequisites

- **Helm 3** installed.
- The `draft` image built and accessible to your cluster:
  ```bash
  docker build -t draft .
  # For a remote cluster, push to your registry and update image.repository / image.tag in values.yaml
  ```
- A cluster with a StorageClass that supports `ReadWriteOnce` PVCs (most managed clusters provide one by default).

### Install

```bash
helm install draft ./kubernetes/draft
```

To set a stable Bearer token and LLM provider at install time:

```bash
helm install draft ./kubernetes/draft \
  --set mcp.token="$(openssl rand -base64 32)" \
  --set env.llmProvider=claude \
  --set secrets.anthropicApiKey="sk-ant-..."
```

### Key values

| Value | Default | Description |
|-------|---------|-------------|
| `replicaCount` | `1` | Number of MCP server pods |
| `image.repository` | `draft` | Container image name |
| `image.tag` | `latest` | Container image tag |
| `mcp.port` | `8059` | MCP HTTP server port |
| `mcp.token` | `""` | Bearer token (auto-generated if empty; check pod logs) |
| `mcp.existingSecret` | `""` | Use a pre-existing Secret for `DRAFT_MCP_TOKEN` |
| `draftHome` | `/data/draft` | `DRAFT_HOME` inside the container (must match PVC mount) |
| `persistence.size` | `2Gi` | PVC size for DRAFT_HOME (sources, vector store, HF cache) |
| `persistence.storageClass` | `""` | StorageClass for PVC (empty = cluster default) |
| `env.llmProvider` | `""` | LLM provider: `claude`, `gemini`, `openai`, or `ollama` |
| `env.llmModel` | `""` | Model name for the chosen provider |
| `secrets.anthropicApiKey` | `""` | Anthropic API key (stored in a k8s Secret) |
| `secrets.geminiApiKey` | `""` | Gemini API key |
| `secrets.openaiApiKey` | `""` | OpenAI API key |
| `otel.serviceName` | `draft-mcp` | OTel service name (`OTEL_SERVICE_NAME`) |
| `otel.otlpEndpoint` | `""` | OTLP collector endpoint; if set, enables OTLP exporters |
| `otel.metricsLog` | `stdout` | Metrics output: `stdout` (pod logs) or a file path on the PVC |
| `service.type` | `ClusterIP` | Kubernetes Service type |
| `resources` | `{}` | CPU/memory requests and limits for the MCP container |

Override any value with `--set key=value` or a custom values file passed with `-f`.

### Helm chart structure

| File | Description |
|------|-------------|
| `kubernetes/draft/Chart.yaml` | Chart metadata |
| `kubernetes/draft/values.yaml` | All configurable values with defaults and inline comments |
| `kubernetes/draft/values.mcp.yaml` | Committed overlay template: `sourcesConfig` + `docSources` with placeholder host paths. Pair with `kubernetes/draft/values.local.yaml` (gitignored) which supplies the real host paths. |
| `kubernetes/draft/values.local.yaml` | **Gitignored.** `docSources` only — your real host paths (e.g. `/Volumes/External/...`). Lives next to `values.mcp.yaml`. Applied alongside it: `helm upgrade ... -f kubernetes/draft/values.mcp.yaml -f kubernetes/draft/values.local.yaml`. |
| `kubernetes/draft/templates/deployment.yaml` | MCP server Deployment (1 replica by default) |
| `kubernetes/draft/templates/service.yaml` | ClusterIP Service on port 8059 |
| `kubernetes/draft/templates/configmap.yaml` | Non-secret env: DRAFT_HOME, HF_HUB_OFFLINE, LLM provider, OTel |
| `kubernetes/draft/templates/configmap-sources.yaml` | `sources.yaml` ConfigMap (rendered from `sourcesConfig`); mounted at `DRAFT_HOME/sources.yaml` via `subPath` |
| `kubernetes/draft/templates/secret.yaml` | DRAFT_MCP_TOKEN and LLM API keys |
| `kubernetes/draft/templates/pvc.yaml` | PVC for DRAFT_HOME (2 Gi default) |
| `kubernetes/draft/templates/_helpers.tpl` | Helm template helpers |

### LLM configuration in Kubernetes

Set the provider and API key via values:

```bash
# Claude
helm upgrade draft ./kubernetes/draft \
  --set env.llmProvider=claude \
  --set env.llmModel=claude-sonnet-4-6 \
  --set secrets.anthropicApiKey="sk-ant-..."

# Ollama in-cluster (no API key needed)
helm upgrade draft ./kubernetes/draft \
  --set env.llmProvider=ollama \
  --set env.llmModel=qwen3:8b
# Also set OLLAMA_HOST pointing at your in-cluster Ollama service via --set or a values file
```

### OpenTelemetry in Kubernetes

OTel requires no code changes. By default (`otel.metricsLog: stdout`), traces and metrics go to pod stdout, captured by `kubectl logs` and any log aggregator (Loki, Datadog, etc.).

For full observability with an OTLP-compatible collector:

```bash
helm upgrade draft ./kubernetes/draft \
  --set otel.otlpEndpoint="http://otel-collector.monitoring.svc.cluster.local:4318"
```

This switches OTel to OTLP HTTP exporters for both traces and metrics, compatible with Jaeger, Tempo, Prometheus, and any OTLP-capable backend.

### Differences from Docker

| Docker | Kubernetes (Helm) |
|--------|-------------------|
| `-v ~/.draft:/root/.draft` | PVC mounted at `draftHome` (`/data/draft` by default) |
| `--env-file .env` | ConfigMap (non-secret) + Secret (API keys, MCP token) |
| `-e DRAFT_MCP_TOKEN=...` | `--set mcp.token=...` or `mcp.existingSecret` |
| HF cache | Under `DRAFT_HOME/.cache/huggingface`; same PVC, no separate volume |

### Verify the deployment

```bash
kubectl get pods
kubectl port-forward svc/draft 8059:8059
curl http://localhost:8059/health
# → {"status": "ok", "llm_ready": ..., "index_ready": ...}
```

If `mcp.token` was not set, retrieve the auto-generated token from pod logs:

```bash
kubectl logs deployment/draft | grep "Generated token"
```

### Resource limits

If HF embed and reranker models run inside the pod, set memory `>= 1 Gi`. For external LLM (cloud API or in-cluster Ollama), the Draft pod itself is lightweight.

```yaml
resources:
  requests:
    cpu: 250m
    memory: 512Mi
  limits:
    cpu: 1000m
    memory: 2Gi
```

---

## Kubernetes Operations Runbook

The sections above cover infrastructure design, Helm chart reference, and Docker. This section is the day-to-day SRE runbook for deploying and operating Draft in Kubernetes.

For local and Docker operations (running modes, token management, health checks, client integration, testing) see **[MCP operations](MCP_operations.md)**.

---

### Helm values reference

#### `values.yaml` — defaults (all environments)

| Value | Default | Description |
|-------|---------|-------------|
| `replicaCount` | `1` | Number of pod replicas. Keep at 1 — the PVC is ReadWriteOnce. |
| `image.repository` | `draft` | Image name for local clusters; full registry path for cloud. |
| `image.tag` | `latest` | Image tag. Pin to a SHA or semver in production. |
| `image.pullPolicy` | `IfNotPresent` | Cloud default. Set `Never` in `values.local.yaml` for local clusters. |
| `mcp.port` | `8059` | MCP HTTP port inside the container. Must match `service.port`. |
| `mcp.token` | `""` | Bearer token. Auto-generated at startup if empty (printed to stderr). Set a stable value — generate with `openssl rand -base64 32`. |
| `mcp.existingSecret` | `""` | Pre-existing Secret with key `DRAFT_MCP_TOKEN`. Use for GitOps / external secret managers. Overrides `mcp.token`. |
| `draftHome` | `/data/draft` | `DRAFT_HOME` inside the container. All app state lives here. |
| `persistence.enabled` | `true` | Create a PVC for `DRAFT_HOME`. Set `false` only for ephemeral tests. |
| `persistence.storageClass` | `""` | Empty = cluster default. |
| `persistence.size` | `2Gi` | PVC size. Increase to 5–10 Gi for many sources or larger models. |
| `persistence.accessMode` | `ReadWriteOnce` | Standard for single-replica. |
| `sourcesConfig` | `""` | YAML body for `sources.yaml`, injected via ConfigMap. Set in `values.mcp.yaml`. |
| `docSources` | `[]` | List of `{name, hostPath, mountPath}`. Creates read-only hostPath volumes. **Arrays do not merge across `-f` files** — define the full list in one file (`values.local.yaml`). |
| `hfCache.hostPath` | `""` | Host path to mount as HuggingFace model cache. Empty = models download to PVC. Set in `values.local.yaml` for local clusters. |
| `env.hfHubOffline` | `"0"` | `"1"` blocks HF Hub network access (use when models are pre-cached). |
| `env.llmProvider` | `""` | LLM provider: `claude`, `gemini`, `openai`, `ollama`. Empty = AI Q&A disabled. |
| `env.llmModel` | `""` | Model name (e.g. `claude-sonnet-4-6`, `gpt-4o`, `qwen3:8b`). |
| `secrets.anthropicApiKey` | `""` | Anthropic API key. Pass via `--set` at deploy time. |
| `secrets.geminiApiKey` | `""` | Google AI API key. |
| `secrets.openaiApiKey` | `""` | OpenAI API key. |
| `otel.serviceName` | `draft-mcp` | OTel service name tag. |
| `otel.otlpEndpoint` | `""` | OTLP HTTP collector endpoint. Empty = console exporter. |
| `otel.metricsLog` | `stdout` | Console exporter output: `stdout` (pod logs) or a file path on the PVC. |
| `service.type` | `ClusterIP` | Use `ClusterIP` + `kubectl port-forward` for local access. |
| `resources` | `{}` | CPU/memory. Recommended: `memory >= 1Gi` (embedding model ~500 MB + app). |
| `indexOnColdStart` | `true` | Run init container that builds the index on cold start (empty PVC). |

#### `values.local.yaml` — local cluster overrides (gitignored)

| Value | Example | Description |
|-------|---------|-------------|
| `image.pullPolicy` | `Never` | Required for kind/minikube — image is loaded locally, no registry. |
| `mcp.token` | `"<openssl rand -base64 32>"` | Pin here so `helm upgrade` never overwrites it. |
| `hfCache.hostPath` | `/mnt/external/huggingface_models` | Host path to pre-downloaded HF models (`all-MiniLM-L6-v2` ~90 MB, `ms-marco-MiniLM-L-6-v2` ~67 MB). |
| `env.hfHubOffline` | `"1"` | Block HF Hub when models are pre-cached. |
| `docSources[].name` | `runbooks` | Kubernetes volume name — unique, lowercase, no underscores. |
| `docSources[].hostPath` | `/mnt/external/draft_mcp_doc/runbooks` | Absolute path on the **host node**. |
| `docSources[].mountPath` | `/mnt/docs/runbooks` | Path **inside the container**. Must match `sourcesConfig` source paths. |

---

### Local Kubernetes (Mac Mini / kind / minikube)

#### First-time setup

```bash
# 1. Start cluster with host mounts (minikube — Apple Silicon)
minikube start --driver=krunkit \
  --mount-string="/Volumes/External:/mnt/external" \
  --mount

# 2. Build and load image
docker build -t draft:latest .
minikube image load draft:latest    # or: kind load docker-image draft:latest

# 3. Create kubernetes/draft/values.local.yaml (gitignored)
cat > kubernetes/draft/values.local.yaml << 'EOF'
image:
  pullPolicy: Never
mcp:
  token: "<openssl rand -base64 32>"    # set a stable token
hfCache:
  hostPath: /mnt/external/huggingface_models
env:
  hfHubOffline: "1"
docSources:
  - name: runbooks
    hostPath: /mnt/external/draft_mcp_doc/runbooks
    mountPath: /mnt/docs/runbooks
  - name: engineering
    hostPath: /mnt/external/draft_mcp_doc/engineering
    mountPath: /mnt/docs/engineering
EOF

# 4. Install
helm install draft ./kubernetes/draft \
  --namespace draft --create-namespace \
  -f kubernetes/draft/values.mcp.yaml \
  -f kubernetes/draft/values.local.yaml

# 5. Verify
kubectl get pods -n draft
kubectl -n draft port-forward svc/draft 8059:8059
curl http://localhost:8059/health
# → {"status":"ok","index_ready":true,...}
```

#### Updating source paths or adding a new doc directory

```bash
# 1. Edit values.mcp.yaml — add new repo entry to sourcesConfig
# 2. Edit values.local.yaml — add corresponding docSources entry with real hostPath
# 3. Upgrade
helm upgrade draft ./kubernetes/draft -n draft \
  -f kubernetes/draft/values.mcp.yaml \
  -f kubernetes/draft/values.local.yaml

# 4. Confirm sources.yaml and directory are visible
kubectl -n draft exec deployment/draft -- cat /data/draft/sources.yaml
kubectl -n draft exec deployment/draft -- ls /mnt/docs/<new-source> | head -10
```

#### Applying changes

After editing any values file, re-apply with `helm upgrade`. Changes to volumes or env vars trigger an automatic pod restart.

```bash
helm upgrade draft ./kubernetes/draft -n draft \
  -f kubernetes/draft/values.mcp.yaml \
  -f kubernetes/draft/values.local.yaml
```

#### Rebuilding the RAG index

The index lives on the PVC and survives pod restarts, image rebuilds, and `helm upgrade`. Rebuild only when content changes:

| Event | Rebuild needed? |
|-------|----------------|
| New or updated `.md` files in a doc source directory | ✅ Yes |
| Embedding model changed | ✅ Yes |
| Cold start — new PVC after `helm uninstall` | ✅ Yes (handled automatically by init container) |
| `docker build` + rollout restart | ❌ No |
| `helm upgrade` (config change only) | ❌ No |
| Pod crash / container restart | ❌ No |

**Cold start is handled automatically** by the `index-builder` init container. On an empty PVC it builds the index before the MCP server starts; on a normal restart it exits in < 1 second.

```bash
# Manual rebuild — after new or updated docs
kubectl -n draft exec deployment/draft -- \
  python scripts/index_for_ai.py --profile quick

# Deep rebuild — after embedding model change
kubectl -n draft exec deployment/draft -- \
  python scripts/index_for_ai.py --profile deep

# Monitor cold-start build
kubectl logs -n draft -l app.kubernetes.io/name=draft -c index-builder -f
```

#### Rolling restart (pick up ConfigMap changes)

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

# 2. Get token and establish session
TOKEN=$(kubectl -n draft get secret draft -o jsonpath='{.data.DRAFT_MCP_TOKEN}' | base64 -d)
BASE="http://localhost:8059/mcp"
HEADERS=(-H "Authorization: Bearer $TOKEN" \
         -H "Content-Type: application/json" \
         -H "Accept: application/json, text/event-stream")

SESSION=$(curl -si -X POST "$BASE" "${HEADERS[@]}" \
  -d '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"sre-test","version":"1.0"}}}' \
  | grep -i "mcp-session-id" | awk '{print $2}' | tr -d '\r')

# 3. List sources
curl -s -X POST "$BASE" "${HEADERS[@]}" -H "Mcp-Session-Id: $SESSION" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_sources","arguments":{}}}' \
  | grep '^data:' | cut -c7- | python3 -m json.tool

# 4. Semantic search
curl -s -X POST "$BASE" "${HEADERS[@]}" -H "Mcp-Session-Id: $SESSION" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"retrieve_chunks","arguments":{"query":"deployment runbook","top_k":3,"rerank":true}}}' \
  | grep '^data:' | cut -c7- | python3 -m json.tool
```

#### Uninstall

```bash
helm uninstall draft -n draft
kubectl delete namespace draft    # also deletes the PVC (vector store, HF cache)
```

---

### Cloud Kubernetes (GKE / EKS / AKS)

#### Key differences from local

| Concern | Local | Cloud |
|---------|-------|-------|
| Image delivery | `kind load` / `minikube image load` | Push to registry (ECR, GCR, Artifact Registry) |
| Doc sources | `hostPath` volumes | CSI driver PV (e.g. Mountpoint for S3) or pre-populated PVC |
| `image.pullPolicy` | `Never` | `Always` or `IfNotPresent` |
| HF model cache | `hfCache.hostPath` on node | PVC (allow download at startup or pre-populate) |
| Token storage | `mcp.token` in `values.local.yaml` | External Secret via `mcp.existingSecret` |

#### Deploy

```bash
# Build and push
docker build -t <registry>/draft:latest .
docker push <registry>/draft:latest

# Install
helm install draft ./kubernetes/draft \
  --namespace draft --create-namespace \
  --set image.repository=<registry>/draft \
  --set image.pullPolicy=Always \
  --set mcp.existingSecret=draft-mcp-secret \
  --set env.llmProvider=claude \
  --set env.llmModel=claude-sonnet-4-6 \
  --set secrets.anthropicApiKey="sk-ant-..." \
  --set persistence.size=4Gi \
  -f kubernetes/draft/values.mcp.yaml

# Upgrade after image push or config change
helm upgrade draft ./kubernetes/draft -n draft \
  --reuse-values \
  -f kubernetes/draft/values.mcp.yaml
```

#### Doc sources: CSI-backed volumes

For S3 or other cloud storage, mount the bucket as a filesystem using a CSI driver. The app sees it as a local path — `sources.yaml` and app code are unchanged. `sourcesConfig` source paths like `/mnt/docs/runbooks` work identically regardless of backing store.

#### Verify

```bash
# Get external endpoint (LoadBalancer or Ingress)
kubectl -n draft get svc draft
curl https://<your-ingress-host>/health
# → {"status": "ok", "llm_ready": true, "index_ready": true, "version": "1.0"}
```

---

## Security

- **Secrets:** Keep API keys in Secrets (Kubernetes) or `.env` (Docker). Do not put them in the image.
- **Mounts:** Mount only the data and cache paths you need. Do not mount the whole host or cluster filesystem.
- **Network:** Restrict access to the LLM endpoint and to Hugging Face (if you allow downloads) as your policy requires.
- **Image:** Build from the repo Dockerfile. Keep the image updated for security fixes.
