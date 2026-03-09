"""
MCP HTTP transport integration tests.

Requires the MCP server to be running on BASE_URL (default http://127.0.0.1:8059).
Token is read from REPO_ROOT/.env as DRAFT_MCP_TOKEN (same as: grep DRAFT_MCP_TOKEN .env | cut -d= -f2).

Run: pytest tests/test_mcp.py -v
      pytest tests/test_mcp.py -v -m integration   # same; all tests here are integration
Skip when server is down: pytest tests/test_mcp.py -m "not integration"

If tool tests fail with 500 and _raw_body "Internal Server Error", the server process likely
hit an exception (e.g. DRAFT_HOME/sources.yaml or index path). Check ~/.draft/draft-mcp.log
and ensure the server was started from the repo root so .env is loaded, and DRAFT_HOME
(or default ~/.draft) contains sources.yaml and, for retrieve_chunks, a built vector index.
"""
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_URL = "http://127.0.0.1:8059"


def _get_token() -> str | None:
    """Read DRAFT_MCP_TOKEN from REPO_ROOT/.env (same as: grep DRAFT_MCP_TOKEN .env | cut -d= -f2)."""
    env_file = REPO_ROOT / ".env"
    if not env_file.is_file():
        return os.environ.get("DRAFT_MCP_TOKEN") or None
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == "DRAFT_MCP_TOKEN":
            return value.strip().strip("'\"").strip() or None
    return os.environ.get("DRAFT_MCP_TOKEN") or None


def _parse_mcp_response(body: bytes) -> dict:
    """Parse MCP response: either a single JSON object or SSE (data: lines). Last data line wins."""
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        return {}
    # Single JSON object (immediate response)
    if text.startswith("{"):
        return json.loads(text)
    # SSE: take last non-empty data: line
    for line in reversed(text.splitlines()):
        if line.startswith("data:"):
            payload = line[5:].strip()
            if payload:
                return json.loads(payload)
    return {}


def _initialize_session(base_url: str, token: str) -> str | None:
    """POST initialize and return Mcp-Session-Id from response headers (see sre.sh)."""
    url = f"{base_url.rstrip('/')}/mcp"
    payload = {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        },
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {token}",
    }
    req = Request(url, data=data, method="POST", headers=headers)
    try:
        with urlopen(req, timeout=10) as resp:
            # Header name may be normalized; check common variants
            session = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
            return session.strip() if session else None
    except (HTTPError, URLError):
        return None


def _post_mcp(
    base_url: str,
    token: str | None,
    payload: dict,
    session_id: str | None = None,
) -> tuple[int, dict]:
    """POST JSON-RPC to base_url/mcp. Returns (status_code, parsed_response_body)."""
    url = f"{base_url.rstrip('/')}/mcp"
    data = json.dumps(payload).encode("utf-8")
    # MCP Streamable HTTP requires Accept: application/json, text/event-stream (see sre.sh)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    req = Request(url, data=data, method="POST", headers=headers)
    try:
        with urlopen(req, timeout=30) as resp:
            body = resp.read()
            return resp.status, _parse_mcp_response(body)
    except HTTPError as e:
        body = e.read() if e.fp else b""
        try:
            parsed = _parse_mcp_response(body) if body else {}
        except Exception:
            parsed = {}
        # Include raw body when 4xx/5xx so failure messages show what the server returned
        if e.code >= 400:
            if body:
                raw = body.decode("utf-8", errors="replace").strip()
                parsed["_raw_body"] = raw[:1000] if raw else "(empty)"
            else:
                parsed["_raw_body"] = "(empty)"
        return e.code, parsed
    except URLError as e:
        raise pytest.skip(f"MCP server not reachable: {e} (start with: python scripts/serve_mcp.py)")


def _get_health(base_url: str) -> tuple[int, dict]:
    """GET base_url/health. Returns (status_code, parsed JSON)."""
    url = f"{base_url.rstrip('/')}/health"
    req = Request(url, method="GET")
    try:
        with urlopen(req, timeout=10) as resp:
            body = resp.read()
            return resp.status, json.loads(body.decode("utf-8")) if body else {}
    except HTTPError as e:
        body = e.read() if e.fp else b""
        return e.code, json.loads(body.decode("utf-8")) if body else {}
    except URLError:
        raise pytest.skip("MCP server not reachable (start with: python scripts/serve_mcp.py)")


@pytest.fixture(scope="module")
def base_url():
    """Base URL for MCP server (env MCP_BASE_URL or default)."""
    return os.environ.get("MCP_BASE_URL", DEFAULT_BASE_URL)


@pytest.fixture(scope="module")
def token(base_url):
    """Bearer token from .env. Skips tests that need auth if missing."""
    t = _get_token()
    if not t:
        pytest.skip("DRAFT_MCP_TOKEN not set in .env (required for authenticated MCP tests)")
    return t


@pytest.fixture(scope="module")
def mcp_session(base_url: str, token: str):
    """Call initialize and return Mcp-Session-Id (required for tools/call; see sre.sh)."""
    session = _initialize_session(base_url, token)
    if not session:
        pytest.skip("MCP initialize did not return Mcp-Session-Id (server may not support session)")
    return session


# ---- 1. list_sources ----
@pytest.mark.integration
def test_mcp_list_sources(base_url: str, token: str, mcp_session: str):
    """POST tools/call list_sources returns JSON-RPC result with repo list."""
    status, data = _post_mcp(base_url, token, {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "list_sources", "arguments": {}},
    }, session_id=mcp_session)
    assert status == 200, f"expected 200, got {status}: {data}"
    assert data.get("jsonrpc") == "2.0"
    assert "result" in data
    result = data["result"]
    assert result.get("isError") is False, result
    content = result.get("content") or []
    assert isinstance(content, list)
    if content:
        assert content[0].get("type") == "text"
        # text field: JSON string of list (or single object), or server may return list/dict directly
        text = content[0].get("text", "[]")
        if isinstance(text, list):
            sources = text
        elif isinstance(text, dict):
            sources = [text]
        elif isinstance(text, str):
            parsed = json.loads(text)
            sources = parsed if isinstance(parsed, list) else [parsed]
        else:
            sources = []
        assert isinstance(sources, list)


# ---- 2. retrieve_chunks ----
@pytest.mark.integration
def test_mcp_retrieve_chunks(base_url: str, token: str, mcp_session: str):
    """POST tools/call retrieve_chunks returns JSON-RPC result with chunks (or empty)."""
    status, data = _post_mcp(base_url, token, {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "retrieve_chunks",
            "arguments": {
                "query": "RAG pipeline chunking strategy",
                "top_k": 3,
                "rerank": True,
            },
        },
    }, session_id=mcp_session)
    assert status == 200, f"expected 200, got {status}: {data}"
    assert data.get("jsonrpc") == "2.0"
    assert "result" in data
    result = data["result"]
    assert result.get("isError") is False, result
    content = result.get("content") or []
    assert isinstance(content, list)
    if content:
        assert content[0].get("type") == "text"
        text = content[0].get("text", "[]")
        if isinstance(text, list):
            chunks = text
        elif isinstance(text, dict):
            chunks = [text]
        elif isinstance(text, str):
            parsed = json.loads(text)
            chunks = parsed if isinstance(parsed, list) else [parsed]
        else:
            chunks = []
        assert isinstance(chunks, list)


# ---- 3. Auth rejection ----
@pytest.mark.integration
def test_mcp_auth_no_token_returns_401(base_url: str):
    """POST /mcp without Authorization header returns 401."""
    status, _ = _post_mcp(base_url, None, {})
    assert status == 401


@pytest.mark.integration
def test_mcp_auth_wrong_token_returns_401(base_url: str):
    """POST /mcp with wrong Bearer token returns 401."""
    status, _ = _post_mcp(base_url, "wrong-token", {})
    assert status == 401


# ---- 4. Health and other MCP tests ----
@pytest.mark.integration
def test_mcp_health_unauthenticated(base_url: str):
    """GET /health returns 200 and status/llm_ready/index_ready/version (no auth)."""
    status, data = _get_health(base_url)
    assert status == 200, data
    assert data.get("status") == "ok"
    assert "llm_ready" in data
    assert "index_ready" in data
    assert "version" in data


@pytest.mark.integration
def test_mcp_search_docs(base_url: str, token: str, mcp_session: str):
    """POST tools/call search_docs returns JSON-RPC result (Whoosh full-text search)."""
    status, data = _post_mcp(base_url, token, {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "search_docs",
            "arguments": {"query": "RAG", "limit": 5},
        },
    }, session_id=mcp_session)
    assert status == 200, f"expected 200, got {status}: {data}"
    assert data.get("jsonrpc") == "2.0"
    assert "result" in data
    result = data["result"]
    assert result.get("isError") is False, result
    content = result.get("content") or []
    assert isinstance(content, list)


@pytest.mark.integration
def test_mcp_list_documents_requires_repo(base_url: str, token: str, mcp_session: str):
    """POST tools/call list_documents with a repo returns JSON-RPC result or error."""
    # Use first repo from list_sources if we had it; here we use "draft" as common name.
    status, data = _post_mcp(base_url, token, {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "list_documents", "arguments": {"repo": "draft"}},
    }, session_id=mcp_session)
    assert status == 200, f"expected 200, got {status}: {data}"
    assert data.get("jsonrpc") == "2.0"
    # Either result with content or error (e.g. repo not in sources)
    assert "result" in data or "error" in data
