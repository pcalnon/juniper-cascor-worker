# Developer Cheatsheet — juniper-cascor-worker

**Version**: 1.1.0
**Date**: 2026-05-04
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

## CI and Security Workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `.github/workflows/ci.yml` | Pushes, PRs, manual dispatch | Main quality gate: pre-commit, docs links, tests, build, dependency docs, and security scans |
| `.github/workflows/codeql.yml` | Pushes to `main`/`develop`, PRs to `main`, weekly schedule | CodeQL semantic SAST for Python with `security-and-quality` queries |
| `.github/workflows/security-scan.yml` | Weekly schedule, manual dispatch | Scheduled Bandit and pip-audit scan with uploaded security reports |

Security scan behavior:

- `ci.yml` runs Gitleaks, Bandit SARIF upload, and pip-audit as the PR-facing `security` job.
- Bandit writes `reports/security/bandit.sarif`; `github/codeql-action/upload-sarif` publishes it to GitHub code scanning.
- `codeql.yml` uses the CodeQL `init`, `autobuild`, and `analyze` actions for Python.
- GitHub Actions are SHA-pinned with version comments. Dependabot bumps should update both the pinned SHA and the trailing version comment together.
- The pip-audit jobs currently ignore `CVE-2026-3219` for the runner-provided pip version until an upstream fix is available; re-check that exception when changing the audit workflow.

---

## CLI Usage

### Start a Worker

```bash
# Default WebSocket mode
juniper-cascor-worker --server-url ws://192.168.1.10:8200/ws/v1/workers --auth-token my-worker-token

# Legacy mode (deprecated)
juniper-cascor-worker --legacy --manager-host 192.168.1.10 --manager-port 50000 --authkey my-legacy-key --workers 4
```

### CLI Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--legacy` | FLAG | `False` | Use deprecated BaseManager path |
| `--server-url` | TEXT | `None` | WebSocket worker endpoint URL |
| `--auth-token` | TEXT | `None` | Token sent in `X-API-Key` header |
| `--heartbeat-interval` | FLOAT | `10.0` | Seconds between heartbeat messages |
| `--tls-cert` | TEXT | `None` | Client certificate path for mTLS |
| `--tls-key` | TEXT | `None` | Client key path for mTLS |
| `--tls-ca` | TEXT | `None` | Custom CA bundle path |
| `--manager-host` | TEXT | `127.0.0.1` | Legacy manager hostname (`--legacy`) |
| `--manager-port` | INTEGER | `50000` | Legacy manager port (`--legacy`) |
| `--authkey` | TEXT | `None` | Legacy auth key (`--legacy`) |
| `--workers` | INTEGER | `1` | Legacy worker process count (`--legacy`) |
| `--mp-context` | CHOICE | `forkserver` | Legacy multiprocessing context (`--legacy`) |
| `--log-level` | CHOICE | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `--cascor-path` | TEXT | -- | Path to CasCor src directory (added to `sys.path`) |

Signal handling: first SIGINT/SIGTERM triggers graceful shutdown; second forces exit.

> See: [docs/REFERENCE.md](REFERENCE.md#cli-reference) for full CLI reference.

---

## Python API

### WorkerConfig

```python
from juniper_cascor_worker import CascorWorkerAgent, WorkerConfig

config = WorkerConfig(
    server_url="ws://192.168.1.10:8200/ws/v1/workers",
    auth_token="my-worker-token",
)

# Or from environment variables (CASCOR_*)
config = WorkerConfig.from_env()
```

### Worker Lifecycle

```python
import asyncio

agent = CascorWorkerAgent(config)
asyncio.run(agent.run())
```

### Lifecycle States

```
(init) --> configured --> connecting --> registered --> processing --> stopped
             validate()      run()         _register()      loops       stop()
```

> See: [docs/REFERENCE.md](REFERENCE.md#python-api) for full API reference.

---

## Distributed Training Architecture

### How It Works

1. **juniper-cascor** exposes the `/ws/v1/workers` endpoint
2. **juniper-cascor-worker** connects via WebSocket, optionally authenticating with `X-API-Key`
3. The worker receives `task_assign` metadata plus binary tensor frames
4. The worker executes candidate training locally and sends `task_result` plus output tensors
5. Heartbeat messages keep liveness and support reconnect behavior

### Communication Flow

```
juniper-cascor (Server)               juniper-cascor-worker (Remote)
+----------------------------+        +----------------------------+
| /ws/v1/workers endpoint    |        | CascorWorkerAgent          |
| JSON + binary task frames  |<------>| async message + heartbeat  |
| X-API-Key auth             |        | local training execution   |
+----------------------------+        +----------------------------+
       WebSocket (ws:// or wss://)
```

### Multiprocessing Context

| Context | Platform | Notes |
|---------|----------|-------|
| `forkserver` | Linux/macOS | Legacy mode default; safest for most scenarios |
| `spawn` | All | Most portable; slower startup |
| `fork` | Unix only | Fastest; can deadlock with threads (legacy mode) |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CASCOR_SERVER_URL` | *(required in default mode)* | WebSocket worker endpoint URL |
| `CASCOR_AUTH_TOKEN` | empty | Token sent in `X-API-Key` header |
| `CASCOR_HEARTBEAT_INTERVAL` | `10.0` | Heartbeat interval in seconds |
| `CASCOR_TLS_CERT` | unset | Client certificate path (mTLS) |
| `CASCOR_TLS_KEY` | unset | Client key path (mTLS) |
| `CASCOR_TLS_CA` | unset | CA bundle path for TLS verification |
| `CASCOR_MANAGER_HOST` | `127.0.0.1` | Manager hostname |
| `CASCOR_MANAGER_PORT` | `50000` | Manager port |
| `CASCOR_AUTHKEY` | *(required)* | Authentication key. No usable default; worker fails validation if unset. `.env.example` uses `juniper` as a sample value. |
| `CASCOR_NUM_WORKERS` | `1` | Number of worker processes |
| `CASCOR_MP_CONTEXT` | `forkserver` | Multiprocessing start method |

All variables are read by `WorkerConfig.from_env()`.

---

## Error Handling

```
WorkerError (base)
+-- WorkerConnectionError    # Connection or protocol failures
+-- WorkerConfigError        # Invalid configuration
```

| Exception | Raised When |
|-----------|-------------|
| `WorkerConfigError` | Invalid WebSocket URL/scheme/heartbeat/backoff or invalid legacy settings |
| `WorkerConnectionError` | WebSocket connection/reconnect failures, closed socket, or registration problems |
| `WorkerError` | Legacy `CandidateTrainingWorker` import/connect/start failures |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Authentication fails in default mode | Using old `--api-key` / `CASCOR_API_KEY` names | Use `--auth-token` and `CASCOR_AUTH_TOKEN` |
| Manager flags appear ignored | Running without `--legacy` | Add `--legacy` to enable BaseManager worker path |
| `server_url is required` | Missing worker endpoint in default mode | Set `--server-url` or `CASCOR_SERVER_URL` |
| `WorkerConnectionError` in legacy mode | Manager not running or wrong host/port/authkey | Verify manager settings and `CASCOR_AUTHKEY` match |
| `WorkerError` in legacy mode | CasCor source not on `sys.path` | Use `--cascor-path` CLI flag or install CasCor source |
| `WorkerConfigError` in legacy mode | Invalid port or worker count | Port must be 1-65535, workers must be >= 1 |

---

## CI and Automation Runbook

### GitHub Actions Layout

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `.github/workflows/ci.yml` | Pushes, pull requests, manual dispatch | Required CI quality gate |
| `.github/workflows/security-scan.yml` | Weekly Monday schedule, manual dispatch | Scheduled Bandit and `pip-audit` scan |
| `.github/workflows/publish.yml` | Published GitHub releases | Build, publish to TestPyPI, verify install, then publish to PyPI |
| `.github/workflows/claude.yml` | `@claude` issue and PR comments/reviews | Runs the Claude Code assistant workflow; canonical copy lives in `juniper-ml` |

Workflow actions are SHA-pinned with adjacent version comments. For GitHub Actions Dependabot PRs, expect the `uses:` SHA and version comment to move together.

### Required CI Gate

`ci.yml` aggregates these jobs in `required-checks`:

1. `pre-commit` on Python 3.12, 3.13, and 3.14.
2. `docs`, which runs `python scripts/check_doc_links.py --exclude templates --exclude history`.
3. `unit-tests` on Linux for Python 3.12, 3.13, and 3.14 plus macOS Python 3.12.
4. `integration-tests` on Python 3.12, 3.13, and 3.14. Failures are reported as warnings during the shakedown cycle.
5. `build`, which builds wheel and sdist artifacts and runs `twine check`.
6. `dependency-docs`, which runs `bash scripts/generate_dep_docs.sh` and uploads generated dependency files.
7. `security`, which runs Gitleaks, Bandit SARIF upload, and `pip-audit`.

When a PR fails the quality gate, inspect the failed upstream job first; `required-checks` usually only reports the aggregate failure.

### Dependabot Updates

Dependabot is configured in `.github/dependabot.yml`:

| Ecosystem | Schedule | PR Limit | Labels | Commit Prefix |
|-----------|----------|----------|--------|---------------|
| `pip` | Weekly Monday 09:00 America/New_York | 5 | `dependencies`, `security` | `deps` |
| `github-actions` | Weekly Monday | 3 | `dependencies`, `ci` | `ci` |

For GitHub Actions PRs, verify that only the intended `uses:` SHA and version comment changed unless Dependabot explicitly updates multiple actions. For Python dependency PRs, run the affected tests plus the coverage command when dependency behavior could affect task execution.

### Common CI Pitfalls

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| Action version comment disagrees with the SHA | Manual edit or incomplete Dependabot update | Reconcile the `uses:` SHA with the upstream release tag before merging |
| `docs` job fails on an internal link | Renamed or moved markdown target | Run `python scripts/check_doc_links.py --exclude templates --exclude history` locally and update the link |
| Linux torch install differs from macOS | Linux CI uses the CPU-only PyTorch index; macOS uses PyPI | Keep OS-specific torch installation branches in `ci.yml` |
| `security` fails on `pip-audit` after a runner image change | Newly reported dependency or runner-provided package vulnerability | Check the generated requirements file and only add ignores for documented no-fix cases |

---

## Cross-References

- [juniper-cascor-worker REFERENCE.md](REFERENCE.md) -- Full API and CLI reference
- [juniper-cascor-worker QUICK_START.md](QUICK_START.md) -- Getting started guide
- [juniper-cascor-worker AGENTS.md](../AGENTS.md) -- Agent development guide
- [Ecosystem Cheatsheet](https://github.com/pcalnon/juniper-ml/blob/main/notes/DEVELOPER_CHEATSHEET.md) -- Cross-project procedures
- [juniper-cascor-client Cheatsheet](https://github.com/pcalnon/juniper-cascor-client/blob/main/docs/DEVELOPER_CHEATSHEET.md) -- HTTP/WebSocket client
