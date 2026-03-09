"""
MCP tools: get_document and list_documents.

get_document    — return the full content of a specific document.
list_documents  — list all indexed .md files in a repo.
"""
from pathlib import Path

from draft_mcp.errors import DocumentNotFound, SourceNotFound
from draft_mcp.instrumentation import instrument_tool_call
from lib.paths import get_draft_home


def _draft_root() -> Path:
    return get_draft_home()


def _resolve_repo_root(repo: str) -> Path:
    from lib.manifest import parse_sources_yaml
    from lib.paths import get_sources_yaml_path, get_effective_repo_root

    sources = parse_sources_yaml(get_sources_yaml_path())
    if repo not in sources:
        raise SourceNotFound(f"Repo '{repo}' not in sources.yaml. Call list_sources to see available repos.")
    info = sources[repo]
    return get_effective_repo_root(repo, info["source"], _draft_root())


def get_document(repo: str, path: str, transport: str = "unknown") -> dict:
    """
    Return the full content of a document.

    repo: repo name as returned by list_sources.
    path: relative path within the repo (e.g. "docs/design.md").
    Returns {repo, path, content, size_bytes}.
    """
    with instrument_tool_call("get_document", transport):
        root = _resolve_repo_root(repo)
        file_path = (root / path).resolve()
        # Guard against path traversal outside the repo root
        if not str(file_path).startswith(str(root.resolve())):
            raise DocumentNotFound(f"Path '{path}' is outside repo root.")
        if not file_path.exists():
            raise DocumentNotFound(f"'{path}' not found in repo '{repo}'.")
        content = file_path.read_text(encoding="utf-8", errors="replace")
    return {"repo": repo, "path": path, "content": content, "size_bytes": len(content.encode())}


def list_documents(repo: str, transport: str = "unknown") -> list[dict]:
    """
    List all .md documents in a repo.

    Returns [{path, size_bytes}] sorted by path.
    """
    from lib.ingest import should_include

    with instrument_tool_call("list_documents", transport):
        root = _resolve_repo_root(repo)
        if not root.is_dir():
            raise SourceNotFound(f"Repo root for '{repo}' does not exist or is not a directory.")
        docs = []
        for file in sorted(root.rglob("*.md")):
            rel = file.relative_to(root)
            if should_include(str(rel)):
                docs.append({"path": str(rel), "size_bytes": file.stat().st_size})
    return docs
