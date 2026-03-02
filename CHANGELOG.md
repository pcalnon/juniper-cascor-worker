# Changelog

All notable changes to `juniper-cascor-worker` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- SHA-pinned all GitHub Actions to immutable commit hashes
- Expanded `.gitignore` to cover all `.env` variants

### Added

- Cross-repo CI dispatch to juniper-cascor
- Dependabot configuration for automated dependency updates
- CODEOWNERS file for PR review routing
- SOPS config and `.env.example` for secrets management
- This CHANGELOG

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

[Unreleased]: https://github.com/pcalnon/juniper-cascor-worker/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/pcalnon/juniper-cascor-worker/releases/tag/v0.1.0
