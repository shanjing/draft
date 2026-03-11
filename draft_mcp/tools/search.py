"""
MCP tools: search_docs (FTS) and retrieve_chunks (semantic).

search_docs   — keyword full-text search via Whoosh; no LLM or vector index needed.
retrieve_chunks — semantic retrieval via ChromaDB embeddings + optional cross-encoder rerank;
                  returns raw ranked chunks for the MCP client (LLM) to synthesize.
"""
from pathlib import Path

from draft_mcp.errors import IndexNotReady
from draft_mcp.instrumentation import instrument_tool_call
from lib.paths import get_draft_home


def _draft_root() -> Path:
    return get_draft_home()


def search_docs(query: str, limit: int = 20, transport: str = "unknown") -> list[dict]:
    """
    Full-text keyword search over all indexed documents.

    Returns [{repo, path, snippet}]. Fast — no LLM or vector store required.
    Use retrieve_chunks for semantic / conceptual search.
    """
    from ui.search_index import ensure_index, search

    draft_root = _draft_root()
    with instrument_tool_call("search_docs", transport):
        ensure_index(draft_root)
        results = search(draft_root, query, limit=limit)
    return results


def retrieve_chunks(
    query: str,
    top_k: int = 5,
    rerank: bool = True,
    transport: str = "unknown",
) -> list[dict]:
    """
    Semantic search: retrieve the top-k most relevant document chunks.

    Returns [{repo, path, heading, text, score, start_line, end_line}].
    Results are ranked by relevance (cross-encoder rerank when rerank=True).
    This is the primary tool for LLM clients — use the returned chunks as context
    for your own synthesis rather than calling query_docs.

    Raises IndexNotReady if the vector store has not been built yet.
    """
    from chromadb.errors import InvalidCollectionException

    from lib.ai_engine import retrieve
    from lib.ai_engine import rerank as rerank_fn

    draft_root = _draft_root()
    with instrument_tool_call("retrieve_chunks", transport):
        try:
            chunks = retrieve(draft_root, query, top_k=max(top_k * 2, 10))
        except (InvalidCollectionException, Exception) as exc:
            if "does not exist" in str(exc) or "collection" in str(exc).lower():
                raise IndexNotReady(
                    "Vector store not built. Run 'python scripts/index_for_ai.py' (requires DRAFT_EMBED_MODEL in .env)"
                    "or use the UI Quick rebuild."
                ) from exc
            raise
        if rerank and chunks:
            chunks = rerank_fn(query, chunks, top_n=top_k)
        else:
            chunks = chunks[:top_k]
    return chunks
