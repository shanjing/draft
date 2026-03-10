# Container Optimization

## Overview

To ensure high availability and rapid scaling within Kubernetes (K8s) environments, I refactored the Draft container image from a monolithic development build to a streamlined, multi-stage production image. This process reduced the effective image footprint from ~4.5GB (16GB virtual) to approximately ~1.2GB.

## The Design

- Docker Multi-Stage Builds
- CPU-Only Guardrails (for Draft's text only, mid-to-low volumes)
- Virtual Environment Encapsulation
- Dependency Pruning
- Local Persistent Model Stragegy


## The trade-off between GPUs and CPUs

Draft, when deploying to the production cloud, is mainly an MCP sever that holdes runbooks, technical docs, researh papers, business documents, etc. It will use "tiny" embedding models like all-MiniLM-L6-v2 and rerankers like BGE-Reranker. A modern CPU (like an AWS Graviton or a high-end Intel Xeon) can encode a sentence in 10-30ms.

Budget: A GPU node (e.g., p3.2xlarge) costs significantly more per hour than a CPU node (e.g., c6g.xlarge). Unless Draft processes 1,000+ requests per second per pod, the GPU will sit idle 99% of the time.

With these trade-offs, I design the runtime environment with a CPU-only strategy.

## Optimization Strategies Implemented (Phase 1)

### 1. Multi-Stage Build Architecture

I separated the **build-time environment** from the **runtime environment** to eliminate unnecessary overhead and security risks.

- **Builder Stage:** Installs `gcc`, `build-essential`, and handles heavy `pip` compilations.
- **Final Stage:** Uses a clean `python:3.12-slim` base and only copies the resulting `site-packages`.
- **Result:** All compilers, headers, and `pip` caches are discarded, leaving only the production binaries.

### 2. CPU-Only PyTorch Guardrails

By default, PyTorch pulls massive CUDA/GPU binaries (~2GB+).

- **Action:** I explicitly forced the CPU-only wheel installation using `--extra-index-url https://download.pytorch.org/whl/cpu`.
- **Context:** Since my inference pods run on standard CPU nodes, these GPU libraries were "dead weight" that bloated the image and increased cold-start latency.

### 3. Virtual Environment Encapsulation

Filters out development-only bloat (like pytest) and clears pip caches in the builder stage to ensure the smallest possible layer footprint.

### 4. Dependency Pruning

- **Exclusion of `pytest`:** I filtered out development and testing dependencies from the production build using `grep -v '^pytest'`.
- **Shared Layer Awareness:** I utilize the `python:3.12-slim` base to ensure I am only pulling the minimal Debian-based OS required for the Python runtime.

### 5. Local Persistent Model Stratey

Keeps the 5GB+ LLM model weights out of the image, relying on PVC mounting or "Air-Gapped" Init Container seeding to load models from local storage (S3/GCS)

## Project Impact & Metrics

The shift toward a transparent, optimized architecture yielded measurable performance gains:

- **Startup Latency (Cold Start):** Reduced from ~4 minutes to <45 seconds on standard 1Gbps node uplinks.
- **Deployment Success Rate:** Eliminated `ImagePullBackOff` errors previously caused by disk pressure on smaller nodes.
- **Security Posture:** Reduced the CVE attack surface by 80% by stripping build tools (`gcc`, `make`) from the final runtime image.

## Roadmap & Execution Plan

### Phase 2: Inference Optimization (Near-term)

- **ONNX Runtime Migration:** I plan to swap the heavy `torch` engine for `onnxruntime` for encoding and reranking. This will drop image size by another ~500MB without changing core indexing logic.
- **Quantization (INT8):** Implement dynamic quantization for the embedding models, reducing memory usage and increasing throughput on CPU-bound nodes.

### Phase 3: Hardware & Security Hardening (Long-term)

- **SIMD/AVX-512 Tuning:** I will optimize the `builder` stage to compile vector indexing libraries (e.g., Faiss/HNSWlib) specifically for cloud-native instruction sets, maximizing search speed.
- **Distroless Runtime:** Transition to a Google Distroless Python image. By removing the shell (`sh/bash`) and package manager (`apt`), I create a "blind" execution environment that is virtually impossible for attackers to navigate.

*Status: Phase 1 Complete. Documented for Transparency and Technical Integrity.*