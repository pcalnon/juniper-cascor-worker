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
- [Directory Layout Reference](#directory-layout-reference)
- [Application Architecture Reference](#application-architecture-reference)
- [Public API Reference](#public-api-reference)
- [Test Details Reference](#test-details-reference)
- [Worker CLI Flag Reference](#worker-cli-flag-reference)
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

## Directory Layout Reference

Relocated verbatim from `AGENTS.md` (P3 of the shared-session-memory plan) so it is read on demand rather than loaded into every session.

```text
juniper-cascor-worker/
+-- AGENTS.md                           # Development operations manual (this file)
+-- CLAUDE.md -> AGENTS.md              # Symlink for Claude Code
+-- CHANGELOG.md                        # Version history (0.1.0 through 0.3.0)
+-- LICENSE                             # MIT License
+-- README.md                           # Package overview and quick-start
+-- pyproject.toml                      # Build config, dependencies, tool settings
+-- .pre-commit-config.yaml             # Pre-commit hooks (22 hook instances)
+-- .markdownlint.yaml                  # Markdown linting rules
+-- .sops.yaml                          # SOPS config for secrets encryption
+-- juniper_cascor_worker/              # Main package
|   +-- __init__.py                     # Public API exports
|   +-- py.typed                        # PEP 561 type marker
|   +-- cli.py                          # CLI entry point
|   +-- config.py                       # WorkerConfig dataclass
|   +-- constants.py                    # Wire-protocol message types, defaults, env var names
|   +-- worker.py                       # CascorWorkerAgent + CandidateTrainingWorker
|   +-- ws_connection.py                # WebSocket connection management
|   +-- task_executor.py                # Training task execution
|   +-- exceptions.py                   # Custom exceptions
+-- tests/                              # Test suite (pytest, 80% coverage)
|   +-- __init__.py
|   +-- conftest.py                     # Shared fixtures (valid_config)
|   +-- test_cli.py                     # CLI argument parsing, mode dispatch, signals
|   +-- test_config.py                  # WorkerConfig validation, env var loading
|   +-- test_worker.py                  # CandidateTrainingWorker (legacy) tests
|   +-- test_worker_agent.py            # CascorWorkerAgent tests
|   +-- test_task_executor.py           # Task execution with mocked cascor
|   +-- test_ws_connection.py           # WebSocket connection, TLS, retry
+-- docs/                               # User documentation
|   +-- DOCUMENTATION_OVERVIEW.md       # Navigation guide
|   +-- QUICK_START.md                  # 5-minute getting started
|   +-- REFERENCE.md                    # Complete API/CLI reference
|   +-- DEVELOPER_CHEATSHEET.md         # Quick-reference for dev tasks
+-- notes/                              # Development/planning documents
|   +-- WORKTREE_SETUP_PROCEDURE.md     # Creating a git worktree
|   +-- WORKTREE_CLEANUP_PROCEDURE_V2.md  # Merging and cleanup (V2)
|   +-- THREAD_HANDOFF_PROCEDURE.md     # Thread handoff protocol
|   +-- PRE_COMMIT_REMEDIATION_PLAN.md  # Pre-commit troubleshooting
|   +-- PIP_DEPENDENCY_FILE_HEADER.md
|   +-- CONDA_DEPENDENCY_FILE_HEADER.md
|   +-- juniper-cascor-worker_OTHER_DEPENDENCIES.md
|   +-- history/                        # Archived procedure versions
|   +-- pull_requests/                  # PR tracking documents
+-- util/
|   +-- run_coverage.bash               # Local coverage-gate helper
|   +-- ad-hoc/README.md                # Temporary script conventions
+-- scripts/                            # Operator/systemd helpers
|   +-- juniper-cascor-worker-ctl       # Worker service control helper
|   +-- juniper-cascor-worker.service   # systemd unit template
+-- .github/
    +-- workflows/
    |   +-- ci.yml                      # Main CI pipeline
    |   +-- sequence-safety.yml         # Per-PR advisory sequence-safety net
    |   +-- main-verify.yml             # Post-merge bypass-proof screen net
    |   +-- security-scan.yml           # Weekly security scanning
    |   +-- publish.yml                 # PyPI publishing (OIDC)
    +-- dependabot.yml                  # Automated dependency updates
```

---

---

## Application Architecture Reference

Relocated verbatim from `AGENTS.md` (P3 of the shared-session-memory plan) so it is read on demand rather than loaded into every session.

### Communication Flow

```text
juniper-cascor (Server)               juniper-cascor-worker (Remote)
+----------------------------+        +----------------------------+
| /ws/v1/workers endpoint    |        | CascorWorkerAgent          |
| JSON + binary task frames  |<------>| async message + heartbeat  |
| X-API-Key auth             |        | local training execution   |
+----------------------------+        +----------------------------+
       WebSocket (ws:// or wss://)
```

### Worker Lifecycle

```text
(init) --> configured --> connecting --> registered --> processing --> stopped
             validate()      run()         _register()      loops       stop()
```

### Message Protocol

- **Control messages**: JSON (type, worker_id, task_id, status, capabilities)
- **Tensor data**: Binary frames — `struct`-encoded shape, dtype, then raw numpy data
- **Message types**: `task_assign`, `heartbeat`, `result_ack`, `registration`

### Module Dependency Graph

```text
cli.py
  |-- config.py
  |-- worker.py
  |   |-- config.py
  |   |-- exceptions.py
  |   |-- ws_connection.py
  |   |   +-- exceptions.py
  |   +-- task_executor.py
  |       +-- candidate_unit (external, cascor codebase)
  +-- exceptions.py
```

### Task Execution Pipeline

1. Receives `task_assign` message with candidate data + training parameters
2. Imports `CandidateUnit` from cascor codebase (dynamic import)
3. Resolves activation function (sigmoid/tanh/relu)
4. Creates `CandidateUnit` instance, converts numpy tensors to torch
5. Calls `candidate.train_detailed()` producing a `TrainingResult`
6. Extracts correlation, epochs_completed, trained weights
7. Converts result tensors back to numpy, returns (result_dict, tensor_dict)

---

---

## Public API Reference

Relocated verbatim from `AGENTS.md` (P3 of the shared-session-memory plan) so it is read on demand rather than loaded into every session.

### Exports (`juniper_cascor_worker/__init__.py`)

```python
from juniper_cascor_worker import (
    CascorWorkerAgent,        # WebSocket worker (default)
    CandidateTrainingWorker,  # Legacy worker (deprecated)
    WorkerConfig,             # Configuration dataclass
    WorkerError,              # Base exception
    WorkerConnectionError,    # Connection/protocol failures
    WorkerConfigError,        # Invalid configuration
    __version__,              # "0.3.0"
)
```

### CascorWorkerAgent (WebSocket — Default)

| Method | Description |
|--------|-------------|
| `__init__(config: WorkerConfig)` | Validate WebSocket config, initialize worker identity and state |
| `async run()` | Connect with retry, register, run message + heartbeat loops |
| `stop()` | Signal graceful shutdown |

**Features**: TLS/mTLS support, capability reporting (CPU cores, GPU, versions), task isolation via threading, exponential backoff reconnection.

### CandidateTrainingWorker (Legacy — Deprecated)

| Method | Description |
|--------|-------------|
| `__init__(config: WorkerConfig)` | Validate legacy config, init multiprocessing manager |
| `connect()` | Connect to remote `CandidateTrainingManager` |
| `start(num_workers=None)` | Spawn local worker processes |
| `stop(timeout=None)` | Gracefully stop workers |
| `disconnect()` | Stop workers and release resources |
| `is_running` (property) | True if any worker process alive |
| `worker_count` (property) | Count of alive worker processes |

Supports context manager protocol (`with CandidateTrainingWorker(config) as worker:`).

### WorkerConfig

| Method | Description |
|--------|-------------|
| `from_env()` (classmethod) | Create config from `CASCOR_*` environment variables |
| `validate(legacy=False)` | Validate config for the selected mode; raises `WorkerConfigError` |
| `address` (property) | Returns `(manager_host, manager_port)` tuple (legacy) |

See **Environment Variables** table above for all fields and defaults.

### Exception Hierarchy

```text
WorkerError (base)
+-- WorkerConnectionError    # Connection/protocol failures
+-- WorkerConfigError        # Invalid configuration
```

---

---

## Test Details Reference

Relocated verbatim from `AGENTS.md` (P3 of the shared-session-memory plan) so it is read on demand rather than loaded into every session.

### Test Framework

- **Framework**: pytest >=7.0.0
- **Async**: pytest-asyncio >=0.21.0
- **Coverage**: pytest-cov aggregate `fail_under=80` plus per-file/pool gate in CI
- **Timeout**: 30 seconds per test

### Test Markers

```python
@pytest.mark.unit         # Unit tests
@pytest.mark.integration  # Integration tests (requires live manager)
```

### Test Files

| File | Purpose |
|------|---------|
| `tests/conftest.py` | Shared fixtures (`valid_config`) |
| `tests/test_cli.py` | CLI argument parsing, WebSocket/legacy mode dispatch, signal handling |
| `tests/test_config.py` | WorkerConfig validation, environment variable loading, error cases |
| `tests/test_worker.py` | CandidateTrainingWorker lifecycle (legacy) |
| `tests/test_worker_agent.py` | CascorWorkerAgent registration, heartbeat, task handling, binary framing |
| `tests/test_task_executor.py` | Task execution with mocked cascor imports |
| `tests/test_ws_connection.py` | WebSocket connect, retry, TLS, binary frames |

### Coverage

Reproduce the CI coverage gates locally (full suite):

```bash
make coverage                 # convenience wrapper
bash util/run_coverage.bash   # source of truth (mirrors .github/workflows/ci.yml)
```

Gates:

- **Aggregate**: 80% package coverage by default (`coverage report --fail-under=${COVERAGE_FAIL_UNDER}`); override with `COVERAGE_FAIL_UNDER=<n>`.
- **Per-file / pooled statement coverage**: CI installs `juniper-ci-tools>=0.6.0,<0.7.0` and runs `juniper-coverage-gap-map --coverage-json reports/coverage.json --enforce`, failing when any source file is below 90% statement coverage or any packaged sub-module is below 95% statement-weighted pooled coverage.

`util/run_coverage.bash` writes `reports/coverage.json` and runs both gates locally when `juniper-coverage-gap-map` is installed. If the tool is missing, the helper prints the install hint and skips only the per-file gate; CI always treats the per-file gate as blocking. The script runs the full suite by design so percentages match CI; for a narrower debug loop use plain `pytest`.

---

---

## Worker CLI Flag Reference

Relocated verbatim from `AGENTS.md` (P3 of the shared-session-memory plan) so it is read on demand rather than loaded into every session.

```text
juniper-cascor-worker [OPTIONS]
```

### Mode Selection

| Flag | Description |
|------|-------------|
| `--legacy` | Use deprecated BaseManager worker mode |

### WebSocket Mode Flags (Default)

| Flag | Default | Description |
|------|---------|-------------|
| `--server-url TEXT` | `JUNIPER_CASCOR_WORKER_SERVER_URL` | WebSocket endpoint (e.g., `ws://host:8200/ws/v1/workers`) |
| `--auth-token TEXT` | `JUNIPER_CASCOR_WORKER_AUTH_TOKEN` | Token for `X-API-Key` authentication |
| `--heartbeat-interval FLOAT` | `10.0` | Heartbeat interval in seconds |
| `--tls-cert PATH` | unset | Client certificate path (mTLS) |
| `--tls-key PATH` | unset | Client key path (mTLS) |
| `--tls-ca PATH` | unset | CA certificate path |

**Note**: `--api-key` is accepted as a compatibility alias for `--auth-token`.

### Legacy Mode Flags (Deprecated)

| Flag | Default | Description |
|------|---------|-------------|
| `--manager-host TEXT` | `127.0.0.1` | Manager hostname |
| `--manager-port INT` | `50000` | Manager port (1-65535) |
| `--authkey TEXT` | `JUNIPER_CASCOR_WORKER_AUTHKEY` | Authentication key (required) |
| `--workers INT` | `1` | Number of worker processes |
| `--mp-context CHOICE` | `forkserver` | Multiprocessing context (`forkserver`/`spawn`/`fork`) |

### Shared Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--log-level CHOICE` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `--cascor-path PATH` | unset | Path to CasCor src directory (added to `sys.path`) |

### Signal Handling

- First `SIGINT`/`SIGTERM`: Graceful shutdown
- Second `SIGINT`/`SIGTERM`: Forced exit (`sys.exit(1)`)

---

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
make coverage                        # Full CI coverage gates
bash util/run_coverage.bash          # Same as make coverage
pytest tests/ --cov=juniper_cascor_worker --cov-report=term-missing --cov-fail-under=80  # Quick aggregate check
```

### Coverage Gate

CI coverage enforcement is aggregate:

- `coverage report --fail-under=${COVERAGE_FAIL_UNDER}` checks package coverage. The default threshold is 80%.

`make coverage` and `bash util/run_coverage.bash` run the full suite because narrowed selections do not reproduce CI percentages. CI also produces JUnit, XML coverage, and HTML coverage artifacts; the local helper focuses on the aggregate gate developers need before pushing.
### Coverage Gates

CI coverage enforcement is additive:

- `coverage report --fail-under=${COVERAGE_FAIL_UNDER}` checks aggregate package coverage. The default threshold is 80%.
- `juniper-coverage-gap-map --coverage-json reports/coverage.json --enforce` checks `reports/coverage.json` for at least 90% statement coverage in each source file and at least 95% statement-weighted pooled coverage in each packaged sub-module.

`make coverage` and `bash util/run_coverage.bash` run the full suite because narrowed selections do not reproduce CI percentages. The helper writes `reports/coverage.json` for the per-file gate. Locally, the per-file gate runs only when `juniper-coverage-gap-map` from `juniper-ci-tools>=0.6.0,<0.7.0` is installed; CI installs the tool and fails the `unit-tests` job if the gate reports gaps.

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
