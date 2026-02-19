# draft

A document mirror: pull documentations files from other repos (or GitHub URLs) into one place and browse them in a simple web UI with full-text search and AI assistence.

This can also be a MCP server for other AI agents. [TODO] 

## Get started (the quickest way)

```bash
./setup.sh
```

## Start it manually

```
source .venv/bin/activate   # optional: activation banner + deps
python scripts/serve.py     # start UI at http://localhost:8058
```

## Run draft as a local Docker container:

```bash
docker build -t draft-ui .
docker run -p 8058:8058 draft-ui
```

Open **http://localhost:8058**. The image includes `sources.yaml` and all repo subdirectories baked in. To serve your local draft repo live (e.g. after running `pull.py`), mount it:

```bash
docker run -p 8058:8058 -v "$(pwd)":/app draft-ui
```

## sources.yaml

Lists the repos (sources) that draft tracks. Each entry is a subdirectory name and a `source`:

- **Local path** — e.g. `./MarginCall` or `../OtherRepo`. Run `python scripts/pull.py` to copy `.md` files from that path into draft.
- **GitHub URL** — e.g. `https://github.com/owner/repo`. Pull fetches `.md` files via the GitHub API (no clone).

Add a source from the UI (**Add source** in the sidebar) or from the CLI:

```bash
python scripts/pull.py -a ../OtherRepo
python scripts/pull.py -a https://github.com/owner/repo
```

You can also edit `sources.yaml` by hand (add a `repos:` key and entries with `source:`), then run `python scripts/pull.py` to refresh. One optional `url:` per repo is allowed (e.g. git origin); it is backfilled for local git repos.

## Ask (AI) over your docs

The **Ask (AI)** panel (top of the content area) answers questions using only your indexed docs (RAG). You need:

1. **Build the AI index once:** `python scripts/index_for_ai.py` (requires Python 3.11 or 3.12; ChromaDB does not support 3.14 yet).
2. **A local LLM or API key:**
   - **Local:** Run **Ollama** and at least one model (e.g. `ollama run qwen3:8b`). Default model is `qwen3:8b`; override with **OLLAMA_MODEL** (env or `.env`). When you run `./setup.sh`, choose "Configure Ask (AI) LLM?" to see `ollama list` and instructions.
   - **Cloud:** Set **ANTHROPIC_API_KEY**; Ask (AI) then uses Claude instead of Ollama. Easiest: copy `.env.example` to `.env` and add `ANTHROPIC_API_KEY=sk-...` (the app loads `.env` when started with `python scripts/serve.py`).

No local LLM is needed for the rest of Draft (tree, search, pull, add source). See `docs/local-oracle-design.md` for details.

## Adding Document Sources

The quickest way:
```
./setup.sh
```