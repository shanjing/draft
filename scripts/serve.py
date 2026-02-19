#!/usr/bin/env python3
"""Launch the Draft UI (document tree browser). Run from repo root."""
import sys
from pathlib import Path

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

def main():
    import uvicorn
    uvicorn.run(
        "ui.app:app",
        host="0.0.0.0",
        port=8058,
        reload=False,
    )

if __name__ == "__main__":
    main()
