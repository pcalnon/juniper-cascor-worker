# Reference

## juniper-cascor-worker Technical Reference

**Version:** 0.1.0
**Status:** Active
**Last Updated:** March 20, 2026
**Project:** Juniper - Distributed CasCor Training Worker

---

## Table of Contents

- [Python API](#python-api)
- [CLI Reference](#cli-reference)
- [WorkerConfig](#workerconfig)
- [Exception Hierarchy](#exception-hierarchy)
- [Worker Lifecycle by Mode](#worker-lifecycle-by-mode)
- [Environment Variables](#environment-variables)
- [Troubleshooting](#troubleshooting)
- [Test Markers and Commands](#test-markers-and-commands)

---

## Python API

### Import

```python
from juniper_cascor_worker import (
    CascorWorkerAgent,
    CandidateTrainingWorker,
    WorkerConfig,
)
```

### CascorWorkerAgent (Default WebSocket Worker)

| Method | Returns | Description |
|--------|---------|-------------|
| `__init__(config)` | `None` | Validate WebSocket config and initialize worker identity/state |
| `run()` | `Coroutine[None]` | Connect with retry, register worker, run message + heartbeat loops |
| `stop()` | `None` | Signal graceful shutdown of the async run loop |

### CandidateTrainingWorker (Legacy, Deprecated)

| Method | Returns | Description |
|--------|---------|-------------|
| `__init__(config=None)` | `None` | Validate legacy config and initialize multiprocessing worker manager |
| `connect()` | `None` | Connect to remote `CandidateTrainingManager` |
| `start(num_workers=None)` | `None` | Spawn local worker processes |
| `stop(timeout=None)` | `None` | Gracefully stop all workers (sends sentinels, waits, terminates) |
| `disconnect()` | `None` | Stop workers (if running) and release all resources |
| `is_running` (property) | `bool` | `True` if any worker process is alive |
| `worker_count` (property) | `int` | Count of alive worker processes |

**Legacy Context Manager:**

```python
with CandidateTrainingWorker(config) as worker:
    worker.start()
    # Auto-calls disconnect() on exit
```

---

## CLI Reference

### Command

```
juniper-cascor-worker [OPTIONS]        # WebSocket mode (default)
juniper-cascor-worker --legacy [OPTIONS]
```

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--legacy` | FLAG | `False` | Use deprecated BaseManager worker mode |
| `--server-url` | TEXT | `None` | WebSocket endpoint URL (fallback: `CASCOR_SERVER_URL`) |
| `--auth-token` | TEXT | `None` | Token used for `X-API-Key` header (fallback: `CASCOR_AUTH_TOKEN`) |
| `--heartbeat-interval` | FLOAT | `10.0` | Heartbeat interval in seconds (WebSocket mode) |
| `--tls-cert` | TEXT | `None` | Client cert path for mTLS (WebSocket mode) |
| `--tls-key` | TEXT | `None` | Client key path for mTLS (WebSocket mode) |
| `--tls-ca` | TEXT | `None` | CA bundle path for TLS verification (WebSocket mode) |
| `--manager-host` | TEXT | `127.0.0.1` | Legacy manager hostname (`--legacy`) |
| `--manager-port` | INTEGER | `50000` | Legacy manager port (`--legacy`) |
| `--authkey` | TEXT | `None` | Legacy auth key (`--legacy`, fallback: `CASCOR_AUTHKEY`) |
| `--workers` | INTEGER | `1` | Legacy worker process count (`--legacy`) |
| `--mp-context` | CHOICE | `forkserver` | Legacy multiprocessing context (`forkserver`, `spawn`, `fork`) |
| `--log-level` | CHOICE | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `--cascor-path` | TEXT | -- | Path to CasCor src directory (added to `sys.path`) |

### Signal Handling

| Signal | First | Second |
|--------|-------|--------|
| SIGINT / SIGTERM | Graceful shutdown (`stop()` / shutdown flag) | Forced exit (`sys.exit(1)`) |

---

## WorkerConfig

### Constructor Parameters

| Parameter | Type | Default | Mode | Description |
|-----------|------|---------|------|-------------|
| `server_url` | `str` | `""` | WebSocket | Server endpoint (`ws://` or `wss://`) |
| `auth_token` | `str` | `""` | WebSocket | Token mapped to `X-API-Key` header |
| `heartbeat_interval` | `float` | `10.0` | WebSocket | Heartbeat interval in seconds (`> 0`) |
| `reconnect_backoff_base` | `float` | `1.0` | WebSocket | Initial reconnect delay (`> 0`) |
| `reconnect_backoff_max` | `float` | `60.0` | WebSocket | Maximum reconnect delay |
| `tls_cert` | `str \| None` | `None` | WebSocket | Client cert path (mTLS) |
| `tls_key` | `str \| None` | `None` | WebSocket | Client private key path (mTLS) |
| `tls_ca` | `str \| None` | `None` | WebSocket | Custom CA bundle path |
| `manager_host` | `str` | `"127.0.0.1"` | Legacy | Manager hostname |
| `manager_port` | `int` | `50000` | Legacy | Manager port (1-65535) |
| `authkey` | `str` | `""` | Legacy | Manager auth key (required in legacy mode) |
| `num_workers` | `int` | `1` | Legacy | Number of worker processes (`>= 1`) |
| `task_queue_timeout` | `float` | `5.0` | Legacy | Queue poll timeout in seconds |
| `stop_timeout` | `int` | `10` | Legacy | Graceful stop timeout in seconds |
| `mp_context` | `str` | `"forkserver"` | Legacy | Multiprocessing start method |

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `from_env()` (classmethod) | `WorkerConfig` | Create config from `CASCOR_*` environment variables |
| `validate(legacy=False)` | `None` | Validate mode-specific config; raises `WorkerConfigError` on invalid values |
| `address` (property) | `tuple[str, int]` | `(manager_host, manager_port)` |

### Multiprocessing Context

| Value | Platform | Notes |
|-------|----------|-------|
| `forkserver` | Linux/macOS | Default for legacy mode; safest for most scenarios |
| `spawn` | All | Most portable; slower startup |
| `fork` | Unix | Fastest; can deadlock with threads |

---

## Exception Hierarchy

```
WorkerError (base)
├── WorkerConnectionError    # Connection or protocol failures
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
| `WorkerConfigError` | `WorkerConfig.validate()` -- invalid `server_url`, heartbeat/backoff, or legacy manager settings |
| `WorkerConnectionError` | WebSocket connect/reconnect errors, closed connection, or registration failure |
| `WorkerError` | Legacy worker import/connect/start failures |

---

## Worker Lifecycle by Mode

### WebSocket Mode (Default)

```
1. Configure:  WorkerConfig(server_url=..., auth_token=...)
                └─ validate(legacy=False)

2. Run:        asyncio.run(CascorWorkerAgent(config).run())
                └─ Connects to /ws/v1/workers (with retry)
                └─ Waits for connection_established
                └─ Sends register and waits for registration_ack

3. Process:    heartbeat loop + message loop
                └─ Receives task_assign + binary tensors
                └─ Executes training task
                └─ Sends task_result + binary tensors

4. Stop:       SIGINT/SIGTERM or agent.stop()
                └─ Closes connection and exits run loop
```

### Legacy Mode (`--legacy`, Deprecated)

```
1. Configure:  WorkerConfig(manager_host=..., authkey=..., num_workers=...)
                └─ validate(legacy=True)

2. Connect:    CandidateTrainingWorker.connect()
                └─ Imports CasCor codebase
                └─ Connects to CandidateTrainingManager

3. Start:      worker.start(num_workers=4)
                └─ Spawns daemon worker processes

4. Stop:       worker.stop(timeout=10) + worker.disconnect()
```

---

## Environment Variables

| Variable | Default | Mode | Used By | Description |
|----------|---------|------|---------|-------------|
| `CASCOR_SERVER_URL` | `""` | WebSocket | `WorkerConfig.from_env()` / CLI fallback | Worker endpoint URL |
| `CASCOR_AUTH_TOKEN` | `""` | WebSocket | `WorkerConfig.from_env()` / CLI fallback | Token sent as `X-API-Key` |
| `CASCOR_HEARTBEAT_INTERVAL` | `"10.0"` | WebSocket | `WorkerConfig.from_env()` | Heartbeat interval in seconds |
| `CASCOR_TLS_CERT` | unset | WebSocket | `WorkerConfig.from_env()` | Client cert path |
| `CASCOR_TLS_KEY` | unset | WebSocket | `WorkerConfig.from_env()` | Client key path |
| `CASCOR_TLS_CA` | unset | WebSocket | `WorkerConfig.from_env()` | CA bundle path |
| `CASCOR_MANAGER_HOST` | `"127.0.0.1"` | Legacy | `WorkerConfig.from_env()` | Manager hostname |
| `CASCOR_MANAGER_PORT` | `"50000"` | Legacy | `WorkerConfig.from_env()` | Manager port |
| `CASCOR_AUTHKEY` | `""` | Legacy | `WorkerConfig.from_env()` / CLI fallback | Manager authentication key |
| `CASCOR_NUM_WORKERS` | `"1"` | Legacy | `WorkerConfig.from_env()` | Number of worker processes |
| `CASCOR_MP_CONTEXT` | `"forkserver"` | Legacy | `WorkerConfig.from_env()` | Multiprocessing method |

`CASCOR_API_KEY` is deprecated in worker docs and codepaths. Use `CASCOR_AUTH_TOKEN`.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| `server_url is required` | Missing WebSocket endpoint | Set `--server-url` or `CASCOR_SERVER_URL` |
| `server_url must start with ws:// or wss://` | Incorrect URL scheme | Use a WebSocket URL |
| Server rejects authentication | Using old option names | Use `--auth-token` / `CASCOR_AUTH_TOKEN` |
| Legacy manager options not taking effect | `--legacy` not provided | Add `--legacy` when using BaseManager path |
| `authkey is required` in legacy mode | Missing `--authkey` / `CASCOR_AUTHKEY` | Provide legacy auth key explicitly |

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
| `tests/test_worker_agent.py` | WebSocket `CascorWorkerAgent` lifecycle and protocol handling |
| `tests/test_ws_connection.py` | WebSocket transport, TLS setup, retry logic |
| `tests/test_task_executor.py` | Training task execution payload handling |
| `tests/test_worker.py` | CandidateTrainingWorker lifecycle and state |
| `tests/test_cli.py` | CLI mode routing, argument parsing, and signal handling |
| `tests/conftest.py` | Shared fixtures |

### Quality Checks

```bash
mypy juniper_cascor_worker --ignore-missing-imports  # Type checking
flake8 juniper_cascor_worker                          # Linting
black --check juniper_cascor_worker                   # Format check
isort --check-only juniper_cascor_worker              # Import order
```

---

**Last Updated:** March 20, 2026
**Version:** 0.1.0
**Maintainer:** Paul Calnon
