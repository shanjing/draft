"""ONNX Runtime embedding provider for Draft RAG.

Replaces sentence-transformers (PyTorch) with ONNX Runtime (~50 MB) for embedding.
Uses the HF Rust tokenizer (tokenizers library) — no transformers dependency.

Usage:
    Set DRAFT_EMBED_PROVIDER=onnx and DRAFT_ONNX_EMBED_DIR=/path/to/onnx_models/embed
    in .env, then rebuild the vector index.

The model directory must contain:
    model.onnx          — exported embedding model (e.g. all-MiniLM-L6-v2)
    tokenizer.json      — HF fast tokenizer file
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

_SESSION_CACHE: dict[str, object] = {}
_TOKENIZER_CACHE: dict[str, object] = {}


def _get_providers() -> list[str]:
    """Return ONNX Runtime execution providers.

    Reads DRAFT_ONNX_PROVIDERS (comma-separated) if set, otherwise auto-detects:
    prefers CUDAExecutionProvider or TensorrtExecutionProvider when available,
    falls back to CPUExecutionProvider.
    """
    val = os.environ.get("DRAFT_ONNX_PROVIDERS", "").strip()
    if val:
        return [p.strip() for p in val.split(",")]
    try:
        import onnxruntime as ort
        available = ort.get_available_providers()
        for p in ("TensorrtExecutionProvider", "CUDAExecutionProvider"):
            if p in available:
                return [p, "CPUExecutionProvider"]
    except Exception:
        pass
    return ["CPUExecutionProvider"]


def _get_session(model_dir: str):
    """Load and cache an ONNX Runtime InferenceSession."""
    if model_dir not in _SESSION_CACHE:
        import onnxruntime as ort

        model_path = os.path.join(model_dir, "model.onnx")
        if not os.path.isfile(model_path):
            raise FileNotFoundError(f"ONNX model not found: {model_path}")
        _SESSION_CACHE[model_dir] = ort.InferenceSession(
            model_path, providers=_get_providers()
        )
    return _SESSION_CACHE[model_dir]


def _get_tokenizer(model_dir: str):
    """Load and cache a HF fast tokenizer from tokenizer.json."""
    if model_dir not in _TOKENIZER_CACHE:
        from tokenizers import Tokenizer

        tokenizer_path = os.path.join(model_dir, "tokenizer.json")
        if not os.path.isfile(tokenizer_path):
            raise FileNotFoundError(f"Tokenizer not found: {tokenizer_path}")
        _TOKENIZER_CACHE[model_dir] = Tokenizer.from_file(tokenizer_path)
    return _TOKENIZER_CACHE[model_dir]


def embed(texts: list[str], model_dir: str) -> list[list[float]]:
    """Embed texts using an ONNX model with mean pooling + L2 normalization.

    Args:
        texts: List of strings to embed.
        model_dir: Path to directory containing model.onnx and tokenizer.json.

    Returns:
        List of embedding vectors (one per input text).
    """
    if not texts:
        return []

    session = _get_session(model_dir)
    tokenizer = _get_tokenizer(model_dir)

    # Enable padding and truncation
    tokenizer.enable_padding()
    tokenizer.enable_truncation(max_length=512)

    encodings = tokenizer.encode_batch(texts)

    input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
    attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
    token_type_ids = np.zeros_like(input_ids, dtype=np.int64)

    # Build feed dict based on model inputs (some models don't take token_type_ids)
    input_names = {inp.name for inp in session.get_inputs()}
    feeds: dict[str, np.ndarray] = {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
    }
    if "token_type_ids" in input_names:
        feeds["token_type_ids"] = token_type_ids

    outputs = session.run(None, feeds)
    # outputs[0] shape: (batch, seq_len, hidden_dim) — token embeddings
    token_embeddings = outputs[0]

    # Mean pooling: average token embeddings weighted by attention_mask
    mask_expanded = attention_mask[:, :, np.newaxis].astype(np.float32)
    sum_embeddings = np.sum(token_embeddings * mask_expanded, axis=1)
    sum_mask = np.clip(mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
    mean_pooled = sum_embeddings / sum_mask

    # L2 normalize
    norms = np.linalg.norm(mean_pooled, axis=1, keepdims=True)
    norms = np.clip(norms, a_min=1e-9, a_max=None)
    normalized = mean_pooled / norms

    return normalized.tolist()
