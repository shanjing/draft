"""
Global logging utility for Draft.
Use get_logger(__name__) in modules; configure at app/script entry points.
"""
import logging

# Root logger name for Draft; all lib.* and draft.* loggers propagate here.
_ROOT = "draft"

# Convenience logger for app-level messages (backward compat).
logger = logging.getLogger(_ROOT)


def get_logger(name: str) -> logging.Logger:
    """Return a logger for the given module. Use __name__ from the caller."""
    return logging.getLogger(name)


def configure(
    level: int = logging.INFO,
    *,
    format: str | None = None,
) -> None:
    """
    Configure logging for Draft. Configures the root logger so all modules work.
    Call at app startup (e.g. ui/app.py) or script entry.
    """
    root = logging.getLogger()
    if root.handlers:
        return
    fmt = format or "%(levelname)s [draft] %(message)s"
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(fmt))
    root.addHandler(handler)
    root.setLevel(level)


def configure_cli(level: int = logging.INFO) -> None:
    """
    Configure logging for CLI scripts. Uses plain format (message only)
    for clean subprocess output (e.g. index_for_ai -v shown in system console).
    """
    configure(level=level, format="%(message)s")


_JSON_EXTRA_KEYS = {"request_id", "tool", "transport", "duration_ms", "status", "error_type"}


class _JsonFormatter(logging.Formatter):
    """Format LogRecord as a single JSON line. Includes message, levelname, ts, and extra keys."""

    def format(self, record: logging.LogRecord) -> str:
        import json
        out = {
            "ts": record.created,
            "levelname": record.levelname,
            "message": record.getMessage(),
        }
        for key in _JSON_EXTRA_KEYS:
            if hasattr(record, key):
                out[key] = getattr(record, key)
        return json.dumps(out) + "\n"


def configure_json(level: int = logging.INFO) -> None:
    """
    Configure logging to emit one JSON object per record (for MCP and other machine-readable logs).
    Uses a minimal JSON formatter: message, levelname, and a fixed set of extra keys
    (request_id, tool, transport, duration_ms, status, error_type).
    Call when --log-json or MCP_LOG_JSON=1.
    """
    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level)
