# Reference

## juniper-cascor-worker Technical Reference

**Version:** 0.1.0
**Status:** Active
**Last Updated:** March 3, 2026
**Project:** Juniper - Distributed CasCor Training Worker

---

## Table of Contents

- [Python API](#python-api)
- [CLI Reference](#cli-reference)
- [WorkerConfig](#workerconfig)
- [Exception Hierarchy](#exception-hierarchy)
- [Worker Lifecycle](#worker-lifecycle)
- [Environment Variables](#environment-variables)
- [Test Markers and Commands](#test-markers-and-commands)

---

## Python API

### Import

```python
from juniper_cascor_worker import CandidateTrainingWorker, WorkerConfig
```

### CandidateTrainingWorker

| Method | Returns | Description |
|--------|---------|-------------|
| `__init__(config=None)` | -- | Create worker; validates config, creates multiprocessing context |
| `connect()` | `None` | Connect to remote CandidateTrainingManager |
| `start(num_workers=None)` | `None` | Spawn local worker processes |
| `stop(timeout=None)` | `None` | Gracefully stop all workers (sends sentinels, waits, terminates) |
| `disconnect()` | `None` | Stop workers (if running) and release all resources |
| `is_running` (property) | `bool` | `True` if any worker process is alive |
| `worker_count` (property) | `int` | Count of alive worker processes |

**Context Manager:**

```python
with CandidateTrainingWorker(config) as worker:
    worker.start()
    # Auto-calls disconnect() on exit
```

---

## CLI Reference

### Command

```
juniper-cascor-worker [OPTIONS]
```

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--manager-host` | TEXT | `127.0.0.1` | Manager hostname |
| `--manager-port` | INTEGER | `50000` | Manager port |
| `--authkey` | TEXT | `juniper` | Authentication key |
| `--workers` | INTEGER | `1` | Number of worker processes |
| `--mp-context` | CHOICE | `forkserver` | Multiprocessing context (`forkserver`, `spawn`, `fork`) |
| `--log-level` | CHOICE | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `--cascor-path` | TEXT | -- | Path to CasCor src directory (added to `sys.path`) |

### Signal Handling

| Signal | First | Second |
|--------|-------|--------|
| SIGINT / SIGTERM | Graceful shutdown | Forced exit (`sys.exit(1)`) |

---

## WorkerConfig

### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `manager_host` | `str` | `"127.0.0.1"` | Manager hostname |
| `manager_port` | `int` | `50000` | Manager port (1-65535) |
| `authkey` | `str` | `"juniper"` | Authentication key |
| `num_workers` | `int` | `1` | Number of worker processes (>= 1) |
| `task_queue_timeout` | `float` | `5.0` | Task queue poll timeout in seconds |
| `stop_timeout` | `int` | `10` | Worker shutdown timeout in seconds |
| `mp_context` | `str` | `"forkserver"` | Multiprocessing start method |

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `from_env()` (classmethod) | `WorkerConfig` | Create config from `CASCOR_*` environment variables |
| `validate()` | `None` | Validate config; raises `WorkerConfigError` on invalid values |
| `address` (property) | `tuple[str, int]` | `(manager_host, manager_port)` |

### Multiprocessing Context

| Value | Platform | Notes |
|-------|----------|-------|
| `forkserver` | Linux/macOS | Default; safest for most scenarios |
| `spawn` | All | Most portable; slower startup |
| `fork` | Unix | Fastest; can deadlock with threads |

---

## Exception Hierarchy

```
WorkerError (base)
├── WorkerConnectionError    # Connection to manager failed
└── WorkerConfigError        # Invalid configuration
```

### Import

```python
from juniper_cascor_worker import (
    WorkerError,
    WorkerConnectionError,
    WorkerConfigError,
)
```

### When Raised

| Exception | Raised By |
|-----------|-----------|
| `WorkerConfigError` | `WorkerConfig.validate()` -- invalid port, num_workers, or mp_context |
| `WorkerConnectionError` | `connect()` -- manager unreachable or auth failure |
| `WorkerError` | `connect()`, `start()` -- CasCor source not importable |
| `WorkerError` | `start()` -- not connected |

---

## Worker Lifecycle

```
1. Configure:  WorkerConfig(manager_host=..., num_workers=...)
                └─ validate() called automatically by worker constructor

2. Connect:    worker.connect()
                └─ Imports CasCor codebase
                └─ Connects to CandidateTrainingManager via multiprocessing

3. Start:      worker.start(num_workers=4)
                └─ Spawns daemon processes running CascadeCorrelationNetwork._worker_loop

4. Monitor:    worker.is_running, worker.worker_count

5. Stop:       worker.stop(timeout=10)
                └─ Sends None sentinels to task queue
                └─ Waits up to timeout per process
                └─ Force-terminates unresponsive workers

6. Disconnect: worker.disconnect()
                └─ Stops workers, clears manager/queue references
```

### State Transitions

```
(init) ──validate──> configured
configured ──connect()──> connected
connected ──start()──> running
running ──stop()──> connected
connected ──disconnect()──> disconnected
```

---

## Environment Variables

| Variable | Default | Used By | Description |
|----------|---------|---------|-------------|
| `CASCOR_MANAGER_HOST` | `127.0.0.1` | `WorkerConfig.from_env()` | Manager hostname |
| `CASCOR_MANAGER_PORT` | `50000` | `WorkerConfig.from_env()` | Manager port |
| `CASCOR_AUTHKEY` | `juniper` | `WorkerConfig.from_env()` | Authentication key |
| `CASCOR_NUM_WORKERS` | `1` | `WorkerConfig.from_env()` | Number of worker processes |
| `CASCOR_MP_CONTEXT` | `forkserver` | `WorkerConfig.from_env()` | Multiprocessing start method |

---

## Test Markers and Commands

### Running Tests

```bash
pytest tests/ -v                    # All tests
pytest tests/ -m unit -v            # Unit tests only
pytest tests/ --cov=juniper_cascor_worker --cov-report=term-missing --cov-fail-under=80
```

### Test Files

| File | Purpose |
|------|---------|
| `tests/test_config.py` | WorkerConfig validation and env var loading |
| `tests/test_worker.py` | CandidateTrainingWorker lifecycle and state |
| `tests/test_cli.py` | CLI argument parsing and signal handling |
| `tests/conftest.py` | Shared fixtures |

### Quality Checks

```bash
mypy juniper_cascor_worker --ignore-missing-imports  # Type checking
flake8 juniper_cascor_worker                          # Linting
black --check juniper_cascor_worker                   # Format check
isort --check-only juniper_cascor_worker              # Import order
```

---

**Last Updated:** March 3, 2026
**Version:** 0.1.0
**Maintainer:** Paul Calnon
