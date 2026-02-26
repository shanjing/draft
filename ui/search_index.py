"""
Full-text search index over draft .md files using Whoosh.
Index is stored under DRAFT_ROOT/.search_index/.
Vault and repo effective roots (from sources.yaml) are indexed; no copy.
"""
import re
from pathlib import Path

from whoosh.fields import ID, TEXT, Schema
from whoosh.index import create_in, open_dir, exists_in
from whoosh.qparser import QueryParser

from lib.gitignore import get_git_ignored_set
from lib.ingest import should_include
from lib.manifest import parse_sources_yaml
from lib.paths import get_effective_repo_root, get_sources_yaml_path, get_vault_root

INDEX_DIR = ".search_index"
CONTENT_FIELD = "content"


def _index_path(draft_root: Path) -> Path:
    return draft_root / INDEX_DIR


def get_schema() -> Schema:
    return Schema(
        repo=ID(stored=True),
        path=ID(stored=True),
        content=TEXT(stored=True),
    )


def _add_repo_to_writer(writer, repo_name: str, repo_dir: Path) -> int:
    candidates: list[tuple[str, Path]] = []
    for f in repo_dir.rglob("*.md"):
        try:
            rel = f.relative_to(repo_dir)
            path_str = rel.as_posix()
        except ValueError:
            continue
        if not should_include(path_str):
            continue
        candidates.append((path_str, f))
    ignored = get_git_ignored_set(repo_dir, [p for p, _ in candidates])
    count = 0
    for path_str, f in candidates:
        if path_str in ignored:
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        writer.add_document(repo=repo_name, path=path_str, content=content)
        count += 1
    return count


def build_index(draft_root: Path) -> int:
    """Index .md under vault and each repo's effective root (sources.yaml). Returns document count."""
    idx_path = _index_path(draft_root)
    idx_path.mkdir(parents=True, exist_ok=True)
    schema = get_schema()
    if exists_in(str(idx_path)):
        import shutil
        shutil.rmtree(idx_path)
        idx_path.mkdir(parents=True, exist_ok=True)
    ix = create_in(str(idx_path), schema)
    writer = ix.writer()
    count = 0
    vault_dir = get_vault_root()
    if vault_dir.is_dir():
        count += _add_repo_to_writer(writer, "vault", vault_dir)
    sources_yaml = get_sources_yaml_path()
    if sources_yaml.is_file():
        repos = parse_sources_yaml(sources_yaml)
        for name, repo in sorted(repos.items()):
            if name == "vault":
                continue
            source = (repo.get("source") or "").strip()
            if not source:
                continue
            repo_root = get_effective_repo_root(name, source, draft_root)
            if repo_root.is_dir():
                count += _add_repo_to_writer(writer, name, repo_root)
            elif repo_root.is_file() and repo_root.suffix == ".md":
                try:
                    content = repo_root.read_text(encoding="utf-8", errors="replace")
                    writer.add_document(repo=name, path=repo_root.name, content=content)
                    count += 1
                except OSError:
                    pass
    writer.commit()
    return count


def ensure_index(draft_root: Path) -> bool:
    """Build index if it does not exist. Returns True if index exists (or was built)."""
    idx_path = _index_path(draft_root)
    if not exists_in(str(idx_path)):
        build_index(draft_root)
    return True


def search(draft_root: Path, q: str, limit: int = 50) -> list[dict]:
    """
    Full-text search over indexed .md files.
    Returns list of {"repo": str, "path": str, "snippet": str}.
    """
    idx_path = _index_path(draft_root)
    if not exists_in(str(idx_path)):
        return []
    q = (q or "").strip()
    if not q:
        return []

    ix = open_dir(str(idx_path))
    parser = QueryParser(CONTENT_FIELD, schema=ix.schema)
    try:
        query = parser.parse(q)
    except Exception:
        return []

    # Strip Whoosh highlight HTML tags for plain-text snippets
    _tag_re = re.compile(r"<[^>]+>")

    results = []
    with ix.searcher() as searcher:
        hits = searcher.search(query, limit=limit)
        for hit in hits:
            snippet = hit.highlights(CONTENT_FIELD, top=1) or ""
            if not snippet:
                content = (hit.get(CONTENT_FIELD) or "")[:200]
                snippet = content + ("…" if len(content) >= 200 else "")
            else:
                snippet = _tag_re.sub("", snippet)
            results.append({
                "repo": hit["repo"],
                "path": hit["path"],
                "snippet": snippet.strip(),
            })
    return results


def reindex_if_exists(draft_root: Path) -> int | None:
    """Rebuild index if it exists. Returns doc count or None if index did not exist."""
    idx_path = _index_path(draft_root)
    if not exists_in(str(idx_path)):
        return None
    return build_index(draft_root)
