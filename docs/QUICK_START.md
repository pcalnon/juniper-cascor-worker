# Quick Start Guide

## Get juniper-cascor-worker Running in 5 Minutes

**Version:** 0.1.0
**Status:** Active
**Last Updated:** March 3, 2026
**Project:** Juniper - Distributed CasCor Training Worker

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Install](#1-install)
- [CLI Usage](#2-cli-usage)
- [Python API](#3-python-api)
- [Environment Variables](#4-environment-variables)
- [Next Steps](#5-next-steps)

---

## Prerequisites

- **Python 3.11+** (`python --version`)
- **juniper-cascor** service running with candidate training manager enabled
- **CasCor source** importable (either via `pip install juniper-cascor` or `--cascor-path` flag)

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
# Connect to manager and spawn 4 worker processes
juniper-cascor-worker --manager-host 192.168.1.100 --manager-port 50000 --workers 4

# With explicit CasCor path
juniper-cascor-worker --manager-host 192.168.1.100 --cascor-path /opt/juniper-cascor/src --workers 8

# Debug logging
juniper-cascor-worker --log-level DEBUG --workers 2
```

Press `Ctrl+C` to gracefully shut down. Press twice to force exit.

---

## 3. Python API

```python
from juniper_cascor_worker import CandidateTrainingWorker, WorkerConfig

# Configure
config = WorkerConfig(
    manager_host="192.168.1.100",
    manager_port=50000,
    num_workers=4,
)

# Run with context manager
with CandidateTrainingWorker(config) as worker:
    worker.start()
    print(f"Running: {worker.worker_count} processes")
    # Workers consume tasks until stopped
    worker.stop()
```

### Load Config from Environment

```python
config = WorkerConfig.from_env()  # Reads CASCOR_* env vars
worker = CandidateTrainingWorker(config)
```

---

## 4. Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CASCOR_MANAGER_HOST` | `127.0.0.1` | Manager hostname |
| `CASCOR_MANAGER_PORT` | `50000` | Manager port |
| `CASCOR_AUTHKEY` | `juniper` | Authentication key |
| `CASCOR_NUM_WORKERS` | `1` | Number of worker processes |
| `CASCOR_MP_CONTEXT` | `forkserver` | Multiprocessing start method |

---

## 5. Next Steps

- [Documentation Overview](DOCUMENTATION_OVERVIEW.md) -- navigation index
- [Reference](REFERENCE.md) -- complete API, CLI, and configuration reference
- [README.md](../README.md) -- project overview
- [AGENTS.md](../AGENTS.md) -- development conventions and commands

---

**Last Updated:** March 3, 2026
**Version:** 0.1.0
**Status:** Active
