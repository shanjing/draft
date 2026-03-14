"""
This is the main module to build indexes for Draft's RAG.
It is invoked by scripts/index_for_ai.py and the UI reindex action.

There are two main functions in this module:
1.collect_chunks(): Reads the repo list from sources.yaml (get_sources_yaml_path + parse_sources_yaml),
  walks vault and each repo's effective root, and uses lib.chunking (chunk_markdown / chunk_python) to
  turn .md and .py files into chunks. Returns list[Chunk].
2.build_index(): Calls collect_chunks(), embeds the chunks, and writes them to the Chroma vector store.

Note:
It uses same file exclusions as scripts/pull.py. Rebuilds the collection on each run.
"""
import chromadb
import contextlib
import io
import logging
import os
import time
import warnings
from pathlib import Path

from chromadb.config import Settings

# sentence_transformers / transformers / huggingface_hub are lazy-imported inside
# the hf provider branch so they are not loaded for onnx/ollama/gemini providers.

from lib.chunking import chunk_markdown, chunk_python, Chunk
from lib.gitignore import get_git_ignored_set
from lib.log import get_logger
from lib.manifest import parse_sources_yaml
from lib.paths import get_effective_repo_root, get_hf_cache_root, get_sources_yaml_path, get_vault_root, get_vector_store_root

log = get_logger(__name__)

# Same exclusions as pull.py (do not depend on scripts)
EXCLUDE_TOPLEVEL: set[str] = set()
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

COLLECTION_NAME = "draft_docs"
DEFAULT_EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Backward-compat for modules that still import these names from ingest.
# Runtime code should prefer DRAFT_EMBED_MODEL and collection metadata.
EMBED_MODEL = (os.environ.get("DRAFT_EMBED_MODEL") or "").strip().strip("'\"") or DEFAULT_EMBED_MODEL
TRUST_REMOTE_CODE = "nomic" in EMBED_MODEL.lower() or "qwen" in EMBED_MODEL.lower()

# Default chunk/batch when building from DRAFT_EMBED_MODEL only (no quick/deep profiles).
INDEX_DEFAULTS = {
    "chunk_max_chars": 1600,
    "chunk_overlap_paras": 0,
    "batch_size": 192,
    "embed_batch_size": 48,
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
    """Collect chunks from vault and from each repo's effective root (sources.yaml; no copy)."""
    chunks: list[Chunk] = []
    vault_dir = get_vault_root()
    if vault_dir.is_dir():
        vault_candidates: list[tuple[str, Path]] = []
        for f in vault_dir.rglob("*.md"):
            try:
                rel = f.relative_to(vault_dir)
                path_str = rel.as_posix()
            except ValueError:
                continue
            if not should_include(path_str):
                continue
            vault_candidates.append((path_str, f))
        for f in vault_dir.rglob("*.py"):
            try:
                rel = f.relative_to(vault_dir)
                path_str = rel.as_posix()
            except ValueError:
                continue
            if not should_include(path_str):
                continue
            vault_candidates.append((path_str, f))
        vault_ignored = get_git_ignored_set(vault_dir, [p for p, _ in vault_candidates])
        for path_str, f in vault_candidates:
            if path_str in vault_ignored:
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if f.suffix.lower() == ".py":
                for c in chunk_python(
                    "vault",
                    path_str,
                    content,
                    chunk_max_chars=chunk_max_chars,
                ):
                    chunks.append(c)
            else:
                for c in chunk_markdown(
                    "vault",
                    path_str,
                    content,
                    chunk_max_chars=chunk_max_chars,
                    chunk_overlap_paras=chunk_overlap_paras,
                ):
                    chunks.append(c)
    sources_yaml = get_sources_yaml_path()
    if not sources_yaml.is_file():
        return chunks
    repos = parse_sources_yaml(sources_yaml)
    for name, repo in sorted(repos.items()):
        if name == "vault":
            continue
        source = (repo.get("source") or "").strip()
        if not source:
            continue
        repo_root = get_effective_repo_root(name, source, draft_root)
        if repo_root.is_file() and repo_root.suffix == ".md":
            try:
                content = repo_root.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for c in chunk_markdown(
                name,
                repo_root.name,
                content,
                chunk_max_chars=chunk_max_chars,
                chunk_overlap_paras=chunk_overlap_paras,
            ):
                chunks.append(c)
            continue
        if not repo_root.is_dir():
            continue
        # Collect (path_str, f) for .md and .py passing should_include, then filter by .gitignore
        candidates: list[tuple[str, Path]] = []
        for f in repo_root.rglob("*.md"):
            try:
                rel = f.relative_to(repo_root)
                path_str = rel.as_posix()
            except ValueError:
                continue
            if not should_include(path_str):
                continue
            candidates.append((path_str, f))
        for f in repo_root.rglob("*.py"):
            try:
                rel = f.relative_to(repo_root)
                path_str = rel.as_posix()
            except ValueError:
                continue
            if not should_include(path_str):
                continue
            candidates.append((path_str, f))
        ignored = get_git_ignored_set(repo_root, [p for p, _ in candidates])
        for path_str, f in candidates:
            if path_str in ignored:
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if f.suffix.lower() == ".py":
                for c in chunk_python(
                    name,
                    path_str,
                    content,
                    chunk_max_chars=chunk_max_chars,
                ):
                    chunks.append(c)
            else:
                for c in chunk_markdown(
                    name,
                    path_str,
                    content,
                    chunk_max_chars=chunk_max_chars,
                    chunk_overlap_paras=chunk_overlap_paras,
                ):
                    chunks.append(c)
    return chunks

# the main function to build the index for the RAG
# this is invoked by scripts/index_for_ai.py and the UI reindex action.
def _reload_env_from_file(draft_root: Path) -> None:
    """Re-load .env so embed/encoder from .env take effect without restart (Docker/K8s)."""
    env_path = draft_root / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=True)
    except ImportError:
        pass


def build_index(draft_root: Path, verbose: bool = False) -> int:
    """
    Rebuild the Chroma vector store from vault and each repo's effective root:
    .md (by section/paragraph) and .py (by ast def/class). Returns the number of chunks indexed.
    Uses DRAFT_EMBED_MODEL from .env (required). Re-loads .env at start so changes take effect without restart.
    """
    _reload_env_from_file(draft_root)
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
    os.environ.setdefault("POSTHOG_DISABLED", "1")
    os.environ.setdefault("DO_NOT_TRACK", "1")
    # HF cache under DRAFT_HOME so models persist in Docker and avoid re-downloads when switching models.
    hf_cache = get_hf_cache_root()
    hf_cache.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(hf_cache)
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
    try:
        from tqdm import tqdm
    except ImportError:
        tqdm = None  # type: ignore[assignment]

    # Embedding model from .env only (no quick/deep profiles).
    env_embed = os.environ.get("DRAFT_EMBED_MODEL", "").strip().strip("'\"")
    if not env_embed:
        raise ValueError(
            "DRAFT_EMBED_MODEL is not set. Set it in .env (e.g. DRAFT_EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2) or run setup.sh step 2."
        )
    env_embed_provider = (os.environ.get("DRAFT_EMBED_PROVIDER", "") or "").strip().lower()
    cfg = dict(INDEX_DEFAULTS)
    cfg["embed_model"] = env_embed
    cfg["trust_remote_code"] = "nomic" in env_embed.lower() or "qwen" in env_embed.lower()
    use_ollama_embed = env_embed_provider == "ollama"
    use_gemini_embed = env_embed_provider == "gemini"
    use_onnx_embed = env_embed_provider == "onnx"

    chunks = collect_chunks(
        draft_root,
        chunk_max_chars=int(cfg["chunk_max_chars"]),
        chunk_overlap_paras=int(cfg["chunk_overlap_paras"]),
    )
    if not chunks:
        if verbose:
            log.info("No chunks to index (docs + code).")
        return 0

    persist_dir = get_vector_store_root()
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
    # Determine embed provider: onnx, ollama, gemini, or hf
    if use_onnx_embed:
        embed_provider = "onnx"
    elif use_ollama_embed:
        embed_provider = "ollama"
    elif use_gemini_embed:
        embed_provider = "gemini"
    else:
        embed_provider = "hf"
    collection = client.create_collection(
        COLLECTION_NAME,
        metadata={
            "description": "Draft docs for RAG",
            "profile": "env",
            "embed_model": str(cfg["embed_model"]),
            "embed_provider": embed_provider,
            "trust_remote_code": bool(cfg["trust_remote_code"]),
            "chunk_max_chars": int(cfg["chunk_max_chars"]),
            "chunk_overlap_paras": int(cfg["chunk_overlap_paras"]),
        },
    )

    if verbose:
        log.info(f"Embedding {len(chunks)} chunks with {cfg['embed_model']} ({embed_provider})...")
    BATCH_SIZE = int(cfg["batch_size"])
    EMBED_BATCH_SIZE = int(cfg["embed_batch_size"])
    starts = range(0, len(chunks), BATCH_SIZE)
    pbar = None
    if tqdm is not None and verbose:
        pbar = tqdm(total=len(chunks), desc="Build RAG/vector index", unit="chunk", leave=True)

    if use_onnx_embed:
        from lib.onnx_embed import embed as onnx_embed
        from lib.ai_engine import _resolve_onnx_embed_dir
        onnx_base_dir = os.environ.get("DRAFT_ONNX_EMBED_DIR", "").strip()
        if not onnx_base_dir:
            raise RuntimeError("DRAFT_ONNX_EMBED_DIR must be set in .env to use ONNX embeddings")
        onnx_model_dir = _resolve_onnx_embed_dir(onnx_base_dir, cfg["embed_model"])
        for start in starts:
            end = min(start + BATCH_SIZE, len(chunks))
            batch = chunks[start:end]
            texts = [c.text for c in batch]
            embeddings = onnx_embed(texts, onnx_model_dir)
            if start == 0 and verbose and embeddings:
                log.info(f"Embedding dimension: {len(embeddings[0])} (onnx: {onnx_model_dir})")
            ids = [f"chunk_{i}" for i in range(start, end)]
            metadatas = []
            for c in batch:
                meta: dict = {
                    "repo": c.repo,
                    "path": c.path,
                    "heading": (c.heading[:200] if c.heading else ""),
                }
                if c.start_line is not None and c.end_line is not None:
                    meta["start_line"] = c.start_line
                    meta["end_line"] = c.end_line
                metadatas.append(meta)
            collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=texts,
            )
            if pbar is not None:
                pbar.update(len(batch))
            elif verbose:
                log.info(f"  Added {end}/{len(chunks)} chunks...")
    elif use_gemini_embed:
        from lib.gemini_embed import embed as gemini_embed
        gemini_model = str(cfg["embed_model"])
        gemini_api_key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
        if not gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY (or GOOGLE_API_KEY) must be set in .env to use Gemini embeddings")
        for start in starts:
            end = min(start + BATCH_SIZE, len(chunks))
            batch = chunks[start:end]
            texts = [c.text for c in batch]
            embeddings = gemini_embed(texts, gemini_model, gemini_api_key)
            # As of 3/11/2026, Gemini embedding throttles requests at 3K tokens per minute (SJ)
            time.sleep(0.5)
            if start == 0 and verbose and embeddings:
                log.info(f"Embedding dimension: {len(embeddings[0])} ({gemini_model})")
            ids = [f"chunk_{i}" for i in range(start, end)]
            metadatas = []
            for c in batch:
                meta: dict = {
                    "repo": c.repo,
                    "path": c.path,
                    "heading": (c.heading[:200] if c.heading else ""),
                }
                if c.start_line is not None and c.end_line is not None:
                    meta["start_line"] = c.start_line
                    meta["end_line"] = c.end_line
                metadatas.append(meta)
            collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=texts,
            )
            if pbar is not None:
                pbar.update(len(batch))
            elif verbose:
                log.info(f"  Added {end}/{len(chunks)} chunks...")
    elif use_ollama_embed:
        from lib.ollama_embed import embed as ollama_embed
        ollama_model = str(cfg["embed_model"])
        for start in starts:
            end = min(start + BATCH_SIZE, len(chunks))
            batch = chunks[start:end]
            texts = [c.text for c in batch]
            embeddings = ollama_embed(ollama_model, texts, batch_size=EMBED_BATCH_SIZE)
            if start == 0 and verbose and embeddings:
                log.info(f"Embedding dimension: {len(embeddings[0])} ({ollama_model})")
            ids = [f"chunk_{i}" for i in range(start, end)]
            metadatas = []
            for c in batch:
                meta: dict = {
                    "repo": c.repo,
                    "path": c.path,
                    "heading": (c.heading[:200] if c.heading else ""),
                }
                if c.start_line is not None and c.end_line is not None:
                    meta["start_line"] = c.start_line
                    meta["end_line"] = c.end_line
                metadatas.append(meta)
            collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=texts,
            )
            if pbar is not None:
                pbar.update(len(batch))
            elif verbose:
                log.info(f"  Added {end}/{len(chunks)} chunks...")
    else:
        from sentence_transformers import SentenceTransformer
        from transformers.utils import logging as transformers_logging
        from huggingface_hub import logging as hf_logging
        transformers_logging.set_verbosity_error()
        hf_logging.set_verbosity_error()
        with contextlib.redirect_stdout(io.StringIO()):
            model = SentenceTransformer(
                str(cfg["embed_model"]),
                trust_remote_code=bool(cfg["trust_remote_code"]),
            )
        emb_dim = model.get_sentence_embedding_dimension()
        if verbose:
            log.info(f"Embedding dimension: {emb_dim} ({cfg['embed_model']})")
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
            metadatas = []
            for c in batch:
                meta: dict = {
                    "repo": c.repo,
                    "path": c.path,
                    "heading": (c.heading[:200] if c.heading else ""),
                }
                if c.start_line is not None and c.end_line is not None:
                    meta["start_line"] = c.start_line
                    meta["end_line"] = c.end_line
                metadatas.append(meta)
            collection.add(
                ids=ids,
                embeddings=embeddings.tolist(),
                metadatas=metadatas,
                documents=texts,
            )
            if pbar is not None:
                pbar.update(len(batch))
            elif verbose:
                log.info(f"  Added {end}/{len(chunks)} chunks...")
    if pbar is not None:
        pbar.close()

    if verbose:
        log.info(f"Indexed {len(chunks)} chunks into {persist_dir}")
    return len(chunks)
