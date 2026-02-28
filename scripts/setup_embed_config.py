"""
Write DRAFT_EMBED_MODEL, DRAFT_CROSS_ENCODER_MODEL, DRAFT_EMBED_PROVIDER, DRAFT_RERANK_PROVIDER to .env.
Called by setup.sh after embedding/cross-encoder model selection.
"""
import re
import sys
from pathlib import Path

# Run from repo root
ROOT = Path(__file__).resolve().parent.parent


def write_embed_config(
    embed_model: str,
    cross_encoder_model: str,
    *,
    embed_provider: str = "",
) -> None:
    """Update .env with embed and cross-encoder model lines."""
    env_path = ROOT / ".env"
    example_path = ROOT / ".env.example"
    if not env_path.exists() and example_path.exists():
        env_path.write_text(example_path.read_text())
    if not env_path.exists():
        env_path.write_text("# Draft RAG: embedding and cross-encoder models\n")

    content = env_path.read_text()
    lines = content.splitlines()
    out: list[str] = []
    embed_handled = cross_handled = provider_handled = rerank_provider_handled = hf_offline_handled = False

    embed_line = f"DRAFT_EMBED_MODEL='{embed_model}'"
    cross_line = f"DRAFT_CROSS_ENCODER_MODEL='{cross_encoder_model}'"
    provider_line = f"DRAFT_EMBED_PROVIDER='{embed_provider}'" if embed_provider else ""
    rerank_provider_line = (
        "DRAFT_RERANK_PROVIDER='ollama'" if embed_provider == "ollama" else ""
    )

    for line in lines:
        if re.match(r"^#?\s*DRAFT_EMBED_MODEL\s*=", line):
            out.append(embed_line)
            embed_handled = True
            continue
        if re.match(r"^#?\s*DRAFT_CROSS_ENCODER_MODEL\s*=", line):
            out.append(cross_line)
            cross_handled = True
            continue
        if re.match(r"^#?\s*DRAFT_EMBED_PROVIDER\s*=", line):
            if provider_line:
                out.append(provider_line)
            else:
                out.append(line)
            provider_handled = True
            continue
        if re.match(r"^#?\s*DRAFT_RERANK_PROVIDER\s*=", line):
            if rerank_provider_line:
                out.append(rerank_provider_line)
            # else: omit line (remove DRAFT_RERANK_PROVIDER when not ollama)
            rerank_provider_handled = True
            continue
        if re.match(r"^#?\s*HF_HUB_OFFLINE\s*=", line):
            out.append("HF_HUB_OFFLINE=1")
            hf_offline_handled = True
            continue
        out.append(line)

    if not hf_offline_handled:
        out.append("HF_HUB_OFFLINE=1")
    if not embed_handled:
        out.append(embed_line)
    if not cross_handled:
        out.append(cross_line)
    if embed_provider and not provider_handled:
        out.append(provider_line)
    if rerank_provider_line and not rerank_provider_handled:
        out.append(rerank_provider_line)

    env_path.write_text("\n".join(out) + "\n")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: setup_embed_config.py <embed_model> <cross_encoder_model> [--provider openai]", file=sys.stderr)
        sys.exit(1)
    provider = ""
    if len(sys.argv) >= 5 and sys.argv[3] == "--provider":
        provider = sys.argv[4]
    write_embed_config(sys.argv[1], sys.argv[2], embed_provider=provider)
