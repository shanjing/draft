# Draft

Draft is a documentation hub that pulls document files from your repos and GitHub projects into one place. You get a unified view of scattered docs — engineering notes, design specs, runbooks — with **full-text and semantic search** and an optional **RAG + LLM** that answers questions from your content. Draft works with or without an LLM (e.g. Ollama for fully offline use).

Draft serves three main use cases: **(1)** personal knowledge base, **(2)** business or team “Confluence-style” deployment, and **(3)** a high-performance MCP server for agentic applications and SRE/ops runbooks.

---

## 1. Personal knowledge base

Use Draft as your personal doc hub: one place to browse, search, and ask questions over your notes and pulled repos.

<img width="1501" height="946" alt="Draft_UserUI" src="https://github.com/user-attachments/assets/3c053376-8925-4980-9c87-b05a018ac166" />


### Get started (quickest way)

```bash
./setup.sh
```

See [Using setup.sh](#using-setupsh) below for what the script does.

### Start the UI

**Daemon (recommended):** server in the background, app opens in your browser.

```bash
./draft.sh ui start             # start on default port 8058
./draft.sh ui start -p 9000    # start on a custom port
./draft.sh ui stop              # stop
./draft.sh ui restart           # restart (force-kills stale process)
./draft.sh status               # show state of both UI and MCP server
```

Logs: `~/.draft/.draft-ui.log` (or `$DRAFT_HOME/.draft-ui.log`).

**Foreground:** `source .venv/bin/activate` then `python scripts/serve.py` (Ctrl+C to stop).

### Where documents are stored (`~/.draft`)

Data lives under **`~/.draft/`** (or **`DRAFT_HOME`**): **sources.yaml** (source list), **.doc_sources/** (one subdir per pulled repo), and **vault/** (curated docs). Set **DRAFT_HOME** to use a different root.

### Document sources (sources.yaml)

**sources.yaml** at `~/.draft/sources.yaml` is your list of doc sources. Run **./setup.sh** or start the app to create it from **sources.example.yaml** if missing.

- **Local path** — e.g. `../my_notes`, `/path/to/repo`.
- **GitHub URL** — e.g. `https://github.com/owner/repo`. Pull fetches `.md` files via the GitHub API (no clone).

**Adding sources:** Use **./setup.sh**, or the UI (**Add source** in the sidebar), or the CLI:

```bash
python scripts/pull.py -a ../OtherRepo
python scripts/pull.py -a https://github.com/owner/repo
```

### Search Draft

- **Full-text search (FTS):** Keyword search over all indexed documents (Whoosh). Fast, no LLM or vector index required. Use the search box in the UI or the MCP tool **search_docs**.
- **Semantic search:** Vector similarity over chunked content, with optional cross-encoder rerank. Powers **Ask (AI)** and the MCP tool **retrieve_chunks**. Requires a built RAG index (`python scripts/index_for_ai.py --profile quick`). Best for conceptual queries (“How do I debug OOM?”); use FTS for exact terms and file names.

### Ask (AI) over your docs

The **Ask (AI)** panel (top of the content area) answers questions using only your indexed docs (RAG). You need a local LLM (Ollama) or a cloud API key. **./setup.sh** lets you choose the model and enter the key.

No LLM is needed for browsing, search, or pull. See [Engineering](docs/engineering.md) for more.

### Data privacy

Draft can run **fully locally** so docs and queries stay on your machine.

- **Hugging Face offline:** Draft sets **HF_HUB_OFFLINE=1** in **.env** so embed/reranker models use only already-downloaded assets.
- **Local LLM:** Use **Ollama** with a local model; **./setup.sh** can configure an all-local stack. No doc content or queries leave your machine.
- **Optional cloud:** You can choose a cloud LLM (Claude, Gemini, OpenAI) in setup; only then are prompts and answers sent to that provider.

For maximum privacy, use **Ollama** and keep **HF_HUB_OFFLINE=1** in **.env**.

---

## 2. Business / “Confluence” alternative

Use Draft as a team or company knowledge base: run it in Docker (or Kubernetes), expose full-text and semantic search, and optionally lock down sensitive content in the vault.

<img width="1503" height="942" alt="Draft_BusinessUser" src="https://github.com/user-attachments/assets/094320c2-28a3-4aef-8769-04ef4da1f6e3" />


### Run Draft in Docker

Build and run with your config and sources (mount **~/.draft** so the container sees **sources.yaml**, **.doc_sources**, and **vault**):

```bash
docker build -t draft-ui .
docker run -p 8058:8058 -v ~/.draft:/root/.draft draft-ui
```

To use your LLM config (Ollama or API keys), mount **.env**. If Ollama runs on the **host**, set **OLLAMA_HOST** (e.g. `http://host.docker.internal:11434`) so the container can reach it.

**Easiest:** run **./setup.sh** and choose **8) Run Draft in a Docker container**. Full details: [Container orchestration](docs/container_orchestration.md).

### Full-text and semantic search

- **FTS:** Keyword search over all docs; no LLM or vector index. Available in the UI and via MCP **search_docs**.
- **Semantic search:** Vector + optional rerank; used by Ask (AI) and MCP **retrieve_chunks**. Requires RAG index. Suited to conceptual and natural-language queries.

See [Search Draft](#search-draft) above and [RAG design](docs/RAG_design.md) for architecture.

### Ask from the CLI (ask.py) and RAG

From the command line you can run:

```bash
python scripts/ask.py -q "Your question here"
```

This uses the same RAG pipeline as the UI: retrieval (vector + optional rerank) then LLM synthesis. Configure the LLM in **.env** (Ollama or cloud provider). For RAG internals (chunking, embed/encoder models, indexing), see [RAG design](docs/RAG_design.md) and [RAG operations](docs/RAG_operations.md).

### Vault and encryption

The **vault** lives at **~/.draft/vault/** (or **$DRAFT_HOME/vault/**). It is separate from **.doc_sources/** so it can later be pointed at encrypted storage (e.g. S3, iCloud). **File encryption is TODO**; today the vault is a plain directory for curated docs.

---

## 3. High-performance MCP server for agentic applications

Use Draft as an **MCP server** for AI agents, SRE runbooks, and ops tooling: expose document search, semantic retrieval, and RAG to Claude Desktop, SRE agents, or any MCP client. The server runs as a **separate process** from the UI (default port **8059**) and can run in a container (Docker or Kubernetes) to host proprietary knowledge bases such as production runbooks.

**MCP client (e.g. SRE subagent) sends a query** — session + `retrieve_chunks` with a natural-language question (e.g. investigating pod resource constraints):

<img width="1692" height="635" alt="MCP_Question" src="https://github.com/user-attachments/assets/9449a439-5162-4413-a069-0ad1e2c999df" />


**Draft MCP returns ranked chunks** — runbook excerpts with repo, path, heading, text, and score (e.g. inference runbook for memory/CPU checks):

<img width="1698" height="315" alt="MCP_Answer" src="https://github.com/user-attachments/assets/6cf958d5-2aad-471f-a0fe-08417d08db21" />


### MCP server

Two transports:

- **Streamable HTTP** — for remote clients, Docker, SRE agents. Bearer token auth (**DRAFT_MCP_TOKEN** in `.env`). `POST http://localhost:8059/mcp` with session from `initialize`.
- **stdio** — for Claude Desktop and local tools. No auth.

**Local daemon (recommended):**

```bash
./draft.sh mcp start            # start HTTP daemon (port 8059, background)
./draft.sh mcp stop             # stop
./draft.sh mcp restart          # restart (force-kills stale process)
./draft.sh mcp start --stdio    # stdio transport (foreground, for Claude Desktop)
./draft.sh mcp logs             # tail the MCP log
./draft.sh status               # show state of both UI and MCP server
```

**Direct (foreground / scripting):**

```bash
python scripts/serve_mcp.py              # HTTP on 8059
python scripts/serve_mcp.py --stdio      # stdio for Claude Desktop
python scripts/serve_mcp.py -p 8060      # HTTP on custom port
```

**Tools:** `search_docs`, `retrieve_chunks`, `query_docs`, `get_document`, `list_documents`, `list_sources`. Logs: `~/.draft/draft-mcp.log`. Full runbook: [MCP operations](docs/MCP_operations.md).

### Observability

Draft uses **OpenTelemetry (OTel)** for metrics and traces (SDK in **requirements.txt**). RAG and MCP tool calls are instrumented; entry points call **configure_otel()** at startup and **shutdown_otel()** on exit so the final metric batch is exported.

- **Metrics:** RAG request counts, retrieval/rerank/LLM latency, MCP tool calls. Default: **~/.draft/otel_metrics.log** (or `$DRAFT_HOME/otel_metrics.log`). Set **DRAFT_OTEL_METRICS_LOG=stdout** or **OTEL_EXPORTER_OTLP_ENDPOINT** for OTLP (Grafana, Honeycomb, Jaeger, etc.).
- **Traces:** Spans for `rag.ask`, `rag.retrieval`, `rag.rerank`, `rag.generation`, and `mcp.tool`; exported to console or OTLP.

See [Observability design](docs/observability_design.md) and [OTel walkthrough](docs/OTel_walkthrough.md).

---

## Using setup.sh

**./setup.sh** is the main one-time (or re-run) setup script. It:

1. **Creates the environment** — `.venv`, installs from `requirements.txt`. Python 3.11 or 3.12. Use **./setup.sh --recreate** to rebuild the venv.
2. **Ensures ~/.draft/sources.yaml** — from `sources.example.yaml` if missing.
3. **Add sources** (option 1) — local path or GitHub URL; runs `pull.py -a` under the hood.
4. **Setup embedding model** (option 2) — Hugging Face or Ollama embed models.
5. **Setup encoder model** (option 3) — cross-encoder for reranking.
6. **Configure LLM for Ask (AI)** (option 4) — Ollama or cloud (Gemini, Claude, OpenAI); writes **.env**.
7. **Build RAG index** (option 5) — quick or deep profile for semantic search and Ask (AI).
8. **Test RAG + LLM** (option 6) — sample Ask to verify the pipeline.
9. **Start UI** (option 7, default).
10. **Run in Docker** (option 8) — builds and runs the container with your data and LLM config.

Re-run **./setup.sh** anytime to add sources or change the LLM. See **docs/RAG_operations.md** for changing models and running RAG tests (ask.py, test_pipeline, CI/CD).

---

## References — docs for engineering and design

| Doc | Purpose |
| --- | --- |
| [Engineering](docs/engineering.md) | Design principles, storage, metadata, vault, intelligence layer, implementation order |
| [RAG design](docs/RAG_design.md) | RAG goals, chunking, two-stage retrieval (bi-encoder + cross-encoder), model choices |
| [RAG operations](docs/RAG_operations.md) | Changing embed/encoder models, tests (ask.py, test_pipeline, CI/CD) |
| [Container orchestration](docs/container_orchestration.md) | Docker and Kubernetes deployment, example manifests in `deployment/` |
| [MCP design](docs/MCP_design.md) | draft_mcp package, tools, Streamable HTTP + stdio, Bearer auth, resources, prompts |
| [MCP operations](docs/MCP_operations.md) | Runbook: run MCP server, token, config, testing, OTel metrics log, troubleshooting |
| [Observability design](docs/observability_design.md) | OTel metrics and traces (RAG + MCP), GenAI semconv, console vs OTLP |
| [OTel walkthrough](docs/OTel_walkthrough.md) | Data-flow walkthrough, metrics log file and env vars |
| [Testing suites](docs/testing_suites.md) | pytest, pipeline test, OTel tests, MCP integration (test_mcp.py), curl integration |
