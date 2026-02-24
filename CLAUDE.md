# draft

This repo stores private documents (tech details, drafts) extracted from other repositories. Each source repo has its own top-level subdirectory. Only **`.md`** files are mirrored; directory structure is preserved.

**Tracked repos** are listed in **`sources.yaml`** at **`~/.draft/sources.yaml`** (or **`$DRAFT_HOME/sources.yaml`**; default **`DRAFT_HOME`** is **`~/.draft`**). The repo ships **`sources.example.yaml`**; run **`./setup.sh`** or start the app to create **`~/.draft/sources.yaml`** from it if missing. In **`sources.yaml`**: each key is the subdirectory name under **`~/.draft/.doc_sources/`**; each value has **`source`** (path or GitHub URL) and optionally a single **`url`** (git origin). Vault lives at **`~/.draft/vault/`**. For local paths that are git repos, **`url`** is added automatically when using **`scripts/pull.py -a`** or on the next pull. Each repo block has at most one **`url`** line (duplicates are normalized on pull).

**Sources:** A source can be (1) a **local path** (e.g. `../OtherRepo`, `./MarginCall`), or (2) a **GitHub URL** (e.g. `https://github.com/owner/repo`). GitHub sources are fetched via the GitHub API (no clone). **`.md`** files are pulled with the same exclusions as local.

**Tooling:** `scripts/pull.py` does pull-only updates (no purge). Run `./setup.sh` to create `.venv` and the activation banner (figlet-style “Draft”, PWD, tracked repos).

---

**Design documents** are in **`docs/`** at the repo root:

- **`docs/storage-and-metadata-design.md`** — Storage layer, vault, **sources.yaml** as source of truth, manifest, file registry, reconnection; includes architecture diagram (Mermaid) and vault improvements.
- **`docs/intelligence-layer-design.md`** — Intelligence layer (embeddings, RAG, LLM).
- **`docs/local-oracle-design.md`** — Local oracle / Q&A over docs.

---

**Document UI:** Web UI (**`ui/`**, FastAPI + static frontend) serves the document tree, renders markdown, and supports Pull, Add source (GitHub URL or local path), full-text search (Whoosh), and pinning repos. Full-text search uses an index under **`.search_index/`**; it is rebuilt after each Pull or via **`POST /api/reindex`**. Endpoints: **`GET /api/tree`**, **`GET /api/doc/{repo}/{path}`**, **`GET /api/search?q=...`**, **`POST /api/pull`**, **`POST /api/add_source`**, **`POST /api/reindex`**. Run with **`python scripts/serve.py`** or **`uvicorn ui.app:app --host 0.0.0.0 --port 8058`**.

---

# Adding a New Repo to draft

## Option A: Use the script (recommended)

From the draft repo root:

```bash
python3 scripts/pull.py -a REPO
```

- **REPO** can be:
  - **Repo name** (e.g. `OtherRepo`) → uses **`../OtherRepo`** as path.
  - **Path** (e.g. `../OtherRepo`, `./path/to/repo`) → resolved; name is taken from the directory name.
  - **GitHub URL** (e.g. `https://github.com/owner/repo`) → added as source; pull fetches **`.md`** via GitHub API (no clone). Subdirectory name is **`owner_repo`**.

The script updates **`sources.yaml`**, adds **`url`** for local git repos (or uses the URL as source for GitHub), and runs pull.

## Option B: Manual steps

### 1. Register in sources.yaml

- Add an entry under **`repos`** with the subdirectory name and **`source`** path (e.g. `../OtherRepo`). Optional **`url`** can be added by hand or is backfilled on the next pull if the source is a git repo.

### 2. Create the subdirectory (or run pull)

- Either run `python3 scripts/pull.py` to create the subdirectory and copy files, or create the subdirectory and copy `.md` files manually (see below).

### 3. Which .md files to include

- **Copy only `.md` files** from the source repo.
- **Preserve directory structure** — path in draft must match path under the source (e.g. `source/docs/foo.md` → **`~/.draft/.doc_sources/<RepoName>/docs/foo.md`**).
- Create only directories that contain at least one copied **`.md`**. Do not create empty or extra directories.

### 4. Exclusions (do not copy)

- Top-level **`README.md`** of the source repo.
- **`CLAUDE.md`** (anywhere).
- Anything under **`.claude/`**, **`.cursor/`**, **`.vscode/`**.
- **`.pytest_cache/`**, **`.venv/`**, **`.git/`**, **`__pycache__/`**, **`.tmp/`**, **`.adk/`**.

### 5. Finish

- Update the top-level **`README.md`** in draft: add a short bullet for the new repo (name, link if you have `url`, and what’s in it).

To **stop tracking** a repo: remove its entry from **`sources.yaml`** and optionally delete its subdirectory under **`~/.draft/.doc_sources/<name>`**.

---

# scripts/pull.py options

- **No options:** Pull from all repos in **`sources.yaml`** (copy only when source is newer; never delete in draft). GitHub sources are fetched via API.
- **`-v`** — Verbose: show each repo name, tree of tracked files (like Linux **`tree`**), and status (up to date / N file(s) updated).
- **`-r DIRECTORY`** — List included **`.md`** files from a repo in tree format (repo need not be in **`sources.yaml`**).
- **`-s`** — With **`-r`**, show the first 3 lines of each file.
- **`-a REPO`** — Add repo to **`sources.yaml`**. REPO can be a repo name (→ **`../name`**), a path, or a GitHub URL (→ fetch via API). Adds **`url`** for local git repos; then runs pull.

---

## Example (manual)

Source repo `../MarginCall` with `ENGINEERING.md`, `README.md`, `CLAUDE.md`, `docs/UI.md`, `.claude/commands/foo.md`:

- Create `MarginCall/`, `MarginCall/docs/`.
- Copy: `ENGINEERING.md` → `MarginCall/ENGINEERING.md`, `docs/UI.md` → `MarginCall/docs/UI.md`.
- Do **not** copy: **`README.md`**, **`CLAUDE.md`**, **`.claude/commands/foo.md`**.
