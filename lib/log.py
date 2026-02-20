"""
Project logger for Draft. Use for server-side logging; system console in the UI
shows a curated subset (e.g. from pull --quiet and API responses).
"""
import logging

logger = logging.getLogger("draft")


def configure(level: int = logging.INFO) -> None:
    """Configure the draft logger if not already configured."""
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s [draft] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(level)
