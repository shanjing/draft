# draft

This repo stores private documents (tech details, drafts) extracted from other repositories. Each source repo has its own top-level subdirectory; only `.md` files are mirrored, with the same directory structure.

**Tracked repos** are listed in **`repos.yaml`**: each key is the subdirectory name in draft; each value has `source` (path to the repo) and optionally `url` (git origin URL). If the source path is a git repo, `url` is added automatically when adding with `scripts/pull.py -a` or on the next pull.

**Tooling:** `scripts/pull.py` does pull-only updates (no purge). Run `./setup.sh` to create `.venv` and the activation banner (figlet-style “Draft”, PWD, tracked repos).

---

# Adding a New Repo to draft

## Option A: Use the script (recommended)

From the draft repo root:

```bash
python3 scripts/pull.py -a REPO
```

- **REPO** = repo name (e.g. `OtherRepo`) → uses `../OtherRepo` as path, or a path (e.g. `../OtherRepo`, `./path/to/repo`). The script updates `repos.yaml`, adds `url` if the path is a git repo, and runs pull.

## Option B: Manual steps

### 1. Register in repos.yaml

- Add an entry under `repos` with the subdirectory name and `source` path (e.g. `../OtherRepo`). Optional `url` can be added by hand or will be backfilled on the next pull if the source is a git repo.

### 2. Create the subdirectory (or run pull)

- Either run `python3 scripts/pull.py` to create the subdirectory and copy files, or create the subdirectory and copy `.md` files manually (see below).

### 3. Which .md files to include

- **Copy only `.md` files** from the source repo.
- **Preserve directory structure**: path in draft must match path under the source (e.g. `source/docs/foo.md` → `draft/<RepoName>/docs/foo.md`).
- **Create only directories that contain at least one copied `.md`**; do not create empty or extra directories.

### 4. Exclusions (do not copy)

- Top-level **`README.md`** of the source repo.
- **`CLAUDE.md`** (anywhere).
- Anything under **`.claude/`**, **`.cursor/`**.
- **`.pytest_cache/`**, **`.venv/`**, **`.git/`**, **`__pycache__/`**, **`.tmp/`**, **`.adk/`**.

### 5. Finish

- Update the top-level **`README.md`** in draft: add a short bullet for the new repo (name, link if you have `url`, and what’s in it).

To **stop tracking** a repo: remove its entry from `repos.yaml` and optionally delete its subdirectory in draft.

---

# scripts/pull.py options

- **No options:** Pull from all repos in `repos.yaml` (copy only when source is newer; never delete in draft).
- **`-v`** — Verbose: show each repo name, tree of tracked files (like Linux `tree`), and status (up to date / N file(s) updated).
- **`-r DIRECTORY`** — List included `.md` files from a repo in tree format (repo need not be in `repos.yaml`).
- **`-s`** — With `-r`, show the first 3 lines of each file.
- **`-a REPO`** — Add repo to `repos.yaml` (name or path), add `url` if git repo, then run pull.

---

## Example (manual)

Source repo `../MarginCall` with `ENGINEERING.md`, `README.md`, `CLAUDE.md`, `docs/UI.md`, `.claude/commands/foo.md`:

- Create `MarginCall/`, `MarginCall/docs/`.
- Copy: `ENGINEERING.md` → `MarginCall/ENGINEERING.md`, `docs/UI.md` → `MarginCall/docs/UI.md`.
- Do **not** copy: `README.md`, `CLAUDE.md`, `.claude/commands/foo.md`.
