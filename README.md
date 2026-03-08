# Draft

Draft is a personal documentation hub. It pulls document files from your other repos and GitHub projects into one browsable place. You get a unified view of scattered docs — engineering notes, design specs, drafts — with full-text search and a local RAG + LLM that answers questions from your content.

Draft works with or without an LLM — Ollama for fully offline use. RAG embed/encoder/reranker models are downloaded from huggingface and run 100% locally.

Draft is also an MCP server that serves contents to internal AI Agents.

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

Build and run with your existing config and sources (mount `**~/.draft**` so the container sees **sources.yaml**, **.doc_sources**, and **vault**):

```bash
docker build -t draft-ui .
docker run -p 8058:8058 -v ~/.draft:/root/.draft draft-ui
# Open http://localhost:8058
```

Without the `-v ~/.draft:/root/.draft` mount, the container uses an empty data dir and will not see your **sources.yaml** or pulled docs. To also use your LLM config (e.g. Ollama or API keys), mount your repo’s **.env**. If Ollama runs on your **host** (not in Docker), set `**OLLAMA_HOST`** so the container can reach it (Docker Desktop provides `host.docker.internal`):

```bash
docker run -p 8058:8058 \
  -v ~/.draft:/root/.draft \
  -v /path/to/draft/repo/.env:/app/.env:ro \
  -e OLLAMA_HOST=http://host.docker.internal:11434 \
  draft-ui
```

Replace `/path/to/draft/repo` with your Draft repo path (e.g. the directory that contains `draft.sh`). Without `OLLAMA_HOST`, the app uses `localhost:11434` (the container’s own loopback), so Ollama on the host won’t be reachable.

**Easiest:** run `**./setup.sh`** and choose **8) Run Draft in a Docker container** — it detects local vs cloud LLM, creates `.env.docker` when using Ollama, stops any running container, then starts a new one. Full details: [docs/container_orchestration_guide.md](docs/container_orchestration_guide.md).

## Where documents are stored (`~/.draft`)

Document data and config live under `**~/.draft/`** (or `**DRAFT_HOME`** if set): `**sources.yaml**` (source list), `**.doc_sources/**` (one subdir per pulled repo), and `**vault/**` (curated docs). The repo holds only code. Set `**DRAFT_HOME**` to use a different data root (default `**~/.draft**`).

## sources.yaml (your config)

`**sources.yaml**` is your personal list of doc sources. It lives at `**~/.draft/sources.yaml**` (or `**$DRAFT_HOME/sources.yaml**`).

- **First time:** Run `**./setup.sh`** or start the app; they create `**~/.draft/sources.yaml`** from the repo’s `**sources.example.yaml**` if missing.
- Each entry is a name and a `source`:
  - **Local path** — e.g. `../my_notes` or `/path/to/repo`.
  - **GitHub URL** — e.g. `https://github.com/owner/repo`. Pull fetches `.md` files via the GitHub API (no clone).

## Adding document sources

**Quickest way:** run `**./setup.sh`**.

You can also add a source from the UI (**Add source** in the sidebar) or from the CLI:

```bash
python scripts/pull.py -a ../OtherRepo
python scripts/pull.py -a https://github.com/owner/repo
```

## Ask (AI) over your docs

The **Ask (AI)** panel (top of the content area) answers questions using only your indexed docs (RAG). To use it you need a local LLM (Ollama) or an API key from a cloud provider. `**./setup.sh`** lets you choose the model and enter the API key.

No LLM is needed for the rest of Draft — tree, search, pull, add source. See [Engineering](docs/engineering.md) for details.

## Observability

Draft uses **OpenTelemetry (OTel)** for metrics and traces when the optional SDK is installed. RAG (retrieve → rerank → generate) and MCP tool calls are instrumented; entry points call `configure_otel()` at startup by default and `shutdown_otel()` on exit so the final metric batch is exported.

- **Metrics:** RAG request counts, retrieval/rerank/LLM latency (GenAI semconv where applicable), MCP tool calls. Default output: `**~/.draft/otel_metrics.log`** (or `$DRAFT_HOME/otel_metrics.log`). Set `**DRAFT_OTEL_METRICS_LOG=stdout**` to print to the terminal, or `**OTEL_EXPORTER_OTLP_ENDPOINT**` to send to an OTLP backend (Grafana, Honeycomb, Jaeger, etc.).
- **Traces:** Spans for `rag.ask`, `rag.retrieval`, `rag.rerank`, `rag.generation`, and `mcp.tool`; exported to console or OTLP.
- **Optional:** Install with `pip install -r requirements-otel.txt`. Without the SDK, all instrumentation is no-op and Draft runs unchanged.

See [Observability design](docs/observability_design.md) for the full spec and [OTel walkthrough](docs/OTel_walkthrough.md) for a data-flow walkthrough and live demo.

## Vault

The **vault** lives at `**~/.draft/vault/`** (or `**$DRAFT_HOME/vault/`**). It is separate from `**.doc_sources/**` so it can later be pointed at encrypted S3, iCloud, etc. File encryption is TODO.

## Privacy

Draft is built so you can run **everything locally** and keep your docs and queries off the network when you want.

- **Hugging Face offline:** Draft sets `**HF_HUB_OFFLINE=1`** in `**.env`** (and uses it by default in code). Hugging Face models (embeddings, cross-encoder) then use only already-downloaded or local assets — no outbound calls to Hugging Face Hub. Setup and the app ensure this is set so RAG stays local.
- **Local LLM:** When resources allow, use **Ollama** with a local model. `**./setup.sh`** can configure an all-local stack (embed + cross-encoder rerank + chat via Ollama). No doc content or queries are sent to the internet.
- **Optional cloud:** You can still choose a cloud LLM (Claude, Gemini, OpenAI) in setup; only then are prompts and answers sent to the provider you configured.

For maximum privacy, use **Ollama** and keep `**HF_HUB_OFFLINE=1`** in `**.env`** so indexing and Ask (AI) run fully on your machine.

## Using setup.sh

`**./setup.sh**` is the main one-time (or re-run) setup script. It:

1. **Creates the environment** — ensures `.venv` exists and installs dependencies from `requirements.txt`. Uses Python 3.11 or 3.12 when available (ChromaDB/sentence-transformers need it for Ask (AI)). Use `**./setup.sh --recreate`** to rebuild the venv (e.g. after switching Python version or upgrading PyTorch for Intel Mac / PC compatibility).
2. **Ensures `~/.draft/sources.yaml`** — copies from `sources.example.yaml` if missing. This file is your list of document sources (local paths or GitHub URLs).
3. **Walks you through adding sources** (option 1) — you can add a local path or a GitHub repo URL. The script runs `pull.py -a` under the hood.
4. **Setup embedding model** (option 2) — shows current model, suggests three Hugging Face models (`all-MiniLM-L6-v2`, `BAAI/bge-small-en-v1.5`, `mixedbread-ai/mxbai-embed-large-v1`), lists local Ollama embedding models, and allows typing a custom Hugging Face model. When the embed model changes, reminds you to rebuild the RAG index (option 5).
5. **Setup encoder model** (option 3) — configures the cross-encoder for reranking (default: `cross-encoder/ms-marco-MiniLM-L-6-v2`). You can accept the default or type a different model.
6. **Configure LLM for Ask (AI)** (option 4) — lists local Ollama models (from `ollama list`), or cloud options (Gemini 2.5 Flash, Claude/Opus, OpenAI), or lets you enter a custom model. Choices are written to `**.env`**. If you run Draft in Docker, restart the container (option 8) to pick up a new LLM.
7. **Build RAG index** (option 5) — after setup, runs the AI index build (quick or deep profile) so Ask (AI) works immediately.
8. **Test RAG + LLM** (option 6) — runs a sample Ask with the configured models to verify the pipeline.
9. **Start UI** (option 7, default) — starts the Draft UI on the local host.
10. **Run in Docker** (option 8) — runs the `draft-ui` container with your data and LLM config; detects local vs cloud LLM, stops any existing container, then starts a new one. See [docs/container_orchestration_guide.md](docs/container_orchestration_guide.md).

You can re-run `**./setup.sh`** anytime to add more sources or change the LLM. To tweak config by hand, edit `**.env`** (embed model, cross-encoder, LLM provider, API keys). See `**docs/RAG_operations.md**` for how to change models and run RAG tests (setup option 6, ask.py, pipeline test, CI/CD).

---

## References — docs for engineering and design

The `**docs/**` folder contains design and operations docs you can use as reference:


| Doc                                                              | Purpose                                                                                                                       |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| [Engineering](docs/engineering.md)                               | reference: design principles, storage, metadata, vault, intelligence layer, local oracle, implementation order (basic → core) |
| [RAG design](docs/RAG_design.md)                                 | RAG goals, architecture, chunking, citations, two-stage retrieval (bi-encoder + cross-encoder), model performance & privacy   |
| [RAG operations](docs/RAG_operations.md)                         | How to change embed/encoder models; how to run tests (setup option 6, ask.py, test_pipeline, CI/CD)                           |
| [Container orchestration](docs/container_orchestration_guide.md) | Docker and Kubernetes deployment, unified LLM endpoint, example manifests in `deployment/`                                    |
| [MCP design](docs/MCP_design.md)                                 | MCP server design: tools, resources, prompts for AI assistants (Claude Desktop, Claude Code)                                  |
| [Observability design](docs/observability_design.md)             | OTel metrics and traces (RAG + MCP), GenAI semconv, console vs OTLP, `lib/otel.py` and `lib/metrics.py`, SLIs                 |
| [OTel walkthrough](docs/OTel_walkthrough.md)                     | Data-flow walkthrough (resource → console), live demo, metrics log file and env vars                                          |
| [Testing suites](docs/testing_suites.md)                         | Test layers, pytest, pipeline test (`test_pipeline.py`), OTel tests, curl integration                                         |


RAG test:

UI: