# =============================================================================
# JuniperCascorWorker — Distributed CasCor Training Worker
# Multi-stage Dockerfile for production deployment
# =============================================================================
# Build: docker build -t juniper-cascor-worker:latest .
# Run:   docker run -e CASCOR_SERVER_URL=ws://juniper-cascor:8200/ws/v1/workers juniper-cascor-worker:latest
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder — Install dependencies
# -----------------------------------------------------------------------------
FROM python:3.14-slim AS builder

WORKDIR /build

# Install build tools
RUN pip install --no-cache-dir --upgrade pip wheel setuptools

# Install CPU-only PyTorch first (avoids pulling CUDA which is ~4 GB)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install pinned dependencies from lockfile (best layer caching)
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

# Copy project files and install without deps (already installed above)
COPY pyproject.toml README.md LICENSE ./
COPY juniper_cascor_worker/ ./juniper_cascor_worker/
RUN pip install --no-cache-dir --no-deps .

# -----------------------------------------------------------------------------
# Stage 2: Runtime — Minimal production image
# -----------------------------------------------------------------------------
FROM python:3.14-slim AS runtime

LABEL org.opencontainers.image.title="JuniperCascorWorker"
LABEL org.opencontainers.image.description="Distributed training worker for the JuniperCascor neural network service"
LABEL org.opencontainers.image.authors="Paul Calnon"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.source="https://github.com/pcalnon/juniper-cascor-worker"

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
ENV CASCOR_SERVER_URL=ws://localhost:8200/ws/v1/workers
ENV CASCOR_HEARTBEAT_INTERVAL=10.0

# Health check — process-based (worker is a WebSocket client, not an HTTP server)
# Verifies PID 1 (the entrypoint process) is still alive.
# start-period=15s: PyTorch + numpy initialization adds ~10s startup overhead
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD kill -0 1 2>/dev/null || exit 1

ENTRYPOINT ["juniper-cascor-worker"]
CMD ["--server-url", "ws://juniper-cascor:8200/ws/v1/workers"]
