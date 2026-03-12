# Pull Request: Security Hardening — Required Auth Key and Security Scanning

**Date:** 2026-03-03
**Version(s):** 0.1.0 → 0.2.0
**Author:** Paul Calnon
**Status:** READY_FOR_MERGE

---

## Summary

Security hardening for juniper-cascor-worker: removes the insecure hardcoded default auth key (`"juniper"`), requiring explicit `WORKER_AUTH_KEY` configuration. Adds scheduled security scanning.

---

## Changes

### Security

- **BREAKING**: Removed hardcoded default `"juniper"` auth key
- `WORKER_AUTH_KEY` environment variable is now REQUIRED — startup fails with clear error if not set

### Added

- `.github/workflows/security-scan.yml` — Weekly Bandit and pip-audit scanning

### Changed

- Updated tests for mandatory auth key requirement

---

## Impact & SemVer

- **SemVer impact:** MINOR (0.1.0 → 0.2.0)
- **Breaking changes:** YES — `WORKER_AUTH_KEY` must be set explicitly (was defaulting to `"juniper"`)
- **Migration steps:** Set `WORKER_AUTH_KEY=<your-key>` in environment before starting worker

---

## Testing & Results

| Test Type | Passed | Failed | Skipped | Notes             |
| --------- | ------ | ------ | ------- | ----------------- |
| Unit      | 46     | 0      | 0       | All tests passing |

---

## Files Changed

- `juniper_cascor_worker/cli.py` — Auth key validation at startup
- `juniper_cascor_worker/config.py` — Removed default auth key value
- `tests/conftest.py` — Updated fixture for mandatory auth key
- `tests/test_config.py` — Tests for auth key requirement
- `tests/test_worker.py` — Updated worker tests
- `.github/workflows/security-scan.yml` — New scanning workflow

---

## Related Issues / Tickets

- Phase Documentation: `juniper-ml/notes/SECURITY_AUDIT_PLAN.md`
