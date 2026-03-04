# MCP Server Design

## Context

Draft exposes document search, RAG Q&A, source management, and vault operations through a FastAPI app. Building an MCP server on top of it lets AI assistants (Claude Desktop, Claude Code, or any MCP-compliant client) use Draft as a live knowledge-base tool — searching docs, asking questions, retrieving raw content — without screen-scraping the UI or calling internal HTTP endpoints.

---

## 1. The Early Design's "Divident" That Allows MCP To Work With the Existing Codebase

### MCP key principle: import `lib/` directly, skip the HTTP layer

When I designed Draft's project structure, the idea of adding an MCP was always in consideration:
  - lib/ is completely decoupled from ui/. lib/ai_engine.py, lib/ingest.py, lib/paths.py etc. are pure Python modules with no HTTP concepts. The FastAPI app in ui/app.py is just a thin wrapper that calls lib/ and formats the result as HTTP responses.
  - No business logic lives in the API layer. Every endpoint in ui/app.py does: validate input → call a lib/ function → format response.
  - ask_stream() is a Python generator, not an HTTP construct. The SSE endpoint in ui/app.py consumes it, and the MCP server can consume it identically — same function, just different caller.
  - lib/paths.py abstracts all storage so any caller can resolve DRAFT_HOME, repo roots, vault etc. without knowing the file system layout.

As results, the MCP server does **not** call `http://localhost:8058`. It imports from `lib/` and `ui/search_index` directly. This means:
- No round-trip latency
- No dependency on the UI server being up
- Shared DRAFT_HOME / path resolution via `lib/paths.py`
- Direct access to `ask_stream()`, `retrieve()`, `rerank()`, `search()`, and `parse_sources_yaml()`

### Directory structure: `mcp/`

```
mcp/
  __init__.py
  server.py          # Server definition: registers all tools, resources, prompts
  tools/
    __init__.py
    search.py        # search_docs, retrieve_chunks
    ask.py           # query_docs (streaming RAG)
    documents.py     # get_document, list_documents
    sources.py       # list_sources, pull_sources, add_source
    indexing.py      # rebuild_index, get_task_status (async)
  auth.py            # Bearer token middleware (Starlette)
  tasks.py           # In-memory async task tracker for long-running ops
  errors.py          # MCP error type wrappers

scripts/
  serve_mcp.py       # Entrypoint: launches MCP server (--stdio or HTTP)
```

### MCP tools that map to existing code
Desing philosophy: decoupling components -> a thin MCP layer uses existint code.

| MCP Tool | Calls | Module |
|---|---|---|
| `search_docs` | `search_index.search()` | `ui/search_index.py` |
| `retrieve_chunks` | `ai_engine.retrieve()` + `ai_engine.rerank()` | `lib/ai_engine.py` |
| `query_docs` | `ai_engine.ask_stream()` | `lib/ai_engine.py` |
| `get_document` | reads via `paths.get_effective_repo_root()` | `lib/paths.py` |
| `list_documents` | walks effective repo root | `lib/paths.py` + `lib/ingest.should_include()` |
| `list_sources` | `manifest.parse_sources_yaml()` | `lib/manifest.py` |
| `pull_sources` | subprocess `scripts/pull.py` + async task tracker | `scripts/pull.py` |
| `rebuild_index` | `ingest.build_index()` in thread | `lib/ingest.py` |
| `get_task_status` | tasks.py in-memory store | `mcp/tasks.py` |

---

## 2. SDK Selection

### The landscape

There are three options in practice:

| Option | What it is |
|---|---|
| `mcp` — low-level `Server` class | Official SDK; explicit transport wiring; maximum control |
| `mcp` — high-level `FastMCP` class | Decorator API built into the official SDK since v1.0 |
| `fastmcp` standalone package | Independent third-party package; inspired the official high-level API; continues separately |

FastMCP's ergonomics were popular enough that Anthropic absorbed a `FastMCP` high-level class directly into the official `mcp` package. `from mcp import FastMCP` is now part of the official SDK. The standalone `fastmcp` package continues independently with additional features (server composition, proxies).

### Trade-offs

**Official `mcp` — low-level `Server`**
- Full control over transport wiring, Starlette middleware, session management
- Auth middleware, request ID injection, and typed error handling sit cleanly at the transport layer
- Spec-aligned by definition; no lag on MCP spec updates
- Verbose: two decorated functions per tool (`list_tools` + `call_tool`); boilerplate accumulates with many tools

**Official `mcp` — high-level `FastMCP` class**
- Decorator API (`@mcp.tool()`) — one function per tool, concise
- Still spec-aligned and officially maintained; can drop to low-level when needed
- Some production hooks (custom auth, request lifecycle) require that drop anyway, leading to a mixed codebase

**Standalone `fastmcp` package**
- Most ergonomic; fastest to prototype; ships features (composition, proxies) ahead of the official SDK
- Independent release cycle — spec updates depend on the maintainer to catch up
- Auth hooks and transport internals are abstracted in ways that are difficult to override precisely
- Version coupling risk: major bumps have broken integrations before

### Why choosing the official `mcp` SDK

Three production requirements drive the decision:

1. **Bearer token auth middleware** — needs to intercept requests before any tool logic runs, at the Starlette middleware layer. The standalone `fastmcp` abstracts the transport in a way that makes clean middleware insertion difficult; the official SDK exposes the ASGI layer directly.

2. **Structured logging with request IDs** — each tool call needs a traceable ID flowing from the transport header through to the log line. This requires lifecycle hooks the official low-level API provides explicitly.

3. **Spec longevity** — the server is intended for Docker/k8s deployment with a long operational life. Tying that to a third-party package's release cadence adds unnecessary risk.

**Chosen approach:** official `mcp` SDK using the **high-level `FastMCP` class for tool and resource definitions** (concise, readable), dropping to **low-level transport wiring for auth middleware and request lifecycle hooks**. Ergonomics where it's cheap; control where production demands it.

```
pip install mcp
```

---

## 3. Transport Protocol

**Primary: Streamable HTTP (MCP spec 2025-03-26)**
**Secondary: stdio (Claude Desktop local integration)**

### Streamable HTTP

Streamable HTTP is the modern replacement for the older SSE transport. It uses a single HTTP endpoint (`POST /mcp`) where:
- Requests arrive as JSON-RPC over POST
- Responses can be immediate JSON or a streamed SSE body (for streaming tools like `query_docs`)
- Works in Docker, k8s, and behind reverse proxies
- Supports session management via `Mcp-Session-Id` header

This maps cleanly onto the existing FastAPI codebase — the MCP endpoint is just another Starlette route.

### stdio

Claude Desktop connects to MCP servers via stdio by default. `scripts/serve_mcp.py --stdio` starts the same server with stdio transport. The same `mcp/server.py` handles both — the SDK manages transport switching.

### Transport routing

```
--stdio flag   →  stdio transport   (Claude Desktop, local)
(default)      →  Streamable HTTP on port 8059
```

### Claude Desktop config (local use)

```json
{
  "mcpServers": {
    "draft": {
      "command": "python",
      "args": ["scripts/serve_mcp.py", "--stdio"],
      "env": { "DRAFT_HOME": "/Users/user/.draft" }
    }
  }
}
```

### Docker / remote use

```
POST http://localhost:8059/mcp
Authorization: Bearer <DRAFT_MCP_TOKEN>
```

---

## 4. On-Demand vs Batch

**The server is on-demand (request/response per tool call).** Tools fall into three latency tiers, each handled differently:

| Tier | Tools | Handling |
|---|---|---|
| Fast (< 500ms) | `search_docs`, `list_sources`, `list_documents`, `get_document`, `retrieve_chunks`, `get_task_status` | Synchronous, return immediately |
| Streaming (1–30s) | `query_docs` | Streaming tool response via MCP streaming annotations; maps directly to `ask_stream()` generator |
| Long-running (seconds–minutes) | `pull_sources`, `rebuild_index` | Async: return `{task_id}` immediately; client polls `get_task_status(task_id)` |

### Async task pattern

```
client calls pull_sources()
  → server spawns asyncio.create_task() wrapping subprocess
  → returns {"task_id": "abc123", "status": "running"}

client calls get_task_status("abc123")
  → returns {"status": "running"|"done"|"error", "logs": [...], "result": {...}}
```

`mcp/tasks.py` maintains an in-memory dict with TTL cleanup (tasks expire after 10 minutes). No Redis, no DB — appropriate for a single-instance deployment.

---

## 5. Production-Grade Requirements
For Draft, a personal document server, Auth is optional. For production-grade SRE agents, auth is required.

### Auth: Bearer token middleware

All HTTP transport requests require:
```
Authorization: Bearer <DRAFT_MCP_TOKEN>
```

Token is set in `.env` as `DRAFT_MCP_TOKEN`. If unset, the server generates a random token on startup and prints it once. Requests without a valid token receive `401 Unauthorized` before any tool logic runs.

`mcp/auth.py` implements this as Starlette middleware on the HTTP transport. stdio transport skips auth (stdio is inherently local/trusted).

### Input validation

All tool inputs are Pydantic models. Invalid inputs return structured MCP errors, not stack traces:

```python
class QueryDocsInput(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
```

### Error handling

`mcp/errors.py` wraps exceptions into MCP `CallToolResult` with `isError=True` and a human-readable message. Error categories:

| Error | Condition |
|---|---|
| `IndexNotReady` | No vector store built yet |
| `SourceNotFound` | Repo name not in sources.yaml |
| `DocumentNotFound` | Path doesn't exist in repo |
| `LLMNotConfigured` | No provider set up in `.env` |
| `TaskNotFound` | Invalid task_id passed to `get_task_status` |

### Structured logging

Each tool call emits a JSON log line via `lib.log.get_logger(__name__)`:

```json
{"level": "info", "tool": "query_docs", "request_id": "uuid4", "duration_ms": 1240, "status": "ok"}
```

Request IDs flow from `Mcp-Session-Id` header (HTTP) or a generated UUID (stdio).

### Timeouts

Implemented via `asyncio.wait_for()` per tier:

| Tool category | Timeout |
|---|---|
| Fast tools | 10s |
| `query_docs` (RAG + LLM) | 120s |
| `pull_sources` async task | 300s |
| `rebuild_index` deep profile | 600s |

### Health endpoint (HTTP transport only)

```
GET http://localhost:8059/health
→ {"status": "ok", "llm_ready": bool, "index_ready": bool, "version": str}
```

Used by Docker `HEALTHCHECK` and k8s liveness probes.

---

## Tool & Resource Specification

### Tools

**`search_docs`**
- Input: `{query: str, limit: int = 20}`
- Output: `[{repo, path, snippet}]`
- Source: `ui.search_index.search()`
- Fast full-text search; no LLM or index required

**`query_docs`** — primary value-add tool
- Input: `{question: str}`
- Output: streaming — text chunks, then `{citations: [{repo, path, heading, score, start_line, end_line, snippet}]}`
- Source: `lib.ai_engine.ask_stream()`
- Requires LLM configured in `.env` and a built vector index
- Note: will use the agentic RAG router once implemented (see `docs/agentic_RAG_design.md`)

**`retrieve_chunks`** — power user / custom RAG
- Input: `{query: str, top_k: int = 5, rerank: bool = True}`
- Output: `[{repo, path, heading, text, score, start_line, end_line}]`
- Source: `ai_engine.retrieve()` + optionally `ai_engine.rerank()`
- Returns raw chunks for callers that want to handle synthesis themselves

**`get_document`**
- Input: `{repo: str, path: str}`
- Output: `{content: str, repo: str, path: str, size_bytes: int}`
- Source: `paths.get_effective_repo_root()` → read file directly

**`list_documents`**
- Input: `{repo: str}`
- Output: `[{path: str, size_bytes: int}]`
- Source: walk effective repo root filtered by `ingest.should_include()`

**`list_sources`**
- Input: none
- Output: `[{name: str, source: str, url: str|None, doc_count: int}]`
- Source: `manifest.parse_sources_yaml()` + walk counts

**`pull_sources`** (async)
- Input: `{source: str|None}` — None pulls all
- Output: `{task_id: str, status: "running"}`
- Long-running; poll with `get_task_status`

**`rebuild_index`** (async)
- Input: `{profile: "quick"|"deep"}`
- Output: `{task_id: str, status: "running"}`
- Long-running; poll with `get_task_status`

**`get_task_status`**
- Input: `{task_id: str}`
- Output: `{task_id, status: "pending"|"running"|"done"|"error", result?: any, logs: [str], started_at: str, elapsed_s: float}`

### Resources

**`draft://sources`**
- Returns JSON of all sources with doc counts

**`draft://doc/{repo}/{path}`**
- Returns raw document content (mirrors `get_document` as a resource URI)
- Allows Claude to reference a specific doc without a tool round-trip

### Prompts

**`answer_from_docs`**
- Pre-built MCP prompt that instructs the model:
  > Use `search_docs` to locate relevant documents first, then `query_docs` for a synthesized answer with citations. For specific content, use `get_document`. Always cite sources by repo and path.

---

## File Changelist

| File | Change |
|---|---|
| `mcp/__init__.py` | New — package marker |
| `mcp/server.py` | New — server definition, tool/resource/prompt registration |
| `mcp/tools/search.py` | New — `search_docs`, `retrieve_chunks` |
| `mcp/tools/ask.py` | New — `query_docs` (streaming) |
| `mcp/tools/documents.py` | New — `get_document`, `list_documents` |
| `mcp/tools/sources.py` | New — `list_sources`, `pull_sources`, `add_source` |
| `mcp/tools/indexing.py` | New — `rebuild_index`, `get_task_status` |
| `mcp/auth.py` | New — Bearer token middleware |
| `mcp/tasks.py` | New — async task tracker with TTL |
| `mcp/errors.py` | New — MCP error type wrappers |
| `scripts/serve_mcp.py` | New — entrypoint (`--stdio` or Streamable HTTP) |
| `requirements.txt` | Add `mcp>=1.0` |
| `.env` / `.env.example` | Add `DRAFT_MCP_TOKEN=` |

---

## Verification

1. **Stdio / Claude Desktop:** Add config to `claude_desktop_config.json` → ask Claude "what docs do I have?" → `list_sources` is called → repos returned
2. **HTTP / curl:**
   ```bash
   curl -X POST http://localhost:8059/mcp \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search_docs","arguments":{"query":"RAG pipeline"}}}'
   ```
3. **Streaming:** Call `query_docs` via Claude Desktop → answer streams in real time, citations appear at end
4. **Auth:** No token → `401`; wrong token → `401`; correct token → `200`
5. **Async task:** Call `pull_sources` → receive `task_id` → poll `get_task_status` → eventually `"done"` with logs
6. **Health:** `GET http://localhost:8059/health` → `{"status": "ok", "llm_ready": true, "index_ready": true}`
7. **Error handling:** Call `query_docs` with no index built → structured error: `IndexNotReady: run rebuild_index first`
8. **Docker:** `docker compose up` → both app and MCP server healthy → `query_docs` routes through Ollama container correctly
