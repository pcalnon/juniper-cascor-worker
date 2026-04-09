# Juniper Cascor Worker v0.2.0 Release Notes

**Release Date:** 2026-03-03
**Version:** 0.2.0
**Codename:** Security Hardening
**Release Type:** MINOR

---

## Overview

Security-hardening release: removes the hardcoded default authentication key and makes `WORKER_AUTH_KEY` a required environment variable. Also adds scheduled security scanning, Dependabot configuration, SOPS-based secrets management, and SHA-pins all GitHub Actions.

> **Status:** STABLE — Pre-1.0 minor release with one breaking change to the auth key requirement.

---

## Release Summary

- **Release type:** MINOR (with one breaking change, allowed pre-1.0 per SemVer)
- **Primary focus:** Security hardening and CI/CD infrastructure
- **Breaking changes:** **YES** — `WORKER_AUTH_KEY` is now required (no default fallback)
- **Priority summary:** Eliminates predictable default credential, adds scheduled vulnerability scanning

---

## Breaking Changes

### `WORKER_AUTH_KEY` Now Required

The hardcoded default `"juniper"` auth key has been removed. The `WORKER_AUTH_KEY` environment variable is now **REQUIRED** for the worker to start.

**Reason:** A predictable default credential allowed any actor with network access to the worker management socket to register a candidate-training worker against a juniper-cascor backend. Forcing operators to set their own key eliminates this attack surface.

**Detection:** Workers started without `WORKER_AUTH_KEY` set will exit immediately with a clear error message at startup.

**Migration:**

```bash
# Set the auth key in your environment / systemd unit / container env file
export WORKER_AUTH_KEY="$(openssl rand -hex 32)"

# Then start the worker as usual
juniper-cascor-worker
```

For production deployments, source the key from a secret store (Docker secrets, Kubernetes secrets, Vault, SOPS-encrypted env file, etc.) rather than a plaintext export.

---

## Security Hardening

- **Removed**: hardcoded default auth key (`"juniper"`)
- **Added**: auth key validation at worker startup with clear error message if not set
- **Added**: `.github/workflows/security-scan.yml` — weekly scheduled security scanning (Bandit + pip-audit)
- **Added**: SOPS configuration (`.sops.yaml`) and `.env.example` for secrets management

---

## What's New

### CI/CD Infrastructure

- Cross-repo CI dispatch to juniper-cascor on push to main
- Dependabot configuration for automated dependency updates (weekly)
- CODEOWNERS file for PR review routing
- This `CHANGELOG.md` (Keep a Changelog format)

---

## Changes

- SHA-pinned all GitHub Actions to immutable commit hashes
- Expanded `.gitignore` to cover all `.env` variants
- Updated tests to require the new mandatory auth key

---

## Test Results

| Metric            | Result |
| ----------------- | ------ |
| **Tests passed**  | 46     |
| **Tests failed**  | 0      |

---

## Upgrade Notes

**This release contains a breaking change.** Operators must set `WORKER_AUTH_KEY` before starting any worker. There is no fallback default.

```bash
# Install or upgrade
pip install --upgrade juniper-cascor-worker==0.2.0

# Set the required auth key
export WORKER_AUTH_KEY="$(openssl rand -hex 32)"

# Start the worker (will error out if WORKER_AUTH_KEY is unset)
juniper-cascor-worker
```

### Migration from v0.1.x

1. Generate a strong auth key and store it in your secret manager.
2. Update your worker startup configuration (systemd unit, Docker env file, Kubernetes secret, etc.) to set `WORKER_AUTH_KEY`.
3. Roll workers one at a time and verify each starts successfully.
4. Update the corresponding cascor backend to use the same `WORKER_AUTH_KEY` value.

---

## Known Issues

- **Documentation drift on auth key naming** — `v0.3.0` later renamed `WORKER_AUTH_KEY` (and the related `--api-key` CLI flag) to `--auth-token` / `CASCOR_AUTH_TOKEN`. Operators upgrading directly from v0.1.x to v0.3.0 should consult the v0.3.0 release notes for the rename mapping.

---

## Cross-Ecosystem Context

This release is part of a coordinated security audit covering 7 Juniper repos and 24 findings. Other repositories shipped corresponding hardening in the same audit cycle.

---

## Version History

| Version | Date       | Description                                                                                         |
| ------- | ---------- | --------------------------------------------------------------------------------------------------- |
| 0.1.0   | 2026-02-22 | Initial release — `CandidateTrainingWorker` distributed candidate training                          |
| 0.1.1   | 2026-03-12 | CI/CD hardening, pre-commit hooks, documentation suite (documented in CHANGELOG; not separately tagged) |
| 0.2.0   | 2026-03-03 | Security hardening — required auth key, scheduled security scanning, Dependabot                     |

---

## Links

- [Full Changelog](../../CHANGELOG.md)
- [Previous Release: v0.1.0](https://github.com/pcalnon/juniper-cascor-worker/releases/tag/v0.1.0)
