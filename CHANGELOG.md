# Changelog

All notable changes to `juniper-cascor-worker` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- New `juniper_cascor_worker/constants.py` module centralizing wire-protocol message-type discriminators (`MSG_TYPE_*`), binary-frame header format (`BINARY_FRAME_*`), auth header / env var names (`AUTH_*`, `ENV_*`), and worker tuning defaults previously embedded as inline literals across `worker.py`, `task_executor.py`, `ws_connection.py`, `config.py`, and `cli.py`.

### Changed

- All five worker-package modules now import from `juniper_cascor_worker.constants` instead of embedding literals (~70 replacements total).
- `MSG_TYPE_*` and `BINARY_FRAME_*` constants are guaranteed bit-identical to the cascor server's `MessageType(StrEnum)` and `BinaryFrame` struct format — verified by Wave 5 cross-repo alignment checks. Drift here would silently break worker/server connectivity.
- `AGENTS.md` gained a new "Constants" section documenting categories, server alignment, and contribution rules.

### Notes

- No public API changes; `WorkerConfig`, `CascorWorkerAgent`, `CandidateTrainingWorker`, CLI flags, and exception hierarchy are all unchanged.
- All 130 existing tests pass without modification; pre-commit (22 hooks) is clean.

## [0.3.0] - 2026-04-08

**Summary**: WebSocket-based worker rewrite — `CascorWorkerAgent` replaces `CandidateTrainingWorker` as the default operating mode. Auth token rename, TLS/mTLS support, Docker and systemd deployment infrastructure, and continued security hardening.

### Added: [0.3.0]

- WebSocket-based `CascorWorkerAgent` as new default operating mode (`worker.py`)
- `WorkerConnection` WebSocket transport with TLS/mTLS support and exponential backoff reconnection (`ws_connection.py`)
- `task_executor` module: isolated candidate training pipeline with dynamic `CandidateUnit` import (`task_executor.py`)
- Binary tensor frame encoding/decoding protocol (struct-encoded shape, dtype, raw numpy data)
- Worker capability reporting (CPU cores, GPU info, package versions)
- Heartbeat keepalive loop for connection health monitoring
- `--auth-token` CLI flag (replaces `--api-key`)
- `CASCOR_AUTH_TOKEN` environment variable (`CASCOR_API_KEY` retained as fallback)
- TLS support: `--tls-cert`, `--tls-key`, `--tls-ca` CLI flags for mTLS client authentication
- `--legacy` CLI flag to opt into deprecated BaseManager mode
- Docker multi-stage build (`Dockerfile`) with CPU-only PyTorch, non-root user
- `requirements.lock` via `uv pip compile` for reproducible builds
- `.dockerignore` for optimized Docker context
- `scripts/juniper-cascor-worker.service` systemd user service unit
- `scripts/juniper-cascor-worker-ctl` management CLI script for host-level deployment

### Changed: [0.3.0]

- Default mode is now WebSocket (no `--legacy` flag needed)
- Build system requires `setuptools>=82.0` (CVE fix for older setuptools vulnerabilities)
- GitHub Actions updated to SHA-pinned versions: `actions/cache` 4.2.3->5.0.4, `actions/upload-artifact` 4.6.0->7.0.0, `actions/setup-python` 5.6.0->6.2.0, `github/codeql-action` 3.28.0->4.35.1

### Deprecated: [0.3.0]

- `CandidateTrainingWorker` (BaseManager/legacy mode) — use `CascorWorkerAgent`; emits `DeprecationWarning`
- `--api-key` CLI flag — use `--auth-token`
- `CASCOR_API_KEY` environment variable — use `CASCOR_AUTH_TOKEN`

### Fixed: [0.3.0]

- Resolved pre-commit Bandit B105 false positives on test fixture credential values
- Stripped `+cpu` local version from torch for pip-audit resolution
- Fixed isort multi-line import formatting in `test_worker_agent.py`

### Security: [0.3.0]

- `setuptools` minimum version bumped to `>=82.0` to address CVE in older versions
- Pre-commit Bandit security scanning adjusted for auth_token test fixtures
- pip-audit dependency vulnerability scanning in CI (`strip +cpu` fix for torch compatibility)

## [0.2.0] - 2026-03-03

**Summary**: Security hardening — required auth key (breaking change) and scheduled security scanning. Also includes previously unreleased CI/CD improvements.

### Security: [0.2.0]

- **BREAKING**: Removed hardcoded default `"juniper"` auth key; `WORKER_AUTH_KEY` environment variable is now REQUIRED
- Added auth key validation at startup — fails with clear error message if not set

### Added: [0.2.0]

- `.github/workflows/security-scan.yml` — Weekly scheduled security scanning (Bandit, pip-audit)
- Cross-repo CI dispatch to juniper-cascor
- Dependabot configuration for automated dependency updates
- CODEOWNERS file for PR review routing
- SOPS config and `.env.example` for secrets management
- This CHANGELOG

### Changed: [0.2.0]

- SHA-pinned all GitHub Actions to immutable commit hashes
- Expanded `.gitignore` to cover all `.env` variants
- Updated tests for mandatory auth key requirement

### Technical Notes: [0.2.0]

- **SemVer impact**: MINOR (breaking auth key change, but pre-1.0)
- **Test count**: 46 passed, 0 failed
- **Part of**: Cross-ecosystem security audit (7 repos, 24 findings)

## [0.1.1] - 2026-03-12

**Summary**: CI/CD hardening, pre-commit hooks, documentation suite, and Dependabot-driven GitHub Actions version bumps.

### Added: [0.1.1]

- Pre-commit hooks configuration: black, isort, flake8, mypy, bandit, shellcheck, yamllint, markdownlint (`.pre-commit-config.yaml`)
- `.markdownlint.yaml` with Juniper ecosystem 512-char line length
- Enhanced CI pipeline with pre-commit, unit tests, security scans, build verification, and quality gate (`.github/workflows/ci.yml`)
- Documentation suite: `DOCUMENTATION_OVERVIEW.md`, `QUICK_START.md`, `REFERENCE.md` (`docs/`)
- Developer cheatsheet (`docs/DEVELOPER_CHEATSHEET.md`)
- AGENTS.md with thread handoff and worktree procedures
- Ecosystem compatibility matrix in README
- Documentation link validation in CI (`scripts/check_doc_links.py`)
- Dependency documentation generation in CI (`scripts/generate_dep_docs.sh`)
- V2 worktree cleanup procedure (fixes CWD-trap bug)

### Changed: [0.1.1]

- Line length standardized to 512 for black, isort, flake8
- Removed Python 3.14 from black target versions
- GitHub Actions bumped: `actions/checkout` 4->6, `actions/setup-python` 5->6, `actions/upload-artifact` 4->6

## [0.1.0] - 2026-02-22

### Added

- Initial release of `juniper-cascor-worker`
- `CandidateTrainingWorker` class for distributed candidate training
- `WorkerConfig` dataclass with environment variable configuration
- CLI entry point (`juniper-cascor-worker`)
- Type annotations with `py.typed` marker
- Unit test suite with 80%+ coverage
- CI/CD pipeline with GitHub Actions
- PyPI and TestPyPI trusted publishing
- README with usage documentation
- Ecosystem compatibility matrix
- AGENTS.md with thread handoff and worktree procedures

[Unreleased]: https://github.com/pcalnon/juniper-cascor-worker/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/pcalnon/juniper-cascor-worker/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/pcalnon/juniper-cascor-worker/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/pcalnon/juniper-cascor-worker/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/pcalnon/juniper-cascor-worker/releases/tag/v0.1.0
