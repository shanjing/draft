# draft

Private repo for documents and tech details extracted from other repositories (not shared in the original repos).

## Layout

Each source repo has its own subdirectory. Only `.md` files are mirrored, preserving the same directory structure as the source (excluding top-level `README.md`, `CLAUDE.md`, and contents of `.claude` / `.cursor`).

### MarginCall

- `MarginCall/` — docs from [MarginCall](https://github.com/shanjing/MarginCall)
  - Root: `ENGINEERING.md`, `AGENTIC_ENGINEERING.md`
  - `docs/` — design and how-to docs
  - `tests/README.md`, `tools/cache/README.md`

## Adding another repo

1. Create a subdirectory named after the repo (e.g. `OtherRepo/`).
2. Copy only the `.md` files you want to keep private, preserving paths (e.g. `OtherRepo/docs/foo.md`).
3. Do not copy: top-level `README.md`, `CLAUDE.md`, or anything under `.claude` or `.cursor`.
