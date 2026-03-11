"""Gemini Embedding 2 provider for Draft RAG.

Uses the new google-genai SDK (google.genai) to call embed_content().
Set DRAFT_EMBED_PROVIDER=gemini and DRAFT_EMBED_MODEL=gemini-embedding-2-preview
(or another Gemini embedding model) in .env, then rebuild the vector index.
"""

from __future__ import annotations

import logging

_GEMINI_BATCH_LIMIT = 100  # Gemini batchEmbedContents API max items per request


def embed(texts: list[str], model: str, api_key: str) -> list[list[float]]:
    """Embed a list of text strings using a Gemini embedding model.

    Splits into sub-batches of up to 100 (API limit) and concatenates results.
    Returns a list of embedding vectors (one per input text).
    """
    # Suppress HTTP request logs (e.g. "HTTP Request: POST ... 200 OK") from the Google client
    for _logger_name in ("urllib3", "httpx", "httpcore", "google.genai", "google_genai", "google_genai.models"):
        logging.getLogger(_logger_name).setLevel(logging.WARNING)

    from google import genai  # google-genai package

    client = genai.Client(api_key=api_key)
    results: list[list[float]] = []
    for i in range(0, len(texts), _GEMINI_BATCH_LIMIT):
        batch = texts[i : i + _GEMINI_BATCH_LIMIT]
        response = client.models.embed_content(model=model, contents=batch)
        results.extend(list(e.values) for e in response.embeddings)
    return results
