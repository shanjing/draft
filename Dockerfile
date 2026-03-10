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

# Install CPU-only PyTorch first — prevents sentence-transformers from pulling
# CUDA wheels. On ARM64 (Apple Silicon / Graviton / Tau T2A) torch is already
# CPU-only; this guards against CUDA bloat on x86_64.
RUN pip install --no-cache-dir \
    torch --extra-index-url https://download.pytorch.org/whl/cpu

# Install remaining requirements, excluding pytest (dev-only).
# torch is already installed; pip will not upgrade to a CUDA variant.
RUN grep -v '^pytest' requirements.txt \
    | pip install --no-cache-dir -r /dev/stdin

# ---- Stage 2: final runtime ----
# Only contains the Python runtime, the virtualenv, and application code.
# No build tools, no pip cache, no dev dependencies.
FROM python:3.12-slim

WORKDIR /app

# Copy the entire virtualenv from builder — cleaner than copying individual
# site-packages dirs and captures any .so files installed outside the default path.
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code (respects .dockerignore)
COPY . .

# MCP HTTP server (8059) and optional UI (8058)
EXPOSE 8059 8058

# Default: run MCP server.
# To run the UI instead, override CMD in docker run or the Helm chart:
#   python -m uvicorn ui.app:app --host 0.0.0.0 --port 8058
CMD ["python", "scripts/serve_mcp.py", "-p", "8059"]
