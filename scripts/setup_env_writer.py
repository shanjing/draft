"""
Update .env with LLM provider, model, and API key. Called by setup.sh after model selection.
MarginCall-style: single script that rewrites .env so values are consistent and quoted.
"""
import re
import sys
from pathlib import Path

# Run from repo root
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import click


@click.command()
@click.option("--mode", required=True, type=click.Choice(["ollama", "claude", "gemini", "openai"]))
@click.option("--model", required=True, help="Model name (e.g. qwen3:8b or gemini-2.5-flash).")
@click.option("--api-key", default="", help="API key (required for cloud modes).")
def main(mode: str, model: str, api_key: str) -> None:
    env_path = ROOT / ".env"
    example_path = ROOT / ".env.example"
    if not env_path.exists() and example_path.exists():
        env_path.write_text(example_path.read_text())
    if not env_path.exists():
        env_path.write_text("# Draft Ask (AI) LLM config\n")

    content = env_path.read_text()
    lines = content.splitlines()
    out: list[str] = []
    keys_handled: set[str] = set()

    provider_line = f"DRAFT_LLM_PROVIDER='{mode}'"
    model_line = f"DRAFT_LLM_MODEL='{model}'" if mode != "ollama" else ""
    ollama_line = f"OLLAMA_MODEL='{model}'" if mode == "ollama" else ""
    api_lines: dict[str, str] = {}
    if mode == "claude" and api_key:
        api_lines["ANTHROPIC_API_KEY"] = f"ANTHROPIC_API_KEY='{api_key}'"
    elif mode == "gemini" and api_key:
        api_lines["GEMINI_API_KEY"] = f"GEMINI_API_KEY='{api_key}'"
    elif mode == "openai" and api_key:
        api_lines["OPENAI_API_KEY"] = f"OPENAI_API_KEY='{api_key}'"

    for line in lines:
        if re.match(r"^#?\s*DRAFT_LLM_PROVIDER\s*=", line):
            out.append(provider_line)
            keys_handled.add("DRAFT_LLM_PROVIDER")
            continue
        if re.match(r"^#?\s*DRAFT_LLM_MODEL\s*=", line):
            if model_line:
                out.append(model_line)
            else:
                out.append(line)
            keys_handled.add("DRAFT_LLM_MODEL")
            continue
        if re.match(r"^#?\s*OLLAMA_MODEL\s*=", line):
            if ollama_line:
                out.append(ollama_line)
            else:
                out.append(line)
            keys_handled.add("OLLAMA_MODEL")
            continue
        for key in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"):
            if re.match(rf"^#?\s*{re.escape(key)}\s*=", line):
                out.append(api_lines[key] if key in api_lines else f"# {key}=  # not used for this provider")
                keys_handled.add(key)
                break
        else:
            out.append(line)

    if "DRAFT_LLM_PROVIDER" not in keys_handled:
        out.append(provider_line)
    if "DRAFT_LLM_MODEL" not in keys_handled and model_line:
        out.append(model_line)
    if "OLLAMA_MODEL" not in keys_handled and ollama_line:
        out.append(ollama_line)
    for key, val in api_lines.items():
        if key not in keys_handled:
            out.append(val)

    env_path.write_text("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
