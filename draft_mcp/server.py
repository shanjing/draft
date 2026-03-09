"""
Draft MCP server.

Registers all tools, resources, and prompts via FastMCP decorator API.
HTTP transport: Starlette app from FastMCP.streamable_http_app() with Bearer
token auth middleware added on top. stdio transport: runs directly (no auth).

Entrypoints called by scripts/serve_mcp.py:
    run_stdio()   — stdio transport for Claude Desktop / local use
    run_http()    — Streamable HTTP on port 8059 with auth middleware
"""
from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from draft_mcp.errors import DraftMCPError
from draft_mcp.instrumentation import instrument_tool_call  # noqa: F401 (re-exported for tools)
from draft_mcp.tools.ask import query_docs as _query_docs
from draft_mcp.tools.documents import get_document as _get_document
from draft_mcp.tools.documents import list_documents as _list_documents
from draft_mcp.tools.search import retrieve_chunks as _retrieve_chunks
from draft_mcp.tools.search import search_docs as _search_docs
from draft_mcp.tools.sources import list_sources as _list_sources

mcp = FastMCP(
    "draft",
    instructions=(
        "Draft is a document knowledge base with full-text and semantic search. "
        "Use search_docs for fast keyword lookup. "
        "Use retrieve_chunks for semantic search — it returns ranked document chunks "
        "that you should synthesize into your answer. "
        "Use query_docs only if you want Draft's LLM to answer for you (non-LLM clients). "
        "Always cite sources by repo and path."
    ),
)

_TRANSPORT_HTTP = "http"
_TRANSPORT_STDIO = "stdio"

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def search_docs(query: str, limit: int = 20) -> list[dict]:
    """
    Full-text keyword search over all indexed documents.

    Returns a list of {repo, path, snippet} matching the query.
    Fast — no LLM or vector store required. Prefer retrieve_chunks for
    semantic / conceptual queries.
    """
    try:
        return _search_docs(query, limit=limit)
    except DraftMCPError:
        raise
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc


@mcp.tool()
def retrieve_chunks(query: str, top_k: int = 5, rerank: bool = True) -> list[dict]:
    """
    Semantic search: retrieve the top-k most relevant document chunks.

    Returns [{repo, path, heading, text, score, start_line, end_line}].
    Results are cross-encoder reranked by default. This is the primary tool
    for LLM clients — use the chunks as context to write your own answer.
    Requires a built vector index (run rebuild from the UI or CLI if missing).
    """
    try:
        return _retrieve_chunks(query, top_k=top_k, rerank=rerank)
    except DraftMCPError:
        raise
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc


@mcp.tool()
def get_document(repo: str, path: str) -> dict:
    """
    Return the full content of a specific document.

    repo: repository name (from list_sources).
    path: relative path within the repo, e.g. "docs/design.md".
    Returns {repo, path, content, size_bytes}.
    """
    try:
        return _get_document(repo, path)
    except DraftMCPError:
        raise
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc


@mcp.tool()
def list_documents(repo: str) -> list[dict]:
    """
    List all .md documents in a repository.

    repo: repository name (from list_sources).
    Returns [{path, size_bytes}] sorted by path.
    """
    try:
        return _list_documents(repo)
    except DraftMCPError:
        raise
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc


@mcp.tool()
def list_sources() -> list[dict]:
    """
    List all tracked document repositories.

    Returns [{name, source, url, doc_count}].
    Use the name field when calling get_document or list_documents.
    """
    try:
        return _list_sources()
    except DraftMCPError:
        raise
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc


@mcp.tool()
def query_docs(question: str) -> dict:
    """
    Answer a question using Draft's RAG pipeline (retrieval + LLM synthesis).

    Returns {answer, citations}. Requires a built vector index and a configured
    LLM in .env (DRAFT_LLM_PROVIDER + API key).

    Note: LLM clients (Claude, GPT, etc.) should use retrieve_chunks instead —
    it avoids double inference and lets you synthesize within your own context.
    Use query_docs when you want a complete, self-contained answer from Draft.
    """
    try:
        return _query_docs(question)
    except DraftMCPError:
        raise
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


@mcp.resource("draft://sources")
def sources_resource() -> str:
    """All tracked repositories as JSON."""
    sources = _list_sources()
    return json.dumps(sources, indent=2)


@mcp.resource("draft://doc/{repo}/{path}")
def document_resource(repo: str, path: str) -> str:
    """Raw content of a specific document. Allows direct reference without a tool call."""
    result = _get_document(repo, path)
    return result["content"]


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------


@mcp.prompt()
def answer_from_docs() -> str:
    """Workflow prompt for answering questions from Draft documents."""
    return (
        "You have access to Draft, a document knowledge base. Follow this workflow:\n\n"
        "1. Call list_sources() to see what repositories are available.\n"
        "2. Call retrieve_chunks(query, top_k=5) with your question as the query. "
        "The returned chunks are semantically ranked — use them as your primary context.\n"
        "3. If you need the full text of a specific document, call get_document(repo, path).\n"
        "4. For keyword lookup, use search_docs(query).\n"
        "5. Synthesize your answer from the retrieved content and always cite sources "
        "by repo and path.\n\n"
        "Only call query_docs() if you want Draft's own LLM to answer instead of you."
    )


# ---------------------------------------------------------------------------
# Entrypoints
# ---------------------------------------------------------------------------


def run_stdio() -> None:
    """Run with stdio transport (Claude Desktop, local trusted use). No auth."""
    mcp.run(transport="stdio")


def run_http(port: int = 8059) -> None:
    """
    Run with Streamable HTTP transport on the given port.
    Wraps the FastMCP Starlette app with Bearer token auth middleware and adds
    a /health endpoint.
    """
    import contextlib

    import uvicorn
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route

    from draft_mcp.auth import BearerTokenMiddleware, get_token
    from lib.ai_engine import llm_ready
    from lib.paths import get_draft_home, get_vector_store_root

    # Force token generation now so it prints before uvicorn starts
    get_token()

    async def health(request: Request) -> JSONResponse:
        draft_root = get_draft_home()
        vector_store = get_vector_store_root()
        return JSONResponse({
            "status": "ok",
            "llm_ready": llm_ready(draft_root),
            "index_ready": vector_store.exists() and any(vector_store.iterdir()),
            "version": "1.0",
        })

    # Build Starlette app: mount the FastMCP ASGI app + health route.
    # The outer app must own the lifespan so the session manager's task group
    # is initialized before any requests arrive. Mounting mcp_asgi alone does
    # not trigger its inner lifespan in Starlette.
    mcp_asgi = mcp.streamable_http_app()

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        async with mcp.session_manager.run():
            yield

    app = Starlette(
        routes=[
            Route("/health", health),
            Mount("/", app=mcp_asgi),
        ],
        lifespan=lifespan,
    )
    app.add_middleware(BearerTokenMiddleware)

    uvicorn.run(app, host="0.0.0.0", port=port)
