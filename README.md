# Draft

Draft is a personal documentation hub. It pulls document files from your other repos and GitHub projects into one browsable place. You get a unified view of scattered docs — engineering notes, design specs, drafts — with full-text search and an AI assistant that answers questions from your content.

No cloud sync. Your docs stay local. Draft works with or without an LLM — Ollama for fully offline use, or Claude, OpenAI, and Gemini.

Draft is also an MCP server. [TODO] 

## Get started (quickest way)

```bash
./setup.sh
```

See [Using setup.sh](#using-setupsh) below for what the script does and how to use it.

## Start the UI

**Option A — daemon (recommended):** starts the server in the background and opens the app in your browser.

```bash
./draft.sh              # start on default port 8058
./draft.sh -p 8059      # start on port 8059
./draft.sh -s           # stop (default port 8058)
./draft.sh -s -p 8059   # stop server on port 8059
./draft.sh -r           # restart (stop then start on 8058)
./draft.sh -r -p 8059   # restart on port 8059
```

If the port is already in use, `draft.sh` will ask whether to restart. Logs go to `~/.draft/.draft-ui.log` (or `$DRAFT_HOME/.draft-ui.log`).

**Option B — foreground:** run the server in the terminal (stops when you Ctrl+C).

```bash
source .venv/bin/activate
python scripts/serve.py   # UI at http://localhost:8058
python scripts/serve.py -p 8059   # custom port
```

## Run Draft as a local Docker container

Build and run with your existing config and sources (mount **`~/.draft`** so the container sees **sources.yaml**, **.doc_sources**, and **vault**):

```bash
docker build -t draft-ui .
docker run -p 8058:8058 -v ~/.draft:/root/.draft draft-ui
# Open http://localhost:8058
```

Without the `-v ~/.draft:/root/.draft` mount, the container uses an empty data dir and will not see your **sources.yaml** or pulled docs. To also use your LLM config (e.g. Ollama or API keys), mount your repo’s **.env**. If Ollama runs on your **host** (not in Docker), set **`OLLAMA_HOST`** so the container can reach it (Docker Desktop provides `host.docker.internal`):

```bash
docker run -p 8058:8058 \
  -v ~/.draft:/root/.draft \
  -v /path/to/draft/repo/.env:/app/.env:ro \
  -e OLLAMA_HOST=http://host.docker.internal:11434 \
  draft-ui
```

Replace `/path/to/draft/repo` with your Draft repo path (e.g. the directory that contains `draft.sh`). Without `OLLAMA_HOST`, the app uses `localhost:11434` (the container’s own loopback), so Ollama on the host won’t be reachable.

**Easiest:** run **`./setup.sh`** and choose **6) Run Draft in a Docker container** — it detects local vs cloud LLM, creates `.env.docker` when using Ollama, stops any running container, then starts a new one. Full details: [docs/docker-guide.md](docs/docker-guide.md).

## Where documents are stored (`~/.draft`)

Document data and config live under **`~/.draft/`** (or **`DRAFT_HOME`** if set): **`sources.yaml`** (source list), **`.doc_sources/`** (one subdir per pulled repo), and **`vault/`** (curated docs). The repo holds only code. Set **`DRAFT_HOME`** to use a different data root (default **`~/.draft`**).


## sources.yaml (your config)

**`sources.yaml`** is your personal list of doc sources. It lives at **`~/.draft/sources.yaml`** (or **`$DRAFT_HOME/sources.yaml`**).

- **First time:** Run **`./setup.sh`** or start the app; they create **`~/.draft/sources.yaml`** from the repo’s **`sources.example.yaml`** if missing.
- Each entry is a name and a `source`:
  - **Local path** — e.g. `../my_notes` or `/path/to/repo`.
  - **GitHub URL** — e.g. `https://github.com/owner/repo`. Pull fetches `.md` files via the GitHub API (no clone).

## Adding document sources

**Quickest way:** run **`./setup.sh`**.

You can also add a source from the UI (**Add source** in the sidebar) or from the CLI:
```bash
python scripts/pull.py -a ../OtherRepo
python scripts/pull.py -a https://github.com/owner/repo
```


## Ask (AI) over your docs

The **Ask (AI)** panel (top of the content area) answers questions using only your indexed docs (RAG). To use it you need a local LLM (Ollama) or an API key from a cloud provider. **`./setup.sh`** lets you choose the model and enter the API key.

No LLM is needed for the rest of Draft — tree, search, pull, add source. See **`docs/local-oracle-design.md`** for details.

## Vault

The **vault** lives at **`~/.draft/vault/`** (or **`$DRAFT_HOME/vault/`**). It is separate from **`.doc_sources/`** so it can later be pointed at encrypted S3, iCloud, etc. File encryption is TODO.

## Privacy

Draft is built so you can run **everything locally** and keep your docs and queries off the network when you want.

- **Hugging Face offline:** Draft sets **`HF_HUB_OFFLINE=1`** in **`.env`** (and uses it by default in code). Hugging Face models (embeddings, cross-encoder) then use only already-downloaded or local assets — no outbound calls to Hugging Face Hub. Setup and the app ensure this is set so RAG stays local.
- **Local LLM:** When resources allow, use **Ollama** with a local model (e.g. Qwen3 embed + reranker). **`./setup.sh`** can configure an all-local stack (embed + rerank + chat via Ollama). No doc content or queries are sent to the internet.
- **Optional cloud:** You can still choose a cloud LLM (Claude, Gemini, OpenAI) in setup; only then are prompts and answers sent to the provider you configured.

For maximum privacy, use **Ollama** and keep **`HF_HUB_OFFLINE=1`** in **`.env`** so indexing and Ask (AI) run fully on your machine.

## Using setup.sh

**`./setup.sh`** is the main one-time (or re-run) setup script. It:

1. **Creates the environment** — ensures `.venv` exists and installs dependencies from `requirements.txt`. Uses Python 3.11 or 3.12 when available (ChromaDB/sentence-transformers need it for Ask (AI)). Use **`./setup.sh --recreate`** to rebuild the venv (e.g. after switching Python version).

2. **Ensures `~/.draft/sources.yaml`** — copies from `sources.example.yaml` if missing. This file is your list of document sources (local paths or GitHub URLs).

3. **Walks you through adding sources** — you can add a local path or a GitHub repo URL. The script runs `pull.py -a` under the hood.

4. **Configures the LLM for Ask (AI)** — if Ollama is installed, it can suggest the Qwen3 model set (embed + reranker) and offer presets: **G** (Gold: 8b embed + 0.6B reranker), **L** (8B+8B), **S** (0.6B+0.6B). Otherwise you can choose a cloud provider (Claude, Gemini, OpenAI) and enter an API key. Choices are written to **`.env`**. If you run Draft in Docker, restart the container (option 6) to pick up a new LLM.

5. **Builds the RAG index** — after setup, it runs the AI index build once so Ask (AI) works immediately.

6. **Run in Docker** — runs the `draft-ui` container with your data and LLM config; detects local vs cloud LLM, stops any existing container, then starts a new one. See [docs/docker-guide.md](docs/docker-guide.md).

You can re-run **`./setup.sh`** anytime to add more sources or change the LLM. To tweak config by hand, edit **`.env`** (embed model, cross-encoder, LLM provider, API keys). See **`docs/RAG_operations.md`** for CLI commands (index build, ask, pipeline test).

---

## References — docs for engineering and design

The **`docs/`** folder contains design and operations docs you can use as reference:

| Doc | Purpose |
|-----|--------|
| [Storage & metadata design](docs/storage-and-metadata-design.md) | Access layer, vault, `sources.yaml`, manifest, reconnection |
| [Core implementations](docs/core-implementations.md) | Source type taxonomy, storage layout under `DRAFT_HOME`, manifest |
| [Design principles](docs/design-principles.md) | Data sources and operations (github, local_dir, local_git, vault, etc.) |
| [Intelligence layer design](docs/intelligence-layer-design.md) | Embeddings, Chroma, LLM integration, RAG pipeline |
| [RAG design principles](docs/RAG-design-principles.md) | RAG goals, architecture, chunking, citations, local vs cloud |
| [RAG operations](docs/RAG_operations.md) | Default models, Qwen3 pairs (G/L/S), CLI: index build, ask, pipeline test |
| [Docker guide](docs/docker-guide.md) | Run in Docker (option 6), OLLAMA_HOST, mounts, K8s plan |
| [Local oracle design](docs/local-oracle-design.md) | When and how a local LLM is used for Ask (AI) |
| [Testing suites](docs/testing-suites.md) | Test layers, pytest, pipeline test (`test_pipeline.py`), curl integration |

<img width="2037" height="1147" alt="Screenshot 2026-02-27 at 9 36 12 AM" src="https://github.com/user-attachments/assets/28a26c52-cc49-4421-8fd1-20ef0638daf0" />

<img width="1925" height="1043" alt="Screenshot 2026-02-27 at 9 39 10 AM" src="https://github.com/user-attachments/assets/4b0a7aad-e733-4c0d-a40c-68e1d5a23b1c" />

<img width="1707" height="1027" alt="Screenshot 2026-02-26 at 10 59 40 PM" src="https://github.com/user-attachments/assets/82c5d7b9-17a9-453a-8c53-412162d117bf" />



