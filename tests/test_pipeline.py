#!/usr/bin/env python3
"""
Test pipeline: build RAG index and run retrieval. Supports 4 model pairs:
  default (d) - sentence-transformers quick profile
  G (Gold)    - 8b embed + 0.6B reranker (Ollama, best balance)
  L (8B+8B)   - 8b embed + 8B reranker (Ollama, highest quality)
  S (0.6B+0.6B) - 0.6b embed + 0.6B reranker (Ollama, fastest)
Uses sources.yaml (DRAFT_HOME). Run from the draft repo root.
"""
import os
import sys
from pathlib import Path

import click

# Disable Chroma telemetry before any chromadb import
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

# Draft repo root = parent of tests/
SCRIPT_DIR = Path(__file__).resolve().parent
DRAFT_ROOT = SCRIPT_DIR.parent

# Ensure lib is importable
sys.path.insert(0, str(DRAFT_ROOT))

# Use project-local cache for HuggingFace/sentence-transformers
_cache = DRAFT_ROOT / ".cache" / "huggingface"
_cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("HF_HOME", str(_cache))

# Load .env (override=False so explicit env vars in main() take precedence)
try:
    from dotenv import load_dotenv
    load_dotenv(DRAFT_ROOT / ".env", override=False)
except ImportError:
    pass
os.environ.setdefault("HF_HUB_OFFLINE", "1")

# Model pairs: (embed, reranker, use_ollama). default uses profile's embed.
DEFAULT_CROSS_ENCODER = "cross-encoder/ms-marco-MiniLM-L-6-v2"
PAIRS = {
    "G": ("qwen3-embedding:8b", "dengcao/Qwen3-Reranker-0.6B:Q8_0", True),
    "L": ("qwen3-embedding:8b", "dengcao/Qwen3-Reranker-8B:Q3_K_M", True),
    "S": ("qwen3-embedding:0.6b", "dengcao/Qwen3-Reranker-0.6B:Q8_0", True),
}
# Profile embed models for default pair
PROFILE_EMBEDS = {
    "quick": "sentence-transformers/all-MiniLM-L6-v2",
    "deep": "nomic-ai/nomic-embed-text-v1.5",
}


def _set_pair_env(pair: str, profile: str = "quick") -> tuple[str, str, bool]:
    """Set env vars for the chosen pair. Returns (embed, reranker, use_ollama)."""
    pk = pair.upper() if pair.upper() in ("G", "L", "S") else pair.lower()
    if pk in ("G", "L", "S"):
        embed, reranker, use_ollama = PAIRS[pk]
    else:
        embed = PROFILE_EMBEDS.get(profile.lower(), PROFILE_EMBEDS["quick"])
        reranker = DEFAULT_CROSS_ENCODER
        use_ollama = False
    os.environ["DRAFT_EMBED_MODEL"] = embed
    os.environ["DRAFT_CROSS_ENCODER_MODEL"] = reranker
    if use_ollama:
        os.environ["DRAFT_EMBED_PROVIDER"] = "ollama"
    else:
        os.environ.pop("DRAFT_EMBED_PROVIDER", None)
    os.environ.pop("DRAFT_RERANK_PROVIDER", None)
    return embed, reranker, use_ollama


@click.command(help="Test RAG pipeline: build index and run retrieval.")
@click.option(
    "-p", "--pair",
    type=click.Choice(["default", "d", "G", "L", "S"], case_sensitive=False),
    default="default",
    help="Model pair: default/d (sentence-transformers), G (Gold 8b+0.6B), L (8B+8B), S (0.6B+0.6B).",
)
@click.option(
    "-q", "--query",
    default="What is this project about?",
    help="Question to ask for retrieval test.",
)
@click.option(
    "--rebuild",
    is_flag=True,
    help="Rebuild index from sources.yaml before retrieval (default: use existing index).",
)
@click.option(
    "--profile",
    type=click.Choice(["quick", "deep"], case_sensitive=False),
    default="quick",
    help="Index profile when building (quick or deep).",
)
@click.option(
    "-v", "--verbose",
    is_flag=True,
    help="Show detailed build and rerank output.",
)
def main(
    pair: str,
    query: str,
    rebuild: bool,
    profile: str,
    verbose: bool,
) -> None:
    # Set env before any lib imports so ingest/ai_engine see correct values
    embed_model, cross_encoder, use_ollama = _set_pair_env(pair, profile)
    # Reload .env with override=False so our vars above are not overwritten
    try:
        from dotenv import load_dotenv
        load_dotenv(DRAFT_ROOT / ".env", override=False)
    except ImportError:
        pass

    if verbose:
        from lib.log import configure_cli
        configure_cli()

    pk = pair.upper() if pair.upper() in ("G", "L", "S") else pair.lower()
    pair_label = {"default": "default (sentence-transformers)", "d": "default", "G": "Gold (8b+0.6B)", "L": "8B+8B", "S": "0.6B+0.6B"}.get(pk, pair)
    click.echo(f"--- Test pipeline: pair={pair_label} ---")
    if use_ollama:
        click.echo(f"  embed_model:      {embed_model} (Ollama, no download)")
    else:
        click.echo(f"  embed_model:      {embed_model}")
    click.echo(f"  cross_encoder:    {cross_encoder}")
    click.echo(f"  query:            {query}")
    click.echo(f"  profile:          {profile}")
    click.echo()

    # Step 1: Build index from sources.yaml (only when --rebuild)
    if rebuild:
        from lib.ingest import build_index

        click.echo("--- Building index from sources.yaml ---")
        if verbose:
            click.echo(f"  Collecting chunks, embedding with {embed_model}...")
        n = build_index(DRAFT_ROOT, verbose=verbose, profile=profile)
        click.echo(f"  Indexed {n} chunks.")
        click.echo()
    else:
        click.echo("--- Using existing index (pass --rebuild to rebuild) ---")
        click.echo()

    # Step 2: Run retrieval (ask_stream triggers retrieve + rerank)
    from lib.ai_engine import ask_stream, llm_ready

    if not llm_ready(DRAFT_ROOT):
        click.echo("Warning: LLM not configured. Retrieval/rerank will run but no answer.", err=True)
        click.echo("Set OLLAMA_MODEL or API keys in .env for full pipeline.", err=True)
        click.echo()

    click.echo("--- Retrieval + rerank ---")
    if verbose:
        click.echo(f"  Retrieving top-k, reranking with {cross_encoder}...")
    click.echo()

    full_text = ""
    citations = []
    error_msg = None

    for kind, payload in ask_stream(DRAFT_ROOT, query.strip(), debug=verbose):
        if kind == "models":
            if verbose:
                click.echo(f"  embed_model (from index): {payload.get('embed_model', '?')}")
                click.echo(f"  cross_encoder_model:      {payload.get('cross_encoder_model', '?')}")
                click.echo(f"  llm_model:               {payload.get('llm_model', '?')}")
                click.echo()
        elif kind == "text":
            full_text += payload
        elif kind == "citations":
            citations = payload
        elif kind == "error":
            error_msg = payload

    if error_msg:
        click.echo(error_msg, err=True)
        sys.exit(1)

    click.echo("--- Answer ---")
    click.echo(full_text or "(No answer.)")
    if citations:
        click.echo()
        click.echo("--- Citations (with rerank scores) ---")
        for i, c in enumerate(citations, 1):
            label = f"{c.get('repo', '')}/{c.get('path', '')}"
            if c.get("heading"):
                label += f" — {c.get('heading', '')}"
            if c.get("start_line") is not None and c.get("end_line") is not None:
                label += f" (lines {c['start_line']}–{c['end_line']})"
            if c.get("score") is not None:
                label += f" [score: {c['score']}]"
            click.echo(f"  {i}. {label}")
    click.echo()
    click.echo("--- Done ---")


if __name__ == "__main__":
    main()
