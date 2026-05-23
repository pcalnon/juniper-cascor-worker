<!-- markdownlint-disable MD013 MD033 MD041 -->
<!--
  MD013 (line-length): README contains prose paragraphs that intentionally
                       exceed the 512-char ecosystem limit (canonical
                       §4 layout). Wrapping harms PyPI rendering.
  MD033 (no-inline-html): The right-aligned logo + spacing rely on HTML.
  MD041 (first-line-heading): The HTML logo is the first line by design.
  Mirrors the per-file disable applied in juniper-ml #283 and juniper-cascor #276.
-->
<div align="right" width="150px" height="150px" align="right" valign="top"> <img src="images/Juniper_Logo_150px.png" alt="Juniper" align="right" valign="top" width="150px" /></div>
<br /> <br /> <br /> <br />

# Juniper: Dynamic Neural Network Research Platform

Juniper is an AI/ML research platform for investigating dynamic neural network architectures and novel learning paradigms.  The project emphasizes ground-up implementations from primary literature, enabling a more transparent exploration of fundamental algorithms.

## Juniper Cascor Worker

`juniper-cascor-worker` is the **distributed candidate-training worker** of the Juniper platform. A worker process connects outbound to a running `juniper-cascor` instance on its `/ws/v1/workers` WebSocket endpoint, receives candidate-unit training tasks from the cascor service, and returns trained candidates so that the cascor service can select the next unit to recruit. The package supports two operating modes — a default WebSocket mode (`CascorWorkerAgent`) and a deprecated legacy mode (`CandidateTrainingWorker` over `multiprocessing.managers`, retained for transitional deployments). The worker is **managed by** `juniper-cascor` rather than imported by it: there is no code-import dependency between the two repositories, only a wire-protocol contract.

## Distribution

`juniper-cascor-worker` is published on PyPI as **[`juniper-cascor-worker`](https://pypi.org/project/juniper-cascor-worker/)**.
The package is also surfaced through the platform meta-distribution
**[`juniper-ml`](https://pypi.org/project/juniper-ml/)**, which installs
the full client stack via `pip install juniper-ml[all]`.

```bash
pip install juniper-cascor-worker
```

## Ecosystem Compatibility

This package is part of the [Juniper](https://github.com/pcalnon/juniper-ml) ecosystem.
Verified compatible versions:

| juniper-data | juniper-cascor | juniper-canopy | data-client | cascor-client | cascor-worker |
|--------------|----------------|----------------|-------------|---------------|---------------|
| 0.6.x        | 0.4.x          | 0.4.x          | >=0.4.1     | >=0.4.0       | >=0.3.0       |

For full-stack Docker deployment and integration tests, see [`juniper-deploy`](https://github.com/pcalnon/juniper-deploy).

## Architecture

`juniper-cascor-worker` is a long-running client process that connects outbound to `juniper-cascor`'s worker WebSocket. The worker holds the candidate-training computation; the cascor service holds the scheduling, candidate selection, and network-growth logic.

```text
┌─────────────────────────┐                  ┌──────────────────────┐
│  juniper-cascor-worker  │ ◄── X-API-Key ──►│   juniper-cascor     │
│  CascorWorkerAgent      │   over WSS/WS    │   Training Svc       │
│  (this package)         │ ──────────────►  │   /ws/v1/workers     │
│                         │   tensor frames  │   Port 8200          │
└─────────────────────────┘                  └──────────────────────┘
```

The worker authenticates with the `X-API-Key` header on connection, exchanges structured JSON control frames plus binary tensor frames for candidate-unit training, and reports task progress through periodic heartbeats. Multiple worker instances may be connected concurrently; `juniper-cascor` distributes candidate-pool training across them.

## Related Services

| Service | Relationship | Notes |
|---------|-------------|-------|
| [juniper-cascor](https://github.com/pcalnon/juniper-cascor) | Worker's upstream service; manages candidate-pool scheduling | Default URL `ws://juniper-cascor:8200/ws/v1/workers` |
| [juniper-deploy](https://github.com/pcalnon/juniper-deploy) | Provides the orchestrated `juniper-cascor-worker` Docker service | See `juniper-deploy/docker-compose.yml` |

## Service Configuration

Environment variables are read by `juniper_cascor_worker/config.py` and grouped by mode. Default mode (WebSocket) reads only the WebSocket variables; `--legacy` mode reads only the legacy variables. The shared variables (logging, health-probe surface) apply to both modes.

> **CFG-06 (>= 0.4.0)**: canonical env-var names are `JUNIPER_CASCOR_WORKER_*`. Legacy `CASCOR_*` (and `CASCOR_WORKER_*`) names still work but emit a `DeprecationWarning` per process. The full legacy → canonical mapping lives in [`AGENTS.md` § Legacy env-var names](./AGENTS.md#legacy-env-var-names).

### WebSocket mode

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `JUNIPER_CASCOR_WORKER_SERVER_URL` | **Yes** | — | Worker endpoint URL (`ws://` or `wss://`) |
| `JUNIPER_CASCOR_WORKER_AUTH_TOKEN` | No | empty | Token sent as the `X-API-Key` header |
| `JUNIPER_CASCOR_WORKER_HEARTBEAT_INTERVAL` | No | `10.0` | Seconds between heartbeat messages |
| `JUNIPER_CASCOR_WORKER_TASK_TIMEOUT` | No | `3600.0` | Maximum seconds for a single training task |
| `JUNIPER_CASCOR_WORKER_TLS_CERT` | No | unset | Client certificate path for mTLS |
| `JUNIPER_CASCOR_WORKER_TLS_KEY` | No | unset | Client private key path for mTLS |
| `JUNIPER_CASCOR_WORKER_TLS_CA` | No | unset | Custom CA bundle for TLS verification |

### Legacy mode (`--legacy`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `JUNIPER_CASCOR_WORKER_MANAGER_HOST` | No | `127.0.0.1` | Manager hostname |
| `JUNIPER_CASCOR_WORKER_MANAGER_PORT` | No | `50000` | Manager port |
| `JUNIPER_CASCOR_WORKER_AUTHKEY` | **Yes** | — | Manager authentication key |
| `JUNIPER_CASCOR_WORKER_NUM_WORKERS` | No | `1` | Worker process count |
| `JUNIPER_CASCOR_WORKER_MP_CONTEXT` | No | `forkserver` | Multiprocessing context (`forkserver`, `spawn`, `fork`) |

### Shared

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CASCOR_WORKER_HEALTH_PORT` | No | `8210` | Health-check HTTP server port (R1.3 health-probe surface) |
| `CASCOR_WORKER_HEALTH_BIND` | No | `127.0.0.1` | Health-check bind address; set to `0.0.0.0` when running under Kubernetes |

## Docker Deployment

```bash
# Full stack (recommended) — see juniper-deploy:
git clone https://github.com/pcalnon/juniper-deploy.git  # (private repository)
cd juniper-deploy && docker compose up --build

# Standalone:
docker build -t juniper-cascor-worker:latest .
docker run --rm \
  -e CASCOR_SERVER_URL=ws://<cascor-host>:8200/ws/v1/workers \
  -e CASCOR_AUTH_TOKEN=<worker-token> \
  juniper-cascor-worker:latest
```

The Dockerfile defaults to `juniper-cascor-worker --server-url ws://juniper-cascor:8200/ws/v1/workers`, which resolves the cascor service by name on the `juniper-deploy` Docker network. Container liveness is probed by `kill -0 1` (PID-1 liveness) rather than an HTTP endpoint to avoid PyTorch initialization races on the dedicated health-server thread.

## Dependency Lockfile

Two lockfiles ship with this package, both regenerated by the same `uv pip compile` invocations.

| File | Purpose |
|------|---------|
| `requirements.lock` | Default lockfile; pins the full GPU-capable dependency surface (includes CUDA-enabled PyTorch wheels) for non-Docker developer installs |
| `requirements-cpu.lock` | CPU-only lockfile (Phase 4E, CW-02); used by the Dockerfile to keep the runtime image slim by excluding the ~2–4 GB NVIDIA/CUDA transitive stack |

Regenerate the default lock:

```bash
uv pip compile pyproject.toml --no-emit-package torch -o requirements.lock
```

Regenerate the CPU-only lock (PyTorch installed separately from the official PyTorch CPU index in the Dockerfile):

```bash
echo "torch==2.9.1+cpu" > /tmp/torch-cpu-override
uv pip compile pyproject.toml \
  --constraint /tmp/torch-cpu-override \
  --extra-index-url https://download.pytorch.org/whl/cpu \
  --index-strategy unsafe-best-match \
  --no-emit-package torch \
  -o requirements-cpu.lock
```

The ecosystem-wide lockfile-freshness gate enforces regeneration on every PR that touches `pyproject.toml`; the `/tmp` + `mv` pattern avoids the self-pin trap of `uv pip compile -o <file>` reading the existing file.

## Active Research Components

`juniper-cascor-worker` contributes the **distributed candidate-pool training** research component to the Juniper platform: a wire-protocol-defined parallelisation of Cascade-Correlation's candidate-unit selection step across an arbitrary number of worker hosts, coordinated by `juniper-cascor` over a WebSocket worker protocol (`/ws/v1/workers`) with mTLS support, structured heartbeats, and reassignment of tasks from workers that have exceeded the heartbeat timeout. The protocol itself — defined by `juniper-cascor-protocol` — is the research artifact; this package is its reference implementation on the worker side.

## Quick Start Guide

### Prerequisites

- Python ≥ 3.12
- A running `juniper-cascor` instance reachable at the URL passed via `--server-url` or `CASCOR_SERVER_URL`
- A worker auth token issued by `juniper-cascor` (`JUNIPER_CASCOR_API_KEYS`); the same token is passed to the worker via `--auth-token` or `CASCOR_AUTH_TOKEN`
- The JuniperCascor source code importable on the worker machine — the worker runs CasCor's candidate-training code locally rather than depending on a published CasCor library

### Installation

```bash
pip install juniper-cascor-worker
```

### Verification — WebSocket mode

```bash
juniper-cascor-worker \
  --server-url ws://<cascor-host>:8200/ws/v1/workers \
  --auth-token <worker-token>
```

A successful start logs `Connected to ws://<cascor-host>:8200/ws/v1/workers`. Configurable behaviour through optional flags (heartbeat interval, mTLS, task timeout) is documented under [Service Configuration](#service-configuration). The worker can also be embedded in Python:

```python
import asyncio
from juniper_cascor_worker import CascorWorkerAgent, WorkerConfig

config = WorkerConfig(
    server_url="ws://<cascor-host>:8200/ws/v1/workers",
    auth_token="<worker-token>",
)

agent = CascorWorkerAgent(config)
asyncio.run(agent.run())
```

### Verification — Legacy mode

Legacy mode is retained only for transitional deployments and is deprecated. New deployments should use WebSocket mode.

```bash
juniper-cascor-worker --legacy \
  --manager-host <manager-host> \
  --manager-port 50000 \
  --authkey <legacy-authkey> \
  --workers 4
```

### Next Steps

- [`docs/QUICK_START.md`](docs/QUICK_START.md) — complete installation and verification guide
- [`docs/REFERENCE.md`](docs/REFERENCE.md) — full configuration and CLI reference
- [`docs/DEVELOPER_CHEATSHEET.md`](docs/DEVELOPER_CHEATSHEET.md) — quick-reference card for development tasks
- [`juniper-cascor`](https://github.com/pcalnon/juniper-cascor) — upstream service the worker connects to
- [`juniper-deploy`](https://github.com/pcalnon/juniper-deploy) — Docker Compose orchestration for the full-stack platform
- [`juniper-ml`](https://pypi.org/project/juniper-ml/) — platform meta-package on PyPI

## Research Philosophy

The Juniper platform exists to study learning algorithms whose network architecture is not fixed in advance. Its initial anchor is the Cascade-Correlation algorithm of Fahlman and Lebiere (1990), implemented from the primary literature without recourse to higher-level abstractions that elide the algorithm's operational detail. The organising commitment is that algorithm implementations remain inspectable at the level at which they were originally specified: candidate units, correlation objectives, weight-freezing semantics, and the structural events that grow the network are first-class artifacts of the codebase rather than internal details of a library wrapper. This permits comparative work — across algorithms, datasets, and hyperparameter regimes — to be conducted on a known and reproducible substrate.

The current platform comprises a Cascade-Correlation training service exposing a REST and WebSocket interface, a dataset-generation service with a named-version registry that includes the ARC-AGI families, a real-time monitoring dashboard for inspecting training dynamics as they occur, and a distributed worker that parallelises candidate-unit training across hosts. Near-term work extends the architectural-growth catalogue beyond Cascade-Correlation, introduces multi-network orchestration for comparative experiments at the level of network populations rather than individual runs, and tightens the dataset–training–monitoring loop into a reproducible research workbench. The longer-term direction is the systematic empirical study of constructive and architecture-growing learning algorithms, with first-class infrastructure for the ablation, comparison, and replication that such a study requires.

## Documentation

| Document | Purpose |
|----------|---------|
| [`docs/DOCUMENTATION_OVERVIEW.md`](docs/DOCUMENTATION_OVERVIEW.md) | Navigation index for all `juniper-cascor-worker` documentation |
| [`docs/QUICK_START.md`](docs/QUICK_START.md) | Complete installation and verification guide |
| [`docs/REFERENCE.md`](docs/REFERENCE.md) | Full configuration, CLI, and environment-variable reference |
| [`docs/DEVELOPER_CHEATSHEET.md`](docs/DEVELOPER_CHEATSHEET.md) | Quick-reference card for development tasks |
| [`CHANGELOG.md`](CHANGELOG.md) | Version history |

## License

MIT License — see [`LICENSE`](LICENSE) for details.
