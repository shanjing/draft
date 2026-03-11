"""
MCP tool: query_docs — RAG + LLM synthesis.

Consumes ask_stream() internally (non-streaming) and returns a complete answer
with citations. Intended for non-LLM clients or cases where the caller wants a
pre-synthesized answer. LLM clients should prefer retrieve_chunks instead.
"""
from pathlib import Path

from draft_mcp.errors import IndexNotReady, LLMNotConfigured
from draft_mcp.instrumentation import instrument_tool_call
from lib.paths import get_draft_home


def _draft_root() -> Path:
    return get_draft_home()


def query_docs(question: str, transport: str = "unknown") -> dict:
    """
    Answer a question using RAG over all indexed documents.

    Retrieves relevant chunks, reranks them, then synthesizes an answer via the
    configured LLM. Returns {answer, citations}.

    Requires: a built vector index (run rebuild from UI or CLI) and a configured
    LLM provider in .env (DRAFT_LLM_PROVIDER + matching API key).

    LLM clients (Claude, GPT, etc.) should use retrieve_chunks instead — it returns
    the raw ranked chunks so the client can do its own synthesis, avoiding double
    inference and preserving conversation context.
    """
    from lib.ai_engine import ask_stream, llm_ready

    draft_root = _draft_root()
    with instrument_tool_call("query_docs", transport):
        if not llm_ready(draft_root):
            raise LLMNotConfigured(
                "No LLM provider configured. Set DRAFT_LLM_PROVIDER and the matching "
                "API key in .env, then restart the MCP server."
            )

        answer_parts: list[str] = []
        citations: list[dict] = []

        for kind, payload in ask_stream(draft_root, question):
            if kind == "text":
                answer_parts.append(payload)
            elif kind == "citations":
                citations = payload
            elif kind == "error":
                # Surface LLM/retrieval errors as a clean MCP error
                if "collection" in payload.lower() or "index" in payload.lower():
                    raise IndexNotReady(
                        "Vector store not ready. Run 'python scripts/index_for_ai.py' (requires DRAFT_EMBED_MODEL in .env)"
                        "or use the UI Quick rebuild."
                    )
                raise RuntimeError(f"query_docs failed: {payload}")

    return {"answer": "".join(answer_parts), "citations": citations}
