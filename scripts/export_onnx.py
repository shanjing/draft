#!/usr/bin/env python3
"""Export embedding and cross-encoder models to ONNX format.

This script runs on a dev machine (requires PyTorch + transformers + sentence-transformers).
The output ONNX files + tokenizer files are what ship to production (no PyTorch needed there).

Usage:
    python scripts/export_onnx.py [--output-dir onnx_models]

Output layout:
    onnx_models/
    ├── embed/          # all-MiniLM-L6-v2
    │   ├── model.onnx
    │   ├── tokenizer.json
    │   ├── tokenizer_config.json
    │   ├── special_tokens_map.json
    │   └── vocab.txt
    └── rerank/         # cross-encoder/ms-marco-MiniLM-L-6-v2
        ├── model.onnx
        ├── tokenizer.json
        ├── tokenizer_config.json
        ├── special_tokens_map.json
        └── vocab.txt
"""

import argparse
import shutil
import sys
from pathlib import Path

DEFAULT_EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def export_embedding_model(model_name: str, output_dir: Path) -> None:
    """Export a sentence-transformers embedding model to ONNX."""
    import torch
    from transformers import AutoModel, AutoTokenizer

    print(f"Loading embedding model: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    model.eval()

    output_dir.mkdir(parents=True, exist_ok=True)

    # Save tokenizer files
    tokenizer.save_pretrained(str(output_dir))
    print(f"  Saved tokenizer to {output_dir}")

    # Export model to ONNX
    dummy_input = tokenizer(
        "This is a test sentence for export.",
        return_tensors="pt",
        padding="max_length",
        truncation=True,
        max_length=128,
    )
    onnx_path = output_dir / "model.onnx"

    input_names = ["input_ids", "attention_mask", "token_type_ids"]
    output_names = ["last_hidden_state"]
    dynamic_axes = {
        "input_ids": {0: "batch", 1: "sequence"},
        "attention_mask": {0: "batch", 1: "sequence"},
        "token_type_ids": {0: "batch", 1: "sequence"},
        "last_hidden_state": {0: "batch", 1: "sequence"},
    }

    with torch.no_grad():
        torch.onnx.export(
            model,
            (
                dummy_input["input_ids"],
                dummy_input["attention_mask"],
                dummy_input["token_type_ids"],
            ),
            str(onnx_path),
            input_names=input_names,
            output_names=output_names,
            dynamic_axes=dynamic_axes,
            opset_version=14,
        )

    size_mb = onnx_path.stat().st_size / (1024 * 1024)
    print(f"  Exported ONNX model: {onnx_path} ({size_mb:.1f} MB)")

    # Clean up unnecessary files (keep only what ONNX inference needs)
    for f in output_dir.iterdir():
        if f.name not in (
            "model.onnx",
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json",
            "vocab.txt",
        ):
            if f.is_file():
                f.unlink()
            elif f.is_dir():
                shutil.rmtree(f)


def export_rerank_model(model_name: str, output_dir: Path) -> None:
    """Export a cross-encoder reranking model to ONNX."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    print(f"Loading cross-encoder model: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name)
    model.eval()

    output_dir.mkdir(parents=True, exist_ok=True)

    # Save tokenizer files
    tokenizer.save_pretrained(str(output_dir))
    print(f"  Saved tokenizer to {output_dir}")

    # Export model to ONNX
    dummy_input = tokenizer(
        "What is the capital of France?",
        "Paris is the capital and largest city of France.",
        return_tensors="pt",
        padding="max_length",
        truncation=True,
        max_length=128,
    )
    onnx_path = output_dir / "model.onnx"

    input_names = ["input_ids", "attention_mask", "token_type_ids"]
    output_names = ["logits"]
    dynamic_axes = {
        "input_ids": {0: "batch", 1: "sequence"},
        "attention_mask": {0: "batch", 1: "sequence"},
        "token_type_ids": {0: "batch", 1: "sequence"},
        "logits": {0: "batch"},
    }

    with torch.no_grad():
        torch.onnx.export(
            model,
            (
                dummy_input["input_ids"],
                dummy_input["attention_mask"],
                dummy_input["token_type_ids"],
            ),
            str(onnx_path),
            input_names=input_names,
            output_names=output_names,
            dynamic_axes=dynamic_axes,
            opset_version=14,
        )

    size_mb = onnx_path.stat().st_size / (1024 * 1024)
    print(f"  Exported ONNX model: {onnx_path} ({size_mb:.1f} MB)")

    # Clean up unnecessary files
    for f in output_dir.iterdir():
        if f.name not in (
            "model.onnx",
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json",
            "vocab.txt",
        ):
            if f.is_file():
                f.unlink()
            elif f.is_dir():
                shutil.rmtree(f)


def main():
    parser = argparse.ArgumentParser(description="Export models to ONNX format for Draft RAG")
    parser.add_argument(
        "--output-dir", default="onnx_models", help="Output directory (default: onnx_models)"
    )
    parser.add_argument(
        "--embed-model", default=DEFAULT_EMBED_MODEL, help=f"Embedding model (default: {DEFAULT_EMBED_MODEL})"
    )
    parser.add_argument(
        "--rerank-model", default=DEFAULT_RERANK_MODEL, help=f"Rerank model (default: {DEFAULT_RERANK_MODEL})"
    )
    parser.add_argument(
        "--embed-only", action="store_true", help="Export only the embedding model"
    )
    parser.add_argument(
        "--rerank-only", action="store_true", help="Export only the rerank model"
    )
    args = parser.parse_args()

    output_root = Path(args.output_dir)

    if not args.rerank_only:
        export_embedding_model(args.embed_model, output_root / "embed")
        print()

    if not args.embed_only:
        export_rerank_model(args.rerank_model, output_root / "rerank")
        print()

    print(f"Done. ONNX models saved to: {output_root.resolve()}")
    print("Copy this directory to your Docker build context or K8s node for air-gapped deployment.")


if __name__ == "__main__":
    main()
