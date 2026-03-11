#!/usr/bin/env python3
"""
Rebuild the RAG vector index from draft/<repo>/*.md.
Run from the draft repo root. Uses same file exclusions as pull.py.
"""
import os
import sys
from pathlib import Path

import click

# Disable Chroma telemetry before any chromadb import
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

# Draft repo root = parent of scripts/
SCRIPT_DIR = Path(__file__).resolve().parent
DRAFT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(DRAFT_ROOT))

# HF cache under DRAFT_HOME so models persist in Docker and avoid re-downloads
from lib.paths import get_hf_cache_root
_cache = get_hf_cache_root()
_cache.mkdir(parents=True, exist_ok=True)
os.environ["HF_HOME"] = str(_cache)

# Load .env for DRAFT_EMBED_MODEL override
try:
    from dotenv import load_dotenv
    load_dotenv(DRAFT_ROOT / ".env")
except ImportError:
    pass
# Allow Hugging Face to download embed/encoder models from .env when not cached
os.environ["HF_HUB_OFFLINE"] = "0"

from lib.ingest import build_index
from lib.log import configure_cli


@click.command(help="Rebuild Draft RAG index using DRAFT_EMBED_MODEL from .env.")
@click.option("-v", "--verbose", is_flag=True, help="Verbose progress output.")
def main(verbose: bool) -> None:
    if verbose:
        configure_cli()
        env_embed = os.environ.get("DRAFT_EMBED_MODEL", "").strip().strip("'\"")
        click.echo(f"embed_model: {env_embed or '(not set)'}")
    n = build_index(DRAFT_ROOT, verbose=verbose)
    click.echo(f"Indexed {n} chunks.")


if __name__ == "__main__":
    main()
