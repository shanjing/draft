"""
Ollama embedding and reranking API. Use local Ollama models instead of downloading from Hugging Face.
"""
import json
import urllib.request


OLLAMA_BASE = "http://localhost:11434"


def rerank(model: str, query: str, documents: list[str], top_n: int = 3) -> list[tuple[str, float]]:
    """
    Rerank documents via Ollama /api/rerank. Returns list of (document, score) sorted by score desc.
    """
    payload = {"model": model, "query": query, "documents": documents, "top_n": top_n}
    req = urllib.request.Request(
        f"{OLLAMA_BASE}/api/rerank",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())
    results = data.get("results", [])
    return [(r.get("document", ""), float(r.get("relevance_score", 0))) for r in results]


def embed(model: str, texts: list[str], *, batch_size: int = 64) -> list[list[float]]:
    """
    Get embeddings from Ollama /api/embed. Returns list of embedding vectors.
    Batches requests to avoid timeouts.
    """
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        payload = {"model": model, "input": batch}
        req = urllib.request.Request(
            f"{OLLAMA_BASE}/api/embed",
            data=json.dumps(payload).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode())
        embeds = data.get("embeddings", [])
        all_embeddings.extend(embeds)
    return all_embeddings


def is_ollama_embed_model(name: str) -> bool:
    """True if name is an Ollama embedding model (e.g. qwen3-embedding:8b, nomic-embed-text)."""
    n = (name or "").strip().lower()
    return ("embed" in n or "embedding" in n) and "/" not in n.split(":")[0]
