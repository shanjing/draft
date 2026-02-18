# draft

Private repo for documents and tech details extracted from other repositories (not shared in the original repos).

## Layout

Each source repo has its own subdirectory. Only `.md` files are mirrored, preserving the same directory structure as the source (excluding top-level `README.md`, `CLAUDE.md`, and contents of `.claude` / `.cursor`).

### MarginCall

- `MarginCall/` — docs from [MarginCall](https://github.com/shanjing/MarginCall)
  - Root: `ENGINEERING.md`, `AGENTIC_ENGINEERING.md`
  - `docs/` — design and how-to docs
  - `tests/README.md`, `tools/cache/README.md`

**Tracked repos** are listed in **`repos.yaml`** (subdirectory name → `source` path).

## Adding another repo

1. Add an entry to **`repos.yaml`** (e.g. `OtherRepo: { source: ../OtherRepo }`).
2. Create a subdirectory named after the repo and copy only the `.md` files you want to keep private, preserving paths (see `CLAUDE.md` for full rules and exclusions).
