# Developer Cheatsheet — juniper-cascor-worker

**Version**: 1.0.0
**Date**: 2026-03-15
**Project**: juniper-cascor-worker

---

## Common Commands

| Command | Description |
|---------|-------------|
| `pip install -e ".[dev]"` | Install in development mode |
| `pip install juniper-cascor-worker` | Install from PyPI |
| `pytest tests/ -v` | Run all tests |
| `pytest tests/ -m unit -v` | Run unit tests only |
| `pytest tests/ --cov=juniper_cascor_worker --cov-report=term-missing --cov-fail-under=80` | Run with coverage |
| `mypy juniper_cascor_worker --ignore-missing-imports` | Type checking |
| `flake8 juniper_cascor_worker --max-line-length=120` | Linting |
| `black --check juniper_cascor_worker` | Format check |
| `isort --check-only juniper_cascor_worker` | Import order check |

---

## CLI Usage

### Start a Worker

```bash
juniper-cascor-worker --manager-host 192.168.1.10 --manager-port 50000 --workers 4
```

### CLI Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--manager-host` | TEXT | `127.0.0.1` | Manager hostname |
| `--manager-port` | INTEGER | `50000` | Manager port |
| `--authkey` | TEXT | `juniper` | Authentication key |
| `--workers` | INTEGER | `1` | Number of worker processes |
| `--mp-context` | CHOICE | `forkserver` | Multiprocessing context (`forkserver`, `spawn`, `fork`) |
| `--log-level` | CHOICE | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `--cascor-path` | TEXT | -- | Path to CasCor src directory (added to `sys.path`) |

Signal handling: first SIGINT/SIGTERM triggers graceful shutdown; second forces exit.

> See: [docs/REFERENCE.md](REFERENCE.md#cli-reference) for full CLI reference.

---

## Python API

### WorkerConfig

```python
from juniper_cascor_worker import CandidateTrainingWorker, WorkerConfig

config = WorkerConfig(
    manager_host="192.168.1.10",
    manager_port=50000,
    authkey="juniper",
    num_workers=4,
    mp_context="forkserver",
)

# Or from environment variables
config = WorkerConfig.from_env()
```

### Worker Lifecycle

```python
with CandidateTrainingWorker(config) as worker:
    worker.connect()    # Connect to remote CandidateTrainingManager
    worker.start()      # Spawn worker processes
    # Workers train candidate units in parallel
    # On exit: auto-calls disconnect() -> stop() -> cleanup
```

### Lifecycle States

```
(init) --> configured --> connected --> running --> connected --> disconnected
             validate()    connect()     start()     stop()      disconnect()
```

| Property | Type | Description |
|----------|------|-------------|
| `worker.is_running` | `bool` | `True` if any worker process is alive |
| `worker.worker_count` | `int` | Count of alive worker processes |

> See: [docs/REFERENCE.md](REFERENCE.md#python-api) for full API reference.

---

## Distributed Training Architecture

### How It Works

1. **juniper-cascor** (manager) starts a `CandidateTrainingManager` on a configured port
2. **juniper-cascor-worker** connects to the manager via Python `multiprocessing.managers`
3. Workers pull candidate training tasks from a shared task queue
4. Each worker trains a candidate unit independently and pushes results back
5. The manager selects the best candidate and installs it into the network

### Communication Flow

```
juniper-cascor (Manager)              juniper-cascor-worker (Remote)
+----------------------------+        +----------------------------+
| CandidateTrainingManager   |        | CandidateTrainingWorker    |
|   task_queue (shared)   <--|--------|-->  worker processes (N)   |
|   result_queue (shared) <--|--------|-->  _worker_loop() each    |
+----------------------------+        +----------------------------+
     multiprocessing.managers (TCP, authkey-authenticated)
```

### Multiprocessing Context

| Context | Platform | Notes |
|---------|----------|-------|
| `forkserver` | Linux/macOS | Default; safest for most scenarios |
| `spawn` | All | Most portable; slower startup |
| `fork` | Unix only | Fastest; can deadlock with threads |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CASCOR_MANAGER_HOST` | `127.0.0.1` | Manager hostname |
| `CASCOR_MANAGER_PORT` | `50000` | Manager port |
| `CASCOR_AUTHKEY` | *(required)* | Authentication key. No usable default; worker fails validation if unset. `.env.example` uses `juniper` as a sample value. |
| `CASCOR_NUM_WORKERS` | `1` | Number of worker processes |
| `CASCOR_MP_CONTEXT` | `forkserver` | Multiprocessing start method |
| `CASCOR_TASK_QUEUE_TIMEOUT` | `5.0` | Seconds to wait for a task before re-checking (WorkerConfig field: `task_queue_timeout`) |
| `CASCOR_STOP_TIMEOUT` | `10` | Seconds to wait for worker processes to exit on stop (WorkerConfig field: `stop_timeout`) |

All variables are read by `WorkerConfig.from_env()`.

---

## Error Handling

```
WorkerError (base)
+-- WorkerConnectionError    # Connection to manager failed
+-- WorkerConfigError        # Invalid configuration
```

| Exception | Raised When |
|-----------|-------------|
| `WorkerConfigError` | Invalid port, num_workers, or mp_context in config |
| `WorkerConnectionError` | Manager unreachable or authentication failure |
| `WorkerError` | CasCor source not importable, or `start()` called before `connect()` |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `WorkerConnectionError` on `connect()` | Manager not running or wrong host/port | Verify juniper-cascor is running with manager enabled |
| `WorkerConnectionError` auth failure | Wrong authkey | Match `CASCOR_AUTHKEY` between manager and worker |
| `WorkerError` on `connect()` | CasCor source not on `sys.path` | Use `--cascor-path` CLI flag to point to CasCor src directory |
| Workers spawn but exit immediately | Task queue empty | Training must be active on the manager side |
| `WorkerConfigError` | Invalid port or num_workers | Port must be 1-65535, num_workers must be >= 1 |

---

## Cross-References

- [juniper-cascor-worker REFERENCE.md](REFERENCE.md) -- Full API and CLI reference
- [juniper-cascor-worker QUICK_START.md](QUICK_START.md) -- Getting started guide
- [juniper-cascor-worker AGENTS.md](../AGENTS.md) -- Agent development guide
- [Ecosystem Cheatsheet](https://github.com/pcalnon/juniper-ml/blob/main/notes/DEVELOPER_CHEATSHEET.md) -- Cross-project procedures
- [juniper-cascor-client Cheatsheet](https://github.com/pcalnon/juniper-cascor-client/blob/main/docs/DEVELOPER_CHEATSHEET.md) -- HTTP/WebSocket client
