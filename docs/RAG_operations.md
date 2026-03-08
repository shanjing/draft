# RAG Operations

How to change embed/encoder models and how to run RAG + LLM tests. See **RAG_design.md** for architecture and model-performance guidance.

---

## a. How to change models

- **Source of truth:** `.env` (`DRAFT_EMBED_MODEL`, `DRAFT_CROSS_ENCODER_MODEL`, and for Ollama embed: `DRAFT_EMBED_PROVIDER=ollama`).
- **Via setup:** Run `./setup.sh`. Use **option 2** (Setup embedding model) and **option 3** (Setup encoder model) to choose or type Hugging Face model names; option 2 also lists local Ollama embedding models. When the embed model changes, setup reminds you to rebuild the index (option 5).
- **Rebuild required:** After changing the embed model, run **option 5** (Build RAG/index) so the vector index matches the new model. The **Actions** section in setup shows `[required]` when the current Embed in `.env` does not match the RAG index.
- **Defaults:** Embed `sentence-transformers/all-MiniLM-L6-v2`; encoder `cross-encoder/ms-marco-MiniLM-L-6-v2`. For strict offline use, set `HF_HUB_OFFLINE=1` in `.env`.
- **16GB laptop (no GPU):** Use `nomic-ai/nomic-embed-text-v1.5` + `BAAI/bge-reranker-v2-m3` (see RAG_design.md).

---

## b. How to run tests

### From setup (interactive)

- **Option 6 — Testing RAG + LLM:** Runs a single ask with a fixed question (ingestion + embedding providers), `--debug` and `--show-prompt`. Use after building the index (option 5) or when you want a quick smoke test.
- **After option 5 (Build RAG/index):** On successful build, setup offers “Would you like to run a test? (Y/n)” and runs the same ask command if you accept.

### Manual CLI

```bash
# From repo root: one-off question (requires built index + LLM config in .env)
python scripts/ask.py -q "Explain the ingestion process for Draft's RAG system and how it handles different embedding providers like Ollama and Hugging Face." --debug --show-prompt
```

### Pipeline test (existing index or rebuild)

```bash
# Use existing index (embed/encoder from .env)
python tests/test_pipeline.py -q "what is vault" -v

# Rebuild index then run retrieval + LLM
python tests/test_pipeline.py --rebuild -q "what is vault" -v
```

Options: `-p default|d|G|L|S` (model pair), `--profile quick|deep`, `--rebuild`, `-v`. Run from draft repo root.

### CI/CD

- Run the test suite (e.g. `pytest tests/`) for unit and integration tests.
- For a RAG pipeline check in CI: run `python tests/test_pipeline.py --rebuild -q "What is this project about?" -v` (or with `-p default`) so the job builds the index from `sources.yaml` and runs one Ask. Ensure `.env` or CI env provides `DRAFT_EMBED_MODEL`, `DRAFT_CROSS_ENCODER_MODEL`, and LLM config (`OLLAMA_MODEL` or API keys) as needed.

---

## c. Vector store location

The RAG vector index (ChromaDB) lives under **`DRAFT_HOME/.vector_store/`** (e.g. `~/.draft/.vector_store` by default). This keeps all user data under one root and ensures the index **persists** in containers when `DRAFT_HOME` is mounted as a volume. Rebuild from the UI or with `python scripts/index_for_ai.py --profile quick`.

**Migration:** If you previously had an index at `<repo>/.vector_store`, it is no longer used. Rebuild the index once—it will be created under `DRAFT_HOME/.vector_store`.

---

## d. Operations in containers (Docker / Kubernetes)

RAG operations work the same way when Draft runs in containers: embed and encoder models are read from **environment configuration** (mounted `.env` or ConfigMap/Secret). The app **re-reads** config on each reindex and on each Ask for the LLM; changing `DRAFT_EMBED_MODEL` or `DRAFT_CROSS_ENCODER_MODEL` does **not** require a container or pod restart—run a reindex (e.g. from the UI or by running the index script in the container) after changing the embed model so the vector index matches. Data lives under a single root (`DRAFT_HOME`) that you mount as a volume—including the vector store at `DRAFT_HOME/.vector_store`; the same image can target local Ollama, in-cluster LLMs, or cloud APIs by changing env. **Disk:** Ensure ~4 GB free for DRAFT_HOME (includes HF cache at `.cache/huggingface`; see [Container orchestration guide](container_orchestration_guide.md#disk-space)). For full setup (build, run, mounts, K8s manifests), see **[Container orchestration guide](container_orchestration_guide.md)**.
