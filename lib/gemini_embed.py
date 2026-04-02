"""Gemini Embedding 2 provider for Draft RAG.

Uses the new google-genai SDK (google.genai) to call embed_content().
Set DRAFT_EMBED_PROVIDER=gemini and
DRAFT_EMBED_MODEL=gemini-embedding-2-preview
(or another Gemini embedding model) in .env, then rebuild the vector index.
"""

from __future__ import annotations

import logging

# Gemini batchEmbedContents API max items per request.
_GEMINI_BATCH_LIMIT = 100


def embed(texts: list[str], model: str, api_key: str) -> list[list[float]]:
    """Embed a list of text strings using a Gemini embedding model.

    Splits into sub-batches of up to 100 (API limit) and concatenates results.
    Returns a list of embedding vectors (one per input text).
    """
    # Suppress noisy request logs from the Google client stack.
    loggers = (
        "urllib3",
        "httpx",
        "httpcore",
        "google.genai",
        "google_genai",
        "google_genai.models",
    )
    for _logger_name in loggers:
        logging.getLogger(_logger_name).setLevel(logging.WARNING)

    try:
        from google import genai  # google-genai package
    except ImportError as exc:
        raise ImportError(
            "Gemini embedding requires the `google-genai` package. "
            "Run `pip install google-genai` "
            "(or reinstall from requirements) and retry."
        ) from exc

    client = genai.Client(api_key=api_key)
    results: list[list[float]] = []
    for i in range(0, len(texts), _GEMINI_BATCH_LIMIT):
        batch = texts[i:i + _GEMINI_BATCH_LIMIT]
        response = client.models.embed_content(model=model, contents=batch)
        results.extend(list(e.values) for e in response.embeddings)
    return results
