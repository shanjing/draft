#!/usr/bin/env python3
"""Launch the Draft UI (document tree browser). Run from repo root."""
import sys
from pathlib import Path

import click

# Ensure draft root is on path and is cwd
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Load .env so ANTHROPIC_API_KEY and OLLAMA_MODEL work without exporting
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

DEFAULT_PORT = 8058


@click.command()
@click.option("-p", "--port", type=int, default=DEFAULT_PORT, help=f"Port to bind (default: {DEFAULT_PORT})")
def main(port):
    import uvicorn
    uvicorn.run(
        "ui.app:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
