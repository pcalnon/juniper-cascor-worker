# juniper-cascor-worker

[![PyPI](https://img.shields.io/pypi/v/juniper-cascor-worker)](https://pypi.org/project/juniper-cascor-worker/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)

**Distributed candidate-training worker for the Juniper Cascade-Correlation platform.**

`juniper-cascor-worker` connects outbound to a running `juniper-cascor` instance, receives
candidate-unit training tasks, trains them, and returns the trained candidates for selection into the
growing network. Run several workers to parallelise candidate-pool training across hosts.

> **Part of the Juniper platform.** juniper-cascor-worker is the distributed candidate-training worker
> for [juniper-cascor](https://github.com/pcalnon/juniper-cascor) in
> [Juniper](https://github.com/pcalnon/juniper-ml) — a multi-package ML research platform built around
> constructive (Cascade-Correlation) and recurrent neural networks. It is managed by cascor over a
> wire protocol, with no code-import dependency between the two.

## Install

```bash
pip install juniper-cascor-worker
```

## Run

The default WebSocket mode connects to a `juniper-cascor` instance:

```bash
juniper-cascor-worker \
  --server-url ws://<cascor-host>:8200/ws/v1/workers \
  --auth-token <worker-token>
```

…or via the canonical environment variables:

```bash
export JUNIPER_CASCOR_WORKER_SERVER_URL=ws://<cascor-host>:8200/ws/v1/workers
export JUNIPER_CASCOR_WORKER_AUTH_TOKEN=<worker-token>
juniper-cascor-worker
```

Legacy `--legacy` mode (a `multiprocessing.managers` worker) is deprecated and kept only for
transitional deployments.

## Configuration

Key environment variables (WebSocket mode); the full surface and the deprecated `CASCOR_*` legacy
aliases (pre-CFG-06) are documented in [`AGENTS.md`](./AGENTS.md):

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `JUNIPER_CASCOR_WORKER_SERVER_URL` | **Yes** | — | Worker endpoint URL (`ws://` or `wss://`) |
| `JUNIPER_CASCOR_WORKER_AUTH_TOKEN` | No | empty | Token sent as the `X-API-Key` header |
| `JUNIPER_CASCOR_WORKER_HEARTBEAT_INTERVAL` | No | `10.0` | Seconds between heartbeats |
| `JUNIPER_CASCOR_WORKER_TASK_TIMEOUT` | No | `3600.0` | Max seconds for a single training task |
| `JUNIPER_CASCOR_WORKER_TLS_CERT` / `_TLS_KEY` / `_TLS_CA` | No | unset | mTLS client cert / key / CA bundle |

## Docker

```bash
docker build -t juniper-cascor-worker:latest .
docker run --rm \
  -e JUNIPER_CASCOR_WORKER_SERVER_URL=ws://<cascor-host>:8200/ws/v1/workers \
  -e JUNIPER_CASCOR_WORKER_AUTH_TOKEN=<worker-token> \
  juniper-cascor-worker:latest
```

The Dockerfile defaults to WebSocket mode against `ws://juniper-cascor:8200/ws/v1/workers`. For the
full stack, see [`juniper-deploy`](https://github.com/pcalnon/juniper-deploy).

## Status

**Live** on PyPI. The current version is shown by the badge above; see [`CHANGELOG.md`](./CHANGELOG.md).

## License

MIT — see [LICENSE](./LICENSE).
