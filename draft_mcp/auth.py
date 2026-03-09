"""
Bearer token middleware for the MCP HTTP transport.

Reads DRAFT_MCP_TOKEN from the environment. If unset, generates a random token
on startup and prints it once to stderr. Requests without a valid token receive
401 before any tool logic runs. stdio transport bypasses this entirely.
"""
import os
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_TOKEN: str | None = None


def get_token() -> str:
    """Return the active Bearer token, generating one if DRAFT_MCP_TOKEN is unset."""
    global _TOKEN
    if _TOKEN is None:
        env_token = os.environ.get("DRAFT_MCP_TOKEN", "").strip()
        if env_token:
            _TOKEN = env_token
        else:
            _TOKEN = secrets.token_urlsafe(32)
            import sys
            sys.stderr.write(
                f"[draft-mcp] No DRAFT_MCP_TOKEN set. Generated token for this session:\n"
                f"  {_TOKEN}\n"
                f"Set DRAFT_MCP_TOKEN in .env to make it persistent.\n"
            )
    return _TOKEN


class BearerTokenMiddleware(BaseHTTPMiddleware):
    """Require Authorization: Bearer <token> on all HTTP MCP requests."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Health endpoint is unauthenticated
        if request.url.path == "/health":
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return Response("Unauthorized", status_code=401)
        token = auth[len("Bearer "):]
        if not secrets.compare_digest(token, get_token()):
            return Response("Unauthorized", status_code=401)
        return await call_next(request)
