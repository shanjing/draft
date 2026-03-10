# Draft

Draft pulls scattered files from your local disks and GitHub projects into one place — a unified knowledge base with full-text and semantic search, and an optional LLM that answers questions from your content. It works fully offline (private Inference stack or ollama for desktop)) or with a cloud provider, and scales from a personal note hub to a team knowledge base or a high-performance lightweight production MCP server.

To get started:
```bash
./setup.sh
```

---

## a) Personal Knowledge Base (PKB)

Browse, search, and ask questions over your notes, design docs, and pulled repos — all in one place.

<img width="1501" height="946" alt="Draft_UserUI" src="https://github.com/user-attachments/assets/3c053376-8925-4980-9c87-b05a018ac166" />

- **Full-text search** — fast keyword search over all docs (Whoosh), no LLM required
- **Semantic search + Ask (AI)** — vector retrieval with cross-encoder rerank; answers questions from your indexed content
- **Pull from anywhere** — local paths or GitHub URLs; only `.md` files are mirrored, directory structure preserved
- **Vault** — curated docs separate from pulled sources, can later be pointed at encrypted storage
- **No LLM required** for browsing and search; add Ollama or a cloud key only when you want AI answers

See [Setup](Setup.md) to configure sources and get started.

---

## b) MCP Server

Expose your knowledge base as an **MCP server** for AI agents, Claude Desktop, etc. Designed to run in Kubernetes or Docker and serve proprietary content (runbooks, engineering docs) to LLM clients over a secured HTTP transport.

**MCP client sends a query** — session + `retrieve_chunks` with a natural-language question (e.g. investigating pod resource constraints):

<img width="1692" height="635" alt="MCP_Question" src="https://github.com/user-attachments/assets/9449a439-5162-4413-a069-0ad1e2c999df" />

**Draft MCP returns ranked chunks** — runbook excerpts with repo, path, heading, text, and score:

<img width="1698" height="315" alt="MCP_Answer" src="https://github.com/user-attachments/assets/6cf958d5-2aad-471f-a0fe-08417d08db21" />

- **Streamable HTTP transport** — Bearer token auth, session-based, for remote clients and agents
- **stdio transport** — for Claude Desktop and local tools, no auth
- **Tools:** `search_docs`, `retrieve_chunks`, `get_document`, `list_documents`, `list_sources`, `query_docs` (when LLM configured)
- **Kubernetes-native** — Helm chart with PVC persistence, init container for cold-start index build, OTel instrumentation
- **Retrieval-only mode** — deploy without an LLM; clients get search + chunks and synthesize answers themselves
- **OpenTelemetry Observability** — for monitoring and debugging

**Fully supports Claude Code/Desktop**

<img width="1059" height="912" alt="ClaudeCodeMCP" src="https://github.com/user-attachments/assets/fdc84392-bf2c-4812-841e-9bdcc09003bb" />
<img width="1022" height="763" alt="ClaudeDesktop_2" src="https://github.com/user-attachments/assets/32028568-ef26-4057-ad78-727733ce55ee" />

**To start the MCP server**

```bash
./draft.sh mcp start    # local HTTP daemon (port 8059)
```

Full runbook: [MCP operations](docs/MCP_operations.md) · Setup: [Setup — MCP](Setup.md#mcp-server)

---

## c) Internal Business Knowledge Base (BKB)

Run Draft as a team or company knowledge base — a Confluence alternative that stays in your infrastructure. Deploy in Docker or Kubernetes, pull from multiple repos and GitHub orgs, and expose search and AI answers to your team.

<img width="1503" height="942" alt="Draft_BusinessUser" src="https://github.com/user-attachments/assets/094320c2-28a3-4aef-8769-04ef4da1f6e3" />

- **Docker or Kubernetes** — single container or Helm-deployed pod; mounts your doc directories
- **Multiple sources** — pull from local paths, GitHub URLs, or host-mounted directories in the pod
- **Full-text + semantic search** — same pipeline as PKB, shared across the team
- **Vault** — separate space for curated or sensitive docs

```bash
docker build -t draft-ui .
docker run -p 8058:8058 -v ~/.draft:/root/.draft draft-ui
```

See [Setup — BKB / Docker](Setup.md#bkb--docker).

---

## d) Privacy

Draft is designed to run **fully locally** — docs and queries never leave your machine.

- **Ollama for PKB** — use any local model (`qwen3:8b`, `llama3`, etc.); `./setup.sh` configures the full local stack
- **Local inference for MCP / BKB** — the MCP server and Docker/K8s deployments support Ollama; no cloud dependency required
- **HuggingFace offline** — embedding and reranker models (`all-MiniLM-L6-v2`, `ms-marco-MiniLM-L-6-v2`) are cached locally; `HF_HUB_OFFLINE=1` blocks all HF network access
- **No telemetry** — OTel metrics and traces stay local (log file or self-hosted OTLP collector) by default
- **Optional cloud** — choose Claude, Gemini, or OpenAI in setup; only then are prompts sent to that provider

For maximum privacy: use a local inference stack, keep `HF_HUB_OFFLINE=1` in `.env`, and run without any cloud API keys.

---

For setup instructions, doc sources, and technical configuration see **[Setup.md](Setup.md)**.

---

Draft is the MCP server of my W.I.P. agentic cloud platform "PrincipalOps.ai" which consists of NeuralGate (Inference Design/Provisioning), SudoRoot (SRE Agents that handle 24x7 Production Support for Kubernetes, Inference and ML infrastructures). "ShipIt!" 🚀
