"""
The main library for the RAG feature.
RAG over draft docs: semantic search + LLM (Claude or Ollama).
Strict "answer only from context" prompting. Returns streamed text + citations.

What makes our RAG system?
1. Our vector store (ChromaDB for this MVP)
2. A strict context-only prompt to the LLM, see SYSTEM_PROMPT in prompts.py
3. A way to retrieve the chunks from the vector store, see retrieve() in this file
4. A way to stream the response from the LLM, see ask_stream() in this file

There are limitations to this MVP RAG system:
1. Not able to rebuild dynamically based on new files. #TODO
2. Scalability is limited by the LLM and the vector store. #TODO
3. too many to mention...
"""
import os
from pathlib import Path

from lib.ingest import VECTOR_DIR, COLLECTION_NAME, EMBED_MODEL, TRUST_REMOTE_CODE  # noqa: F401
from lib.log import get_logger
from lib.manifest import parse_sources_yaml
from lib.paths import get_effective_repo_root, get_sources_yaml_path, get_vault_root
from lib.prompts import SYSTEM_PROMPT

log = get_logger(__name__)
_EMBED_MODEL_CACHE: dict[tuple[str, bool], object] = {}


def _env_strip(key: str, default: str = "") -> str:
    """Get env var and strip surrounding whitespace and quotes (safe for .env and Docker --env-file)."""
    val = os.environ.get(key, default)
    if not isinstance(val, str):
        return default
    return val.strip().strip("'\"")


def _ensure_env_loaded(draft_root: Path) -> None:
    """Load .env from draft root so DRAFT_LLM_* and OLLAMA_MODEL are set (MarginCall-style)."""
    env_path = draft_root / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=False)  # do not override already-set vars
    except ImportError:
        pass


def llm_ready(draft_root: Path) -> bool:
    """True if a valid LLM is configured: local (Ollama model set) or cloud with non-empty API key. No network check."""
    _ensure_env_loaded(draft_root)
    provider = _env_strip("DRAFT_LLM_PROVIDER", "").lower()
    cloud_model = _env_strip("CLOUD_AI_MODEL")
    local_model = _env_strip("LOCAL_AI_MODEL")
    ollama_model = _env_strip("OLLAMA_MODEL")
    if not provider and cloud_model:
        provider = "gemini"
    if not provider and (local_model or ollama_model):
        provider = "ollama"
    if not provider:
        provider = "ollama"
    if provider == "ollama":
        return bool(ollama_model or local_model)
    if provider == "claude":
        return bool(_env_strip("ANTHROPIC_API_KEY"))
    if provider == "gemini":
        return bool(_env_strip("GEMINI_API_KEY") or _env_strip("GOOGLE_API_KEY"))
    if provider == "openai":
        return bool(_env_strip("OPENAI_API_KEY"))
    return False


# Vector search returns top RETRIEVAL_TOP_K; cross-encoder reranks to RERANK_TOP_N for LLM.
RETRIEVAL_TOP_K = 10
RERANK_TOP_N = 3
CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def _get_cross_encoder_model() -> str:
    """Cross-encoder model name; DRAFT_CROSS_ENCODER_MODEL env overrides default. Strips quotes for Docker --env-file."""
    return _env_strip("DRAFT_CROSS_ENCODER_MODEL", "") or CROSS_ENCODER_MODEL

_CROSS_ENCODER_CACHE: dict[str, object] = {}


def _coerce_bool(v, default: bool) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("1", "true", "yes", "y", "on"):
            return True
        if s in ("0", "false", "no", "n", "off"):
            return False
    return default


def _get_embedding_model(embed_model: str | None = None, trust_remote_code: bool | None = None):
    try:
        import numpy as np
        major = int(np.__version__.split(".")[0])
        if major >= 2:
            raise RuntimeError("NumPy 2.x not compatible. Run: pip install 'numpy<2'")
    except ImportError:
        pass
    from sentence_transformers import SentenceTransformer
    model_name = embed_model or EMBED_MODEL
    trust = TRUST_REMOTE_CODE if trust_remote_code is None else bool(trust_remote_code)
    key = (model_name, trust)
    if key not in _EMBED_MODEL_CACHE:
        _EMBED_MODEL_CACHE[key] = SentenceTransformer(model_name, trust_remote_code=trust)
    return _EMBED_MODEL_CACHE[key]


def _get_collection(draft_root: Path):
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
    import numpy as np  # Chroma/DuckDB expect numpy to be available; load before chromadb
    import chromadb
    from chromadb.config import Settings
    persist_dir = draft_root / VECTOR_DIR
    if not persist_dir.is_dir():
        return None
    client = chromadb.PersistentClient(
        path=str(persist_dir),
        settings=Settings(anonymized_telemetry=False),
    )
    try:
        return client.get_collection(COLLECTION_NAME)
    except Exception:
        return None


def _get_cross_encoder(model_name: str | None = None):
    """Load and cache CrossEncoder for reranking. Uses HF_HOME if set (e.g. by ingest)."""
    name = model_name or _get_cross_encoder_model()
    if name not in _CROSS_ENCODER_CACHE:
        from sentence_transformers import CrossEncoder
        _CROSS_ENCODER_CACHE[name] = CrossEncoder(name)
    return _CROSS_ENCODER_CACHE[name]


def rerank(query: str, chunks: list[dict], top_n: int = RERANK_TOP_N) -> list[dict]:
    """
    Rerank chunks using Hugging Face cross-encoder only. Returns top_n chunks with "score" attached.
    """
    if not chunks:
        return []
    model_name = _get_cross_encoder_model()
    # HF CrossEncoder: strip :tag from model name if present
    hf_model = model_name.split(":")[0] if ":" in model_name else model_name
    model = _get_cross_encoder(hf_model)
    pairs = [(query, c.get("text", "") or "") for c in chunks]
    scores = model.predict(pairs)
    indexed = list(zip(scores.tolist(), chunks))
    indexed.sort(key=lambda x: x[0], reverse=True)
    out = []
    for score, c in indexed[:top_n]:
        item = dict(c)
        item["score"] = round(float(score), 4)
        out.append(item)
    return out


def retrieve(draft_root: Path, query: str, top_k: int = RETRIEVAL_TOP_K) -> list[dict]:
    """
    Semantic search over the vector store. Returns list of
    {"repo", "path", "heading", "text"} for the top-k chunks.
    """
    coll = _get_collection(draft_root)
    if coll is None:
        return []
    meta = (getattr(coll, "metadata", None) or {})
    embed_model = meta.get("embed_model") or EMBED_MODEL
    embed_provider = (meta.get("embed_provider") or "").strip().lower()
    trust_remote_code = _coerce_bool(meta.get("trust_remote_code"), TRUST_REMOTE_CODE)

    def _query_with_hf(model_name: str, trust: bool):
        model = _get_embedding_model(model_name, trust)
        q_emb = model.encode([query], show_progress_bar=False)
        return coll.query(
            query_embeddings=q_emb.tolist(),
            n_results=min(top_k, 20),
            include=["metadatas", "documents"],
        )

    def _query_with_ollama(ollama_model: str):
        from lib.ollama_embed import embed as ollama_embed
        q_embs = ollama_embed(ollama_model, [query], batch_size=1)
        if not q_embs:
            return {"metadatas": [[]], "documents": [[]]}
        return coll.query(
            query_embeddings=[q_embs[0]],
            n_results=min(top_k, 20),
            include=["metadatas", "documents"],
        )

    try:
        if embed_provider == "ollama":
            result = _query_with_ollama(embed_model)
        else:
            result = _query_with_hf(embed_model, trust_remote_code)
    except Exception as e:
        msg = str(e)
        # Backward-compat: old collections may be quick-built but missing metadata.
        if "Embedding dimension" in msg and "collection dimensionality" in msg and embed_model != "sentence-transformers/all-MiniLM-L6-v2":
            result = _query_with_hf("sentence-transformers/all-MiniLM-L6-v2", False)
        else:
            raise
    out = []
    metadatas = result.get("metadatas") or []
    documents = result.get("documents") or []
    meta_list = metadatas[0] if metadatas else []
    docs_list = documents[0] if documents else []
    for i, m in enumerate(meta_list):
        item = {
            "repo": m.get("repo", ""),
            "path": m.get("path", ""),
            "heading": m.get("heading") or "",
            "text": docs_list[i] if i < len(docs_list) else (m.get("text") or ""),
        }
        sl, el = m.get("start_line"), m.get("end_line")
        if sl is not None and el is not None:
            try:
                item["start_line"] = int(sl)
                item["end_line"] = int(el)
            except (TypeError, ValueError):
                pass
        out.append(item)
    return out


def _build_context(chunks: list[dict]) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        repo, path, heading, text = c.get("repo", ""), c.get("path", ""), c.get("heading", ""), c.get("text", "")
        parts.append(f"[Source {i}: {repo}/{path}" + (f" — {heading}" if heading else "") + "]\n" + (text or "")[:8000])
    return "\n\n---\n\n".join(parts)


def _build_citations(draft_root: Path, chunks: list[dict]) -> list[dict]:
    """Build citation dicts with optional start_line, end_line, snippet, score."""
    repos_config: dict = {}
    sources_yaml = get_sources_yaml_path()
    if sources_yaml.is_file():
        repos_config = parse_sources_yaml(sources_yaml)

    citations = []
    for c in chunks:
        cit: dict = {
            "repo": c.get("repo", ""),
            "path": c.get("path", ""),
            "heading": c.get("heading") or "",
        }
        if "score" in c:
            cit["score"] = c["score"]
        start_line = c.get("start_line")
        end_line = c.get("end_line")
        if start_line is not None and end_line is not None and isinstance(start_line, int) and isinstance(end_line, int):
            repo_name = cit["repo"]
            path_str = cit["path"]
            if repo_name == "vault":
                root = get_vault_root()
            else:
                source = (repos_config.get(repo_name) or {}).get("source") or ""
                root = get_effective_repo_root(repo_name, source, draft_root)
            full = root / path_str
            snippet = ""
            if full.is_file():
                try:
                    lines = full.read_text(encoding="utf-8", errors="replace").splitlines()
                    start = max(1, min(start_line, len(lines)))
                    end = min(max(start, end_line), len(lines))
                    snippet = "\n".join(lines[start - 1 : end])
                except OSError:
                    pass
            cit["start_line"] = start_line
            cit["end_line"] = end_line
            cit["snippet"] = snippet
        citations.append(cit)
    return citations

#the entry point for RAG retrieval and LLM processing
def ask_stream(draft_root: Path, query: str, *, debug: bool = False, show_prompt: bool = False):
    """
    Retrieve top-k chunks, rerank with cross-encoder to top-n, call LLM, stream response.
    Yields: ("models", dict), ("prompt", dict) if show_prompt, ("text", str), ("citations", list), ("error", str).
    When debug=True, logs embed_model, cross_encoder_model, retrieval count, and rerank scores.
    When show_prompt=True, yields ("prompt", {"system": str, "user": str}) with the final prompt before calling the LLM.
    """
    # Use same HF cache as ingest for cross-encoder
    hf_cache = draft_root / ".cache" / "huggingface"
    hf_cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(hf_cache))

    coll = _get_collection(draft_root)
    meta = (getattr(coll, "metadata", None) or {}) if coll else {}
    embed_model = meta.get("embed_model") or EMBED_MODEL

    chunks = retrieve(draft_root, query, top_k=RETRIEVAL_TOP_K)
    if debug:
        log.info(f"embed_model: {embed_model}")
        log.info(f"cross_encoder_model: {_get_cross_encoder_model()}")
        log.info(f"retrieval: {len(chunks)} chunks (top_k={RETRIEVAL_TOP_K})")

    chunks = rerank(query, chunks, top_n=RERANK_TOP_N)
    #log the rerank scores for debugging
    if debug and chunks:
        for i, c in enumerate(chunks, 1):
            score = c.get("score", "?")
            label = f"{c.get('repo', '')}/{c.get('path', '')}"
            if c.get("heading"):
                label += f" — {c.get('heading', '')}"
            log.info(f"rerank #{i} score={score} {label}")

    citations = _build_citations(draft_root, chunks)

    # Compute LLM model for display (before early return)
    _ensure_env_loaded(draft_root)
    provider = _env_strip("DRAFT_LLM_PROVIDER", "").lower()
    model_override = _env_strip("DRAFT_LLM_MODEL") or None
    cloud_model = _env_strip("CLOUD_AI_MODEL")
    local_model = _env_strip("LOCAL_AI_MODEL")
    if local_model and local_model.startswith("ollama_chat/"):
        local_model = local_model.replace("ollama_chat/", "", 1)
    if not provider and cloud_model:
        provider = "gemini"
    if not provider and (local_model or _env_strip("OLLAMA_MODEL")):
        provider = "ollama"
    ollama_model = _env_strip("OLLAMA_MODEL") or local_model or "qwen3:8b"
    if provider == "claude" or (not provider and _env_strip("ANTHROPIC_API_KEY")):
        llm_model = model_override or "claude-3-5-sonnet-20241022"
    elif provider == "gemini":
        llm_model = (model_override or cloud_model or "gemini-2.5-flash").strip()
    elif provider == "openai":
        llm_model = model_override or "gpt-4o-mini"
    else:
        llm_model = ollama_model

    # Emit model info after retrieval+rerank, before streaming
    yield ("models", {
        "embed_model": embed_model,
        "cross_encoder_model": _get_cross_encoder_model(),
        "llm_model": llm_model,
    })

    if not chunks:
        yield ("error", "No indexed documents. Run 'python scripts/index_for_ai.py' to build the AI index.")
        return

    context = _build_context(chunks)
    user_content = f"Context from documentation:\n\n{context}\n\n---\n\nQuestion: {query}"

    if show_prompt:
        yield ("prompt", {"system": SYSTEM_PROMPT, "user": user_content})

    if provider == "claude" or (not provider and _env_strip("ANTHROPIC_API_KEY")):
        api_key = _env_strip("ANTHROPIC_API_KEY")
        if api_key:
            yield from _stream_claude(user_content, api_key, model_override)
        else:
            yield from _stream_ollama(user_content, ollama_model)
    elif provider == "gemini":
        api_key = _env_strip("GEMINI_API_KEY") or _env_strip("GOOGLE_API_KEY")
        if api_key:
            yield from _stream_gemini(user_content, api_key, (model_override or cloud_model).strip() or None)
        else:
            yield ("error", "GEMINI_API_KEY or GOOGLE_API_KEY not set. Run setup.sh to configure.")
    elif provider == "openai":
        api_key = _env_strip("OPENAI_API_KEY")
        if api_key:
            yield from _stream_openai(user_content, api_key, model_override)
        else:
            yield ("error", "OPENAI_API_KEY not set. Run setup.sh to configure.")
    elif provider == "ollama" or not provider:
        yield from _stream_ollama(user_content, ollama_model)
    else:
        yield ("error", f"Unknown DRAFT_LLM_PROVIDER={provider}. Use ollama, claude, gemini, or openai.")

    yield ("citations", citations)


def _stream_claude(user_content: str, api_key: str, model_override: str | None = None):
    import anthropic
    model = model_override or "claude-3-5-sonnet-20241022"
    client = anthropic.Anthropic(api_key=api_key)
    try:
        with client.messages.stream(
            model=model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        ) as stream:
            for text in stream.text_stream:
                if text:
                    yield ("text", text)
    except Exception as e:
        yield ("error", str(e))


def _stream_gemini(user_content: str, api_key: str, model_override: str | None = None):
    import google.generativeai as genai
    model_name = model_override or "gemini-2.5-flash"
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    try:
        full_prompt = f"{SYSTEM_PROMPT}\n\n{user_content}"
        response = model.generate_content(full_prompt, stream=True)
        for chunk in response:
            if chunk.text:
                yield ("text", chunk.text)
    except Exception as e:
        yield ("error", str(e))


def _stream_openai(user_content: str, api_key: str, model_override: str | None = None):
    from openai import OpenAI
    model_name = model_override or "gpt-4o-mini"
    client = OpenAI(api_key=api_key)
    try:
        stream = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=1024,
            stream=True,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield ("text", chunk.choices[0].delta.content)
    except Exception as e:
        yield ("error", str(e))


def _stream_ollama(user_content: str, model_name: str | None = None):
    import urllib.request
    import json
    from lib.ollama_embed import OLLAMA_BASE
    model = model_name or "qwen3:8b"
    try:
        req = urllib.request.Request(
            f"{OLLAMA_BASE}/api/generate",
            data=json.dumps({
                "model": model,
                "prompt": f"{SYSTEM_PROMPT}\n\n{user_content}",
                "stream": True,
            }).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            for line in resp:
                line = line.decode().strip()
                if not line:
                    continue
                obj = json.loads(line)
                if obj.get("response"):
                    yield ("text", obj["response"])
                if obj.get("done"):
                    break
    except Exception as e:
        yield ("error", f"Ollama: {e}. Is Ollama running? Try: ollama run {model}")
