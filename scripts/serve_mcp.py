#!/usr/bin/env python3
"""
MCP server entrypoint. Configures JSON logging and OTel when requested; then runs the MCP server.
Use --stdio for stdio transport or default to Streamable HTTP. --log-json or MCP_LOG_JSON=1 for JSON logs.
"""
import atexit
import os
import sys
from pathlib import Path

# Draft repo root
SCRIPT_DIR = Path(__file__).resolve().parent
DRAFT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(DRAFT_ROOT))

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(DRAFT_ROOT / ".env")
except ImportError:
    pass


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="Draft MCP server")
    p.add_argument("--stdio", action="store_true", help="Use stdio transport")
    p.add_argument("--log-json", action="store_true", help="Emit JSON log lines (or set MCP_LOG_JSON=1)")
    args = p.parse_args()

    if args.log_json or os.environ.get("MCP_LOG_JSON"):
        from lib.log import configure_json
        configure_json()

    # OTel: initialize by default; shutdown_otel at exit so final metric batch is exported.
    try:
        from lib.otel import configure_otel, shutdown_otel
        configure_otel(service_name=os.environ.get("OTEL_SERVICE_NAME") or "draft-mcp")
        atexit.register(shutdown_otel)
    except Exception:
        pass

    # MCP server implementation not yet present; observability is wired for when it is.
    try:
        from mcp import server  # noqa: F401
    except ImportError:
        sys.stderr.write("MCP server (mcp.server) not implemented yet. Observability (OTel, JSON logs) is configured.\n")
        sys.exit(0)

    # When mcp.server exists, run it with args.stdio
    if args.stdio:
        from mcp.server import run_stdio
        run_stdio()
    else:
        from mcp.server import run_http
        run_http()


if __name__ == "__main__":
    main()
