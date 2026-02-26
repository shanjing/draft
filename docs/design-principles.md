## Design Principles

**Data Sources and operations:**

1. **`github`** — remote GitHub repo: user provides a URL, draft will:
   a. Clone the repo to `~/.draft/.clones/<name>` (first time) or `git pull` (subsequent pulls)
   b. Record in `sources.yaml` with `source` (the URL) and `url`
   c. Supports Pull operation (draft owns the clone)

2. **`local_dir`** — local directory (no `url`): user provides a path to a local folder, draft will:
   a. Create an entry in `sources.yaml` with the path as `source`
   b. Read in-place (no copy, no pull) — draft is a reader, not a repo manager

3. **`local_git`** — local git repo (has `url`): same as `local_dir` but the `url` field is populated (backfilled from the repo's `origin` remote on first pull):
   a. Read in-place; `url` is display/linking metadata only
   b. No `git pull` — the repo owner manages their own git state; running pull on an actively developed repo is disruptive and out of scope for draft

4. **`local_file`** — local single `.md` file: user provides a path to a single file, draft will:
   a. Create an entry in `sources.yaml` with the file path as `source`
   b. Read in-place; no copy, no pull operation
   c. File appears as a single-file repo in the UI tree, search, and RAG index

5. **`x_post`** — X/Twitter post URL: user provides an `x.com/` or `twitter.com/` URL, draft will:
   a. Record in `sources.yaml` with the URL as `source`
   b. Fetch and store post content under `~/.draft/.x_posts/<name>/` (separate from vault; kept apart so x_post-specific operations can be added later)
   c. Does not require a recurring Pull operation (fetched once)
   *(Fetching is not yet implemented; the path infrastructure is in place.)*

6. **`vault`** — user-managed upload area: `~/.draft/vault/`, populated via UI upload or `save-from-doc`. Not pulled from any external source.

---

**AI vector indexing:**
The index (`lib/ingest.py`) must handle all source types: directories are walked recursively; single files (`local_file`) are chunked directly.

**Search:**
The full-text search index (`ui/search_index.py`) must handle all source types the same way.

---

**Architectural answers:**

- `sources.yaml` **is** the metadata layer. It is the single source of truth for what draft tracks. `draft_config.json` (the manifest) is a derived cache — always regenerated from `sources.yaml`; never hand-edited.
- Draft reads content in-place wherever possible. The only data draft copies/creates under `~/.draft/` is:
  - `.clones/<name>/` — git clones of GitHub sources (draft owns these)
  - `.x_posts/<name>/` — fetched X post content (draft owns these)
  - `vault/` — user uploads
  - `.search_index/` and `.vector_store/` — derived indexes (always rebuildable)

**Core principles:**

1. Draft is a reader, not a repo manager. It does not run `git pull` on repos the user is actively developing.
2. Keep data in-place wherever possible to avoid content drift and reduce duplication.
3. `sources.yaml` knows each content source and its allowed operations; the source type taxonomy encodes those rules.
