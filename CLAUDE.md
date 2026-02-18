# draft

This repo stores private documents (tech details, drafts) extracted from other repositories. Each source repo has its own top-level subdirectory; only `.md` files are mirrored, with the same directory structure.

**Tracked repos** are listed in **`repos.yaml`**: each key is the subdirectory name in draft, and `source` is the path to that repo. Use this file as the source of truth for what draft tracks.

---

# Adding a New Repo to draft

When asked to add or mirror docs from another repo into this draft repo:

## 1. Register in repos.yaml

- Add an entry under `repos` in **`repos.yaml`** with the repo’s subdirectory name and `source` path (e.g. `../OtherRepo`).
- The subdirectory name must match the key (e.g. `MarginCall` → `MarginCall/` in draft).

## 2. Create the subdirectory

- Add one top-level subdirectory named **exactly like the key in repos.yaml** (e.g. `MarginCall`, `OtherRepo`).
- Do not create any other top-level structure.

## 3. Which .md files to include

- **Copy only `.md` files** from the source repo.
- **Preserve directory structure**: path in draft must match path under the source repo (e.g. `source/docs/foo.md` → `draft/<RepoName>/docs/foo.md`).
- **Create only directories that contain at least one copied `.md`**; do not create empty or extra directories.

## 4. Exclusions (do not copy)

- Top-level **`README.md`** of the source repo (stays in the source only).
- **`CLAUDE.md`** (anywhere).
- Anything under **`.claude/`**.
- Anything under **`.cursor/`**.
- Tool/cache dirs that only have incidental .md (e.g. **`.pytest_cache/`**) — omit unless you explicitly want them.

## 5. Steps to perform

1. Add the repo to **`repos.yaml`** (name → `source` path).
2. From the **draft** repo root, read the source path from `repos.yaml` (or use e.g. `../MarginCall`).
3. List all `.md` files in the source repo (e.g. `find` or glob `**/*.md`), then remove paths matching the exclusions above.
4. For each included path:
   - Create `draft/<RepoName>/<relative path>` dirs as needed.
   - Copy the file to `draft/<RepoName>/<relative path>`.
5. Update the top-level **`README.md`** in draft: add a short bullet for the new repo (name, link if applicable, and what’s in it).

To **stop tracking** a repo: remove its entry from `repos.yaml` and optionally delete its subdirectory in draft.

## Example

Source repo `../MarginCall` with `ENGINEERING.md`, `README.md`, `CLAUDE.md`, `docs/UI.md`, `.claude/commands/foo.md`:

- Create `MarginCall/`, `MarginCall/docs/`.
- Copy: `ENGINEERING.md` → `MarginCall/ENGINEERING.md`, `docs/UI.md` → `MarginCall/docs/UI.md`.
- Do **not** copy: `README.md`, `CLAUDE.md`, `.claude/commands/foo.md`.
