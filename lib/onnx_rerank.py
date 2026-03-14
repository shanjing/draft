"""ONNX Runtime cross-encoder reranker for Draft RAG.

Replaces sentence-transformers CrossEncoder (PyTorch) with ONNX Runtime.
Uses the HF Rust tokenizer (tokenizers library) — no transformers dependency.

Usage:
    Set DRAFT_ONNX_RERANK_DIR=/path/to/onnx_models/rerank in .env.

The model directory must contain:
    model.onnx          — exported cross-encoder (e.g. ms-marco-MiniLM-L-6-v2)
    tokenizer.json      — HF fast tokenizer file
"""

from __future__ import annotations

import os

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
            raise FileNotFoundError(f"ONNX rerank model not found: {model_path}")
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


def predict(query: str, passages: list[str], model_dir: str) -> list[float]:
    """Score (query, passage) pairs using an ONNX cross-encoder model.

    Args:
        query: The search query.
        passages: List of passage texts to score against the query.
        model_dir: Path to directory containing model.onnx and tokenizer.json.

    Returns:
        List of relevance scores (one per passage), matching CrossEncoder.predict() shape.
    """
    if not passages:
        return []

    session = _get_session(model_dir)
    tokenizer = _get_tokenizer(model_dir)

    # Enable padding and truncation for pair encoding
    tokenizer.enable_padding()
    tokenizer.enable_truncation(max_length=512)

    # Encode (query, passage) pairs
    encodings = tokenizer.encode_batch([(query, p) for p in passages])

    input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
    attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
    token_type_ids = np.array([e.type_ids for e in encodings], dtype=np.int64)

    # Build feed dict based on model inputs
    input_names = {inp.name for inp in session.get_inputs()}
    feeds: dict[str, np.ndarray] = {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
    }
    if "token_type_ids" in input_names:
        feeds["token_type_ids"] = token_type_ids

    outputs = session.run(None, feeds)
    logits = outputs[0]  # shape: (batch, num_labels) or (batch,)

    # Cross-encoder for relevance: take the raw logit score.
    # For single-label models (ms-marco-MiniLM), logits shape is (batch, 1).
    if logits.ndim == 2 and logits.shape[1] == 1:
        scores = logits[:, 0]
    elif logits.ndim == 2:
        # Multi-label: take the last column (positive class)
        scores = logits[:, -1]
    else:
        scores = logits

    return scores.tolist()
