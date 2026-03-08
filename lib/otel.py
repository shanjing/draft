"""
OpenTelemetry setup for Draft.

This module provides the tracer and meter used for RAG and MCP instrumentation.
OTel is optional: when the SDK is not installed, get_tracer() and get_meter() return
no-op implementations so call sites do not need "if otel_enabled" checks.

Setup flow:
  - Entry points (ui/app.py lifespan, scripts/ask.py, scripts/serve_mcp.py) call
    configure_otel() at startup by default (service name from OTEL_SERVICE_NAME or a default).
  - configure_otel() initializes TracerProvider and MeterProvider. If OTEL_EXPORTER_OTLP_ENDPOINT
    is set, it uses OTLP HTTP exporter; otherwise console exporter. Console metrics default to
    ~/.draft/otel_metrics.log (or DRAFT_HOME/otel_metrics.log). Set DRAFT_OTEL_METRICS_LOG=stdout
    to use stdout, or a path for another file.
  - After that, get_tracer() and get_meter() return real providers. Instrumentation
    in ai_engine.py and mcp/instrumentation.py uses them to create spans and record metrics.
  - On exit, entry points call shutdown_otel() so the meter provider force_flush() and shutdown()
    run, avoiding dropping the final metric batch (PeriodicExportingMetricReader exports every 10s).
"""
from contextlib import contextmanager
from typing import Any

# No-op implementations: same method names as real OTel objects so call sites work without guards.


class _NoopSpan:
    def set_status(self, status: Any, message: str = "") -> None:
        pass

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def record_exception(self, exception: BaseException) -> None:
        pass


class _NoopTracer:
    @contextmanager
    def start_as_current_span(self, name: str, **kwargs: Any):
        yield _NoopSpan()


class _NoopMeter:
    def create_counter(self, name: str, *args: Any, **kwargs: Any) -> Any:
        return _NoopCounter()

    def create_histogram(self, name: str, *args: Any, **kwargs: Any) -> Any:
        return _NoopHistogram()


class _NoopCounter:
    def add(self, value: int | float, attributes: dict[str, str] | None = None) -> None:
        pass


class _NoopHistogram:
    def record(self, value: int | float, attributes: dict[str, str] | None = None) -> None:
        pass


_noop_tracer = _NoopTracer()
_noop_meter = _NoopMeter()

# Set by configure_otel(); None until then so get_tracer/get_meter return no-ops.
_tracer: Any = None
_meter: Any = None

# Stored so shutdown_otel() can force_flush and shutdown; avoids dropping the final metric batch on exit.
_tracer_provider: Any = None
_meter_provider: Any = None

# Kept open so ConsoleMetricExporter can write; default output is ~/.draft/otel_metrics.log.
_otel_metrics_file: Any = None

try:
    from opentelemetry.trace import StatusCode
except ImportError:
    class StatusCode:
        ERROR = "error"
        OK = "ok"

# OTel tracer for traces
def get_tracer(name: str, version: str = "") -> Any:
    """Return the configured tracer, or no-op tracer if OTel is not configured."""
    return _tracer if _tracer is not None else _noop_tracer

# OTel meter for metrics
def get_meter(name: str, version: str = "") -> Any:
    """Return the configured meter, or no-op meter if OTel is not configured."""
    return _meter if _meter is not None else _noop_meter

# OTel configure
def configure_otel(
    service_name: str | None = None,
    otlp_endpoint: str | None = None,
) -> None:
    """
    Initialize TracerProvider and MeterProvider. Call at app/script startup.
    If otlp_endpoint is set (or OTEL_EXPORTER_OTLP_ENDPOINT env var), uses OTLP exporter;
    otherwise uses console exporter. On ImportError (SDK not installed): no-op.
    """
    global _tracer, _meter, _tracer_provider, _meter_provider, _otel_metrics_file
    import os
    import sys
    endpoint = otlp_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    name = service_name or os.environ.get("OTEL_SERVICE_NAME", "draft")
    try:
        from opentelemetry import trace, metrics
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SpanExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader, ConsoleMetricExporter, MetricExporter
        from opentelemetry.sdk.resources import Resource
    except ImportError:
        _tracer = None
        _meter = None
        _tracer_provider = None
        _meter_provider = None
        return

    resource = Resource.create({"service.name": name})

    # Tracer: spans go to OTLP or console. Used by RAG (rag.ask, rag.retrieval, etc.) and MCP (mcp.tool).
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            span_exporter: SpanExporter = OTLPSpanExporter(endpoint=endpoint.rstrip("/") + "/v1/traces")
        except ImportError:
            span_exporter = ConsoleSpanExporter()
    else:
        span_exporter = ConsoleSpanExporter()
    _tracer_provider = TracerProvider(resource=resource)
    _tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(_tracer_provider)
    _tracer = trace.get_tracer(name, "1.0.0")

    # Meter: histograms and counters for RAG and MCP. Exported periodically (e.g. every 10s).
    # Console output: default is ~/.draft/otel_metrics.log; set DRAFT_OTEL_METRICS_LOG=stdout for stdout, or a path.
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
            metric_exporter: MetricExporter = OTLPMetricExporter(endpoint=endpoint.rstrip("/") + "/v1/metrics")
        except ImportError:
            metric_exporter = ConsoleMetricExporter()
    else:
        _raw = os.environ.get("DRAFT_OTEL_METRICS_LOG")
        if _raw is not None and (_raw.strip().lower() == "stdout" or _raw.strip() == ""):
            _out = sys.stdout
        else:
            _draft_home = os.environ.get("DRAFT_HOME", os.path.expanduser("~/.draft"))
            _path = (_raw or "").strip() or os.path.join(_draft_home, "otel_metrics.log")
            os.makedirs(os.path.dirname(_path), exist_ok=True)
            _otel_metrics_file = open(_path, "a", encoding="utf-8")
            _out = _otel_metrics_file
        metric_exporter = ConsoleMetricExporter(out=_out)
    reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=10_000)
    _meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(_meter_provider)
    _meter = metrics.get_meter(name, "1.0.0")


def shutdown_otel() -> None:
    """
    Flush and shutdown the global TracerProvider and MeterProvider so the final metric batch
    is exported (PeriodicExportingMetricReader otherwise drops it on process exit). Call from
    entry-point cleanup: ui/app.py lifespan shutdown, scripts/ask.py finally, scripts/serve_mcp.py atexit.
    No-op if OTel was never configured or SDK not installed.
    """
    global _tracer_provider, _meter_provider
    try:
        if _meter_provider is not None and hasattr(_meter_provider, "force_flush"):
            _meter_provider.force_flush(5_000)
        if _meter_provider is not None and hasattr(_meter_provider, "shutdown"):
            _meter_provider.shutdown()
        if _tracer_provider is not None and hasattr(_tracer_provider, "force_flush"):
            _tracer_provider.force_flush(5_000)
        if _tracer_provider is not None and hasattr(_tracer_provider, "shutdown"):
            _tracer_provider.shutdown()
    except Exception:
        pass
    _tracer_provider = None
    _meter_provider = None
