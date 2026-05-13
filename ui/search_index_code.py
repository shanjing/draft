"""
Full-text search index over draft code files using Whoosh.
Index is stored under DRAFT_ROOT/.search_index_code/.
Vault and repo effective roots (from sources.yaml) are indexed; no copy.
"""
import re
from pathlib import Path

from whoosh.fields import ID, TEXT, Schema
from whoosh.index import create_in, open_dir, exists_in
from whoosh.qparser import QueryParser, OrGroup

from lib.gitignore import get_git_ignored_set
from lib.ingest import should_include
from lib.manifest import parse_sources_yaml
from lib.paths import get_effective_repo_root, get_sources_yaml_path, get_vault_root

INDEX_DIR = ".search_index_code"
CONTENT_FIELD = "content"
CODE_EXTENSIONS = (".py", ".sh", ".bash", ".zsh", ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp")


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
    for f in repo_dir.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in CODE_EXTENSIONS:
            continue
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
    """Index code files under vault and each repo's effective root. Returns document count."""
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
            elif repo_root.is_file() and repo_root.suffix.lower() in CODE_EXTENSIONS:
                try:
                    content = repo_root.read_text(encoding="utf-8", errors="replace")
                    writer.add_document(repo=name, path=repo_root.name, content=content)
                    count += 1
                except OSError:
                    pass
    writer.commit()
    return count


def ensure_index(draft_root: Path) -> bool:
    """Build code index if it does not exist. Returns True if index exists (or was built)."""
    idx_path = _index_path(draft_root)
    if not exists_in(str(idx_path)):
        build_index(draft_root)
    return True


def search(
    draft_root: Path,
    q: str,
    limit: int = 50,
    include_content: bool = False,
    path_hints: list[str] | None = None,
) -> list[dict]:
    """
    Full-text search over indexed code files.
    Returns list of {"repo", "path", "snippet"} by default.
    If include_content=True, includes full "content".
    """
    idx_path = _index_path(draft_root)
    if not exists_in(str(idx_path)):
        return []
    q = (q or "").strip()
    if not q:
        return []

    ix = open_dir(str(idx_path))
    parser = QueryParser(CONTENT_FIELD, schema=ix.schema, group=OrGroup.factory(0.9))
    try:
        query = parser.parse(q)
    except Exception:
        return []

    results = []
    with ix.searcher() as searcher:
        seen: set[tuple[str, str]] = set()
        hits = searcher.search(query, limit=limit)
        if not hits:
            terms = re.findall(r"[a-zA-Z0-9_.:/-]{3,}", q)
            if terms:
                try:
                    query = parser.parse(" OR ".join(terms[:10]))
                    hits = searcher.search(query, limit=limit)
                except Exception:
                    hits = []
        for hit in hits:
            content = hit.get(CONTENT_FIELD) or ""
            snippet = content[:200] + ("..." if len(content) >= 200 else "")
            item = {
                "repo": hit["repo"],
                "path": hit["path"],
                "snippet": snippet.strip(),
            }
            if include_content:
                item["content"] = content
            results.append(item)
            seen.add((item["repo"], item["path"]))
        for hint in (path_hints or []):
            try:
                doc = searcher.document(path=hint)
            except Exception:
                doc = None
            if not doc:
                continue
            repo = doc.get("repo", "")
            path = doc.get("path", "")
            if (repo, path) in seen:
                continue
            content = doc.get(CONTENT_FIELD) or ""
            item = {
                "repo": repo,
                "path": path,
                "snippet": (content[:200] + ("..." if len(content) >= 200 else "")).strip(),
            }
            if include_content:
                item["content"] = content
            results.insert(0, item)
            seen.add((repo, path))
        if len(results) > limit:
            results = results[:limit]
    return results

