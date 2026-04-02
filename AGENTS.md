# AGENTS.md - Juniper Cascor Worker

**Project**: juniper-cascor-worker — Distributed CasCor Training Worker
**Version**: 0.3.0
**License**: MIT License
**Author**: Paul Calnon
**Python**: >=3.11 (supports 3.11, 3.12, 3.13, 3.14)
**Last Updated**: 2026-04-02

---

## Quick Reference

### Essential Commands

```bash
# Install in development mode
pip install -e ".[dev]"

# Run all tests
pytest tests/ -v

# Run with coverage (80% threshold enforced)
pytest tests/ --cov=juniper_cascor_worker --cov-report=term-missing --cov-fail-under=80

# Type checking
mypy juniper_cascor_worker --ignore-missing-imports

# Linting
flake8 juniper_cascor_worker --max-line-length=512
black --check --diff juniper_cascor_worker
isort --check-only --diff juniper_cascor_worker

# Run worker CLI (WebSocket mode — default)
juniper-cascor-worker --server-url ws://host:8200/ws/v1/workers --auth-token <token>

# Run worker CLI (legacy mode — deprecated)
juniper-cascor-worker --legacy --manager-host <host> --manager-port 50000 --authkey <key> --workers 4

# Validate documentation links
python scripts/check_doc_links.py

# Run pre-commit hooks
pre-commit run --all-files
```

### Environment Variables

#### WebSocket Mode (Default)

| Variable | Description | Default |
|----------|-------------|---------|
| `CASCOR_SERVER_URL` | WebSocket endpoint URL (`ws://` or `wss://`) | *(required)* |
| `CASCOR_AUTH_TOKEN` | Token sent as `X-API-Key` header | empty |
| `CASCOR_API_KEY` | Deprecated alias for `CASCOR_AUTH_TOKEN` | empty |
| `CASCOR_HEARTBEAT_INTERVAL` | Heartbeat interval in seconds | `10.0` |
| `CASCOR_TLS_CERT` | Client certificate path (mTLS) | unset |
| `CASCOR_TLS_KEY` | Client private key path (mTLS) | unset |
| `CASCOR_TLS_CA` | Custom CA bundle path | unset |

#### Legacy Mode (Deprecated)

| Variable | Description | Default |
|----------|-------------|---------|
| `CASCOR_MANAGER_HOST` | Manager hostname | `127.0.0.1` |
| `CASCOR_MANAGER_PORT` | Manager port | `50000` |
| `CASCOR_AUTHKEY` | Authentication key | *(required)* |
| `CASCOR_NUM_WORKERS` | Number of worker processes | `1` |
| `CASCOR_MP_CONTEXT` | Multiprocessing context (`forkserver`/`spawn`/`fork`) | `forkserver` |

### Key Files

| File | Purpose |
|------|---------|
| `juniper_cascor_worker/cli.py` | CLI entry point (`main`) — dispatches to WebSocket or legacy mode |
| `juniper_cascor_worker/__init__.py` | Package init — exports public API |
| `juniper_cascor_worker/config.py` | `WorkerConfig` dataclass with validation and env var loading |
| `juniper_cascor_worker/worker.py` | `CascorWorkerAgent` (WebSocket) + `CandidateTrainingWorker` (legacy) |
| `juniper_cascor_worker/ws_connection.py` | `WorkerConnection` — WebSocket lifecycle, TLS, reconnection |
| `juniper_cascor_worker/task_executor.py` | `execute_training_task()` — CandidateUnit training pipeline |
| `juniper_cascor_worker/exceptions.py` | Exception hierarchy: `WorkerError`, `WorkerConnectionError`, `WorkerConfigError` |
| `juniper_cascor_worker/py.typed` | PEP 561 type marker |
| `pyproject.toml` | Package config, dependencies, tool settings |
| `CHANGELOG.md` | Version history (0.1.0 through 0.3.0) |
| `docs/REFERENCE.md` | Complete API and CLI reference |
| `docs/QUICK_START.md` | 5-minute install and run guide |
| `docs/DEVELOPER_CHEATSHEET.md` | Quick-reference for common dev tasks |
| `scripts/check_doc_links.py` | Internal markdown link validator |
| `.pre-commit-config.yaml` | Pre-commit hook configuration |
| `.github/workflows/ci.yml` | CI/CD pipeline (8 jobs) |

---

## Project Overview

`juniper-cascor-worker` is a distributed candidate training worker for the JuniperCascor neural network platform. It connects to a JuniperCascor training server and processes candidate training tasks on remote hardware.

### Two Operating Modes

- **WebSocket mode** (default, since 0.2.0): Connects via WebSocket to the `/ws/v1/workers` endpoint. Async, no pickle, JSON + binary tensor framing.
- **Legacy mode** (deprecated since 0.3.0): Connects via Python's `multiprocessing.managers.BaseManager`. Emits `DeprecationWarning`.

### Dependencies

| Library | Version | Purpose |
|---------|---------|---------|
| `numpy` | `>=1.24.0` | Array operations, tensor encoding/decoding |
| `torch` | `>=2.0.0` | Neural network activations, tensor operations |
| `websockets` | `>=11.0` | Async WebSocket client |

#### Dynamic Imports (Required on Worker Machine)

The worker dynamically imports from the JuniperCascor source:

| Import | Source | Used By |
|--------|--------|---------|
| `candidate_unit.candidate_unit.CandidateUnit` | juniper-cascor | `task_executor.py` |
| `cascade_correlation.cascade_correlation.CandidateTrainingManager` | juniper-cascor | `worker.py` (legacy only) |
| `cascade_correlation.cascade_correlation.CascadeCorrelationNetwork` | juniper-cascor | `worker.py` (legacy only) |

The cascor source must be on `sys.path` via `--cascor-path <path>` CLI flag or pre-installed in the environment.

---

## Application Architecture

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

## Public API

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

## CLI Reference

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
| `--server-url TEXT` | `CASCOR_SERVER_URL` | WebSocket endpoint (e.g., `ws://host:8200/ws/v1/workers`) |
| `--auth-token TEXT` | `CASCOR_AUTH_TOKEN` | Token for `X-API-Key` authentication |
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
| `--authkey TEXT` | `CASCOR_AUTHKEY` | Authentication key (required) |
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

## Directory Layout

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
+-- scripts/                            # Utility scripts
|   +-- check_doc_links.py              # Markdown link validator
|   +-- generate_dep_docs.sh            # Dependency doc generator
+-- .github/
    +-- workflows/
    |   +-- ci.yml                      # Main CI pipeline (8 jobs)
    |   +-- security-scan.yml           # Weekly security scanning
    |   +-- publish.yml                 # PyPI publishing (OIDC)
    +-- dependabot.yml                  # Automated dependency updates
```

---

## Test Details

### Test Framework

- **Framework**: pytest >=7.0.0
- **Async**: pytest-asyncio >=0.21.0
- **Coverage**: pytest-cov; `fail_under=80` enforced
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

---

## CI/CD

### Main Pipeline (`.github/workflows/ci.yml`)

**Triggers**: Push to `main`/`develop`/`feature/**/`/`fix/**/`, all PRs, manual dispatch.

| Job | Python | Description |
|-----|--------|-------------|
| **pre-commit** | 3.11, 3.12, 3.13 | Run all pre-commit hooks (parallel matrix) |
| **docs** | 3.13 | Run `check_doc_links.py` for internal link validation |
| **unit-tests** | 3.13 | Unit tests with coverage enforcement (>=80%) |
| **build** | 3.13 | Build wheel + sdist, verify package metadata |
| **dependency-docs** | 3.13 | Generate dependency documentation |
| **security** | 3.13 | Gitleaks, Bandit SARIF, pip-audit |
| **required-checks** | -- | Aggregates all job results (single pass/fail) |
| **notify-downstream** | -- | Notify dependent repos of changes |

### Security Scanning (`.github/workflows/security-scan.yml`)

**Schedule**: Weekly (Monday 08:00 UTC). Runs Bandit, pip-audit, and Gitleaks.

### Publishing (`.github/workflows/publish.yml`)

**Trigger**: GitHub release (`v*.*.*` tags). Publishes to PyPI via trusted publishing (OIDC, no stored credentials).

### Pre-commit Hooks

| Hook | Purpose |
|------|---------|
| Black | Code formatting (line-length=512) |
| isort | Import sorting (black profile) |
| Flake8 | Linting (line-length=512) |
| MyPy | Static type checking (--ignore-missing-imports) |
| Bandit | Security scanning (skips B101, B311 in tests) |
| ShellCheck | Shell script linting |
| yamllint | YAML validation |
| markdownlint | Markdown formatting |
| SOPS | Blocks unencrypted `.env` files |
| check-yaml/toml/json | Config file syntax |
| check-merge-conflict | Prevents unresolved markers |
| detect-private-key | Blocks committed private keys |

---

## Resource Locations

When working on this project, consult these resources based on task type:

| Task | Resource |
|------|----------|
| API or CLI details | `docs/REFERENCE.md` |
| Getting started / setup | `docs/QUICK_START.md` |
| Common dev tasks | `docs/DEVELOPER_CHEATSHEET.md` |
| Doc navigation | `docs/DOCUMENTATION_OVERVIEW.md` |
| Creating a worktree | `notes/WORKTREE_SETUP_PROCEDURE.md` |
| Finishing a task | `notes/WORKTREE_CLEANUP_PROCEDURE_V2.md` |
| Thread handoff | `notes/THREAD_HANDOFF_PROCEDURE.md` |
| Pre-commit issues | `notes/PRE_COMMIT_REMEDIATION_PLAN.md` |
| Non-pip dependencies | `notes/juniper-cascor-worker_OTHER_DEPENDENCIES.md` |
| Full project context | `/home/pcalnon/Development/python/Juniper/CLAUDE.md` |

---

## Ecosystem Context

Part of the Juniper ecosystem. See the parent directory's `CLAUDE.md` at `/home/pcalnon/Development/python/Juniper/CLAUDE.md` for the full project map, dependency graph, shared conventions, and conda environment details.

### Position in Dependency Graph

```text
juniper-ml[worker] --> juniper-cascor-worker --WebSocket--> juniper-cascor (server)
```

The worker does **not** import juniper-data, juniper-cascor, or juniper-canopy as Python packages. It communicates with juniper-cascor exclusively via WebSocket (or legacy BaseManager) protocol.

### Ecosystem Compatibility

| juniper-data | juniper-cascor | juniper-cascor-worker | juniper-canopy |
|---|---|---|---|
| 0.4.x | 0.3.x | 0.3.x | 0.2.x |

---

## Worktree Procedures (Mandatory — Task Isolation)

> **OPERATING INSTRUCTION**: All feature, bugfix, and task work SHOULD use git worktrees for isolation. Worktrees keep the main working directory on the default branch while task work proceeds in a separate checkout.

### What This Is

Git worktrees allow multiple branches of a repository to be checked out simultaneously in separate directories. For the Juniper ecosystem, all worktrees are centralized in **`/home/pcalnon/Development/python/Juniper/worktrees/`** using a standardized naming convention.

The full setup and cleanup procedures are defined in:

- **`notes/WORKTREE_SETUP_PROCEDURE.md`** — Creating a worktree for a new task
- **`notes/WORKTREE_CLEANUP_PROCEDURE_V2.md`** — Merging, removing, and pushing after task completion (V2 — fixes CWD-trap bug)

Read the appropriate file when starting or completing a task.

### Worktree Directory Naming

Format: `<repo-name>--<branch-name>--<YYYYMMDD-HHMM>--<short-hash>`

Example: `juniper-cascor-worker--feature--add-gpu-support--20260225-1430--047c3f61`

- Slashes in branch names are replaced with `--`
- All worktrees reside in `/home/pcalnon/Development/python/Juniper/worktrees/`

### When to Use Worktrees

| Scenario | Use Worktree? |
| -------- | ------------- |
| Feature development (new feature branch) | **Yes** |
| Bug fix requiring a dedicated branch | **Yes** |
| Quick single-file documentation fix on main | No |
| Exploratory work that may be discarded | **Yes** |
| Hotfix requiring immediate merge | **Yes** |

### Quick Reference

**Setup** (full procedure in `notes/WORKTREE_SETUP_PROCEDURE.md`):

```bash
cd /home/pcalnon/Development/python/Juniper/juniper-cascor-worker
git fetch origin && git checkout main && git pull origin main
BRANCH_NAME="feature/my-task"
git branch "$BRANCH_NAME" main
REPO_NAME=$(basename "$(pwd)")
SAFE_BRANCH=$(echo "$BRANCH_NAME" | sed 's|/|--|g')
WORKTREE_DIR="/home/pcalnon/Development/python/Juniper/worktrees/${REPO_NAME}--${SAFE_BRANCH}--$(date +%Y%m%d-%H%M)--$(git rev-parse --short=8 HEAD)"
git worktree add "$WORKTREE_DIR" "$BRANCH_NAME"
cd "$WORKTREE_DIR"
```

**Cleanup** (full procedure in `notes/WORKTREE_CLEANUP_PROCEDURE_V2.md`):

```bash
# Phase 1: Push current work
cd "$OLD_WORKTREE_DIR" && git push origin "$OLD_BRANCH"
# Phase 2: Create new worktree BEFORE removing old (prevents CWD-trap)
git fetch origin
git worktree add "$NEW_WORKTREE_DIR" -b "$NEW_BRANCH" origin/main
cd "$NEW_WORKTREE_DIR"
# Phase 3: Create PR (do NOT merge directly to main)
gh pr create --base main --head "$OLD_BRANCH" --title "<title>" --body "<body>"
# Phase 4: Cleanup
git worktree remove "$OLD_WORKTREE_DIR"
git branch -d "$OLD_BRANCH"
git worktree prune
```

### Rules

- **Centralized location**: All worktrees go in `/home/pcalnon/Development/python/Juniper/worktrees/`. Never create worktrees inside the repo directory.
- **Clean before you start**: Ensure the main working directory is clean before creating a worktree.
- **Push before you merge**: Always push the working branch to remote before merging (backup).
- **Prune after cleanup**: Run `git worktree prune` after removing a worktree to clean metadata.
- **Do not leave stale worktrees**: Clean up worktrees promptly after merging.

---

## Thread Handoff (Mandatory — Replaces Thread Compaction)

> **CRITICAL OPERATING INSTRUCTION**: Thread handoff MUST be performed instead of thread compaction. This section defines mandatory behavior that overrides Claude Code's default compaction process.

### What This Is

When a long-running conversation approaches context limits, Claude Code normally performs **thread compaction** — summarizing prior context to free token capacity. This introduces information loss. Instead, Claude Code instances working on this project MUST perform a **proactive thread handoff**: transferring a curated, high-signal summary to a fresh thread with full context capacity.

The full handoff protocol is defined in **`notes/THREAD_HANDOFF_PROCEDURE.md`**. Read that file when a handoff is triggered.

### When to Trigger a Handoff

**Automatic trigger (pre-compaction threshold):** Initiate a thread handoff when token utilization reaches **95% to 99%** of the level at which thread compaction would normally be triggered.

**Additional triggers**:

| Condition | Indicator |
| --------- | --------- |
| **Context saturation** | Thread has performed 15+ tool calls or edited 5+ files |
| **Phase boundary** | A logical phase of work is complete |
| **Degraded recall** | Re-reading a file already read, or re-asking a resolved question |
| **Multi-module transition** | Moving between major components |
| **User request** | User says "hand off", "new thread", or similar |

**Do NOT handoff** when:

- The task is nearly complete (< 2 remaining steps)
- The current thread is still sharp and producing correct output
- The work is tightly coupled and splitting would lose critical in-flight state

### How to Execute a Handoff

1. **Checkpoint**: Inventory what was done, what remains, what was discovered, and what files are in play
2. **Compose the handoff goal**: Write a concise, actionable summary (see templates in `notes/THREAD_HANDOFF_PROCEDURE.md`)
3. **Present to user**: Output the handoff goal to the user and recommend starting a new thread with that goal as the initial prompt
4. **Include verification commands**: Always specify how the new thread should verify its starting state
5. **State git status**: Mention branch, staged files, and any uncommitted work

### Rules

- **This is not optional.** Every Claude Code instance on this project must follow these rules.
- **Handoff early, not late.** A handoff at 70% context usage is better than compaction at 95%.
- **Do not duplicate CLAUDE.md content** in the handoff goal — the new thread reads CLAUDE.md automatically.
- **Be specific** in the handoff goal: include file paths, decisions made, and test status.
