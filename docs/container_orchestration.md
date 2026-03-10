# Container orchestration guide for Draft

This guide describes the **infrastructure design** for running Draft in containers (Docker and Kubernetes), how to deploy it, and how models are managed, changed, downloaded, and accessed. The goal is to keep the project **ready for container orchestration**.

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

| Variable | Purpose |
|----------|---------|
| **DRAFT_HOME** | Data root. Set to the volume mount path in the container (e.g. `/.draft`). |
| **DRAFT_LLM_ENDPOINT** | Unified LLM base URL (Ollama or OpenAI-compatible). When set, it overrides provider-based config. |
| **DRAFT_LLM_API_KEY** | Optional. Set for OpenAI-compatible endpoint. Omit for Ollama. |
| **DRAFT_LLM_MODEL** | Model name for the unified endpoint. |
| **OLLAMA_HOST** | Ollama base URL when **DRAFT_LLM_ENDPOINT** is not set (e.g. `http://host.docker.internal:11434`). |
| **OLLAMA_MODEL** | Model name for Ollama (e.g. `qwen3:8b`). |
| **DRAFT_EMBED_MODEL**, **DRAFT_CROSS_ENCODER_MODEL** | Embed and encoder model names. Re-read on each reindex. After changing embed model, rebuild the index so Ask uses it. |
| **DRAFT_EMBED_PROVIDER** | Set to `ollama` when you use an Ollama embed model. |

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

The sections above cover infrastructure: Helm values, PVCs, config, and image delivery. For the day-to-day SRE workflow — updating source paths, deploying with values overlays, rebuilding the RAG index, and verifying the MCP server end-to-end — see:

**[MCP Operations → Kubernetes Operations](MCP_operations.md#kubernetes-operations)**

That section is the canonical operational runbook and covers:

| Task | Where |
|------|-------|
| First-time setup (image load, values.local.yaml, helm install) | [Local Kubernetes](MCP_operations.md#local-kubernetes-mac-mini--kind--on-prem) |
| Adding a new doc source / updating source paths | [Updating source paths](MCP_operations.md#updating-source-paths-or-adding-a-new-doc-directory) |
| Rebuilding the RAG index after new docs | [Rebuilding the RAG index](MCP_operations.md#rebuilding-the-rag-index) |
| Full verify + MCP test sequence (health → token → session → list\_sources → retrieve\_chunks) | [Verify and test](MCP_operations.md#verify-and-test) |
| Cloud Kubernetes differences (image registry, CSI-backed S3 volumes, ExternalSecret) | [Cloud Kubernetes](MCP_operations.md#cloud-kubernetes-gke--eks--aks) |

---

## Container image optimization

For detailed guidance on slimming the Docker image, multi-stage builds, virtualenv layout, and model cache handling, see **[Container optimization](container_optimization.md)**.

## Security

- **Secrets:** Keep API keys in Secrets (Kubernetes) or `.env` (Docker). Do not put them in the image.
- **Mounts:** Mount only the data and cache paths you need. Do not mount the whole host or cluster filesystem.
- **Network:** Restrict access to the LLM endpoint and to Hugging Face (if you allow downloads) as your policy requires.
- **Image:** Build from the repo Dockerfile. Keep the image updated for security fixes.
