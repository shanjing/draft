# Docker guide for Draft

How to run Draft in a container, how configuration and resources work, security considerations, and a Kubernetes deployment plan.

---

## 1. How to start in Docker

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

Replace `/path/to/draft/repo` with your Draft repo path (e.g. the directory that contains `draft.sh`). Open http://localhost:8058.

**Using env files (recommended for repeat runs):**

When using **local Ollama**, create `.env.docker` in the repo with `OLLAMA_HOST=http://host.docker.internal:11434` (or run setup.sh option 6 once to have it created). When using only cloud LLM, `--env-file .env` is enough. Example with host Ollama:

```bash
docker run -p 8058:8058 \
  -v ~/.draft:/root/.draft \
  --env-file /path/to/draft/repo/.env \
  --env-file /path/to/draft/repo/.env.docker \
  -e DRAFT_HOME=/root/.draft \
  draft-ui
```

If you mount `~/.draft` at `/root/.draft`, the app’s default `DRAFT_HOME` is already `/root/.draft`, so you can omit `-e DRAFT_HOME`. If you mount elsewhere (e.g. `/.draft`), set `-e DRAFT_HOME=/.draft`.

### Via setup.sh

Run `./setup.sh` and choose **6) Run Draft in a Docker container**. The script aligns Docker with your local LLM settings:

- **Local LLM (Ollama) detected** — If `.env` has `DRAFT_LLM_PROVIDER=ollama` or `OLLAMA_MODEL` set, setup creates or updates `.env.docker` with `OLLAMA_HOST=http://host.docker.internal:11434`, then runs the container with `--env-file .env` and `--env-file .env.docker` so the container can reach Ollama on the host.
- **Cloud LLM configured** — If `.env` has a cloud provider (claude/gemini/openai) and the corresponding API key set, setup runs the container with `--env-file .env` only (no `.env.docker`; no `OLLAMA_HOST`).
- **No LLM configured** — Setup informs you that Ask (AI) / semantic search will not work, suggests configuring LLM in step 3, and prompts **“Run anyway (browse docs only)? (y/N)”**. If you choose **y**, it runs the container with `.env` only (browse docs, tree, search). If **N**, it exits so you can configure LLM first.

Then:

- Ensure `.env` exists (copy from `.env.example` if missing).
- Build the `draft-ui` image if it doesn’t exist (prompts to build).
- **Restart logic:** If a container from image `draft-ui` is already running, setup stops it, then starts a new one so the new container gets the current `.env` (e.g. after you changed the LLM in option 3).
- Run the container with a mount of `$DRAFT_HOME` at `/.draft` and `DRAFT_HOME=/.draft` in the container.

The container runs in the foreground; Ctrl+C stops it. **Local runs** (e.g. `./draft.sh`, `python scripts/serve.py`) never load `.env.docker`, so they keep using the default `localhost:11434` for Ollama and are unchanged.

**After changing the LLM (option 3):** Setup prints a reminder: *If you run Draft in Docker, restart the container (option 6) to pick up the new LLM.* The container reads `.env` only at start; run option 6 again to restart and load the new model.

---

## 2. Configuration

### Environment variables

| Variable | Purpose | Docker note |
|----------|---------|-------------|
| **DRAFT_HOME** | Data root: `sources.yaml`, `.doc_sources/`, `vault/`. | Set to the path where the volume is mounted in the container (e.g. `/.draft` or `/root/.draft`). |
| **OLLAMA_HOST** | Base URL for Ollama API (embed, rerank, generate). | On Docker Desktop (Mac/Windows), use `http://host.docker.internal:11434` to reach Ollama on the host. Omit or use another URL when Ollama runs inside the cluster or elsewhere. |
| **DRAFT_LLM_PROVIDER** | `ollama` \| `claude` \| `gemini` \| `openai`. | From `.env`. |
| **OLLAMA_MODEL** | Model name for Ollama (e.g. `qwen3:8b`). | From `.env`. |
| **DRAFT_EMBED_MODEL**, **DRAFT_CROSS_ENCODER_MODEL** | Embedding and reranker models. | From `.env`. |
| **DRAFT_EMBED_PROVIDER**, **DRAFT_RERANK_PROVIDER** | Set to `ollama` for Ollama embed/rerank (G/L/S). | From `.env`. |
| **HF_HUB_OFFLINE** | Set to `1` so Hugging Face uses only local/cached assets. | In `.env` or set in image/code. |
| API keys | **ANTHROPIC_API_KEY**, **GEMINI_API_KEY**, **OPENAI_API_KEY**, etc. | From `.env`; use Secrets in K8s. |

### Files and mounts

- **`.env`** — Main config (LLM provider, model, embed/rerank, API keys). Same file works for local and Docker; mount it or pass via `--env-file`. Local runs never load `.env.docker`, so they are unchanged. When running in Docker with **local Ollama**, use a second file **`.env.docker`** (e.g. `OLLAMA_HOST=http://host.docker.internal:11434`) so the container can reach the host’s Ollama; setup.sh creates this only when it detects local LLM.
- **`DRAFT_HOME` (e.g. `~/.draft`)** — Must be mounted into the container so the app can read/write:
  - `sources.yaml`
  - `.doc_sources/` (pulled docs)
  - `.clones/` (GitHub clones, if used)
  - `vault/`
  Without this mount, the container has an empty data dir and will not see your sources or vault.

**Quoted env values:** Values from `--env-file` (e.g. `DRAFT_CROSS_ENCODER_MODEL='cross-encoder/ms-marco-MiniLM-L-6-v2'`) can include quotes. The app strips surrounding quotes from model and provider env vars so Hugging Face repo ids remain valid.

### Local path sources in sources.yaml

If `sources.yaml` lists a **local path** (e.g. `/Users/you/other-repo`), that path is resolved **inside** the container. The container only sees its own filesystem and the mounted volume. So either:

- Use **GitHub** sources (pull writes into `DRAFT_HOME/.doc_sources` and `.clones`, which are on the mount), or
- Add an extra volume mount for each such path, e.g. `-v /Users/you/other-repo:/Users/you/other-repo:ro`.

---

## 3. Resource consumption

### Where work runs

- **LLM (chat/generate)**  
  - Flow: UI → `POST /api/ask` → `ask_stream()` → `_stream_ollama()` → HTTP to `OLLAMA_BASE/api/generate`.  
  - With `OLLAMA_HOST=http://host.docker.internal:11434`, the request goes to **Ollama on the host**.  
  - **CPU/GPU/memory:** On the **host** (Ollama process). The container only does HTTP and streaming.

- **Embed and rerank (Ollama)**  
  - When `DRAFT_EMBED_PROVIDER=ollama` and `DRAFT_RERANK_PROVIDER=ollama` (e.g. G/L/S):  
  - Embed: HTTP to `OLLAMA_BASE/api/embed`.  
  - Rerank: HTTP to `OLLAMA_BASE/api/rerank`.  
  - With `OLLAMA_HOST` pointing at the host, **embed and rerank run on the host** (Ollama). The container does not run these models.

- **Embed and rerank (sentence-transformers / Hugging Face)**  
  - When not using Ollama for embed/rerank, the app loads **SentenceTransformer** and **CrossEncoder** **inside the container**.  
  - **CPU/memory:** Used by the **container** (Docker uses the host’s CPU/RAM that it is allowed to use).  
  - **GPU:** Only if the container is run with GPU access (e.g. `--gpus all` on Docker).

### Summary

| Component | With Ollama (G/L/S) | With Hugging Face (default) |
|-----------|----------------------|-----------------------------|
| LLM       | Host (Ollama)        | Host (Ollama) or cloud API  |
| Embed     | Host (Ollama)        | Container                   |
| Rerank    | Host (Ollama)        | Container                   |

For maximum use of host GPU and a single Ollama instance, use the Ollama path for LLM, embed, and rerank and set `OLLAMA_HOST` to the host (or to an Ollama service in K8s).

---

## 4. Security

- **Secrets:** Keep API keys and secrets in `.env` (or in K8s Secrets). Do not bake them into the image. Use `--env-file` or mount a read-only `.env` so the container gets env without storing secrets in the image.
- **Mounts:** Only mount the minimum needed (e.g. `DRAFT_HOME` and optionally `.env`). Avoid mounting the whole host filesystem.
- **Network:** The container only needs to reach Ollama (or your LLM/embed/rerank endpoints) and, if you use GitHub sources or cloud LLMs, the internet. Restrict as needed (e.g. internal network only for Ollama).
- **HF_HUB_OFFLINE:** With `HF_HUB_OFFLINE=1`, Hugging Face does not contact the internet; only local/cached assets are used. Reduces exposure and keeps behavior predictable.
- **Image:** Build from the repo Dockerfile; avoid untrusted base images or extra layers. Keep the image updated for security fixes.
- **User:** The Dockerfile does not set a non-root user; the process runs as root inside the container. For stricter environments, consider adding a USER and adjusting permissions in the image.

---

## 5. Kubernetes deployment plan

The app is written to use environment variables and a single data root (`DRAFT_HOME`), so it fits standard K8s patterns. The following adapts the “Docker on a laptop” setup to a cluster.

### Differences from local Docker

| Local Docker (e.g. Docker Desktop) | Kubernetes |
|-------------------------------------|------------|
| `OLLAMA_HOST=http://host.docker.internal:11434` | `host.docker.internal` does not exist. Use an Ollama **Service** URL (e.g. `http://ollama:11434`) or an external Ollama URL. |
| `-v ~/.draft:/root/.draft` (host dir) | No host `~/.draft`. Use a **PersistentVolumeClaim (PVC)** (or similar) and mount it at a path (e.g. `/data/draft`). Set `DRAFT_HOME` to that path. |
| `--env-file .env` / `.env.docker` | Inject env from **ConfigMap** and **Secret** (e.g. `env` / `envFrom` in the pod spec). |

### Steps

1. **Ollama in the cluster (or external)**  
   - Run Ollama as a **Deployment** and expose it with a **Service** (e.g. name `ollama`, port 11434), or use an external Ollama instance.  
   - Set **OLLAMA_HOST** in the Draft pod to that service URL (e.g. `http://ollama.<namespace>.svc.cluster.local:11434`) or the external URL. Do not use `host.docker.internal`.

2. **Storage for Draft data**  
   - Create a **PersistentVolumeClaim** for Draft data (sources, vault, .doc_sources, .clones).  
   - In the Draft Deployment, mount the PVC at a path, e.g. `/data/draft`.  
   - Set **DRAFT_HOME=/data/draft** in the pod env so the app uses that volume for all data.

3. **Config and secrets**  
   - Put non-sensitive config (e.g. `DRAFT_LLM_PROVIDER`, `OLLAMA_MODEL`, `DRAFT_EMBED_MODEL`, `OLLAMA_HOST`, `HF_HUB_OFFLINE`) in a **ConfigMap**.  
   - Put API keys and other secrets in a **Secret**.  
   - In the pod spec, use `envFrom` and/or `env` to inject ConfigMap and Secret. Same variable names as in `.env`; only the source of the env changes.

4. **Image and port**  
   - Use the same **draft-ui** image (e.g. from a registry).  
   - Container listens on **0.0.0.0:8058**. Expose it with a **Service** (ClusterIP, NodePort, or LoadBalancer) and optionally **Ingress**.

5. **Resource limits**  
   - If embed/rerank run in the Draft pod (sentence-transformers path), set **requests/limits** for CPU and memory (and GPU if you give the pod GPU access).  
   - If all heavy work is in Ollama, the Draft pod can be relatively small (mainly HTTP and orchestration).

6. **Optional: RAG index and vector store**  
   - The vector store (e.g. `.vector_store`) may live under the app root in the image or under a volume. If you want the index to persist across pod restarts, mount a volume for that path (or ensure it is under `DRAFT_HOME` if you decide to keep it there in the app).

### Example sketch (pod env and volume)

```yaml
# Conceptual only; adjust names and namespace.
env:
  - name: DRAFT_HOME
    value: "/data/draft"
  - name: OLLAMA_HOST
    value: "http://ollama:11434"
  - name: DRAFT_LLM_PROVIDER
    valueFrom:
      configMapKeyRef:
        name: draft-config
        key: DRAFT_LLM_PROVIDER
  - name: OLLAMA_MODEL
    valueFrom:
      configMapKeyRef:
        name: draft-config
        key: OLLAMA_MODEL
  # ... other keys from ConfigMap/Secret
volumeMounts:
  - name: draft-data
    mountPath: /data/draft
volumes:
  - name: draft-data
    persistentVolumeClaim:
      claimName: draft-data-pvc
```

No code changes are required; the same image works with env and volume configuration appropriate for the cluster.
