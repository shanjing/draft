"""
Ingest vault and .doc_sources (under ~/.draft) into a Chroma vector store for RAG.
Uses same file exclusions as scripts/pull.py. Rebuilds the collection on each run.
"""
from pathlib import Path

from lib.chunking import chunk_markdown, Chunk
from lib.paths import get_doc_sources_root, get_vault_root

# Same exclusions as pull.py (do not depend on scripts)
EXCLUDE_TOPLEVEL = {"README.md"}
EXCLUDE_BASENAME = {"CLAUDE.md"}
EXCLUDE_DIRS = (
    ".claude",
    ".cursor",
    ".pytest_cache",
    ".venv",
    ".git",
    "__pycache__",
    ".tmp",
    ".adk",
)

VECTOR_DIR = ".vector_store"
COLLECTION_NAME = "draft_docs"

# nomic-embed-text-v1.5 requires trust_remote_code=True. Alternative: "sentence-transformers/all-MiniLM-L6-v2" (no trust_remote_code).
EMBED_MODEL = "nomic-ai/nomic-embed-text-v1.5"
TRUST_REMOTE_CODE = True


def should_include(rel_path: str) -> bool:
    if rel_path in EXCLUDE_TOPLEVEL:
        return False
    if Path(rel_path).name in EXCLUDE_BASENAME:
        return False
    parts = Path(rel_path).parts
    if parts and parts[0] in EXCLUDE_DIRS:
        return False
    return True


def collect_chunks(draft_root: Path) -> list[Chunk]:
    """Collect chunks from ~/.draft/vault and ~/.draft/.doc_sources/<repo>/*.md (same exclusions as pull)."""
    chunks: list[Chunk] = []
    vault_dir = get_vault_root()
    if vault_dir.is_dir():
        for f in vault_dir.rglob("*.md"):
            try:
                rel = f.relative_to(vault_dir)
                path_str = rel.as_posix()
            except ValueError:
                continue
            if not should_include(path_str):
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for c in chunk_markdown("vault", path_str, content):
                chunks.append(c)
    sources_dir = get_doc_sources_root()
    if not sources_dir.is_dir():
        return chunks
    for repo_dir in sorted(sources_dir.iterdir()):
        if not repo_dir.is_dir() or repo_dir.name.startswith("."):
            continue
        repo = repo_dir.name
        for f in repo_dir.rglob("*.md"):
            try:
                rel = f.relative_to(repo_dir)
                path_str = rel.as_posix()
            except ValueError:
                continue
            if not should_include(path_str):
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for c in chunk_markdown(repo, path_str, content):
                chunks.append(c)
    return chunks


def build_index(draft_root: Path, verbose: bool = False) -> int:
    """
    Rebuild the Chroma vector store from draft/<repo>/*.md.
    Returns the number of chunks indexed.
    """
    import os
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
    try:
        import numpy as np
        if int(np.__version__.split(".")[0]) >= 2:
            raise RuntimeError("NumPy 2.x not compatible. Run: pip install 'numpy<2'")
    except ImportError:
        pass
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer

    chunks = collect_chunks(draft_root)
    if not chunks:
        if verbose:
            print("No .md chunks to index.")
        return 0

    persist_dir = draft_root / VECTOR_DIR
    persist_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(
        path=str(persist_dir),
        settings=Settings(anonymized_telemetry=False),
    )
    # Delete and recreate so we always reflect current draft/
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(
        COLLECTION_NAME,
        metadata={"description": "Draft docs for RAG"},
    )

    if verbose:
        print(f"Embedding {len(chunks)} chunks with {EMBED_MODEL}...")
    model = SentenceTransformer(EMBED_MODEL, trust_remote_code=TRUST_REMOTE_CODE)
    texts = [c.text for c in chunks]
    embeddings = model.encode(texts, show_progress_bar=verbose)

    ids = [f"chunk_{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "repo": c.repo,
            "path": c.path,
            "heading": (c.heading[:200] if c.heading else ""),
        }
        for c in chunks
    ]
    documents = [c.text for c in chunks]

    # Add in batches to avoid "Invalid buffer size" / DuckDB memory limits.
    BATCH_SIZE = 4000
    for start in range(0, len(chunks), BATCH_SIZE):
        end = min(start + BATCH_SIZE, len(chunks))
        collection.add(
            ids=ids[start:end],
            embeddings=embeddings[start:end].tolist(),
            metadatas=metadatas[start:end],
            documents=documents[start:end],
        )
        if verbose and end < len(chunks):
            print(f"  Added {end}/{len(chunks)} chunks...")

    if verbose:
        print(f"Indexed {len(chunks)} chunks into {persist_dir}")
    return len(chunks)
