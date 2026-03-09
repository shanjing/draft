"""
MCP error types. Each is raised by a tool and caught by the dispatcher,
which returns a CallToolResult with isError=True and the message string.
"""


class DraftMCPError(Exception):
    """Base class for all Draft MCP errors."""


class IndexNotReady(DraftMCPError):
    """Vector store has not been built yet. Run rebuild_index from the UI or CLI first."""


class SourceNotFound(DraftMCPError):
    """Repo name is not registered in sources.yaml."""


class DocumentNotFound(DraftMCPError):
    """Document path does not exist under the repo root."""


class LLMNotConfigured(DraftMCPError):
    """No LLM provider is configured in .env. query_docs requires an LLM."""
