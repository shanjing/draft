"""
MCP tools: list_sources.

Returns all registered repos with doc counts.
Pull and rebuild operations are CLI/UI only — not exposed via MCP.
"""
from pathlib import Path

from draft_mcp.instrumentation import instrument_tool_call
from lib.paths import get_draft_home


def _draft_root() -> Path:
    return get_draft_home()


def list_sources(transport: str = "unknown") -> list[dict]:
    """
    List all tracked document sources.

    Returns [{name, source, url, doc_count}].
    doc_count is the number of .md files currently available under each repo root.
    """
    from lib.manifest import parse_sources_yaml
    from lib.paths import get_sources_yaml_path, get_effective_repo_root
    from lib.ingest import should_include

    with instrument_tool_call("list_sources", transport):
        try:
            draft_root = _draft_root()
            sources_yaml = get_sources_yaml_path()
            if not sources_yaml.exists():
                return []
            sources = parse_sources_yaml(sources_yaml)
        except Exception:
            return []
        result = []
        for name, info in sources.items():
            try:
                source_val = info.get("source", "")
                root = get_effective_repo_root(name, source_val, draft_root)
                doc_count = 0
                if root.is_dir():
                    for f in root.rglob("*.md"):
                        try:
                            rel = str(f.relative_to(root))
                            if should_include(rel):
                                doc_count += 1
                        except ValueError:
                            continue
                result.append({
                    "name": name,
                    "source": source_val,
                    "url": info.get("url"),
                    "doc_count": doc_count,
                })
            except Exception:
                result.append({
                    "name": name,
                    "source": info.get("source", ""),
                    "url": info.get("url"),
                    "doc_count": 0,
                })
    return result
