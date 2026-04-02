# AGENTS.md Drift Analysis — juniper-cascor-worker

**Date**: 2026-04-02
**Auditor**: Claude Code (automated audit)
**Baseline**: AGENTS.md as of commit `f351324` (main branch)
**Codebase Version**: 0.3.0

---

## Executive Summary

The AGENTS.md file for `juniper-cascor-worker` has significant drift from the current codebase state. The file reflects an early version (0.1.0) of the project and has not been updated through the 0.2.0 and 0.3.0 development cycles that introduced WebSocket-based worker architecture, TLS/mTLS support, a binary tensor protocol, expanded test coverage, comprehensive documentation, and CI/CD pipelines.

**Severity**: High — the AGENTS.md omits the project's primary operating mode (WebSocket) and contains incorrect CLI flags, dependency lists, and configuration defaults.

---

## Drift Categories

### 1. CRITICAL — Incorrect Information

| Item | AGENTS.md States | Actual Codebase | Impact |
|------|-----------------|-----------------|--------|
| **Version** | `0.1.0` | `0.3.0` | Misleading; two major releases behind |
| **Last Updated** | `2026-02-25` | Needs `2026-04-02` | Stale date |
| **CLI run command** | `juniper-cascor-worker --host <manager-host> --port <manager-port>` | `juniper-cascor-worker --server-url <url> --auth-token <token>` (default) or `--legacy --manager-host <host> --manager-port <port>` | **Agents will use non-existent CLI flags** |
| **AUTHKEY default** | `juniper` | Empty string (required, validated) | Incorrect default will cause connection failures |
| **Flake8 line length** | `--max-line-length=120` | `512` (pyproject.toml, pre-commit) | Linting inconsistency |

### 2. HIGH — Missing Core Architecture

| Missing Content | Description | Impact |
|----------------|-------------|--------|
| **WebSocket mode** | CascorWorkerAgent is the default worker — not documented at all | Agents have no awareness of the primary operating mode |
| **Binary tensor protocol** | JSON control messages + struct-encoded binary tensor frames | Wire protocol undocumented |
| **TLS/mTLS support** | `wss://` protocol, `--tls-cert/--tls-key/--tls-ca` flags | Security features invisible |
| **CascorWorkerAgent class** | Async event loop, registration, heartbeat, task handling | Primary class undocumented |
| **WorkerConnection class** | WebSocket lifecycle, reconnection with exponential backoff | Connection management undocumented |
| **Task executor** | `execute_training_task()` function, CandidateUnit import | Training pipeline undocumented |
| **Exception hierarchy** | WorkerError → WorkerConnectionError, WorkerConfigError | Error handling undocumented |
| **Legacy deprecation** | CandidateTrainingWorker emits DeprecationWarning since 0.3.0 | Mode status unclear |

### 3. HIGH — Missing Environment Variables

| Variable | Mode | Description |
|----------|------|-------------|
| `CASCOR_SERVER_URL` | WebSocket | Server endpoint URL (required) |
| `CASCOR_AUTH_TOKEN` | WebSocket | X-API-Key authentication token |
| `CASCOR_API_KEY` | WebSocket | Alias for CASCOR_AUTH_TOKEN |
| `CASCOR_HEARTBEAT_INTERVAL` | WebSocket | Heartbeat interval in seconds |
| `CASCOR_TLS_CERT` | WebSocket | Client certificate path |
| `CASCOR_TLS_KEY` | WebSocket | Client private key path |
| `CASCOR_TLS_CA` | WebSocket | CA bundle path |

Legacy variables (`CASCOR_MANAGER_HOST`, `CASCOR_MANAGER_PORT`, `CASCOR_AUTHKEY`, `CASCOR_NUM_WORKERS`, `CASCOR_MP_CONTEXT`) are documented but should be marked as legacy-only.

### 4. HIGH — Missing Dependencies

| Package | Version | Purpose | Status in AGENTS.md |
|---------|---------|---------|-------------------|
| `websockets` | `>=11.0` | WebSocket client (async) | **Not listed** |
| `numpy` | `>=1.24.0` | Numerical computations | Listed |
| `torch` | `>=2.0.0` | Neural network operations | Listed |

### 5. MEDIUM — Missing Key Files

The Key Files table lists only 4 entries. The following are missing:

| File | Purpose |
|------|---------|
| `juniper_cascor_worker/config.py` | WorkerConfig dataclass with validation |
| `juniper_cascor_worker/worker.py` | CascorWorkerAgent + CandidateTrainingWorker implementations |
| `juniper_cascor_worker/ws_connection.py` | WebSocket connection management |
| `juniper_cascor_worker/task_executor.py` | Training task execution pipeline |
| `juniper_cascor_worker/exceptions.py` | Custom exception hierarchy |
| `juniper_cascor_worker/py.typed` | PEP 561 type marker |
| `CHANGELOG.md` | Version history (0.1.0 → 0.3.0) |
| `scripts/check_doc_links.py` | Internal markdown link validator |
| `scripts/generate_dep_docs.sh` | Dependency documentation generator |
| `docs/DOCUMENTATION_OVERVIEW.md` | Documentation navigation guide |
| `docs/QUICK_START.md` | 5-minute install and run guide |
| `docs/REFERENCE.md` | Complete API and CLI reference |
| `docs/DEVELOPER_CHEATSHEET.md` | Quick-reference for common dev tasks |
| `.pre-commit-config.yaml` | Pre-commit hook configuration |
| `.github/workflows/ci.yml` | CI/CD pipeline |
| `.github/workflows/security-scan.yml` | Weekly security scanning |
| `.github/workflows/publish.yml` | PyPI publishing workflow |

### 6. MEDIUM — Missing Entire Sections

The following sections have no representation in AGENTS.md:

| Section | Content |
|---------|---------|
| **Application Architecture** | Two-mode architecture, worker lifecycle, module dependency graph |
| **Public API** | Exports from `__init__.py`, class interfaces, exception hierarchy |
| **Configuration Details** | WorkerConfig dataclass fields, validation rules, from_env() method |
| **Directory Layout** | Full tree structure with descriptions |
| **CI/CD Pipeline** | 6-job pipeline: pre-commit, tests, security, build, docs, quality-gate |
| **Pre-commit Hooks** | Black, isort, flake8, mypy, bandit, shellcheck, yamllint, markdownlint, SOPS |
| **Documentation** | docs/ directory with 4 user-facing documents |
| **Scripts** | scripts/ directory with 2 utility scripts |
| **Test Details** | 6 test files, ~83 tests, ~1571 lines, individual file descriptions |
| **Python Version** | `>=3.11` requirement, supported versions 3.11-3.14 |
| **Signal Handling** | Dual SIGINT/SIGTERM with force-exit on second signal |
| **Dynamic Imports** | CandidateUnit and CascadeCorrelationNetwork from cascor codebase |
| **Security** | Auth token, mTLS, weekly security scanning, Gitleaks, Bandit, pip-audit |

### 7. LOW — Stale References

| Item | Issue |
|------|-------|
| `conf/requirements_ci.txt` | Referenced in AGENTS.md env var context but `conf/` directory is empty |
| `conf/conda_environment_ci.yaml` | Referenced but does not exist |
| Ecosystem compatibility table | Lists `0.1.x` worker version, should be `0.3.x` |

---

## Quantitative Summary

| Metric | Value |
|--------|-------|
| Total drift items identified | 42 |
| Critical (incorrect information) | 5 |
| High (missing core content) | 17 |
| Medium (missing supplementary content) | 16 |
| Low (stale references) | 4 |
| Current AGENTS.md line count | 204 |
| Estimated corrected line count | ~500-600 |
| Sections needing addition | 12 |
| Sections needing correction | 3 |
| Sections unchanged (correct as-is) | 2 (Worktree Procedures, Thread Handoff) |

---

## Sections Assessment

| Section | Status | Action Required |
|---------|--------|----------------|
| Header/Metadata | **INCORRECT** | Update version, date |
| Quick Reference — Essential Commands | **INCORRECT** | Fix CLI command, line-length flag |
| Quick Reference — Environment Variables | **INCOMPLETE** | Add WebSocket vars, mark legacy |
| Quick Reference — Key Files | **INCOMPLETE** | Add all module files, docs, scripts |
| Project Overview | **INCOMPLETE** | Add architecture, WebSocket mode |
| Dependencies | **INCOMPLETE** | Add websockets |
| Ecosystem Context | CORRECT | No change needed |
| Worktree Procedures | CORRECT | No change needed |
| Thread Handoff | CORRECT | No change needed |
| Application Architecture | **MISSING** | New section required |
| Public API | **MISSING** | New section required |
| Configuration Details | **MISSING** | New section required |
| Directory Layout | **MISSING** | New section required |
| CI/CD Pipeline | **MISSING** | New section required |
| Pre-commit Hooks | **MISSING** | New section required |
| Documentation | **MISSING** | New section required |
| Scripts | **MISSING** | New section required |
| Test Details | **MISSING** | New section required |
| Python Requirements | **MISSING** | New section required |
| Security | **MISSING** | New section required |
| Signal Handling & CLI | **MISSING** | New section required |
| Dynamic Imports | **MISSING** | New section required |
