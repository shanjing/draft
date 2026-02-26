# Core Implementations

This document describes the finalized design for draft's content management layer.

---

## Source Type Taxonomy

Six source types are recognized. The `source_type` field in `draft_config.json` (and in `_source_type()` in `lib/manifest.py`) encodes how draft handles each source.

| Type | `source` value | Storage under `DRAFT_HOME` | Copy/pull policy | Pull operation |
|---|---|---|---|---|
| `vault` | `~/.draft/vault/` | `vault/` | User uploads; append-only | None |
| `github` | `https://github.com/owner/repo` | `.clones/<name>/` | draft owns the clone | `git clone` / `git pull` |
| `local_dir` | Path to a directory (no git remote) | None (read in-place) | No copy | None |
| `local_git` | Path to a git repo directory | None (read in-place) | No copy | None (`url` is display metadata only) |
| `local_file` | Path to a single `.md` file | None (read in-place) | No copy | None |
| `x_post` | `https://x.com/...` or `https://twitter.com/...` | `.x_posts/<name>/` | draft fetches once | None (fetch-on-add, not recurring) |

---

## Storage Layout under `DRAFT_HOME` (`~/.draft/`)

```
~/.draft/
├── sources.yaml          # source of truth — tracked sources
├── vault/                # user uploads (vault source type)
├── .clones/              # git clones of GitHub sources
│   └── <name>/
├── .x_posts/             # fetched X/Twitter post content (future)
│   └── <name>/
├── .search_index/        # Whoosh FTS index (derived; rebuildable)
└── .vector_store/        # ChromaDB vector index (derived; rebuildable)
```

Draft root (repo) also has:
```
<draft_root>/
└── .draft/
    └── draft_config.json # manifest (derived from sources.yaml; never hand-edited)
```

---

## `get_effective_repo_root()` — the unified path abstraction

`lib/paths.get_effective_repo_root(name, source, draft_root)` is the single function all layers use to resolve "where do I read content for this source?":

- **GitHub**: returns `~/.draft/.clones/<name>` (always a directory)
- **Local dir / local git**: returns the resolved absolute path (always a directory)
- **Local file**: returns the resolved absolute path to the file (a file, not a directory)
- **x_post / vault**: callers use `get_x_posts_root()` / `get_vault_root()` directly

Callers must check `.is_dir()` or `.is_file()` on the returned path. The function never creates paths; it returns a path that may not exist.

---

## `sources.yaml` → manifest flow

```
sources.yaml  →  lib/manifest.build_manifest()  →  .draft/draft_config.json
```

- `sources.yaml` is written by `pull.py -a` (add) and the UI add/remove endpoints.
- `lib/manifest.update_manifest()` is called after every pull and source add/remove.
- `draft_config.json` records `source_type`, `source`, optional `url`, and `resolved_path` (if the path/clone currently exists on disk).
- `draft_config.json` is a cache for tooling; the authoritative state is always `sources.yaml`.

Type detection (`_source_type()`):
1. Name == `vault` → `vault`
2. `github.com` in source → `github`
3. `x.com/` or `twitter.com/` in source → `x_post`
4. Source path has `.md` suffix → `local_file`
5. Has `url` → `local_git`
6. Otherwise → `local_dir`

---

## Operations matrix per source type

| Operation | vault | github | local_dir | local_git | local_file | x_post |
|---|---|---|---|---|---|---|
| Add to sources.yaml | via upload/UI | `pull -a <url>` | `pull -a <path>` | `pull -a <path>` | `pull -a <file>` | UI (future) |
| Pull | — | `git pull` | echo "up to date" | echo "up to date" | echo "up to date" | — |
| URL backfill | — | — | — | yes (from git remote) | — | — |
| FTS index | `_add_repo_to_writer` | `_add_repo_to_writer` | `_add_repo_to_writer` | `_add_repo_to_writer` | single-file branch | dir walk (future) |
| RAG index | dir walk | dir walk | dir walk | dir walk | single-file branch | dir walk (future) |
| UI tree | `_repo_tree_entry` | `_repo_tree_entry` | `_repo_tree_entry` | `_repo_tree_entry` | `_repo_file_entry` | `_repo_tree_entry` (future) |
| Remove | — | deletes `.clones/<name>` | sources.yaml only | sources.yaml only | sources.yaml only | deletes `.x_posts/<name>` |

---

## Key implementation files

| File | Role |
|---|---|
| `lib/paths.py` | All DRAFT_HOME paths; `get_effective_repo_root()` |
| `lib/manifest.py` | `_source_type()`, `_resolved_path()`, `build_manifest()`, `update_manifest()` |
| `scripts/pull.py` | Add/pull sources; url backfill; GitHub clone/pull |
| `lib/ingest.py` | RAG chunking; `collect_chunks()` iterates all sources |
| `ui/search_index.py` | Whoosh FTS; `build_index()` iterates all sources |
| `ui/app.py` | FastAPI; tree building, doc serving, add/remove source endpoints |
| `lib/verify_sources.py` | Validates sources.yaml before manifest update |

---

## x_post path infrastructure

`lib/paths.X_POSTS_DIR = ".x_posts"` and `get_x_posts_root()` are in place. Fetching X post content is not yet implemented. When implemented:

1. `scripts/pull.py` or a dedicated fetch script fetches post content to `~/.draft/.x_posts/<name>/`
2. `_resolved_path()` for `x_post` already resolves to that directory
3. The search and RAG indexes will pick it up via the standard dir-walk path (the content directory will be a normal directory of `.md` files)
