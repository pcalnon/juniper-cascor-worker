# Juniper Cascor Worker v0.3.0 Release Notes

**Release Date:** 2026-04-08
**Version:** 0.3.0
**Codename:** WebSocket Worker Rewrite
**Release Type:** MINOR

---

## Overview

Major rewrite of the worker transport: `CascorWorkerAgent` (WebSocket-based) replaces `CandidateTrainingWorker` (BaseManager-based) as the default operating mode. Adds TLS/mTLS support, Docker and systemd deployment infrastructure, an `--auth-token` rename of the previous `--api-key` flag, and continued security hardening including a `setuptools` CVE fix.

> **Status:** STABLE — Backward-compatible at the deployment level (legacy mode remains available via `--legacy`), but the default operating mode has changed.

---

## Release Summary

- **Release type:** MINOR
- **Primary focus:** WebSocket-based worker rewrite, deployment infrastructure (Docker + systemd), TLS/mTLS support, security
- **Breaking changes:** No (legacy mode preserved behind `--legacy` flag with deprecation warning)
- **Priority summary:** New default operating mode, modern transport, container-ready deployment, CVE remediation

---

## What's New

### WebSocket Worker Agent

The new default worker is `CascorWorkerAgent`, which connects over a long-lived WebSocket and processes work units pushed from the cascor backend.

- **`worker.py`**: `CascorWorkerAgent` class — new default mode
- **`ws_connection.py`**: `WorkerConnection` WebSocket transport with TLS/mTLS support and exponential backoff reconnection
- **`task_executor.py`**: isolated candidate training pipeline with dynamic `CandidateUnit` import
- **Binary tensor frames**: struct-encoded shape, dtype, and raw numpy data for efficient on-wire weight transfer
- **Worker capability reporting**: CPU cores, GPU info, package versions sent on connect
- **Heartbeat keepalive loop**: periodic heartbeats for connection health monitoring

### TLS/mTLS Support

- `--tls-cert`, `--tls-key`, `--tls-ca` CLI flags for mTLS client authentication
- Certificate-based worker identification supported alongside auth tokens

### Auth Token Rename

`--api-key` / `CASCOR_API_KEY` are renamed to `--auth-token` / `CASCOR_AUTH_TOKEN` for clarity. The old names are retained as fallbacks but emit `DeprecationWarning`.

| Old                | New                  | Status                 |
| ------------------ | -------------------- | ---------------------- |
| `--api-key`        | `--auth-token`       | Deprecated (still works) |
| `CASCOR_API_KEY`   | `CASCOR_AUTH_TOKEN`  | Deprecated (still works) |

### Deployment Infrastructure

**Docker:**

- Multi-stage `Dockerfile` with CPU-only PyTorch and non-root user
- `requirements.lock` via `uv pip compile` for reproducible builds
- `.dockerignore` for optimized Docker context

**Systemd:**

- `scripts/juniper-cascor-worker.service` user service unit
- `scripts/juniper-cascor-worker-ctl` management CLI for host-level deployment

### Legacy Mode Preserved

The previous BaseManager-based `CandidateTrainingWorker` remains available behind the `--legacy` flag for operators who need a transition period. It emits `DeprecationWarning` and will be removed in a future major release.

---

## Bug Fixes

### Bandit B105 False Positives

**Problem:** Pre-commit Bandit security scanning flagged auth-token test fixture credential values as hardcoded passwords.

**Solution:** Adjusted Bandit configuration to suppress B105 for known-safe test fixtures.

### `pip-audit` torch Local Version Tag

**Problem:** `pip-audit` could not resolve `torch==X.Y.Z+cpu` because of the `+cpu` local version identifier.

**Solution:** Strip `+cpu` local version from torch in CI before running `pip-audit`.

### isort Import Formatting

**Problem:** Multi-line import in `test_worker_agent.py` failed isort formatting check.

**Solution:** Collapsed multi-line import to satisfy isort.

---

## Security

### CVE: setuptools

**Risk:** Older `setuptools` versions had a CVE affecting source distribution handling.

**Fix:** Bumped `setuptools` minimum version to `>=82.0` in `pyproject.toml` build-system requirements.

### Pre-commit Bandit Integration

Bandit continues to scan all worker code on every commit. The configuration was tuned to avoid false positives on known-safe test fixtures (see Bug Fixes above).

### pip-audit Dependency Scanning

`pip-audit` runs in CI to catch dependency CVEs. The torch `+cpu` local version handling fix above unblocks reliable scanning of the worker dependency tree.

---

## Deprecations

The following surfaces are deprecated but remain functional in v0.3.0. Plan to migrate before the next major release.

| Surface                              | Replacement                  | Notes                                       |
| ------------------------------------ | ---------------------------- | ------------------------------------------- |
| `CandidateTrainingWorker` (legacy)   | `CascorWorkerAgent`          | Use `--legacy` to opt in; emits warning     |
| `--api-key` CLI flag                 | `--auth-token`               | Old flag still parsed                       |
| `CASCOR_API_KEY` env var             | `CASCOR_AUTH_TOKEN`          | Old var still read as fallback              |

---

## Changes

- **Default mode**: WebSocket (no `--legacy` flag needed)
- **Build system**: requires `setuptools>=82.0`
- **GitHub Actions**: SHA-pinned to immutable commit hashes; bumped `actions/cache` 4.2.3→5.0.4, `actions/upload-artifact` 4.6.0→7.0.0, `actions/setup-python` 5.6.0→6.2.0, `github/codeql-action` 3.28.0→4.35.1

---

## Upgrade Notes

This is a backward-compatible release at the deployment level. Operators may continue using the BaseManager-based worker via `--legacy` during their migration window.

```bash
# Install or upgrade
pip install --upgrade juniper-cascor-worker==0.3.0

# Default mode (WebSocket-based CascorWorkerAgent)
juniper-cascor-worker --auth-token "$(cat /run/secrets/cascor_auth_token)"

# Legacy mode (deprecated; emits DeprecationWarning)
juniper-cascor-worker --legacy --auth-token "$(cat /run/secrets/cascor_auth_token)"
```

### TLS/mTLS Setup

```bash
juniper-cascor-worker \
  --auth-token "$(cat /run/secrets/cascor_auth_token)" \
  --tls-cert /etc/juniper/tls/worker.crt \
  --tls-key  /etc/juniper/tls/worker.key \
  --tls-ca   /etc/juniper/tls/ca.crt
```

### Docker Deployment

```bash
docker run --rm \
  -e CASCOR_AUTH_TOKEN \
  --network juniper_backend \
  ghcr.io/pcalnon/juniper-cascor-worker:0.3.0
```

### Systemd Deployment

```bash
# Install the user-service unit
cp scripts/juniper-cascor-worker.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now juniper-cascor-worker.service

# Or use the management CLI wrapper
scripts/juniper-cascor-worker-ctl start
```

---

## Known Issues

None known at time of release. Operators using legacy mode should plan a migration to the WebSocket agent before the next major version.

---

## Version History

| Version | Date       | Description                                                                                  |
| ------- | ---------- | -------------------------------------------------------------------------------------------- |
| 0.1.0   | 2026-02-22 | Initial release — `CandidateTrainingWorker` distributed candidate training                   |
| 0.2.0   | 2026-03-03 | Security hardening — required auth key, scheduled security scanning, Dependabot              |
| 0.3.0   | 2026-04-08 | WebSocket worker rewrite, TLS/mTLS, Docker + systemd deployment, auth token rename, CVE fix  |

---

## Links

- [Full Changelog](../../CHANGELOG.md)
- [Previous Release: v0.2.0](RELEASE_NOTES_v0.2.0.md)
