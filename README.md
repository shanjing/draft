# Draft

Draft is a personal documentation hub. It pulls document files from your other repos and GitHub projects into one browsable place. You get a unified view of scattered docs — engineering notes, design specs, drafts — with full-text search and an AI assistant that answers questions from your content.

No cloud sync. Your docs stay local. Draft works with or without an LLM — Ollama for fully offline use, or Claude, OpenAI, and Gemini.

Draft is also an MCP server. [TODO] 

## Get started (quickest way)

```bash
./setup.sh
```

## Start it manually

```bash
source .venv/bin/activate
python scripts/serve.py   # UI at http://localhost:8058
```

## Run Draft as a local Docker container

```bash
docker build -t draft-ui .
docker run -p 8058:8058 draft-ui
# Open http://localhost:8058
```


## Where documents are stored (`~/.draft`)

Document data and config live under **`~/.draft/`** (or **`DRAFT_HOME`** if set): **`sources.yaml`** (source list), **`.doc_sources/`** (one subdir per pulled repo), and **`vault/`** (curated docs). The repo holds only code. Set **`DRAFT_HOME`** to use a different data root (default **`~/.draft`**).


## sources.yaml (your config)

**`sources.yaml`** is your personal list of doc sources. It lives at **`~/.draft/sources.yaml`** (or **`$DRAFT_HOME/sources.yaml`**).

- **First time:** Run **`./setup.sh`** or start the app; they create **`~/.draft/sources.yaml`** from the repo’s **`sources.example.yaml`** if missing.
- Each entry is a name and a `source`:
  - **Local path** — e.g. `../my_notes` or `/path/to/repo`.
  - **GitHub URL** — e.g. `https://github.com/owner/repo`. Pull fetches `.md` files via the GitHub API (no clone).

## Adding document sources

**Quickest way:** run **`./setup.sh`**.

You can also add a source from the UI (**Add source** in the sidebar) or from the CLI:
```bash
python scripts/pull.py -a ../OtherRepo
python scripts/pull.py -a https://github.com/owner/repo
```


## Ask (AI) over your docs

The **Ask (AI)** panel (top of the content area) answers questions using only your indexed docs (RAG). To use it you need a local LLM (Ollama) or an API key from a cloud provider. **`./setup.sh`** lets you choose the model and enter the API key.

No LLM is needed for the rest of Draft — tree, search, pull, add source. See **`docs/local-oracle-design.md`** for details.

## Vault

The **vault** lives at **`~/.draft/vault/`** (or **`$DRAFT_HOME/vault/`**). It is separate from **`.doc_sources/`** so it can later be pointed at encrypted S3, iCloud, etc. File encryption is TODO.

## Engineering

Design docs are in **`docs/`**:

- [Storage & metadata design](docs/storage-and-metadata-design.md) — access layer, vault, sources.yaml, reconnection
- [Intelligence layer design](docs/intelligence-layer-design.md) — embeddings, Chroma, LLM, RAG
- [Local oracle design](docs/local-oracle-design.md) — when a local LLM is required
- [Testing suite](docs/testing-suites.md) — test layers and commands

<img width="1707" height="1027" alt="Screenshot 2026-02-26 at 10 59 40 PM" src="https://github.com/user-attachments/assets/82c5d7b9-17a9-453a-8c53-412162d117bf" />

<img width="1305" height="1024" alt="Screenshot 2026-02-26 at 11 11 13 AM" src="https://github.com/user-attachments/assets/eb2f9a98-7ab1-4a91-a0c1-81691ef82e4e" />

