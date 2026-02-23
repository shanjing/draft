"""
RAG over draft docs: semantic search + LLM (Claude or Ollama).
Strict "answer only from context" prompting. Returns streamed text + citations.
"""
import os
from pathlib import Path

from lib.ingest import VECTOR_DIR, COLLECTION_NAME, EMBED_MODEL, TRUST_REMOTE_CODE  # noqa: F401

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


TOP_K = 5

SYSTEM_PROMPT = """You are a direct, precise assistant. Answer only using the provided context from the user's private documentation. If the answer is not in the context, say you don't know. Do not guess or use external knowledge. Be concise and cite which doc/section when relevant."""


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


def retrieve(draft_root: Path, query: str, top_k: int = TOP_K) -> list[dict]:
    """
    Semantic search over the vector store. Returns list of
    {"repo", "path", "heading", "text"} for the top-k chunks.
    """
    coll = _get_collection(draft_root)
    if coll is None:
        return []
    meta = (getattr(coll, "metadata", None) or {})
    embed_model = meta.get("embed_model") or EMBED_MODEL
    trust_remote_code = _coerce_bool(meta.get("trust_remote_code"), TRUST_REMOTE_CODE)

    def _query_with(model_name: str, trust: bool):
        model = _get_embedding_model(model_name, trust)
        q_emb = model.encode([query], show_progress_bar=False)
        return coll.query(
            query_embeddings=q_emb.tolist(),
            n_results=min(top_k, 20),
            include=["metadatas", "documents"],
        )

    try:
        result = _query_with(embed_model, trust_remote_code)
    except Exception as e:
        msg = str(e)
        # Backward-compat: old collections may be quick-built but missing metadata.
        if "Embedding dimension" in msg and "collection dimensionality" in msg and embed_model != "sentence-transformers/all-MiniLM-L6-v2":
            result = _query_with("sentence-transformers/all-MiniLM-L6-v2", False)
        else:
            raise
    out = []
    metadatas = result.get("metadatas") or []
    documents = result.get("documents") or []
    meta_list = metadatas[0] if metadatas else []
    docs_list = documents[0] if documents else []
    for i, m in enumerate(meta_list):
        out.append({
            "repo": m.get("repo", ""),
            "path": m.get("path", ""),
            "heading": m.get("heading") or "",
            "text": docs_list[i] if i < len(docs_list) else (m.get("text") or ""),
        })
    return out


def _build_context(chunks: list[dict]) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        repo, path, heading, text = c.get("repo", ""), c.get("path", ""), c.get("heading", ""), c.get("text", "")
        parts.append(f"[Source {i}: {repo}/{path}" + (f" — {heading}" if heading else "") + "]\n" + (text or "")[:8000])
    return "\n\n---\n\n".join(parts)


def ask_stream(draft_root: Path, query: str):
    """
    Retrieve top-k chunks, call LLM with strict context-only prompt, stream response.
    Yields: ("text", str) for each delta, ("citations", list), ("error", str).
    """
    chunks = retrieve(draft_root, query, top_k=TOP_K)
    citations = [{"repo": c["repo"], "path": c["path"], "heading": c.get("heading") or ""} for c in chunks]

    if not chunks:
        yield ("error", "No indexed documents. Run 'python scripts/index_for_ai.py' to build the AI index.")
        return

    context = _build_context(chunks)
    user_content = f"Context from documentation:\n\n{context}\n\n---\n\nQuestion: {query}"

    _ensure_env_loaded(draft_root)
    provider = _env_strip("DRAFT_LLM_PROVIDER", "").lower()
    model_override = _env_strip("DRAFT_LLM_MODEL") or None
    cloud_model = _env_strip("CLOUD_AI_MODEL")
    local_model = _env_strip("LOCAL_AI_MODEL")
    if local_model and local_model.startswith("ollama_chat/"):
        local_model = local_model.replace("ollama_chat/", "", 1)

    # MarginCall-style: CLOUD_AI_MODEL set → cloud (Gemini); LOCAL_AI_MODEL or OLLAMA_MODEL → local
    if not provider and cloud_model:
        provider = "gemini"
    if not provider and (local_model or _env_strip("OLLAMA_MODEL")):
        provider = "ollama"

    ollama_model = _env_strip("OLLAMA_MODEL") or local_model or "qwen3:8b"

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
    model = model_name or "qwen3:8b"
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
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
