# Draft

Draft is a personal documentation hub that pulls document files from your other repos and GitHub
projects into one browsable place. It gives you a unified view of scattered docs — engineering
notes, design specs, drafts — with full-text search and an AI assistant that answers questions
directly from your content.                                                                      

No cloud sync. Your docs stay local. Works with or without any LLM — Ollama for fully offline use, or 
Claude, OpenAI, and Gemini.

Draft is alo a MCP server. [TODO] 

## Get started (the quickest way)

```bash
./setup.sh
```

## Start it manually

```
source .venv/bin/activate
python scripts/serve.py     # start UI at http://localhost:8058
```

## Run draft as a local Docker container:

```bash
docker build -t draft-ui .
docker run -p 8058:8058 draft-ui
#Open **http://localhost:8058**.
```


## Where documents are stored (`~/.draft`)

Document data and config live under **`~/.draft/`** (or **`DRAFT_HOME`** if set): **`sources.yaml`** (your source list), **`.doc_sources/`** (one subdir per pulled repo), and **`vault/`** (curated docs). The repo holds only code. Set **`DRAFT_HOME`** to use a different data root (default is **`~/.draft`**).


## sources.yaml (your config)

**`sources.yaml`** is your personal list of doc sources. It lives at **`~/.draft/sources.yaml`** (or **`$DRAFT_HOME/sources.yaml`**).

- **First time:** Run **`./setup.sh`** or start the app; they create **`~/.draft/sources.yaml`** from the repo’s **`sources.example.yaml`** if missing.
- Each entry is a name and a `source`:
  - **Local path** — e.g. `../my_notes` or `/path/to/repo`.
  - **GitHub URL** — e.g. `https://github.com/owner/repo`. Pull fetches `.md` files via the GitHub API (no clone).

## Adding Document Sources

The quickest way:
```
./setup.sh
```

Add a source from the UI (**Add source** in the sidebar)

Add sources from the CLI:
```bash
python scripts/pull.py -a ../OtherRepo
python scripts/pull.py -a https://github.com/owner/repo
```


## Ask (AI) over your docs

The **Ask (AI)** panel (top of the content area) answers questions using only your indexed docs (RAG).
To do that ou need a local LLM model (ollama) or an API from major cloud LLM providers. The setup.sh will let you choose the model and enter the API key.


No local LLM is needed for the rest of Draft (tree, search, pull, add source). See `docs/local-oracle-design.md` for details.

## Vault

The **vault** source lives at **`~/.draft/vault/`** (or `$DRAFT_HOME/vault/`). It is separate from `.doc_sources/` so it can later be pointed at encrypted S3, iCloud, etc. Files are encrypted (TODO).

## Engineering

Design documents in `docs/`:

- [Storage & metadata design](docs/storage-and-metadata-design.md) — access layer, vault, sources.yaml, reconnection
- [Intelligence layer design](docs/intelligence-layer-design.md) — embeddings, Chroma, LLM, RAG
- [Local oracle design](docs/local-oracle-design.md) — when a local LLM is required
- [Testing suite](docs/testing-suites.md) - testing suite
  
<img width="1436" height="988" alt="Screenshot 2026-02-23 at 10 50 21 AM" src="https://github.com/user-attachments/assets/b629e867-07b9-4351-abb3-642e616fb707" />

<img width="1383" height="936" alt="draft-screenshot" src="https://github.com/user-attachments/assets/d43b43f1-ba37-44ed-bfbe-681d1de2969e" />


