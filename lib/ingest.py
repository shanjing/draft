"""
Ingest vault and .doc_sources (under ~/.draft) into a Chroma vector store for RAG.
Uses same file exclusions as scripts/pull.py. Rebuilds the collection on each run.
"""
import contextlib
import io
import logging
import os
import warnings
from pathlib import Path

from lib.chunking import chunk_markdown, Chunk
from lib.paths import get_doc_sources_root, get_vault_root

# Same exclusions as pull.py (do not depend on scripts)
EXCLUDE_TOPLEVEL = {"README.md"}
EXCLUDE_BASENAME = {"CLAUDE.md"}
EXCLUDE_DIRS = (
    ".claude",
    ".cursor",
    ".vscode",
    ".pytest_cache",
    ".venv",
    ".git",
    "__pycache__",
    ".tmp",
    ".adk",
    ".cache",
)

VECTOR_DIR = ".vector_store"
COLLECTION_NAME = "draft_docs"

# nomic-embed-text-v1.5 requires trust_remote_code=True. Alternative: "sentence-transformers/all-MiniLM-L6-v2" (no trust_remote_code).
EMBED_MODEL = "nomic-ai/nomic-embed-text-v1.5"
TRUST_REMOTE_CODE = True
INDEX_PROFILES = {
    "quick": {
        "embed_model": "sentence-transformers/all-MiniLM-L6-v2",
        "trust_remote_code": False,
        "chunk_max_chars": 1600,
        "chunk_overlap_paras": 0,
        "batch_size": 192,
        "embed_batch_size": 48,
    },
    "deep": {
        "embed_model": EMBED_MODEL,
        "trust_remote_code": TRUST_REMOTE_CODE,
        "chunk_max_chars": 2400,
        "chunk_overlap_paras": 1,
        "batch_size": 128,
        "embed_batch_size": 32,
    },
}


def should_include(rel_path: str) -> bool:
    if rel_path in EXCLUDE_TOPLEVEL:
        return False
    if Path(rel_path).name in EXCLUDE_BASENAME:
        return False
    parts = Path(rel_path).parts
    if any(p in EXCLUDE_DIRS for p in parts):
        return False
    return True


def collect_chunks(
    draft_root: Path,
    *,
    chunk_max_chars: int = 2400,
    chunk_overlap_paras: int = 1,
) -> list[Chunk]:
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
            for c in chunk_markdown(
                "vault",
                path_str,
                content,
                chunk_max_chars=chunk_max_chars,
                chunk_overlap_paras=chunk_overlap_paras,
            ):
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
            for c in chunk_markdown(
                repo,
                path_str,
                content,
                chunk_max_chars=chunk_max_chars,
                chunk_overlap_paras=chunk_overlap_paras,
            ):
                chunks.append(c)
    return chunks


def build_index(draft_root: Path, verbose: bool = False, profile: str = "quick") -> int:
    """
    Rebuild the Chroma vector store from draft/<repo>/*.md.
    Returns the number of chunks indexed.
    """
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
    os.environ.setdefault("POSTHOG_DISABLED", "1")
    os.environ.setdefault("DO_NOT_TRACK", "1")
    # Keep HF cache under project-local .cache and avoid deprecation warning by not using TRANSFORMERS_CACHE.
    hf_cache = draft_root / ".cache" / "huggingface"
    hf_cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(hf_cache))
    warnings.filterwarnings(
        "ignore",
        message=r"Using `TRANSFORMERS_CACHE` is deprecated.*",
        category=FutureWarning,
    )
    # Reduce noisy third-party logs (telemetry + dynamic module notices).
    logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)
    logging.getLogger("posthog").setLevel(logging.CRITICAL)
    logging.getLogger("transformers").setLevel(logging.ERROR)
    logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
    try:
        import numpy as np
        if int(np.__version__.split(".")[0]) >= 2:
            raise RuntimeError("NumPy 2.x not compatible. Run: pip install 'numpy<2'")
    except ImportError:
        pass
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
    from transformers.utils import logging as transformers_logging
    from huggingface_hub import logging as hf_logging
    try:
        from tqdm import tqdm
    except ImportError:
        tqdm = None  # type: ignore[assignment]
    transformers_logging.set_verbosity_error()
    hf_logging.set_verbosity_error()

    mode = (profile or "quick").strip().lower()
    if mode not in INDEX_PROFILES:
        raise ValueError(f"Unknown index profile: {profile}. Use quick or deep.")
    cfg = INDEX_PROFILES[mode]

    chunks = collect_chunks(
        draft_root,
        chunk_max_chars=int(cfg["chunk_max_chars"]),
        chunk_overlap_paras=int(cfg["chunk_overlap_paras"]),
    )
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
        metadata={
            "description": "Draft docs for RAG",
            "profile": mode,
            "embed_model": str(cfg["embed_model"]),
            "trust_remote_code": bool(cfg["trust_remote_code"]),
            "chunk_max_chars": int(cfg["chunk_max_chars"]),
            "chunk_overlap_paras": int(cfg["chunk_overlap_paras"]),
        },
    )

    if verbose:
        print(f"Embedding {len(chunks)} chunks with {cfg['embed_model']} ({mode})...")
    # Some remote-code models print noisy non-critical stdout; suppress that while loading.
    with contextlib.redirect_stdout(io.StringIO()):
        model = SentenceTransformer(
            str(cfg["embed_model"]),
            trust_remote_code=bool(cfg["trust_remote_code"]),
        )
    # Stream in small batches to keep memory bounded and avoid large Arrow/DuckDB buffers.
    BATCH_SIZE = int(cfg["batch_size"])
    EMBED_BATCH_SIZE = int(cfg["embed_batch_size"])
    starts = range(0, len(chunks), BATCH_SIZE)
    if verbose and tqdm is not None:
        total_batches = (len(chunks) + BATCH_SIZE - 1) // BATCH_SIZE
        starts = tqdm(starts, total=total_batches, desc=f"Index ({mode})", unit="batch", leave=True)

    for start in starts:
        end = min(start + BATCH_SIZE, len(chunks))
        batch = chunks[start:end]
        texts = [c.text for c in batch]
        embeddings = model.encode(
            texts,
            batch_size=EMBED_BATCH_SIZE,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        ids = [f"chunk_{i}" for i in range(start, end)]
        metadatas = [
            {
                "repo": c.repo,
                "path": c.path,
                "heading": (c.heading[:200] if c.heading else ""),
            }
            for c in batch
        ]
        collection.add(
            ids=ids,
            embeddings=embeddings.tolist(),
            metadatas=metadatas,
            documents=texts,
        )
        if verbose and tqdm is None:
            print(f"  Added {end}/{len(chunks)} chunks...")

    if verbose:
        print(f"Indexed {len(chunks)} chunks into {persist_dir}")
    return len(chunks)
