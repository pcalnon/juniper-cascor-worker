# Changelog

All notable changes to `juniper-cascor-worker` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/pcalnon/juniper-cascor-worker/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/pcalnon/juniper-cascor-worker/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/pcalnon/juniper-cascor-worker/releases/tag/v0.1.0
