# Quick Start Guide

## Get juniper-cascor-worker Running in 5 Minutes

**Version:** 0.1.0
**Status:** Active
**Last Updated:** March 20, 2026
**Project:** Juniper - Distributed CasCor Training Worker

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Install](#1-install)
- [CLI Usage](#2-cli-usage)
- [Python API](#3-python-api)
- [Environment Variables](#4-environment-variables)
- [Troubleshooting](#5-troubleshooting)
- [Next Steps](#6-next-steps)

---

## Prerequisites

- **Python 3.11+** (`python --version`)
- **juniper-cascor** service running with the worker endpoint enabled (`/ws/v1/workers`)
- **Auth token** for server-side `X-API-Key` auth (if your deployment requires it)
- **CasCor source** importable on the worker machine (for task execution in both modes)

---

## 1. Install

```bash
pip install juniper-cascor-worker
```

Or install from source for development:

```bash
cd juniper-cascor-worker
pip install -e ".[dev]"
```

---

## 2. CLI Usage

```bash
# Default mode (WebSocket)
juniper-cascor-worker \
  --server-url ws://192.168.1.100:8200/ws/v1/workers \
  --auth-token my-worker-token

# WebSocket mode with custom heartbeat and TLS/mTLS
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
  --authkey legacy-secret \
  --workers 4
```

Press `Ctrl+C` to gracefully shut down. Press twice to force exit.

---

## 3. Python API

```python
import asyncio

from juniper_cascor_worker import CascorWorkerAgent, WorkerConfig

# Configure WebSocket mode (default)
config = WorkerConfig(
    server_url="ws://192.168.1.100:8200/ws/v1/workers",
    auth_token="my-worker-token",
)

agent = CascorWorkerAgent(config)
asyncio.run(agent.run())
```

### Load WebSocket Config from Environment

```python
config = WorkerConfig.from_env()  # Reads CASCOR_* env vars
agent = CascorWorkerAgent(config)
asyncio.run(agent.run())
```

---

## 4. Environment Variables

| Variable | Mode | Default | Description |
|----------|------|---------|-------------|
| `CASCOR_SERVER_URL` | WebSocket (default) | *(required)* | Worker endpoint URL (`ws://` or `wss://`) |
| `CASCOR_AUTH_TOKEN` | WebSocket (default) | empty | Token sent as `X-API-Key` header |
| `CASCOR_HEARTBEAT_INTERVAL` | WebSocket (default) | `10.0` | Heartbeat interval in seconds |
| `CASCOR_TLS_CERT` | WebSocket (default) | unset | Client certificate path (mTLS) |
| `CASCOR_TLS_KEY` | WebSocket (default) | unset | Client private key path (mTLS) |
| `CASCOR_TLS_CA` | WebSocket (default) | unset | CA bundle path for TLS verification |
| `CASCOR_MANAGER_HOST` | Legacy (`--legacy`) | `127.0.0.1` | Manager hostname |
| `CASCOR_MANAGER_PORT` | Legacy (`--legacy`) | `50000` | Manager port |
| `CASCOR_AUTHKEY` | Legacy (`--legacy`) | *(required in legacy mode)* | Manager auth key |
| `CASCOR_NUM_WORKERS` | Legacy (`--legacy`) | `1` | Number of worker processes |
| `CASCOR_MP_CONTEXT` | Legacy (`--legacy`) | `forkserver` | Multiprocessing start method |

---

## 5. Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| `server_url is required` | Missing `--server-url` / `CASCOR_SERVER_URL` in default mode | Set a `ws://` or `wss://` endpoint |
| `server_url must start with ws:// or wss://` | Used `http://` or `https://` | Use the WebSocket URL scheme |
| Auth failure after recent updates | Still using old `--api-key` or `CASCOR_API_KEY` names | Use `--auth-token` and `CASCOR_AUTH_TOKEN` |
| Manager flags seem ignored | Running default mode without `--legacy` | Add `--legacy` for BaseManager flow |

---

## 6. Next Steps

- [Documentation Overview](DOCUMENTATION_OVERVIEW.md) -- navigation index
- [Reference](REFERENCE.md) -- complete API, CLI, and configuration reference
- [README.md](../README.md) -- project overview
- [AGENTS.md](../AGENTS.md) -- development conventions and commands

---

**Last Updated:** March 20, 2026
**Version:** 0.1.0
**Status:** Active
