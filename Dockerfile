# ---- Stage 1: builder ----
# Installs all Python dependencies into an isolated virtualenv.
# Build tools and pip cache are discarded after this stage.
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc build-essential && \
    rm -rf /var/lib/apt/lists/*

# Create a self-contained virtualenv so the final stage gets a clean,
# portable copy without hunting down stray .so files in /usr/local.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .

# Build mode args:
#   ONNX_ONLY=1   — skip PyTorch/sentence-transformers (saves ~2 GB); required for ONNX_GPU=1
#   ONNX_GPU=1    — install onnxruntime-gpu instead of onnxruntime (mutually exclusive packages)
#                   implies ONNX_ONLY=1; requires a CUDA-capable base image at runtime
ARG ONNX_ONLY=0
ARG ONNX_GPU=0

# Install CPU-only PyTorch first (skipped for ONNX-only or GPU builds).
RUN if [ "$ONNX_ONLY" = "0" ] && [ "$ONNX_GPU" = "0" ]; then \
      pip install --no-cache-dir torch --extra-index-url https://download.pytorch.org/whl/cpu; \
    fi

# Install requirements, excluding pytest (dev-only).
# ONNX_GPU=1 or ONNX_ONLY=1: exclude torch/sentence-transformers/transformers and swap
# onnxruntime for onnxruntime-gpu (these two packages are mutually exclusive on PyPI).
RUN if [ "$ONNX_GPU" = "1" ] || [ "$ONNX_ONLY" = "1" ]; then \
      grep -v -E '^(pytest|sentence-transformers|transformers[^/]|onnxruntime[^-])' requirements.txt \
        | pip install --no-cache-dir -r /dev/stdin; \
      if [ "$ONNX_GPU" = "1" ]; then \
        pip install --no-cache-dir onnxruntime-gpu; \
      fi; \
    else \
      grep -v '^pytest' requirements.txt \
        | pip install --no-cache-dir -r /dev/stdin; \
    fi

# ---- Stage 2: final runtime ----
# Only contains the Python runtime, the virtualenv, and application code.
# No build tools, no pip cache, no dev dependencies.
FROM python:3.12-slim

# Non-root app user — runs the server without root privileges.
# UID/GID 1000 is the conventional first non-system user on Linux.
RUN groupadd -r app --gid 1000 && \
    useradd -r -g app --uid 1000 --home /home/app --create-home app

WORKDIR /app

# Copy the entire virtualenv from builder — cleaner than copying individual
# site-packages dirs and captures any .so files installed outside the default path.
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code (respects .dockerignore)
COPY --chown=app:app . .

# ONNX models — baked in for air-gapped deployment.
# Place onnx_models/ in the build context (created by scripts/export_onnx.py).
# The directory is optional; the COPY uses a wildcard so the build succeeds
# even if the directory is absent (non-ONNX builds).
COPY --chown=app:app onnx_model[s]/ /app/onnx_models/

# Default ONNX env vars (overridable at runtime).
# These only take effect when DRAFT_EMBED_PROVIDER=onnx is set in .env or env.
ENV DRAFT_ONNX_EMBED_DIR=/app/onnx_models/embed
ENV DRAFT_ONNX_RERANK_DIR=/app/onnx_models/rerank

# MCP HTTP server (8059) and optional UI (8058)
EXPOSE 8059 8058

USER app

# Default: run MCP server.
# To run the UI instead, override CMD in docker run or the Helm chart:
#   python -m uvicorn ui.app:app --host 0.0.0.0 --port 8058
CMD ["python", "scripts/serve_mcp.py", "-p", "8059"]
