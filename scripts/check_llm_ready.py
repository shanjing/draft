#!/usr/bin/env python3
"""Exit 0 if a valid LLM is configured (local or cloud with API key), else 1. Used by setup.sh and callers."""
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DRAFT_ROOT = SCRIPT_DIR.parent
if str(DRAFT_ROOT) not in sys.path:
    sys.path.insert(0, str(DRAFT_ROOT))

from lib.ai_engine import llm_ready

if __name__ == "__main__":
    sys.exit(0 if llm_ready(DRAFT_ROOT) else 1)
