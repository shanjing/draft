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

The sections below give concrete steps for **Docker** and **Kubernetes**. Example manifests are in the **`deployment/`** directory.

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
- **Kubernetes:** Use one PVC (`draft-data-pvc`) at **4 Gi**. HF cache is under the same mount. See `pvc.yaml`.

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

Draft uses standard Kubernetes patterns: one **Deployment**, one **Service**, config from **ConfigMap** and **Secret**, and persistent storage from **PersistentVolumeClaim**. Use the **unified LLM endpoint** (`DRAFT_LLM_ENDPOINT`). Then when you change the endpoint URL (e.g. in a ConfigMap), the app points at another in-cluster deployment or a public LLM without image changes or pod restart.

### Prerequisites

- A **PersistentVolumeClaim** for Draft data (sources, vault, .doc_sources, .vector_store, .cache/huggingface). Default size: **4 Gi** (see [Disk space](#disk-space)).
- **ConfigMap** and **Secret** with the same variables you would put in `.env` (see Docker section). Prefer **DRAFT_LLM_ENDPOINT** and, for OpenAI-compatible backends, **DRAFT_LLM_API_KEY** and **DRAFT_LLM_MODEL**.

### Example manifests

Example manifests are in the **`deployment/`** directory at the repo root:

| File | Description |
|------|-------------|
| `deployment/pvc.yaml` | PersistentVolumeClaim for Draft data (4 Gi; includes HF cache under DRAFT_HOME). |
| `deployment/configmap.yaml` | Example ConfigMap (DRAFT_HOME, DRAFT_LLM_ENDPOINT, model names, etc.). |
| `deployment/secret.yaml` | Example Secret for DRAFT_LLM_API_KEY and other secrets (optional). |
| `deployment/rbac.yaml` | ServiceAccount, Role, and RoleBinding for the Draft pod. |
| `deployment/deployment.yaml` | Draft UI Deployment with volume mounts and env from ConfigMap/Secret. |
| `deployment/service.yaml` | Service (ClusterIP) that exposes the Draft UI on port 8058. |

Adjust namespace, image name, and PVC names to match your cluster. **Apply order:** PVCs → ConfigMap → Secret → RBAC → Deployment → Service. Push the `draft-ui` image to a registry your cluster can pull from, or use a local image and set `imagePullPolicy: Never` for testing.

### Unified LLM endpoint in Kubernetes

Set **DRAFT_LLM_ENDPOINT** in the Draft pod to the URL of your LLM service:

- **Ollama in cluster:** `DRAFT_LLM_ENDPOINT=http://ollama.<namespace>.svc.cluster.local:11434`, and set **OLLAMA_MODEL**.
- **OpenAI-compatible in cluster or public:** Set **DRAFT_LLM_ENDPOINT**, **DRAFT_LLM_API_KEY** (from Secret), and **DRAFT_LLM_MODEL**.

When you update the endpoint (and key/model if needed) in ConfigMap or Secret, the next Ask uses the new target. You do not need to restart the pod.

### Differences from Docker

| Docker | Kubernetes |
|--------|------------|
| `-v ~/.draft:/root/.draft` | Mount a **PVC** at e.g. `/data/draft` and set **DRAFT_HOME=/data/draft**. |
| `--env-file .env` | Inject env from **ConfigMap** and **Secret** via `envFrom` or `env`. |
| HF cache | Under `DRAFT_HOME/.cache/huggingface`; no separate volume. |

### Resource limits

If embed and rerank run in the Draft pod (Hugging Face path), set CPU and memory requests and limits on the Deployment. If the LLM is external (Ollama or gateway), the Draft pod can be smaller.

---

## Security

- **Secrets:** Keep API keys in Secrets (Kubernetes) or `.env` (Docker). Do not put them in the image.
- **Mounts:** Mount only the data and cache paths you need. Do not mount the whole host or cluster filesystem.
- **Network:** Restrict access to the LLM endpoint and to Hugging Face (if you allow downloads) as your policy requires.
- **Image:** Build from the repo Dockerfile. Keep the image updated for security fixes.
