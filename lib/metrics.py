"""
Draft observability metrics. Single source of truth for RAG and MCP metric instruments.

Instrumentation workflow:
  - ai_engine.ask_stream() and mcp/instrumentation.py call the record_* functions below.
  - Each record_* uses a _get_* helper to obtain the instrument. The helper calls get_meter()
    at first use, so instruments are created only after configure_otel() has run (e.g. in UI
    lifespan or ask.py main). That way we never capture the no-op meter at import time.
  - Metrics use GenAI semantic conventions (gen_ai.*) where defined; RAG and MCP use custom names.

When opentelemetry-sdk is not installed, get_meter() returns a no-op meter and all record_* are no-ops.

SLIs (Service Level Indicators) derived from these metrics:
- RAG availability: rate(rag.requests{status="ok"}) / rate(rag.requests)
- RAG p99 latency: histogram quantile 0.99 on gen_ai.client.operation.duration
- Token consumption trend: sum of gen_ai.client.token.usage over time
"""
from __future__ import annotations

from lib.otel import get_meter

# Lazy-initialized instruments. get_meter() is called at first use so OTel is configured (e.g. by startup) before we create instruments.
_rag_requests: object = None
_rag_retrieval_duration: object = None
_rag_rerank_duration: object = None
_rag_chunks_retrieved: object = None
_gen_ai_token_usage: object = None
_gen_ai_operation_duration: object = None
_mcp_tool_calls: object = None
_mcp_tool_duration: object = None


# --- RAG instruments (counters and histograms). Unit ms for latency; "1" for counts. ---


# OTel counter for total RAG requests
def _get_rag_requests():
    global _rag_requests
    if _rag_requests is None:
        meter = get_meter("draft", "1.0.0")
        _rag_requests = meter.create_counter(name="rag.requests", description="Total RAG requests", unit="1")
    return _rag_requests

# OTel histogram for retrieval latency (ms)
def _get_rag_retrieval_duration():
    global _rag_retrieval_duration
    if _rag_retrieval_duration is None:
        meter = get_meter("draft", "1.0.0")
        _rag_retrieval_duration = meter.create_histogram(name="rag.retrieval.duration", description="Retrieval latency", unit="ms")
    return _rag_retrieval_duration

# OTel histogram for rerank latency (ms)
def _get_rag_rerank_duration():
    global _rag_rerank_duration
    if _rag_rerank_duration is None:
        meter = get_meter("draft", "1.0.0")
        _rag_rerank_duration = meter.create_histogram(name="rag.rerank.duration", description="Rerank latency", unit="ms")
    return _rag_rerank_duration

# OTel histogram for number of chunks retrieved
def _get_rag_chunks_retrieved():
    global _rag_chunks_retrieved
    if _rag_chunks_retrieved is None:
        meter = get_meter("draft", "1.0.0")
        _rag_chunks_retrieved = meter.create_histogram(name="rag.chunks.retrieved", description="Number of chunks retrieved", unit="1")
    return _rag_chunks_retrieved


# --- GenAI semconv instruments (unit "s" for duration per spec). ---

# OTel histogram for LLM token usage (GenAI semconv)
def _get_gen_ai_token_usage():
    global _gen_ai_token_usage
    if _gen_ai_token_usage is None:
        meter = get_meter("draft", "1.0.0")
        _gen_ai_token_usage = meter.create_histogram(name="gen_ai.client.token.usage", description="LLM token usage (GenAI semconv)", unit="1")
    return _gen_ai_token_usage

# OTel histogram for LLM operation duration (GenAI semconv)
def _get_gen_ai_operation_duration():
    global _gen_ai_operation_duration
    if _gen_ai_operation_duration is None:
        meter = get_meter("draft", "1.0.0")
        _gen_ai_operation_duration = meter.create_histogram(
            name="gen_ai.client.operation.duration", description="LLM operation duration (GenAI semconv)", unit="s"
        )
    return _gen_ai_operation_duration


# --- MCP instruments. ---


# OTel counter for MCP tool calls
def _get_mcp_tool_calls():
    global _mcp_tool_calls
    if _mcp_tool_calls is None:
        meter = get_meter("draft", "1.0.0")
        _mcp_tool_calls = meter.create_counter(name="mcp.tool.calls", description="MCP tool invocations", unit="1")
    return _mcp_tool_calls

# OTel histogram for MCP tool call duration (ms)
def _get_mcp_tool_duration():
    global _mcp_tool_duration
    if _mcp_tool_duration is None:
        meter = get_meter("draft", "1.0.0")
        _mcp_tool_duration = meter.create_histogram(name="mcp.tool.duration", description="MCP tool call duration", unit="ms")
    return _mcp_tool_duration


# OTel counter for RAG requests
def record_rag_request(status: str, error_type: str | None = None) -> None:
    """Record one RAG request (counter). status: 'ok' | 'error'. error_type: optional string for errors."""
    attrs = {"status": status}
    if error_type:
        attrs["error_type"] = error_type
    _get_rag_requests().add(1, attrs)

# OTel histogram for retrieval latency (ms) and chunk count
def record_retrieval(duration_sec: float, embed_model: str, top_k: int, chunk_count: int) -> None:
    """Record retrieval stage: latency (ms) and chunk count. Called from ask_stream after retrieve()."""
    duration_ms = duration_sec * 1000.0
    _get_rag_retrieval_duration().record(duration_ms, {"rag.embed_model": embed_model, "rag.top_k": str(top_k)})
    _get_rag_chunks_retrieved().record(chunk_count, {})

# OTel histogram for rerank latency (ms)
def record_rerank(duration_sec: float, reranker_model: str) -> None:
    """Record rerank stage latency (ms). Called from ask_stream after rerank()."""
    duration_ms = duration_sec * 1000.0
    _get_rag_rerank_duration().record(duration_ms, {"rag.reranker_model": reranker_model})


# Not yet called from ai_engine: streaming providers do not surface token counts. Deferred until provider-specific handling exists (e.g. get_final_message().usage, stream.usage).
def record_llm_tokens(
    input_tokens: int,
    output_tokens: int,
    system: str,
    model: str,
) -> None:
    """Record LLM token usage (GenAI semconv: gen_ai.system, gen_ai.request.model, gen_ai.token.type)."""
    attrs_base = {"gen_ai.system": system, "gen_ai.request.model": model}
    token_usage = _get_gen_ai_token_usage()
    if input_tokens > 0:
        token_usage.record(input_tokens, {**attrs_base, "gen_ai.token.type": "input"})
    if output_tokens > 0:
        token_usage.record(output_tokens, {**attrs_base, "gen_ai.token.type": "output"})

# OTel histogram via GenAI semconv for LLM operation duration (unit: seconds).
def record_llm_duration(duration_sec: float, system: str, model: str, operation: str = "chat") -> None:
    """Record LLM operation duration. GenAI semconv: unit is seconds. Called from ask_stream in finally after streaming."""
    _get_gen_ai_operation_duration().record(
        duration_sec,
        {"gen_ai.system": system, "gen_ai.request.model": model, "gen_ai.operation.name": operation},
    )

# OTel counter for MCP tool calls
def record_mcp_tool_call(tool: str, transport: str, status: str) -> None:
    """Record one MCP tool call. tool: name; transport: 'http' | 'stdio'; status: 'ok' | 'error'."""
    _get_mcp_tool_calls().add(1, {"mcp.tool": tool, "mcp.transport": transport, "status": status})

# OTel histogram for MCP tool call duration (ms)
def record_mcp_tool_duration(duration_ms: float, tool: str) -> None:
    """Record MCP tool call duration."""
    _get_mcp_tool_duration().record(duration_ms, {"mcp.tool": tool})
