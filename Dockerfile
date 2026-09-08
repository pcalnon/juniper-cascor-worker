# =============================================================================
# JuniperCascorWorker — Distributed CasCor Training Worker
# Multi-stage Dockerfile for production deployment
# =============================================================================
# Build: docker build -t juniper-cascor-worker:latest .
# Run:   docker run -e JUNIPER_CASCOR_WORKER_SERVER_URL=ws://juniper-cascor:8200/ws/v1/workers juniper-cascor-worker:latest
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder — Install dependencies
# -----------------------------------------------------------------------------
FROM python:3.14-slim AS builder

WORKDIR /build

# Install build tools
RUN pip install --no-cache-dir --upgrade pip wheel setuptools

# CW-02 (Phase 4E): the CPU-only lock keeps the runtime image slim. requirements-cpu.lock
# is compiled with ``--no-emit-package torch`` and an ``--override torch==X.Y.Z+cpu`` (its
# header carries the exact recipe), so torch is installed here, separately, from the
# PyTorch CPU index. Two rules make that actually CPU-only, and both were missing when
# the 2026-09-07 image shipped torch 2.12.1+cu130 plus the whole nvidia-*/triton stack
# (3 GB per Raspberry Pi node):
#
#   1. PIN torch to the lock header's ``+cpu`` version. The lock's torch-derived pins
#      (setuptools==70.2.0, sympy, networkx, ...) are only consistent with THAT torch;
#      an unpinned install gets the newest CPU wheel, and when its requirements disagree
#      (torch>=2.13 needs setuptools>=77) the next pip install re-resolves torch.
#   2. Give the lock install the CPU index too, and the same pin. pip only searches the
#      indexes it is given, so without this a re-resolution can only find the CUDA build
#      on PyPI; with it, torch can only ever be the +cpu wheel, and a genuine conflict
#      fails the build instead of silently swapping the stack.
#
# ``--extra-index-url`` and not ``--index-url`` on the lock install: the CPU index serves
# torch and a few of its deps but 403s the rest of the lock (pydantic, websockets), so
# REPLACING the default index breaks the build. Keep ARG TORCH_VERSION equal to the lock
# header's override -- tests/test_dockerfile_cpu_torch_pin.py fails otherwise, and
# util/check_image_cpu_only.py asserts the built image inside the publish workflow. The
# companion ``requirements.lock`` (full NVIDIA stack) remains for non-Docker GPU dev installs.
ARG TORCH_VERSION=2.12.0
ARG TORCH_CPU_INDEX=https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir "torch==${TORCH_VERSION}+cpu" --index-url "${TORCH_CPU_INDEX}"

# Install pinned dependencies from lockfile (best layer caching)
COPY requirements-cpu.lock ./
RUN pip install --no-cache-dir --extra-index-url "${TORCH_CPU_INDEX}" "torch==${TORCH_VERSION}+cpu" -r requirements-cpu.lock

# Copy project files and install without deps (already installed above), then prove the
# installed set is mutually consistent: a re-resolved, missing or conflicting dependency
# fails HERE, at build time, rather than on a Pi at import time.
COPY pyproject.toml README.md LICENSE ./
COPY juniper_cascor_worker/ ./juniper_cascor_worker/
RUN pip install --no-cache-dir --no-deps . && pip check

# -----------------------------------------------------------------------------
# Stage 2: Runtime — Minimal production image
# -----------------------------------------------------------------------------
FROM python:3.14-slim AS runtime

# Build provenance (juniper-ml notes/BUILD_PROVENANCE_DESIGN_2026-06-14.md):
# the deploy Makefile passes this worker's own git SHA, an ISO-8601 build
# timestamp, and the package version at build time. They are stamped as OCI
# labels and exported as env vars (below) so the running worker reports them
# on /v1/health and `make doctor` can detect stale-image drift. Default empty
# when the image is built bare (read back as None by the worker).
ARG GIT_SHA=""
ARG BUILD_DATE=""
ARG APP_VERSION=""

LABEL org.opencontainers.image.title="JuniperCascorWorker"
LABEL org.opencontainers.image.description="Distributed training worker for the JuniperCascor neural network service"
LABEL org.opencontainers.image.authors="Paul Calnon"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.source="https://github.com/pcalnon/juniper-cascor-worker"
LABEL org.opencontainers.image.revision="${GIT_SHA}"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
LABEL org.opencontainers.image.version="${APP_VERSION}"

# Create non-root user
RUN groupadd --gid 1000 juniper && \
    useradd --uid 1000 --gid juniper --shell /bin/bash --create-home juniper

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Create log directory
RUN mkdir -p logs && chown -R juniper:juniper /app

USER juniper

# Worker configuration (overridden by Docker Compose environment)
# CFG-06 (>= 0.4.0): canonical JUNIPER_CASCOR_WORKER_* env-var defaults.
# Legacy CASCOR_* names still work via the alias-with-deprecation helper
# but emit a DeprecationWarning per process; setting the canonical names
# here keeps the worker quiet by default when running the image bare.
ENV JUNIPER_CASCOR_WORKER_SERVER_URL=ws://localhost:8200/ws/v1/workers
ENV JUNIPER_CASCOR_WORKER_HEARTBEAT_INTERVAL=10.0

# Build provenance (see the ARG block in the runtime stage above): exported
# so the worker process can read its own source revision / build date and
# report them on /v1/health. Empty when built bare (read back as None).
ENV JUNIPER_CASCOR_WORKER_GIT_SHA=${GIT_SHA}
ENV JUNIPER_CASCOR_WORKER_BUILD_DATE=${BUILD_DATE}

# Health check — process-based (worker is a WebSocket client, not an HTTP server)
# Verifies PID 1 (the entrypoint process) is still alive.
# start-period=15s: PyTorch + numpy initialization adds ~10s startup overhead
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD kill -0 1 2>/dev/null || exit 1

ENTRYPOINT ["juniper-cascor-worker"]
CMD ["--server-url", "ws://juniper-cascor:8200/ws/v1/workers"]
