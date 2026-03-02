#!/usr/bin/env python3
"""
Ask a question over your draft docs (RAG). Run from the draft repo root.
Requires AI index (scripts/index_for_ai.py) and LLM config (.env).
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

# Use project-local cache for HuggingFace (cross-encoder)
_cache = DRAFT_ROOT / ".cache" / "huggingface"
_cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("HF_HOME", str(_cache))

# Ensure lib is importable
sys.path.insert(0, str(DRAFT_ROOT))

# Load .env from repo root
try:
    from dotenv import load_dotenv
    load_dotenv(DRAFT_ROOT / ".env")
except ImportError:
    pass
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from lib.ai_engine import ask_stream, llm_ready
from lib.log import configure_cli

#mainly for testing and debugging
@click.command(help="Ask a question over your draft docs (RAG).")
@click.option("-q", "--query", required=True, help="Question to ask.")
@click.option("--debug", is_flag=True, help="Log embed_model, cross-encoder, and rerank scores.")
@click.option("--show-prompt", is_flag=True, help="Print the final prompt (system + user) sent to the LLM after encoding and reranking.")
def main(query: str, debug: bool, show_prompt: bool) -> None:
    if not query.strip():
        click.echo("Error: query cannot be empty.", err=True)
        sys.exit(1)

    if not llm_ready(DRAFT_ROOT):
        click.echo("Error: LLM not configured. Set OLLAMA_MODEL or API keys in .env.", err=True)
        sys.exit(1)

    if debug:
        configure_cli()

    full_text = ""
    citations = []
    error_msg = None

    for kind, payload in ask_stream(DRAFT_ROOT, query.strip(), debug=debug, show_prompt=show_prompt):
        if kind == "models":
            click.echo("Models: embed=%s, encoder=%s, LLM=%s" % (
                payload.get("embed_model", "?"),
                payload.get("cross_encoder_model", "?"),
                payload.get("llm_model", "?"),
            ))
            click.echo()
        elif kind == "prompt":
            click.echo("--- Final prompt to LLM ---")
            click.echo("\n[System]\n%s" % (payload.get("system", ""),))
            click.echo("\n[User]\n%s" % (payload.get("user", ""),))
            click.echo("\n---\n")
        elif kind == "text":
            full_text += payload
        elif kind == "citations":
            citations = payload
        elif kind == "error":
            error_msg = payload

    if error_msg:
        click.echo(error_msg, err=True)
        sys.exit(1)

    click.echo(full_text or "(No answer.)")
    if citations:
        click.echo()
        click.echo("---")
        for i, c in enumerate(citations, 1):
            label = f"{c.get('repo', '')}/{c.get('path', '')}"
            if c.get("heading"):
                label += f" — {c.get('heading', '')}"
            if c.get("start_line") is not None and c.get("end_line") is not None:
                label += f" (lines {c['start_line']}–{c['end_line']})"
            if c.get("score") is not None:
                label += f" [score: {c['score']}]"
            click.echo(f"  {i}. {label}")


if __name__ == "__main__":
    main()
