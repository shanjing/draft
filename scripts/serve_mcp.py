#!/usr/bin/env python3
"""
MCP server entrypoint. Configures JSON logging and OTel when requested; then runs the MCP server.
Use --stdio for stdio transport or default to Streamable HTTP. --log-json or MCP_LOG_JSON=1 for JSON logs.
"""
import atexit
import os
import sys
from pathlib import Path

import click

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

DEFAULT_PORT = 8059


@click.command(help="Draft MCP server: stdio (Claude Desktop) or Streamable HTTP.")
@click.option("--stdio", is_flag=True, help="Use stdio transport (no auth).")
@click.option("--log-json", is_flag=True, help="Emit JSON log lines (or set MCP_LOG_JSON=1).")
@click.option("-p", "--port", type=int, default=DEFAULT_PORT, help=f"HTTP port when not --stdio (default: {DEFAULT_PORT}).")
def main(stdio: bool, log_json: bool, port: int) -> None:
    use_json_log = log_json or os.environ.get("MCP_LOG_JSON")
    if use_json_log:
        from lib.log import configure_json
        configure_json()

    # File log: always write to ~/.draft/draft-mcp.log in addition to stderr.
    import logging
    from lib.log import _JsonFormatter
    from lib.paths import get_draft_home
    _log_path = get_draft_home() / "draft-mcp.log"
    _fh = logging.FileHandler(_log_path)
    _fh.setFormatter(
        _JsonFormatter() if use_json_log
        else logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    logging.getLogger().addHandler(_fh)

    # OTel: initialize by default; shutdown_otel at exit so final metric batch is exported.
    try:
        from lib.otel import configure_otel, shutdown_otel
        configure_otel(service_name=os.environ.get("OTEL_SERVICE_NAME") or "draft-mcp")
        atexit.register(shutdown_otel)
    except Exception:
        pass

    if stdio:
        from draft_mcp.server import run_stdio
        run_stdio()
    else:
        from draft_mcp.server import run_http
        run_http(port=port)


if __name__ == "__main__":
    main()
