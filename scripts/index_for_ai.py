#!/usr/bin/env python3
"""
Rebuild the RAG vector index from draft/<repo>/*.md.
Run from the draft repo root. Uses same file exclusions as pull.py.
"""
import os
import sys
import argparse
from pathlib import Path

# Disable Chroma telemetry before any chromadb import
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

# Draft repo root = parent of scripts/
SCRIPT_DIR = Path(__file__).resolve().parent
DRAFT_ROOT = SCRIPT_DIR.parent

# Use project-local cache for HuggingFace/sentence-transformers (avoids ~/.cache)
_cache = DRAFT_ROOT / ".cache" / "huggingface"
_cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("HF_HOME", str(_cache))

# Ensure lib is importable
sys.path.insert(0, str(DRAFT_ROOT))

from lib.ingest import build_index


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild Draft RAG index.")
    parser.add_argument(
        "--profile",
        choices=["quick", "deep"],
        default="quick",
        help="Index profile: quick (default, faster) or deep (higher-quality, nomic).",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose progress output.")
    args = parser.parse_args()
    n = build_index(DRAFT_ROOT, verbose=args.verbose, profile=args.profile)
    print(f"Indexed {n} chunks.")


if __name__ == "__main__":
    main()
