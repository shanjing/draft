"""
Single instrumentation point for MCP tool calls.

Workflow: The tool dispatcher wraps each call in instrument_tool_call(tool, transport).
Inside we start an OTel span (mcp.tool), set attributes (tool, transport, request_id),
then in finally we record metrics (record_mcp_tool_call, record_mcp_tool_duration) and
emit one JSON log line. Request ID comes from request_id_var; set it before entering
(e.g. from Mcp-Session-Id when HTTP server exists).

TODO: When MCP HTTP server is implemented, add middleware that sets request_id_var from
the Mcp-Session-Id header so HTTP transport has a non-None request_id.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import time

from lib.log import get_logger

log = get_logger(__name__)

# Optional request ID for this MCP request. Set by transport layer so spans and logs can carry it.
request_id_var: ContextVar[str | None] = ContextVar("mcp_request_id", default=None)


@contextmanager
def instrument_tool_call(tool: str, transport: str):
    """
    Context manager for one MCP tool call. Starts a span, records metrics and
    one JSON log line on exit. Set request_id_var before entering.
    """
    from lib.metrics import record_mcp_tool_call, record_mcp_tool_duration
    from lib.otel import StatusCode, get_tracer

    tracer = get_tracer("draft-mcp", "1.0.0")
    request_id = request_id_var.get()
    t0 = time.perf_counter()
    status = "ok"
    error_type = None
    message = ""

    # OTel span for this tool call. Attributes: mcp.tool, mcp.transport, request_id (if set).
    with tracer.start_as_current_span("mcp.tool") as span:
        span.set_attribute("mcp.tool", tool)
        span.set_attribute("mcp.transport", transport)
        if request_id:
            span.set_attribute("request_id", request_id)
        try:
            yield span
        except Exception as e:
            status = "error"
            error_type = type(e).__name__
            message = str(e)
            span.record_exception(e)
            span.set_status(StatusCode.ERROR, message[:200])
            raise
        finally:
            # Always record MCP metrics and one JSON log line (duration, status, error_type).
            duration_ms = (time.perf_counter() - t0) * 1000.0
            record_mcp_tool_call(tool, transport, status)
            record_mcp_tool_duration(duration_ms, tool)
            log.info(
                message or "ok",
                extra={
                    "request_id": request_id,
                    "tool": tool,
                    "transport": transport,
                    "duration_ms": round(duration_ms, 2),
                    "status": status,
                    "error_type": error_type,
                },
            )
