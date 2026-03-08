"""Tests for OpenTelemetry (OTel) implementation: lib/otel.py, lib/metrics.py, mcp/instrumentation.py.

All tests run without the opentelemetry-sdk installed. We assert the no-op path: get_tracer/get_meter
return no-op implementations, record_* and spans do not raise, and instrument_tool_call works as a
context manager. This matches the design: core Draft and tests run without OTel deps.
"""
import pytest


class TestOtelNoop:
    """lib.otel: get_tracer and get_meter return no-ops when OTel is not configured."""

    def test_get_tracer_returns_object_with_start_as_current_span(self):
        from lib.otel import get_tracer
        tracer = get_tracer("draft", "1.0.0")
        assert hasattr(tracer, "start_as_current_span")
        with tracer.start_as_current_span("test.span") as span:
            assert span is not None

    def test_noop_span_accepts_set_attribute_set_status_record_exception(self):
        from lib.otel import get_tracer
        tracer = get_tracer("draft", "1.0.0")
        with tracer.start_as_current_span("test") as span:
            span.set_attribute("key", "value")
            span.set_attribute("num", 42)
            span.set_status("ok", "done")
            span.record_exception(ValueError("test"))
        # No exception means no-op path works

    def test_get_meter_returns_object_with_create_counter_and_histogram(self):
        from lib.otel import get_meter
        meter = get_meter("draft", "1.0.0")
        assert hasattr(meter, "create_counter")
        assert hasattr(meter, "create_histogram")
        c = meter.create_counter("test.counter", description="x", unit="1")
        h = meter.create_histogram("test.histogram", description="x", unit="ms")
        assert c is not None
        assert h is not None

    def test_noop_counter_add_and_noop_histogram_record_do_not_raise(self):
        from lib.otel import get_meter
        meter = get_meter("draft", "1.0.0")
        c = meter.create_counter("c", description="", unit="1")
        h = meter.create_histogram("h", description="", unit="ms")
        c.add(1)
        c.add(2, {"status": "ok"})
        h.record(1.5)
        h.record(100.0, {"tag": "a"})

    def test_configure_otel_safe_to_call_without_sdk(self):
        """configure_otel() does not raise when SDK is not installed; get_* still return no-ops."""
        import os
        from lib import otel
        prev_tracer, prev_meter = otel._tracer, otel._meter
        prev_log = os.environ.pop("DRAFT_OTEL_METRICS_LOG", None)
        try:
            os.environ["DRAFT_OTEL_METRICS_LOG"] = "stdout"
            otel._tracer = None
            otel._meter = None
            otel.configure_otel(service_name="test")
            tracer = otel.get_tracer("test", "1.0.0")
            meter = otel.get_meter("test", "1.0.0")
            with tracer.start_as_current_span("x") as span:
                span.set_attribute("a", "b")
            meter.create_counter("c", description="", unit="1").add(1)
        finally:
            if prev_log is not None:
                os.environ["DRAFT_OTEL_METRICS_LOG"] = prev_log
            else:
                os.environ.pop("DRAFT_OTEL_METRICS_LOG", None)
            otel._tracer = prev_tracer
            otel._meter = prev_meter
            # Shutdown global providers so PeriodicExportingMetricReader does not export after test (closed stdout).
            try:
                from opentelemetry import metrics, trace
                mp = metrics.get_meter_provider()
                if hasattr(mp, "shutdown"):
                    mp.shutdown()
                tp = trace.get_tracer_provider()
                if hasattr(tp, "shutdown"):
                    tp.shutdown()
            except Exception:
                pass


class TestMetricsRecordFunctions:
    """lib.metrics: all record_* functions run without error (no-op when OTel not configured)."""

    def test_record_rag_request_ok_and_error(self):
        from lib.metrics import record_rag_request
        record_rag_request("ok")
        record_rag_request("error", "NoChunks")
        record_rag_request("error")

    def test_record_retrieval_and_rerank(self):
        from lib.metrics import record_retrieval, record_rerank
        record_retrieval(0.1, "test-embed", 20, 15)
        record_rerank(0.05, "test-reranker")

    def test_record_llm_duration(self):
        from lib.metrics import record_llm_duration
        record_llm_duration(1.5, "ollama", "qwen3:8b", "chat")

    def test_record_llm_tokens(self):
        from lib.metrics import record_llm_tokens
        record_llm_tokens(10, 20, "ollama", "qwen3:8b")

    def test_record_mcp_tool_call_and_duration(self):
        from lib.metrics import record_mcp_tool_call, record_mcp_tool_duration
        record_mcp_tool_call("query_docs", "stdio", "ok")
        record_mcp_tool_call("other", "http", "error")
        record_mcp_tool_duration(50.0, "query_docs")


class TestMcpInstrumentation:
    """mcp.instrumentation: instrument_tool_call context manager and request_id_var."""

    def test_instrument_tool_call_success_path(self):
        from mcp.instrumentation import instrument_tool_call
        with instrument_tool_call("query_docs", "stdio") as span:
            assert span is not None
            span.set_attribute("custom", "value")

    def test_instrument_tool_call_exception_propagates_and_span_used(self):
        from mcp.instrumentation import instrument_tool_call
        with pytest.raises(ValueError, match="expected"):
            with instrument_tool_call("test_tool", "stdio") as span:
                span.set_attribute("mcp.tool", "test_tool")
                raise ValueError("expected")

    def test_request_id_var_default_none(self):
        from mcp.instrumentation import request_id_var
        assert request_id_var.get() is None

    def test_request_id_var_set_and_restore(self):
        from mcp.instrumentation import request_id_var
        token = request_id_var.set("req-123")
        try:
            assert request_id_var.get() == "req-123"
        finally:
            request_id_var.reset(token)
        assert request_id_var.get() is None


class TestAiEngineOtelPath:
    """lib.ai_engine: ask_stream runs with OTel no-op path (no crash; metrics/spans are no-ops)."""

    def test_ask_stream_no_index_completes_with_otel_noop(self, temp_draft_root):
        """ask_stream with no index yields models and error; OTel no-op path is used."""
        from lib.ai_engine import ask_stream
        events = list(ask_stream(temp_draft_root, "test query"))
        types = [e[0] for e in events]
        assert "models" in types
        assert "error" in types

    @pytest.mark.slow
    def test_ask_stream_with_index_no_llm_records_retrieval_rerank_no_crash(self, temp_draft_root):
        """With index, ask_stream runs retrieve and rerank; record_* are no-ops, no exception."""
        from lib.ingest import build_index
        from lib.ai_engine import ask_stream
        build_index(temp_draft_root, verbose=False)
        events = list(ask_stream(temp_draft_root, "Draft document mirror"))
        types = [e[0] for e in events]
        assert "models" in types
        # May yield error if LLM not configured, or text/citations if mock/LLM works
        assert len(events) >= 1
