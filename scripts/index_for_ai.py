#!/usr/bin/env python3
"""
Rebuild the RAG vector index from draft/<repo>/*.md.
Run from the draft repo root. Uses same file exclusions as pull.py.
"""
import os
import sys
from pathlib import Path

# Draft repo root = parent of scripts/
SCRIPT_DIR = Path(__file__).resolve().parent
DRAFT_ROOT = SCRIPT_DIR.parent

# Use project-local cache for HuggingFace/sentence-transformers (avoids ~/.cache)
_cache = DRAFT_ROOT / ".cache" / "huggingface"
_cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("TRANSFORMERS_CACHE", str(_cache))
os.environ.setdefault("HF_HOME", str(_cache))

# Ensure lib is importable
sys.path.insert(0, str(DRAFT_ROOT))

from lib.ingest import build_index


def main() -> None:
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    n = build_index(DRAFT_ROOT, verbose=verbose)
    print(f"Indexed {n} chunks.")


if __name__ == "__main__":
    main()
