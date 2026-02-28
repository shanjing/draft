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
