# MCP Server Operations Runbook

## Overview

Draft's MCP server exposes document search, semantic retrieval, and RAG Q&A to any MCP-compliant client. It runs as a separate process from the UI server (port 8059 vs 8058) and can be started independently.

Two transports are supported:


| Transport           | Use case                                | Auth                    |
| ------------------- | --------------------------------------- | ----------------------- |
| **stdio**           | Claude Desktop, local trusted tools     | None (process-isolated) |
| **Streamable HTTP** | Remote agents, Docker, SRE agents, curl | Bearer token            |


---

## Prerequisites

```bash
# Python 3.11 or 3.12 (3.14+ not supported)
python --version

# Install dependencies (includes mcp>=1.0)
pip install -r requirements.txt

# Verify MCP package is available
python -c "from mcp.server.fastmcp import FastMCP; print('ok')"

# Verify draft_mcp loads cleanly
python -c "from draft_mcp.server import mcp; print([t.name for t in mcp._tool_manager.list_tools()])"
# → ['search_docs', 'retrieve_chunks', 'get_document', 'list_documents', 'list_sources', 'query_docs']
```

The MCP server requires the same `~/.draft/` data directory used by the UI. If Draft is already set up and indexed, the MCP server is ready to run.

---

## Configuration

All configuration is in `.env` at the repo root (same file as the UI). Copy `.env.example` if starting fresh.

### MCP-specific variables


| Variable            | Default        | Purpose                                                                                                |
| ------------------- | -------------- | ------------------------------------------------------------------------------------------------------ |
| `DRAFT_MCP_TOKEN`   | auto-generated | Bearer token for HTTP transport. If unset, a random token is printed to stderr on startup.             |
| `MCP_LOG_JSON`      | unset          | Set to `1` to emit structured JSON log lines instead of plain text (affects both stderr and log file). |
| `OTEL_SERVICE_NAME` | `draft-mcp`    | OTel service name for traces and metrics.                                                              |


### Log file

The server always writes logs to `~/.draft/draft-mcp.log` in addition to stderr. No configuration required — the file is created automatically on first run.

```bash
tail -f ~/.draft/draft-mcp.log
```

With `MCP_LOG_JSON=1` the file contains one JSON object per line:

```json
{"ts": 1741442324.1, "levelname": "INFO", "message": "ok", "tool": "retrieve_chunks", "duration_ms": 41.2, "status": "ok"}
```

### LLM variables (required only for `query_docs`)


| Variable             | Purpose                                   |
| -------------------- | ----------------------------------------- |
| `DRAFT_LLM_PROVIDER` | `ollama` | `claude` | `gemini` | `openai` |
| `OLLAMA_MODEL`       | e.g. `qwen3:8b` (if provider is ollama)   |
| `ANTHROPIC_API_KEY`  | Required if provider is `claude`          |
| `GEMINI_API_KEY`     | Required if provider is `gemini`          |
| `OPENAI_API_KEY`     | Required if provider is `openai`          |


### DRAFT_HOME

The server resolves `DRAFT_HOME` from the environment (defaults to `~/.draft`). If you run the server as a different user or in Docker, set this explicitly.

```bash
DRAFT_HOME=/path/to/.draft python scripts/serve_mcp.py
```

---

### MCP Token

#### How Draft manages the token

Draft uses a single Bearer token for all HTTP clients (curl, Claude Desktop HTTP, MCP SDK).

| Deployment | Source of truth | Survives restart? |
|---|---|---|
| Local daemon (`draft.sh mcp`) | `.env` — `DRAFT_MCP_TOKEN=<value>` | ✅ Yes — same `.env` on every start |
| Kubernetes | `values.local.yaml` — `mcp.token: <value>` → Kubernetes Secret | ✅ Yes — if set in values; ❌ No — if left empty (`helm upgrade` overwrites with empty) |
| Auto-generated (no token set) | Printed to stderr on startup only | ❌ No — new token each restart |

**Rule:** always set an explicit token. Auto-generation is convenient for a first run but breaks clients after any restart.

#### Generate a token

```bash
openssl rand -base64 32
```

#### Local: set token in `.env`

```bash
# Add or update in .env at repo root
echo "DRAFT_MCP_TOKEN=$(openssl rand -base64 32)" >> .env
# Then restart the server
./draft.sh mcp restart
```

#### Kubernetes: set token in `values.local.yaml` (recommended)

Add once — every `helm upgrade` will preserve it:

```yaml
# kubernetes/draft/values.local.yaml  (gitignored)
mcp:
  token: "<output of: openssl rand -base64 32>"
```

Then upgrade:
```bash
helm upgrade draft ./kubernetes/draft -n draft \
  -f kubernetes/draft/values.mcp.yaml \
  -f kubernetes/draft/values.local.yaml
```

#### Get the current token from a running cluster

```bash
kubectl -n draft get secret draft \
  -o jsonpath='{.data.DRAFT_MCP_TOKEN}' | base64 -d
```

If the secret is empty (token was auto-generated), read it from the pod logs:

```bash
kubectl logs -n draft deployment/draft -c mcp | grep -i "generated token"
```

Then pin it in `values.local.yaml` and run `helm upgrade` so it persists across future upgrades.

#### Upgrade without losing the existing token

If `mcp.token` is not yet set in `values.local.yaml`, use this pattern to read the live token and
pass it through the upgrade in one step — so clients don't need to re-authenticate:

```bash
TOKEN=$(kubectl -n draft get secret draft -o jsonpath='{.data.DRAFT_MCP_TOKEN}' | base64 -d)
helm upgrade draft ./kubernetes/draft -n draft \
  --set mcp.token="$TOKEN" \
  -f kubernetes/draft/values.mcp.yaml \
  -f kubernetes/draft/values.local.yaml
```

After the upgrade, add `mcp.token: "<TOKEN>"` to `values.local.yaml` so future upgrades preserve it
automatically without the `--set` flag.

---

## Running Modes

### 1. Local daemon — `draft.sh mcp` (recommended for local use)

`draft.sh` is the unified local process manager for the UI and MCP server. It handles PID tracking, force-kill on restart/stop, and combined status.

```bash
./draft.sh mcp start             # HTTP daemon, port 8059, background
./draft.sh mcp start --log-json  # same, with JSON-format logs
./draft.sh mcp stop              # stop (SIGTERM → SIGKILL → port sweep)
./draft.sh mcp restart           # stop then start
./draft.sh mcp start --stdio     # stdio transport (foreground)
./draft.sh mcp logs              # tail ~/.draft/draft-mcp.log
./draft.sh status                # show state of both UI and MCP
```

### 2. stdio (Claude Desktop / local)

```bash
./draft.sh mcp start --stdio     # via draft.sh (recommended)
# or directly:
python scripts/serve_mcp.py --stdio
```

- Reads JSON-RPC from stdin, writes to stdout
- No auth — the process boundary is the security perimeter
- Started and managed by the MCP client (e.g. Claude Desktop launches and owns the process)
- Logs go to stderr and `~/.draft/draft-mcp.log`

### 3. HTTP daemon (foreground / scripting)

```bash
python scripts/serve_mcp.py
```

- Streamable HTTP on `0.0.0.0:8059`
- Bearer token auth on all requests except `/health`
- Token printed to stderr if `DRAFT_MCP_TOKEN` is not set

### 4. HTTP daemon with JSON logging

Logs are always written to `~/.draft/draft-mcp.log`. Setting `MCP_LOG_JSON=1` switches both stderr and the log file to JSON format:

```bash
./draft.sh mcp start --log-json   # via draft.sh (recommended)
# or directly:
MCP_LOG_JSON=1 python scripts/serve_mcp.py
```

Each tool call emits one JSON line to `~/.draft/draft-mcp.log`:

```json
{"ts": 1741442324.1, "levelname": "INFO", "message": "ok", "tool": "retrieve_chunks", "duration_ms": 41.2, "status": "ok"}
```

### 5. Kubernetes / Helm

For Kubernetes deployment and operations, see **[Container orchestration → Kubernetes Operations Runbook](container_orchestration.md#kubernetes-operations-runbook)**.

---

### 6. Docker (HTTP)

No docker-compose exists yet; run directly from the same image as the UI:

```bash
# Build (same Dockerfile, same image)
docker build -t draft .

# Run MCP server (port 8059)
docker run -d \
  --name draft-mcp \
  -p 8059:8059 \
  -v ~/.draft:/root/.draft \
  --env-file .env \
  --env-file .env.docker \
  draft \
  python scripts/serve_mcp.py

# Logs
docker logs -f draft-mcp

# Stop
docker stop draft-mcp && docker rm draft-mcp
```

> **Note:** If using Ollama on the host, `.env.docker` sets `OLLAMA_HOST=http://host.docker.internal:11434`. On Linux replace with `http://172.17.0.1:11434` or use `--network=host`.

## Stopping the Server

```bash
# Local daemon (started with draft.sh):
./draft.sh mcp stop

# By process name (fallback):
pkill -f "serve_mcp.py"

# Docker:
docker stop draft-mcp

# Kubernetes:
helm uninstall draft --namespace draft
```

stdio processes are managed by the MCP client — Claude Desktop stops them automatically.

---

## Health & Status Verification

The `/health` endpoint is unauthenticated and is the primary liveness/readiness check.

```bash
curl http://localhost:8059/health
```

```json
{
  "status": "ok",
  "llm_ready": true,
  "index_ready": true,
  "version": "1.0"
}
```


| Field         | Meaning                                                            |
| ------------- | ------------------------------------------------------------------ |
| `status`      | Always `"ok"` if the process is alive                              |
| `llm_ready`   | LLM provider is configured in `.env` (`query_docs` will work)      |
| `index_ready` | Vector store exists and is non-empty (`retrieve_chunks` will work) |


If `index_ready` is `false`, run a rebuild before clients call `retrieve_chunks`:

```bash
python scripts/index_for_ai.py --profile quick
```

---

## Client Integration

### Claude Desktop (stdio)

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:
(note: Claude Desktop and Claude Code access the MCP via local stdio and does not need the auth token)
```json
{
  "mcpServers": {
    "draft": {
      "command": "/path/to/draft/.venv/bin/python",
      "args": ["/path/to/draft/scripts/serve_mcp.py", "--stdio"],
      "cwd": "/path/to/draft",
      "env": {
        "DRAFT_HOME": "/Users/yourname/.draft"
      }
    }
  }
}
```

Replace `/path/to/draft` with the absolute path to your Draft repo (e.g. `/Users/yourname/workspace/draft`).

**Two requirements for Claude Desktop:**
- **Use the venv Python** — Claude Desktop does not activate any virtualenv; system `python` won't have Draft's dependencies. Use `.venv/bin/python` inside the repo.
- **Use absolute paths** — Claude Desktop does not reliably honor `cwd`, so relative paths in `args` will fail. Both the Python path and the script path must be absolute.

Restart Claude Desktop. In any conversation, Draft's tools will appear in the tool picker. The `answer_from_docs` prompt is available under the prompts menu.

---

### Claude Code (stdio)

Use the `claude mcp add` command — Claude Code reads MCP config from `~/.claude.json`, not `~/.claude/settings.json`:

```bash
claude mcp add \
  -e DRAFT_HOME=/Users/yourname/.draft \
  -s user \
  draft -- \
  /path/to/draft/.venv/bin/python \
  /path/to/draft/scripts/serve_mcp.py --stdio
```

Replace `/path/to/draft` and `/Users/yourname/.draft` with your actual paths. The `-s user` flag makes the server available across all projects (omit for project-local only).

Verify registration:

```bash
claude mcp list
```

MCP servers connect at session start. **Start a new `claude` session** after adding the server, then run `/mcp` — you should see `draft` with `search_docs`, `retrieve_chunks`, `get_document`, `list_documents`, `list_sources`, and `query_docs`.

### HTTP client (any agent / curl)

**Step 1: Get the token**

```bash
# From .env
grep DRAFT_MCP_TOKEN .env

# Or read from startup log if auto-generated
python scripts/serve_mcp.py 2>&1 | head -5
# [draft-mcp] No DRAFT_MCP_TOKEN set. Generated token for this session:
#   <TOKEN>
```

**Step 2: Set the token persistently**

```bash
echo "DRAFT_MCP_TOKEN=your-token-here" >> .env
```

**Step 3: Initialize a session**

The Streamable HTTP transport requires an `initialize` handshake. The server returns an `Mcp-Session-Id` header that must be included in all subsequent requests.

```bash
TOKEN=$(grep DRAFT_MCP_TOKEN .env | cut -d= -f2)
BASE="http://localhost:8059/mcp"
HEADERS=(-H "Authorization: Bearer $TOKEN" \
         -H "Content-Type: application/json" \
         -H "Accept: application/json, text/event-stream")

SESSION=$(curl -si -X POST "$BASE" "${HEADERS[@]}" \
  -d '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' \
  | grep -i "mcp-session-id" | awk '{print $2}' | tr -d '\r')

echo "Session: $SESSION"
```

**Step 4: Make tool calls**

All tool calls go to `POST http://localhost:8059/mcp` with the session ID header. Responses are Server-Sent Events (SSE); pipe through `grep '^data:' | cut -c7-` to extract the JSON payload.

---

## Testing

### Full Test Suite

A full test suite is in `tests/test_mcp.py`.

```bash
source .venv/bin/activate
pytest tests/test_mcp.py -v
```

### Quick Individual Tests Setup (run once per shell session)

```bash
TOKEN=$(grep DRAFT_MCP_TOKEN .env | cut -d= -f2)
BASE="http://localhost:8059/mcp"
HEADERS=(-H "Authorization: Bearer $TOKEN" \
         -H "Content-Type: application/json" \
         -H "Accept: application/json, text/event-stream")

SESSION=$(curl -si -X POST "$BASE" "${HEADERS[@]}" \
  -d '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' \
  | grep -i "mcp-session-id" | awk '{print $2}' | tr -d '\r')

echo "Session: $SESSION"
```

---

### Test 1 — List available sources

Verifies the server is running, auth works, and `sources.yaml` is read correctly.

```bash
curl -s -X POST "$BASE" "${HEADERS[@]}" -H "Mcp-Session-Id: $SESSION" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "list_sources",
      "arguments": {}
    }
  }' | grep '^data:' | cut -c7- | python3 -m json.tool
```

If `SESSION` is empty, the `initialize` call failed — check the token and that the server is running. If the server returns 500, restart the MCP server after code changes; ensure `DRAFT_HOME` (or default `~/.draft`) has `sources.yaml`.

**Expected response:**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "[{\"name\": \"draft\", \"source\": \".\", \"url\": null, \"doc_count\": 12}, ...]"
      }
    ],
    "isError": false
  }
}
```

The `text` field contains a JSON-encoded list of repo objects. If `doc_count` is 0 for all repos, run `python scripts/pull.py` first.

---

### Test 2 — Semantic search for a concept

Verifies the vector index is built and `retrieve_chunks` returns ranked results.

```bash
curl -s -X POST "$BASE" "${HEADERS[@]}" -H "Mcp-Session-Id: $SESSION" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "retrieve_chunks",
      "arguments": {
        "query": "how to check the high-level status of the InferenceService and view the rollout status of the underlying predictor deployment?",
        "top_k": 3,
        "rerank": true
      }
    }
  }' | grep '^data:' | cut -c7- | python3 -m json.tool
```

**Expected response** (abbreviated):

```json
{
    "jsonrpc": "2.0",
    "id": 2,
    "result": {
        "content": [
            {
                "type": "text",
                "text": "{\n  \"repo\": \"runbooks\",\n  \"path\": \"Inference_runbook.md\",\n  \"heading\": \"Deployment and rollout\",\n  \"text\": \"Each model is an **InferenceService**; KServe creates a **Deployment** and **Service** for the predictor. Check InferenceService `.status.conditions` for Ready, and the underlying Deployment rollout status. Stuck or failed rollouts appear here.\\n\\n**Commands**\\n\\n```bash\\n# List InferenceServices and high-level status\\nkubectl get inferenceservice -n inference\\n\\n# InferenceService conditions and status (replace <model-name> with e.g. qwen3-8b)\\nkubectl describe inferenceservice <model-name> -n inference\\n\\n# Underlying Deployments (KServe names them <model-name>-predictor)\\nkubectl get deployment -n inference\\n\\n# Rollout status for a predictor Deployment (replace <model-name> with actual name)\\nkubectl rollout status deployment/<model-name>-predictor -n inference\\n\\n# ReplicaSets and desired/current replicas\\nkubectl get replicaset -n inference -l neural-gate/role=model-server\\n```\\n\\n---\",\n  \"score\": 7.6109\n}"
            },
```

Each chunk has `repo`, `path`, `heading`, `text`, `score`, `start_line`, `end_line`. The client LLM uses these chunks to write its own synthesized answer.

**If `isError: true` with `IndexNotReady`:**

```bash
python scripts/index_for_ai.py --profile quick
# Then retry
```

---

### Test 3 — Auth rejection

Confirms the middleware is active.

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -X POST http://localhost:8059/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{}'
# → 401

curl -s -o /dev/null -w "%{http_code}" \
  -X POST http://localhost:8059/mcp \
  -H "Authorization: Bearer wrong-token" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{}'
# → 401
```

---

## Tool Reference (Client Quick Card)


| Tool              | When to call                               | Key parameters                    |
| ----------------- | ------------------------------------------ | --------------------------------- |
| `list_sources`    | Always first — understand what repos exist | none                              |
| `search_docs`     | Keyword / exact phrase lookup              | `query`, `limit=20`               |
| `retrieve_chunks` | Conceptual / semantic questions (primary)  | `query`, `top_k=5`, `rerank=true` |
| `get_document`    | Read a full document by path               | `repo`, `path`                    |
| `list_documents`  | Browse what files exist in a repo          | `repo`                            |
| `query_docs`      | Non-LLM clients wanting a complete answer  | `question`                        |


**Decision guide for LLM clients:**

```
Do I know the exact document I need?
  → get_document(repo, path)

Do I have a keyword to search for?
  → search_docs(query) to find paths, then get_document if needed

Do I have a question or concept?
  → retrieve_chunks(query, top_k=5)   ← use chunks as your context, synthesize yourself

Am I a non-LLM client that needs a complete answer?
  → query_docs(question)
```

---

## Best Practices

### For operators

**Set a persistent token.** A random token changes on every restart, breaking any clients configured with the old value.

```bash
# Generate once and store
python -c "import secrets; print(secrets.token_urlsafe(32))"
# → paste into .env: DRAFT_MCP_TOKEN=<value>
```

**Keep the vector index current.** When new docs are pulled (`scripts/pull.py`), rebuild the index:

```bash
python scripts/index_for_ai.py --profile quick   # fast, good for daily updates
python scripts/index_for_ai.py --profile deep    # thorough, run weekly or after large ingestions
```

**Run behind a reverse proxy for TLS in production.** The server binds to `0.0.0.0:8059` with no TLS. For anything beyond a local network, add nginx or Caddy in front:

```nginx
location /mcp/ {
    proxy_pass http://127.0.0.1:8059/;
}
```

**Use JSON logs for production.** `MCP_LOG_JSON=1` writes machine-parseable JSON lines to `~/.draft/draft-mcp.log`, which can be tailed or forwarded to log aggregators (Loki, CloudWatch, Datadog):

```bash
MCP_LOG_JSON=1 python scripts/serve_mcp.py
# Logs land in ~/.draft/draft-mcp.log automatically
```

**stdio for local, HTTP for remote.** Don't expose the HTTP server on a public interface without a token and ideally TLS. stdio is always safe — it never opens a port.

### For LLM clients / agents

**Call `list_sources` once at session start**, not on every query. Cache the result.

**Use `retrieve_chunks` as the primary tool.** `search_docs` is complementary for keyword recall but has no semantic understanding. `query_docs` adds a second LLM call with no benefit if you're already an LLM.

**Include `repo` and `path` in your citations.** Both fields are present in every chunk. Cite as `repo/path` or link to the doc by path. This is the contract between Draft and its clients.

**Handle `IndexNotReady` gracefully.** If `retrieve_chunks` returns `IndexNotReady`, surface it to the user rather than silently falling back to `search_docs` only — it means the semantic index is missing, which affects answer quality significantly.

---

## Troubleshooting


| Symptom                              | Likely cause                    | Fix                                                                             |
| ------------------------------------ | ------------------------------- | ------------------------------------------------------------------------------- |
| `ImportError: No module named 'mcp'` | SDK not installed               | `pip install "mcp>=1.0"`                                                        |
| `IndexNotReady` on `retrieve_chunks` | Vector store not built          | `python scripts/index_for_ai.py --profile quick`                                |
| `LLMNotConfigured` on `query_docs`   | No provider in `.env`           | Set `DRAFT_LLM_PROVIDER` and matching API key                                   |
| `SourceNotFound` on `get_document`   | Repo name wrong                 | Call `list_sources` to get exact names                                          |
| `401 Unauthorized`                   | Token mismatch                  | Check `DRAFT_MCP_TOKEN` in `.env`; restart server after changing                |
| `doc_count: 0` in `list_sources`     | Docs not pulled                 | Run `python scripts/pull.py`                                                    |
| Empty `retrieve_chunks` results      | Index empty or query too narrow | Try `search_docs` first; rebuild index with `--profile deep`                    |
| Claude Desktop shows no tools        | stdio process not starting      | Check `claude_desktop_config.json` path; run the command manually to see stderr |


