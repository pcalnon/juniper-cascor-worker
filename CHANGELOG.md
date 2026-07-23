# Changelog

All notable changes to `juniper-cascor-worker` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0] - 2026-07-23

### Added

- **Build provenance on `/v1/health`.** The worker now reports the source
  ``git_sha`` and ISO-8601 ``build_date`` baked into its image at build time
  (new `GIT_SHA` / `BUILD_DATE` build-args → OCI labels +
  `JUNIPER_CASCOR_WORKER_GIT_SHA` / `_BUILD_DATE` env vars in the Dockerfile,
  read by `HealthServer`). Both are ``null`` when the worker runs outside a
  provenance-stamped image (local dev / bare build). Foundation for the
  ecosystem stale-image-detection effort — see juniper-ml
  ``notes/BUILD_PROVENANCE_DESIGN_2026-06-14.md``. The image also gains the
  standard `org.opencontainers.image.revision` / `.created` / `.version`
  labels.

### Changed

- **CI: per-file coverage is now a blocking gate (ecosystem per-file coverage rollout C-5).**
  The `unit-tests` job now emits `--cov-report=json` and runs the shared
  `juniper-coverage-gap-map --enforce` gate from `juniper-ci-tools>=0.6.0,<0.7.0`,
  **failing the build** when any source file's statement coverage is below 90% or any
  packaged sub-module's pooled (statement-weighted) coverage is below 95%. This is additive
  to the existing aggregate `--cov-fail-under=80` gate; the shared tool computes statement %
  itself from `reports/coverage.json`, so the `branch = true` coverage config does not change
  the gate basis. `util/run_coverage.bash` reproduces both gates locally (the per-file gate is
  skipped with a hint when `juniper-coverage-gap-map` is not installed). See juniper-ml
  `notes/JUNIPER_ECOSYSTEM_PER_FILE_COVERAGE_ROLLOUT_SCOPING_2026-06-30.md`.

### Tests

- **Lifted per-file / pooled coverage to the ratified bars** (overall 92.5% → 95.5%
  statement-pooled) with no production-code changes. Added error-path tests for
  `http_health.py` (88.96% → 98%: request-line / header read timeouts, empty / oversize /
  non-ASCII request lines, the never-crash 500 outer handler, and the missing-`resource`-module
  fallback), `ws_connection.py` (receive-when-disconnected, the `ConnectionClosed` unwind, the
  best-effort `close()` swallow, and the mTLS `load_verify_locations` / `load_cert_chain`
  branches), and `task_executor.py` (tensor→float-list correlation coercion and the
  `_get_activation_function` lowercase-retry / unknown-name fallback). Every source file is now
  ≥90% statement and the `juniper_cascor_worker` sub-module pools to 96.83%.

### Fixed

- **`juniper_cascor_worker.__version__` aligned `0.3.0` → `0.4.0`** to match
  `pyproject.toml` `[project].version` and `AGENTS.md`. The health probe reports
  the installed-distribution version via `importlib.metadata`, so this stale
  module constant was latent, but it could mislead code importing `__version__`
  directly.
- **`cli.py` now routes env reads through `_resolve` so `_FILE` indirection
  is honored at the production entry point**. The `_FILE`-suffix support
  shipped in [#94](https://github.com/pcalnon/juniper-cascor-worker/pull/94)
  only fixed `config._resolve` / `WorkerConfig.from_env`; the WebSocket-mode
  CLI (`_run_websocket`) and legacy-mode CLI (`_run_legacy`) both called
  `juniper_config_tools.env_with_legacy_alias` **directly** — which has no
  `_FILE` handling. End-to-end verification against the rebuilt worker image
  after #94 surfaced the gap immediately: cascor's `api_keys` populated
  correctly, manual `WorkerConfig.from_env()` inside the container returned
  the token, but the production `cli.main()` path still produced
  `auth_token=""` because `args.auth_token or env_with_legacy_alias(...)`
  never looked at `CASCOR_AUTH_TOKEN_FILE`. Workers 403'd on every WS
  handshake.

  All six `env_with_legacy_alias(...)` call sites in `cli.py` are now
  `_resolve(None, ...)` — same name pair, same precedence, plus `_FILE`
  indirection. The helper import is preserved (pinned by the CFG-06
  source-scope lint) so the dependency surface is unchanged. The lint's
  error message was updated to acknowledge both `_resolve` (preferred —
  honors `_FILE`) and `env_with_legacy_alias` (no `_FILE` support) as
  acceptable resolvers.

  New regression tests in `tests/test_resolve_file_indirection.py`:
  `TestCliFileIndirection` (2 tests) drives `cli._run_websocket` with a
  fake `CascorWorkerAgent` and mocked `signal.signal` / `asyncio.run`,
  pinning that `CASCOR_AUTH_TOKEN_FILE` (legacy `_FILE`) and
  `JUNIPER_CASCOR_WORKER_AUTH_TOKEN_FILE` (canonical `_FILE`) both flow
  through `cli.main()` into `WorkerConfig.auth_token`.

### Added

- **`_FILE`-suffix indirection in `_resolve`**: every env var the worker resolves
  (`JUNIPER_CASCOR_WORKER_*` canonical names and their legacy aliases) now
  honors a `<NAME>_FILE` companion that contains the path to a file with the
  value. The file's content is read with `strip()`, matching the
  Docker-secrets / k8s-secrets convention. Order of precedence per name pair:
  canonical `_FILE` → canonical direct → legacy `_FILE` (with one
  `DeprecationWarning`) → legacy direct (existing warning shape preserved) →
  default. Missing / empty / unreadable files fall through silently so an
  un-populated Docker secret doesn't masquerade as a deliberate empty value.

  Closes the gap that left worker → cascor auth silently broken under
  juniper-deploy's DEPLOY-09 hardening (compose sets
  `CASCOR_AUTH_TOKEN_FILE=/run/secrets/cascor_auth_token` and mounts the
  secret file, but pre-fix `_resolve` only read env-var values — worker
  booted with `auth_token=""`). New regression suite at
  `tests/test_resolve_file_indirection.py` (16 tests) pins canonical `_FILE`
  precedence, legacy `_FILE` deprecation-warning shape (names both legacy
  and canonical `_FILE` vars), file-content stripping, fall-through on
  missing / empty / unreadable / directory paths, production-path
  (`os.environ`) parity, and `WorkerConfig.from_env` end-to-end resolution
  from `CASCOR_AUTH_TOKEN_FILE`.

  Production `_resolve` no longer delegates to
  `juniper_config_tools.env_with_legacy_alias`; the helper does not currently
  understand the `_FILE` suffix and adding that handling outside it would
  duplicate the env lookup. Once `juniper_config_tools >= 0.2` supports
  `_FILE` natively, the inline path can collapse back to a delegation. The
  helper remains imported (pinned by the CFG-06 source-scope lint) so the
  dependency surface is unchanged.

### Fixed

- **Lockfile**: `requirements-cpu.lock` regenerated to include `juniper-config-tools==0.1.0`. PR [#88](https://github.com/pcalnon/juniper-cascor-worker/pull/88) patched the same CFG-06 fallout in `requirements.lock` but missed the CPU-only sibling, leaving the CI `Check requirements-cpu.lock contains every pyproject dep` step annotating every PR. Transitive pins refreshed alongside: `filelock` 3.25.2 → 3.29.0, `fsspec` 2026.2.0 → 2026.4.0, `numpy` 2.4.3 → 2.4.4. The CPU-only Docker container build now resolves all worker runtime deps from a single lockfile.

## [0.4.0] - 2026-05-23

### Changed

- **CFG-06** (v7 roadmap §20): all 15 worker env vars renamed from bare `CASCOR_*` (or partial-scope `CASCOR_WORKER_*`) to the ecosystem-canonical `JUNIPER_CASCOR_WORKER_*` prefix. Legacy names continue to work via the shared `juniper-config-tools>=0.1.0,<0.2.0` alias-with-deprecation helper (added as a new runtime dep — stdlib-only, does not regress the `tests/test_no_pydantic_at_runtime.py` invariant). Each legacy use emits one `DeprecationWarning` per process naming both old + new env-var names. Affected constants: `ENV_*` in `juniper_cascor_worker/constants.py:151-165` now hold canonical names; new `LEGACY_ENV_*` constants hold the bare-`CASCOR_*` / `CASCOR_WORKER_*` legacy values. `WorkerConfig.from_env()` and `cli.py` route all reads through the helper; the dual-legacy `auth_token` chain (`CASCOR_AUTH_TOKEN` + `CASCOR_API_KEY` → `JUNIPER_CASCOR_WORKER_AUTH_TOKEN`) is preserved. **Version bumped 0.3.0 → 0.4.0** (additive runtime dep + behaviour-change-with-warning warrants a minor). New regression suite at `tests/test_cfg_06_env_prefix_aliases.py` (85 tests) pins the per-field × 4-env-state matrix (14 × 4 = 56 cases), the dual-legacy chain (4 cases), the `from_env(env: Mapping)` test-injection contract (5 cases, see below), source-level scope guards on `config.py` + `cli.py` (no raw `os.getenv("CASCOR_*")`), and the no-pydantic-at-runtime invariant (3 subprocess-isolated cases including juniper-config-tools itself). Mirrors the cascor CFG-03/05 pattern; follows the proven juniper-doc-tools / juniper-ci-tools migration shape with juniper-config-tools as the new shared package home (Wave 0 + Wave 1 + Wave 2 of the [juniper-config-tools PyPI migration plan](https://github.com/pcalnon/juniper-ml/blob/main/notes/JUNIPER_2026-05-22_JUNIPER-ML_CONFIG-TOOLS-PYPI-MIGRATION-PLAN.md)).
- **CFG-06 (test-injection contract, Open Q §10.4 resolution)**: `WorkerConfig.from_env(env: Mapping[str, str] | None = None)` now accepts an explicit env mapping. When `None` (the default and production path), reads from `os.environ` via `juniper_config_tools.env_with_legacy_alias`. When provided, reads from the mapping via a local `_resolve` adapter that mirrors the helper's semantics (same warning text, `stacklevel=2`, once-per-location). The duplication is deliberate; `_resolve` collapses to a single delegation when juniper-config-tools 0.2.0 adds the `env` kwarg. Tests can now inject `from_env(env={...})` instead of `monkeypatch.setenv(...)` for cleaner test surfaces.
- **CFG-06 docs sweep** (follow-up #3 from the design doc §7 rollout plan; juniper-deploy half shipped via juniper-deploy [#80](https://github.com/pcalnon/juniper-deploy/pull/80)). Operator-facing env-var documentation updated to canonical `JUNIPER_CASCOR_WORKER_*` names with a "Legacy env-var names" section preserving the legacy → canonical mapping for in-flight migrations:
  - `AGENTS.md` — WebSocket-mode + Legacy-mode env-var tables + CLI-flag-default tables now use canonical names; new `### Legacy env-var names` subsection with the 15-row legacy → canonical mapping (incl. the dual-legacy `CASCOR_AUTH_TOKEN` + `CASCOR_API_KEY` → `JUNIPER_CASCOR_WORKER_AUTH_TOKEN` row).
  - `README.md` — WebSocket-mode + Legacy-mode env-var tables now use canonical names; cross-link to `AGENTS.md#legacy-env-var-names` for the mapping.
  - `Dockerfile` — baked `ENV` defaults switched from `CASCOR_SERVER_URL` / `CASCOR_HEARTBEAT_INTERVAL` to the canonical `JUNIPER_CASCOR_WORKER_*` names so operators running the image bare (no compose) don't see DeprecationWarnings by default. Run-line example in the file header comment updated to match.

### Added

- **`util/test_agents_md_version_drift.py`** -- portable port of juniper-ml's lint test pinning `AGENTS.md`'s `**Version**:` header to `pyproject.toml`'s `[project].version`. Catches the failure class where a `pyproject.toml` bump leaves the agent-facing contract stale. Preventive-only here: cascor-worker's `AGENTS.md` and `pyproject.toml` are already in sync at `0.4.0`. Wired into the CI tests job next to the existing `test_workflow_script_paths.py` lint.

- **METRICS-MON R3.7 (soak complete)**: macOS leg of the unit-tests CI matrix flipped from `experimental: true` → `experimental: false`, making the `macos-latest` (Python 3.12) leg **required**. Failures on macOS now block the job. The `continue-on-error: ${{ matrix.experimental == true }}` job-level guard is preserved as a future-proof escape hatch for future experimental matrix entries; with `experimental: false` it evaluates to `false`. Soak window 2026-05-01 → 2026-05-15 confirmed clean (per user direction). Closes the post-soak follow-up of the R3.7 fan-out.

- **METRICS-MON R3.7 / seed-(R1.3 design)**: macOS leg added to the unit-tests CI matrix. `.github/workflows/ci.yml::unit-tests` now runs on `${{ matrix.os }}` with a single new `macos-latest` (Apple Silicon / ARM) entry pinned to Python 3.12; Linux legs (Python 3.12 + 3.13 + 3.14) are unchanged. The macOS leg starts in **`continue-on-error: true`** mode for a 2-week soak (2026-04-30 → 2026-05-14) so platform-divergence failures (cross-platform `rss_mb` sampling, POSIX-only assumptions) surface in CI without blocking PRs while environment-specific issues are identified. The torch wheel install branches by OS — Linux uses the CPU-only PyTorch index (`https://download.pytorch.org/whl/cpu`) which has no macOS-arm64 wheels; macOS uses the default PyPI index which does. After the soak, flip the include block's `experimental` flag to `false` to make the macOS leg required. Closes the cascor-worker leg of [METRICS_MONITORING_R3_ENTRY_PLAN_2026-04-30.md](https://github.com/pcalnon/juniper-ml/blob/main/notes/code-review/METRICS_MONITORING_R3_ENTRY_PLAN_2026-04-30.md) §3 Q1.

### Changed

- **METRICS-MON R2.2.6 / seed-05**: worker now consumes the shared `juniper-cascor-protocol>=0.1.0` package as a runtime dependency to single-source the `/ws/v1/workers` wire-protocol surface.
  - `juniper_cascor_worker/constants.py` — the `MSG_TYPE_*` `Final[str]` literals are now derived from `juniper_cascor_protocol.worker.WorkerMessageType` rather than declared inline. The string values are byte-identical to the previous declarations (`"register"`, `"heartbeat"`, `"task_assign"`, `"task_result"`, `"registration_ack"`, `"result_ack"`, `"token_refresh"`, `"error"`, `"connection_established"`); a future cascor-server rename of any wire string would propagate here automatically.
  - `juniper_cascor_worker/worker.py::_encode_binary_frame` — delegates to `juniper_cascor_protocol.worker.BinaryFrame.encode` so the on-the-wire bytes for outbound tensor frames are guaranteed to match the cascor server's encoder. Encoded output is byte-identical to the pre-migration implementation (verified by `test_encode_binary_frame_uses_shared_codec`).
  - `juniper_cascor_worker/worker.py::_decode_binary_frame` — **kept local intentionally**. The worker enforces stricter SEC-18 bounds (`BINARY_FRAME_MAX_TOTAL_ELEMENTS = 100_000_000`, `BINARY_FRAME_MAX_DTYPE_LEN = 32`) than the shared lib's defaults, and replacing with `juniper_cascor_protocol.worker.BinaryFrame.decode` would relax the dtype-length cap from 32 to 64 bytes. Round-tripping with the shared encoder still works (verified by `test_local_decoder_still_round_trips_with_shared_encoder`).
  - The dispatch loop in `CascorWorkerAgent._run` now emits a **structured** WARNING log line `juniper_cascor_worker_unrecognized_ws_frame` (with `type` and `worker_id` extra keys) when an inbound JSON frame's `type` is not one of the recognized `MSG_TYPE_*` values. Replaces the previous unstructured `logger.warning("Unknown message type: %s", msg_type)` so log shippers (Loki, etc.) can count unrecognized frames per worker pod without the worker depending on `prometheus-client` (per the R2 exit-gate decision, the worker does not gain a `/metrics` endpoint).
  - **No Pydantic at runtime**: importing any worker module — `juniper_cascor_worker`, `juniper_cascor_worker.constants`, `juniper_cascor_worker.worker`, `juniper_cascor_worker.cli`, `juniper_cascor_worker.config`, `juniper_cascor_worker.http_health`, `juniper_cascor_worker.task_executor`, `juniper_cascor_worker.ws_connection` — does not place `pydantic` in `sys.modules`. The Pydantic wheel ships on disk as a transitive dep of `juniper-cascor-protocol`, but the worker only imports `juniper_cascor_protocol.worker.*` (numpy-only) and never crosses the envelope subpackage. Pinned by the new test suite at `tests/test_no_pydantic_at_runtime.py` (6 tests across the public worker import surface).
  - See [`notes/code-review/METRICS_MONITORING_R2.2_WS_FRAME_SCHEMA_DESIGN_2026-04-29.md`](https://github.com/pcalnon/juniper-ml/blob/main/notes/code-review/METRICS_MONITORING_R2.2_WS_FRAME_SCHEMA_DESIGN_2026-04-29.md) §Q3 in juniper-ml for the rationale.

### Added

- **METRICS-MON R1.3 / seed-04**: HTTP health-probe surface for the worker.
  - New `juniper_cascor_worker/http_health.py` module — `HealthServer` class hand-rolled on `asyncio.start_server` (no new dependencies; FastAPI/uvicorn deliberately not added to the slim worker image). Hosts three GET endpoints on a configurable port (default `8210`, localhost-only):
    - `GET /v1/health` — backwards-compatible no-op (`{"status": "ok", "worker_id": ..., "version": ...}`, 200).
    - `GET /v1/health/live` — runs an in-process tick (WS connection bound + heartbeat counter fresh) within a 250 ms budget; 503 + `{"status": "unresponsive", ...}` on tick failure or budget exceedance.
    - `GET /v1/health/ready` — required deps are WS connected AND registration handshake complete; 503 + `status="not_ready"` + `X-Juniper-Readiness` header otherwise.
  - Hand-rolled HTTP/1.1 handler accepts `GET` only, caps total request bytes at 4096, applies a 2 s read timeout, rejects malformed request lines and oversize headers, and survives bad requests without crashing the listener.
  - **Enriched heartbeat payload** (`MSG_TYPE_HEARTBEAT`): now sends `in_flight_tasks`, `last_task_completed_at`, `rss_mb`, `tasks_completed`, `tasks_failed` alongside the existing `worker_id` + `timestamp`. Cascor's `WorkerRegistration` accepts these (see companion juniper-cascor PR) and surfaces them on `/v1/workers`.
  - **Task accounting** wired around `_handle_task_assign`: `try/finally` increments `in_flight_tasks` at start, decrements at end, sets `last_task_completed_at = time.time()`, and increments `tasks_completed` on training success or `tasks_failed` on protocol rejection / timeout / exception. Liveness counter bumps on each task completion AND each heartbeat send so progress in the message-loop thread is an additional liveness signal.
  - **Config**: new `health_port` and `health_bind` fields on `WorkerConfig` (defaults `8210` / `127.0.0.1`); env vars `CASCOR_WORKER_HEALTH_PORT` and `CASCOR_WORKER_HEALTH_BIND`. Validation ensures port is in `[1, 65535]` and bind host is non-empty.
  - **Cross-platform `rss_mb` sampling**: Linux uses `ru_maxrss / 1024` (kilobytes → MB); macOS uses `ru_maxrss / 1024**2` (bytes → MB). Falls back to `0.0` on platforms without `resource` (e.g. Windows). No `psutil` dependency.
  - See [`notes/code-review/METRICS_MONITORING_R1.3_WORKER_HEARTBEAT_DESIGN_2026-04-27.md`](https://github.com/pcalnon/juniper-ml/blob/main/notes/code-review/METRICS_MONITORING_R1.3_WORKER_HEARTBEAT_DESIGN_2026-04-27.md) in juniper-ml for the cross-repo contract. Companion PRs: cascor (merged) and juniper-deploy (forthcoming, two-step rollout — chart adds the wiring with `worker.healthcheck.enabled=false` first, flag flip after staging burn-in).
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
