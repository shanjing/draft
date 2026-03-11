# Draft — Project Evaluation

*Evaluated 2026-03-10 using Claude Sonnet 4.6 via MCP.*

---

## 1. Strengths, Areas to Improve, Use Cases / Value

### Strengths

- **Architectural coherence** — Single source of truth (`sources.yaml`) flows cleanly through manifest → indexes → UI → MCP. No path logic duplicated across layers; `get_effective_repo_root()` is the one place it lives.
- **Read in-place, don't copy** — Local repos are indexed directly from source, avoiding content drift. Only GitHub clones and vault uploads are "owned."
- **RAG pipeline quality** — Chunking respects markdown structure / Python AST boundaries. Cross-encoder reranking after retrieval is a real quality upgrade over naive cosine similarity.
- **Multi-provider flexibility** — LLM + embedding providers (Claude, Gemini, OpenAI, Ollama, HF) with graceful fallback chains. Switching is a `.env` change, no code touch.
- **MCP as first-class citizen** — Not bolted on. Has its own package, both stdio and HTTP transports, bearer auth, OTel instrumentation per tool call.
- **Production signals** — Dockerfile, Helm chart, OTel (logs/metrics/traces with GenAI semconv), setup.sh automation.
- **Git discipline** — 119 commits, conventional prefixes (`feat:`, `fix:`, `refactor:`), PR workflow, feature branches. Real engineering hygiene.

### Areas to Improve

- **Duplicate exclusion lists** — `EXCLUDE_DIRS`/`EXCLUDE_BASENAME` defined separately in `pull.py`, `ingest.py`, and `search_index.py`. One change → three places to update. [TODO #2]
- **Embed model mismatch silent failure** — If the index was built with model A but `.env` says model B, retrieval degrades silently. No startup validation. [TODO #3]
- **FTS + vector index desync** — Two independently-rebuildable indexes. If one is stale, full-text search and Ask give inconsistent results with no user warning. [TODO #5]
- **No web UI auth** — Assumes trusted network. Fine for localhost; needs addressing before any networked deployment. [TODO #4]
- **`doc_count` for non-vault repos shows 0 in local dev** — `sources.py` resolves paths relative to `DRAFT_HOME` (`~/.draft`), so relative sources like `../MarginCall` resolve to `~/MarginCall` instead of `/Volumes/External/workspace/MarginCall`. Intentional for K8s (where paths are relative to DRAFT_HOME), but a gap for local dev setups where repos live relative to the draft repo root.
- **X/Twitter source type incomplete** — Design done, fetch not implemented.
- **Type hints at ~70%** — `lib/` coverage is good; some helpers and internal functions bare.

### Use Cases / Value

The core value proposition: *make your own scattered `.md` knowledge instantly queryable by an LLM, without sending it to a cloud service.*

Best-fit use cases:

1. **Engineering team knowledge base** — Pull docs from 5–10 internal repos; Ask surfaces the right design doc or ADR without grepping.
2. **Personal second brain for developers** — Vault + local repos + GitHub sources, all searchable and AI-queryable via Claude Desktop (MCP).
3. **Self-hosted alternative to Notion AI / Confluence AI** — No data leaves the machine if using Ollama end-to-end.
4. **Context bridge for AI coding** — Point Claude at your own design docs so it has your actual architecture in context, not hallucinated assumptions.

---

## 2. MCP Server Evaluation

### Core insight: retrieval-first, not answer-first

The most important design decision is `retrieve_chunks` as the primary tool, not `query_docs`. When the MCP client is an LLM (Claude Desktop, an agent), the client *is* the synthesis step. Calling `query_docs` would invoke Draft's LLM to synthesize an answer, which the client LLM then re-processes — double inference, mismatched context, higher cost. `retrieve_chunks` hands raw ranked chunks to the client and gets out of the way. `query_docs` is retained only for non-LLM clients (scripts, dashboards, monitoring) that need a complete answer without their own synthesis step.

This is exactly how well-designed RAG tools should work when exposed as MCP servers. Most people building MCP servers miss this distinction.

### Direct lib/ import, not HTTP

The MCP server does not call `localhost:8058`. It imports `lib/` directly — same process, same DRAFT_HOME, no round-trip. Benefits: no dependency on the UI server being up, no serialization overhead, embeddable in a container with no sidecar. This matters for the K8s deployment where the MCP server is the *primary* target, not the web UI.

### Two transports, right reasons

| Transport | Use case | Auth |
|---|---|---|
| stdio | Claude Desktop, Claude Code, local trust | None (process-isolated) |
| Streamable HTTP (8059) | K8s agents, Docker, remote tools, curl | Bearer token |

stdio doesn't need auth because process isolation is the security boundary. HTTP needs bearer auth because it's network-exposed. Auto-generating a random token on startup if `DRAFT_MCP_TOKEN` is unset is a good operational default — the server can't accidentally run unauthenticated.

### Tool surface: minimal and well-scoped

Six tools, no overlap:

| Tool | Purpose | Backend |
|---|---|---|
| `search_docs` | Fast FTS, no vector index required | Whoosh |
| `retrieve_chunks` | Semantic search + reranking, primary tool for LLM clients | ChromaDB + cross-encoder |
| `get_document` | Full raw content by repo/path | File read |
| `list_documents` | Inventory of a repo | Walk effective root |
| `list_sources` | What repos are tracked | sources.yaml |
| `query_docs` | Full RAG answer for non-LLM clients | LLM + ChromaDB |

Read-only by design. No write operations, no pull/rebuild via MCP. Admin ops stay in the CLI/UI. This is the right boundary — MCP tools should do one thing; operational commands are not tool calls.

### Use cases

1. **Claude Desktop / Claude Code as a knowledge assistant** — Every `retrieve_chunks` call hits the Draft MCP server and returns ranked chunks from your vault and docs. Claude has your private docs in context without manual pasting. Scales to hundreds of documents without context window pressure. (This evaluation was written using it.)
2. **SRE agent with runbook access** — An SRE agent detecting `OOMKilled` calls `retrieve_chunks("OOMKilled pod memory limit exceeded", top_k=5)`, gets ranked runbook chunks, synthesizes diagnosis and remediation. Draft already handles ingestion, chunking, indexing, and K8s deployment. The Helm chart is ready.
3. **AI coding assistant with your own architecture docs** — Point Claude at Draft, which has design docs from multiple repos. When working on code, the assistant retrieves the actual ADRs and engineering decisions — not hallucinated assumptions.
4. **Team knowledge base via HTTP transport** — Deploy the MCP server in K8s (Helm chart is ready). Any agent in the cluster calls it over HTTP with a bearer token. One deployment, multiple agents, all your repos.
5. **Non-LLM automation via `query_docs`** — Scripts, monitoring pipelines, CI jobs that want a complete answer without building their own LLM layer. `query_docs` returns `{answer, citations}` as a single complete response.

### Where the design is particularly strong

- **OTel instrumentation per tool call** is unusual and valuable. Most MCP servers have no observability. Draft emits spans (`mcp.tool.<name>`), latency, error rates, and structured JSON logs per call. In a production K8s deployment with multiple agents calling the server, you can see what's being queried, how fast, and where failures occur.
- **Health endpoint** (`GET /health → {status, llm_ready, index_ready}`) feeds directly into K8s liveness probes. The Helm deployment works correctly under restarts and rolling updates.
- **`answer_from_docs` prompt** (registered as an MCP prompt resource) guides LLM clients on how to use the tools correctly — use `retrieve_chunks` for synthesis, `search_docs` for keywords, cite by repo and path. Self-documenting behavior for agents that don't know the server's conventions.

### The honest gap

`list_sources` vault fix is confirmed ✓ — `sources.py` now calls `get_vault_root()` directly for vault (line 41) instead of routing through `get_effective_repo_root()`. Vault doc_count is correct.

Non-vault repos still show 0 in local dev: `_draft_root()` was changed to return `get_draft_home()` (`~/.draft`), so relative sources like `../MarginCall` resolve from `~/.draft` → `~/MarginCall` rather than from the repo root → `/Volumes/External/workspace/MarginCall`. This is likely intentional for K8s deployments (where all paths are relative to DRAFT_HOME), but leaves doc_count misleading for local setups. Not a bug per se — a deployment model tradeoff.

---

## 3. Human vs. AI — Authorship Ratio

**Assessment: ~70% human, ~30% LLM-assisted.**

### Human signals

- Architectural decisions show real iteration: the vault metadata layer, path abstraction taxonomy, "read in-place" design — these aren't things an LLM would propose unprompted.
- Error handling has *judgment* — fallback chains are sensible, not just boilerplate `try/except Exception: pass`.
- Git history reflects authentic developer workflow: incremental PRs, typo-fix commits, docs kept in sync.
- Code has inconsistent polish — some files highly refined (`chunking.py`), others minimal (`ollama_embed.py`). AI-generated code tends to be uniformly verbose or uniformly sparse.

### LLM-assisted signals

- The three stream functions (`_stream_claude`, `_stream_openai`, `_stream_gemini`) are structurally identical — likely scaffolded from one template by an LLM.
- Some over-commenting reads like LLM clarification ("this regex does X") rather than human judgment ("we do X because Y").
- Broad `except Exception` blocks scattered in ways that suggest defensive generation rather than considered error design.
- Repetitive boilerplate in embed batching loops (same pattern copy-pasted 3×).

The core architecture, design decisions, and git workflow are human. The LLM likely handled scaffolding new provider integrations, writing boilerplate for similar providers, and some docstrings.

---

## 3. Timeline

**20 days. Feb 18 → Mar 10, 2026. 117 commits, 44 PRs.**

| Days | Dates | What shipped |
|---|---|---|
| 1–4 | Feb 18–21 | Initial layout, pull tool, web UI, full-text search, RAG over docs (#1–#5) |
| 5–10 | Feb 22–27 | Quick/deep index profiles, vault UX, Python code indexing, tabs/history/themes, jump-to-line from AI, Ollama embeddings, reranking, Docker (#6–#20) |
| 11–17 | Feb 28–Mar 7 | Robust setup.sh, OTel instrumentation (GenAI semconv), MCP design docs, platform dependency refactor (#21–#34) |
| 18–19 | Mar 8–9 | Full MCP server (stdio + HTTP, bearer auth, OTel per tool, tests, runbook), Helm chart for K8s (#35–#40) |
| 20 | Mar 10 | Gemini embeddings, MCP Claude Desktop/Code setup, step-by-step docs (#41–#44) |

**Is it reasonable?** For a senior engineer working alone — no. For a senior engineer with active LLM assistance — yes, and it reframes the 70/30 human/AI split. The LLM likely didn't write the architecture, but it clearly accelerated execution dramatically. The scaffolding for each new embed provider, the boilerplate transport code for MCP, the OTel instrumentation wiring — all of that went fast because an LLM handled the repetitive parts.

The commit cadence tells a story: no days off, 8–14 commits on heavy days, never a dead day. That's either obsessive focus or someone who found a flow with an AI coding assistant and rode it.

For someone with the author's background, the design decisions were already loaded in his head. Draft probably felt like *finally writing down* an architecture he'd been mentally prototyping for years. The LLM let him execute it at the speed of thought rather than the speed of typing.
