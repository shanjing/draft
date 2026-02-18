# draft

Private repo for documents and tech details extracted from other repositories (not shared in the original repos).

## Layout

Each source repo has its own subdirectory. Only `.md` files are mirrored, preserving the same directory structure as the source (excluding top-level `README.md`, `CLAUDE.md`, and contents of `.claude` / `.cursor`).

### MarginCall

- `MarginCall/` — docs from [MarginCall](https://github.com/shanjing/MarginCall)
  - Root: `ENGINEERING.md`, `AGENTIC_ENGINEERING.md`
  - `docs/` — design and how-to docs
  - `tests/README.md`, `tools/cache/README.md`

**Tracked repos** are listed in **`repos.yaml`** (subdirectory name → `source` path and optional `url`). If the source path is a git repo, its origin URL is added to the file (when adding with `-a` or on the next pull).

## Updating from source repos (pull)

From the draft repo root, run:

```bash
python3 scripts/pull.py
```

This reads `repos.yaml`, finds all `.md` files in each `source` path (with the same exclusions as in `CLAUDE.md`), and copies them into the matching subdirectory under draft **only when the source file is newer**. It does not delete files in draft when they are removed from the source (pull only, not sync). Use this after changing docs in a tracked repo to refresh draft.

**Setup (optional):** Run `./setup.sh` to create `.venv`, install dependencies, and install an activation banner (block-art “draft” in light blue when you `source .venv/bin/activate`).

**Options** (requires `click`; `pip install click` or use the repo’s `.venv`):

- **`-r DIRECTORY`** — List all included `.md` files from a repo (path). The repo does not need to be in `repos.yaml`; any directory is valid.
- **`-s`** — With `-r`, show the first 3 lines of each listed file.
- **`-v`** — Verbose: show each repo being scanned and all tracked files in tree format (like Linux `tree`).
- **`-a REPO`** — Add a repo to management: pass a **repo name** (e.g. `OtherRepo`; uses `../OtherRepo` as path) or a **relative/absolute path** (e.g. `../OtherRepo`). Updates `repos.yaml` and runs pull so the new repo is scanned immediately.

Examples: `python3 scripts/pull.py -r ../MarginCall` (list); `python3 scripts/pull.py -r ../OtherRepo -s` (list with snippets).

## Adding another repo

1. Add an entry to **`repos.yaml`** (e.g. `OtherRepo: { source: ../OtherRepo }`).
2. Create a subdirectory named after the repo and copy only the `.md` files you want to keep private, preserving paths (see `CLAUDE.md` for full rules and exclusions).
