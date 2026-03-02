# Container orchestration guide for Draft

This guide describes the **infrastructure design** for running Draft in containers (Docker and Kubernetes), how to deploy it, and how models are managed, changed, downloaded, and accessed so the project stays **container-orchestration ready**.

---

## Infrastructure design for container orchestration

Draft is designed so that **configuration is external to the image** and **models are not baked in**. That makes it suitable for Docker and Kubernetes without rebuilding the image when you change models or LLM endpoints.

**How models are managed and changed**

- **Embedding and encoder (reranker)** model names come from environment configuration (e.g. `.env` or a ConfigMap). The app **re-reads** this configuration on each **reindex**; at Ask time, the embed model comes from the index (collection metadata). Changing `DRAFT_EMBED_MODEL` or `DRAFT_CROSS_ENCODER_MODEL` does **not** require a container or pod restart—the next **reindex** uses the new model. Rebuild the RAG index after changing the embed model for it to take effect on Ask.
- **LLM (chat)** is driven by a **unified endpoint**: a single URL (`DRAFT_LLM_ENDPOINT`) that can point to local Ollama, an in-cluster Ollama or gateway, or a public OpenAI-compatible API. Changing the endpoint (e.g. in a ConfigMap) is enough to point to another deployment or public LLM; the app re-reads env on each Ask.

**How models are downloaded and accessed**

- **Hugging Face** (embed and encoder): Models are **downloaded at runtime** the first time they are needed. They are stored in a cache directory (e.g. `/app/.cache/huggingface` in the container). In Docker you mount a **named volume** for this path so the cache persists across restarts and new runs; in Kubernetes you use a **PersistentVolumeClaim**. No image rebuild is required when you switch to a different embed or encoder model—the new model is downloaded into the same cache volume on first use.
- **Ollama** (LLM and optional embed): The container does not run the model; it sends HTTP requests to an **endpoint** (e.g. `OLLAMA_HOST` or `DRAFT_LLM_ENDPOINT`). That endpoint can be the host (Docker), another container, or a Kubernetes Service. No download inside the Draft container.

**Why this project is ready for container deployment**

- **Single data root** (`DRAFT_HOME`): All runtime data (sources, vault, pulled docs, vector store at `.vector_store/`) lives under one directory, which you mount as a volume. No hardcoded host paths. The RAG index persists in containers because it is stored under `DRAFT_HOME`.
- **Env-driven config**: Embed, encoder, and LLM are configured via environment variables (and optional mounted `.env`). Same image works for local Ollama, in-cluster Ollama, or cloud LLM by changing env (ConfigMap/Secret).
- **No restart for config changes**: Mounting `.env` (Docker) or updating ConfigMap/Secret (Kubernetes) and re-reading on each request means you can change models and endpoints without restarting the container or pod.
- **Unified LLM endpoint**: One URL (`DRAFT_LLM_ENDPOINT`) plus optional API key supports both Ollama-style and OpenAI-compatible backends, so Kubernetes can point Draft at any in-cluster or public LLM by updating the endpoint.

The sections below give concrete steps for **Docker** and **Kubernetes**, with example manifests in the **`deployment/`** directory.

---

## Disk space

### Estimated usage

| Volume | Typical | Heavy | Components |
|-------|---------|-------|------------|
| **DRAFT_HOME** | 50–200 MB | up to ~500 MB | sources.yaml, `.doc_sources/`, `vault/`, `.vector_store/`, `.clones/` |
| **HF cache** (under DRAFT_HOME) | 250 MB (quick) / 750 MB (deep) | ~1 GB (both profiles) | Embed models (~90 MB quick, ~550 MB deep), cross-encoder (~90 MB). Stored at `DRAFT_HOME/.cache/huggingface`; Hugging Face checks cache before downloading. |

### Allocation (2× estimate)

Ensure **2×** the estimated usage for headroom:

| Volume | Estimate | Allocated (2×) |
|--------|----------|----------------|
| **DRAFT_HOME** (data + HF cache) | 1.5 GB | **4 Gi** |

- **Docker:** Mount `~/.draft` (or your data dir). HF cache lives at `DRAFT_HOME/.cache/huggingface`; no separate volume. Ensure the host has at least **4 GB free** before running.
- **Kubernetes:** One PVC (`draft-data-pvc`) at **4 Gi**; HF cache is under the same mount. See `pvc.yaml`.

---

## Docker deployment guide

### Build the image

From the repo root:

```bash
docker build -t draft-ui .
```

### Run with your data and config

**Minimal (use your existing `~/.draft` so the container sees sources and vault):**

```bash
docker run -p 8058:8058 -v ~/.draft:/root/.draft draft-ui
```

**With LLM config and host Ollama** (mount `.env` and set `OLLAMA_HOST` so the container can reach Ollama on the host):

```bash
docker run -p 8058:8058 \
  -v ~/.draft:/root/.draft \
  -v /path/to/draft/repo/.env:/app/.env:ro \
  -e OLLAMA_HOST=http://host.docker.internal:11434 \
  draft-ui
```

Replace `/path/to/draft/repo` with your Draft repo path. Open http://localhost:8058.

**Using env files (recommended):**

When using **local Ollama**, create `.env.docker` in the repo with `OLLAMA_HOST=http://host.docker.internal:11434` (or run setup.sh option 6 once). Example:

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

- Detects local vs cloud LLM and creates `.env.docker` when using Ollama.
- Stops any running `draft-ui` container and starts a new one with mounts for **`.env`** and **DRAFT_HOME** (HF cache at `DRAFT_HOME/.cache/huggingface`; no separate volume).

No restart is needed when you change embed, encoder, or LLM in `.env`—the app re-reads it on each reindex (and for LLM, on each Ask). Rebuild the RAG index after changing the embed model for it to take effect.

### Configuration summary

| Variable | Purpose |
|----------|---------|
| **DRAFT_HOME** | Data root; set to the volume mount path in the container (e.g. `/.draft`). |
| **DRAFT_LLM_ENDPOINT** | Unified LLM base URL (Ollama or OpenAI-compatible). When set, overrides provider-based config. |
| **DRAFT_LLM_API_KEY** | Optional; set for OpenAI-compatible endpoint. Omit for Ollama. |
| **DRAFT_LLM_MODEL** | Model name for unified endpoint. |
| **OLLAMA_HOST** | Ollama base URL when **DRAFT_LLM_ENDPOINT** is not set (e.g. `http://host.docker.internal:11434`). |
| **OLLAMA_MODEL** | Model name for Ollama (e.g. `qwen3:8b`). |
| **DRAFT_EMBED_MODEL**, **DRAFT_CROSS_ENCODER_MODEL** | Embed and encoder model names; re-read on each reindex. Rebuild the index after changing embed model for Ask to use it. |
| **DRAFT_EMBED_PROVIDER** | Set to `ollama` when using an Ollama embed model. |

**Mounts**

- **DRAFT_HOME** — Mount your data dir (e.g. `~/.draft`) so the app can read/write `sources.yaml`, `.doc_sources/`, `vault/`, `.vector_store/`, and `DRAFT_HOME/.cache/huggingface` (HF models). Ensure ~4 GB free on the host.
- **`.env`** — Mount the repo `.env` at `/app/.env:ro` so config changes (including embed/encoder/LLM) take effect without restart.

### Resource and security notes

- **LLM**: When using Ollama, the LLM runs on the host (or wherever the endpoint points); the container only does HTTP. When using cloud or an in-cluster gateway, the container only forwards requests.
- **Embed (Ollama)**: Same as LLM—HTTP to the endpoint. **Embed (Hugging Face)** and **rerank**: Run inside the container; models are cached under `DRAFT_HOME/.cache/huggingface` (checked before download).
- **Secrets**: Keep API keys in `.env` or use Docker secrets; do not bake them into the image. Use read-only mount for `.env` when possible.

---

## Kubernetes deployment guide

Draft fits standard Kubernetes patterns: one **Deployment**, one **Service**, config via **ConfigMap** and **Secret**, and persistent storage via **PersistentVolumeClaim**. Use the **unified LLM endpoint** (`DRAFT_LLM_ENDPOINT`) so that changing the endpoint URL (e.g. in a ConfigMap) points the app at another in-cluster deployment or a public LLM without image changes or pod restart.

### Prerequisites

- A **PersistentVolumeClaim** for Draft data (sources, vault, .doc_sources, .vector_store, .cache/huggingface). Default size: **4 Gi** (see [Disk space](#disk-space)).
- **ConfigMap** and **Secret** with the same variables you would put in `.env` (see Docker section). Prefer **DRAFT_LLM_ENDPOINT** (and **DRAFT_LLM_API_KEY** + **DRAFT_LLM_MODEL** for OpenAI-compatible backends).

### Example manifests

Example manifests are in the **`deployment/`** directory at the repo root:

| File | Description |
|------|-------------|
| `deployment/pvc.yaml` | PersistentVolumeClaim for Draft data (4 Gi; includes HF cache under DRAFT_HOME). |
| `deployment/configmap.yaml` | Example ConfigMap (DRAFT_HOME, DRAFT_LLM_ENDPOINT, model names, etc.). |
| `deployment/secret.yaml` | Example Secret for DRAFT_LLM_API_KEY and other secrets (optional). |
| `deployment/rbac.yaml` | ServiceAccount, Role, and RoleBinding for the Draft pod. |
| `deployment/deployment.yaml` | Draft UI Deployment with volume mounts and env from ConfigMap/Secret. |
| `deployment/service.yaml` | Service (ClusterIP) exposing the Draft UI on port 8058. |

Adjust namespace, image name, and PVC names to match your cluster. **Apply order:** PVCs → ConfigMap → Secret → RBAC → Deployment → Service. Push the `draft-ui` image to a registry your cluster can pull from, or use a local image and set `imagePullPolicy: Never` for testing.

### Unified LLM endpoint in Kubernetes

Set **DRAFT_LLM_ENDPOINT** in the Draft pod to the URL of your LLM service:

- **Ollama in cluster:** `DRAFT_LLM_ENDPOINT=http://ollama.<namespace>.svc.cluster.local:11434`, plus **OLLAMA_MODEL**.
- **OpenAI-compatible in cluster or public:** `DRAFT_LLM_ENDPOINT`, **DRAFT_LLM_API_KEY** (from Secret), **DRAFT_LLM_MODEL**.

Updating the endpoint (and key/model if needed) in ConfigMap or Secret is enough; the next Ask uses the new target. No pod restart required.

### Differences from Docker

| Docker | Kubernetes |
|--------|------------|
| `-v ~/.draft:/root/.draft` | Mount a **PVC** at e.g. `/data/draft` and set **DRAFT_HOME=/data/draft**. |
| `--env-file .env` | Inject env from **ConfigMap** and **Secret** via `envFrom` or `env`. |
| HF cache | Under `DRAFT_HOME/.cache/huggingface`; no separate volume. |

### Resource limits

If embed and rerank run in the Draft pod (Hugging Face path), set CPU/memory requests and limits on the Deployment. If the LLM is external (Ollama or gateway), the Draft pod can be relatively small.

---

## Security

- **Secrets:** Keep API keys in Secrets (Kubernetes) or `.env` (Docker); never bake them into the image.
- **Mounts:** Mount only the data and cache paths you need; avoid mounting the whole host or cluster filesystem.
- **Network:** Restrict access to the LLM endpoint and to Hugging Face (if you allow downloads) as required by your policy.
- **Image:** Build from the repo Dockerfile; keep the image updated for security fixes.
