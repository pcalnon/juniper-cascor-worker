# juniper-cascor-worker

Remote candidate training worker for the JuniperCascor cascade correlation neural network service.

## Overview

This package enables distributed candidate training on remote hardware.

It supports two worker modes:

- **WebSocket mode (default)**: `CascorWorkerAgent` connects to the
  `juniper-cascor` `/ws/v1/workers` endpoint and exchanges structured JSON and
  binary tensor frames.
- **Legacy mode (`--legacy`)**: `CandidateTrainingWorker` connects to a
  `CandidateTrainingManager` over `multiprocessing.managers` (deprecated).

## Ecosystem Compatibility

This package is part of the [Juniper](https://github.com/pcalnon/juniper-ml) ecosystem.
Compatible with:

| juniper-data | juniper-cascor | juniper-canopy |
|---|---|---|
| 0.4.x | 0.3.x | 0.2.x |

## Installation

```bash
pip install juniper-cascor-worker
```

**Note:** This package requires the JuniperCascor source code to be importable
on the worker machine (the worker runs CasCor's training code locally).

## CLI Usage

```bash
# Default mode (WebSocket)
juniper-cascor-worker \
    --server-url ws://192.168.1.100:8200/ws/v1/workers \
    --auth-token my-worker-token

# WebSocket mode with mTLS and custom heartbeat
juniper-cascor-worker \
    --server-url wss://cascor.example.com/ws/v1/workers \
    --auth-token my-worker-token \
    --heartbeat-interval 15 \
    --tls-cert /etc/juniper/worker.crt \
    --tls-key /etc/juniper/worker.key \
    --tls-ca /etc/juniper/ca.pem

# Legacy mode (deprecated)
juniper-cascor-worker \
    --legacy \
    --manager-host 192.168.1.100 \
    --manager-port 50000 \
    --authkey my-secret-key \
    --workers 4 \
    --mp-context forkserver \
    --log-level INFO
```

## Python API

```python
import asyncio

from juniper_cascor_worker import CascorWorkerAgent, WorkerConfig

config = WorkerConfig(
    server_url="ws://192.168.1.100:8200/ws/v1/workers",
    auth_token="my-worker-token",
)

agent = CascorWorkerAgent(config)
asyncio.run(agent.run())
```

## Environment Variables

| Variable | Mode | Description | Default |
|----------|------|-------------|---------|
| `CASCOR_SERVER_URL` | WebSocket (default) | Worker endpoint URL (`ws://` or `wss://`) | *(required)* |
| `CASCOR_AUTH_TOKEN` | WebSocket (default) | Token sent as `X-API-Key` header | empty |
| `CASCOR_HEARTBEAT_INTERVAL` | WebSocket (default) | Seconds between heartbeat messages | `10.0` |
| `CASCOR_TLS_CERT` | WebSocket (default) | Client certificate path for mTLS | unset |
| `CASCOR_TLS_KEY` | WebSocket (default) | Client private key path for mTLS | unset |
| `CASCOR_TLS_CA` | WebSocket (default) | Custom CA bundle for TLS verification | unset |
| `CASCOR_MANAGER_HOST` | Legacy (`--legacy`) | Manager hostname | `127.0.0.1` |
| `CASCOR_MANAGER_PORT` | Legacy (`--legacy`) | Manager port | `50000` |
| `CASCOR_AUTHKEY` | Legacy (`--legacy`) | Manager authentication key | *(required in legacy mode)* |
| `CASCOR_NUM_WORKERS` | Legacy (`--legacy`) | Worker process count | `1` |
| `CASCOR_MP_CONTEXT` | Legacy (`--legacy`) | Multiprocessing method | `forkserver` |

## Juniper Ecosystem

This package is part of the Juniper Cascade Correlation Neural Network Research Platform.

| Package | Description | Install |
|---------|-------------|---------|
| [juniper-data-client](https://github.com/pcalnon/juniper-data-client) | Dataset service client | `pip install juniper-data-client` |
| [juniper-cascor-client](https://github.com/pcalnon/juniper-cascor-client) | Neural network service client | `pip install juniper-cascor-client` |
| [juniper-cascor-worker](https://github.com/pcalnon/juniper-cascor-worker) | Distributed training worker (this package) | `pip install juniper-cascor-worker` |

## License

MIT License - see [LICENSE](LICENSE) for details.
