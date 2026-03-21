# Pre-commit Remediation Plan: Bandit B105 and Test Warning Cleanup

**Date**: 2026-03-21
**Branch**: `fix/pre-commit-bandit-b105`
**Author**: Claude Opus 4.6

---

## Executive Summary

The juniper-cascor-worker pre-commit checks fail due to Bandit B105
(`hardcoded_password_string`) findings in test files. Additionally, the test
suite produces 26 warnings (23 DeprecationWarnings, 3 RuntimeWarnings) that
must be eliminated per project standards.

---

## Root Cause Analysis

### Issue 1: Bandit B105 Pre-commit Failure

**Root cause**: The `auth_token` field (containing "token" in Bandit's regex
`RE_WORDS = "(pas+wo?r?d|pass(phrase)?|pwd|token|secrete?)"`) was introduced
in the WebSocket Phase 2 refactoring (commit `9fa4cef`) AFTER the pre-commit
configuration was finalized. The original field name `api_key` did not trigger
B105 because "key" is not in Bandit's credential word list.

**Scope**: 11 B105 findings across 3 test files:

| File | Count | Trigger Patterns |
|------|-------|-----------------|
| `tests/test_cli.py` | 4 | `mock_args.auth_token = "..."`, `config_arg.auth_token == "..."` |
| `tests/test_config.py` | 6 | `"CASCOR_AUTH_TOKEN": "..."`, `config.auth_token == "..."` |
| `tests/test_worker_agent.py` | 1 | `"auth_token": "test-key"` dict literal |

**Assessment**: All 11 findings are false positives — test fixtures using dummy
credential values, not real secrets.

### Issue 2: DeprecationWarnings (23)

**Root cause**: `CandidateTrainingWorker.__init__()` emits a `DeprecationWarning`
via `warnings.warn()` at `worker.py:326`. Every test in `test_worker.py` that
instantiates this deprecated class triggers the warning. These warnings are
expected and intentional — `test_worker.py` exists specifically to exercise the
deprecated legacy API.

### Issue 3: RuntimeWarnings (3)

**Root cause**: Unawaited `CascorWorkerAgent.run()` coroutines created during
mock-based test cleanup. When `CascorWorkerAgent` instances are garbage-collected
during tests, Python detects the unawaited coroutine and emits a
`RuntimeWarning`.

---

## Solutions Evaluated

### For Bandit B105

| Solution | Description | Verdict |
|----------|-------------|---------|
| **A: Add B105 to test skip list** | Add B105 to `--skip` in `.pre-commit-config.yaml` test Bandit hook | **RECOMMENDED** |
| B: Inline `# nosec B105` | Add suppression comments to 11 lines | Not recommended — contradicts ecosystem convention |
| C: Centralize in conftest.py | Move credentials to fixtures | Not recommended — over-engineering |
| D: Environment variables | Read test creds from env | Not recommended — doesn't solve B105 |

**Rationale for Solution A**: Matches the exact pattern used across all Juniper
repos for test-specific Bandit rule relaxation. The split source/test Bandit hook
architecture was designed for this purpose. Source code B105 scanning is
preserved. One-line change, zero maintenance burden.

### For DeprecationWarnings

| Solution | Description | Verdict |
|----------|-------------|---------|
| **A: Module-level filterwarnings** | Add `pytestmark` filterwarnings to `test_worker.py` | **RECOMMENDED** |
| B: pyproject.toml filterwarnings | Global filter in pytest config | Not recommended — too broad |

**Rationale**: A targeted module-level filter in `test_worker.py` suppresses only
the expected deprecation warnings from the legacy API tests, while preserving
DeprecationWarning detection in all other test modules.

### For RuntimeWarnings

| Solution | Description | Verdict |
|----------|-------------|---------|
| **A: Targeted filterwarnings** | Filter the specific coroutine warning in pyproject.toml | **RECOMMENDED** |
| B: Fix mock cleanup | Ensure coroutines are properly awaited/closed | Not recommended — complex for minimal gain |

**Rationale**: The RuntimeWarning about unawaited coroutines is an artifact of
mock-based testing where `CascorWorkerAgent` instances are created but never
actually run. A targeted filter for this specific warning pattern is the
appropriate approach.

---

## Implementation Plan

### Phase 1: Pre-commit Configuration Fix

**Files modified**: `.pre-commit-config.yaml`

1. Add `B105` to the `--skip` argument on line 195, maintaining numerical order:
   `--skip=B101,B104,B105,B108,B110,B311`
2. Add comment: `# B105: hardcoded_password_string (test fixtures use dummy credentials)`

**Validation**: `pre-commit run --all-files` passes all hooks.

### Phase 2: Test Warning Remediation

**Files modified**: `tests/test_worker.py`, `pyproject.toml`

1. Add module-level `pytestmark` to `tests/test_worker.py`:
   ```python
   pytestmark = pytest.mark.filterwarnings(
       "ignore:CandidateTrainingWorker is deprecated:DeprecationWarning"
   )
   ```
2. Add filterwarnings to `pyproject.toml` `[tool.pytest.ini_options]` for the
   RuntimeWarning:
   ```toml
   filterwarnings = [
       "error",
       "ignore:CandidateTrainingWorker is deprecated:DeprecationWarning:tests.test_worker",
       "ignore:coroutine .* was never awaited:RuntimeWarning",
   ]
   ```

**Validation**: `pytest tests/ -W error` passes (no warnings promoted to errors
except for the filtered ones). `pytest tests/ -v` shows 0 warnings.

### Phase 3: Regression Prevention

**Files modified**: `pyproject.toml`

1. The `filterwarnings = ["error", ...]` configuration in pyproject.toml ensures
   that any NEW unexpected warnings will cause test failures, preventing silent
   warning accumulation going forward.
2. The `"error"` base filter treats all warnings as errors by default, with
   explicit exceptions only for known, intentional warnings.

**Validation**: Adding a new `warnings.warn()` call in source code and
verifying it causes a test failure (manual verification during implementation).

### Phase 4: Final Validation

1. Run `pre-commit run --all-files` — all hooks pass
2. Run `pytest tests/ -v` — 101 tests pass, 0 warnings
3. Run `pytest tests/ --cov=juniper_cascor_worker --cov-report=term-missing --cov-fail-under=80` — coverage >= 80%
4. Run `pre-commit run --all-files` on all files (final confirmation)

---

## Risk Assessment

| Change | Risk Level | Mitigation |
|--------|-----------|------------|
| B105 skip in test Bandit | Low | Source Bandit hook unaffected; `detect-private-key` hook catches real secrets |
| DeprecationWarning filter in test_worker.py | Low | Scoped to single module; other modules still surface deprecation warnings |
| `filterwarnings = ["error"]` in pyproject.toml | Medium | May surface previously-hidden warnings; validated by running full suite |
| RuntimeWarning filter | Low | Targeted to specific coroutine pattern only |

---

## Files Changed Summary

| File | Change Type | Description |
|------|------------|-------------|
| `.pre-commit-config.yaml` | Modified | Add B105 to test Bandit skip list |
| `tests/test_worker.py` | Modified | Add module-level DeprecationWarning filter |
| `pyproject.toml` | Modified | Add filterwarnings config with `error` base + exceptions |

---

## Verification Commands

```bash
# Phase 1 verification
pre-commit run --all-files

# Phase 2 verification
pytest tests/ -v  # 0 warnings expected

# Phase 3 verification
pytest tests/ -v  # "error" base filter catches new warnings

# Phase 4 final validation
pre-commit run --all-files
pytest tests/ --cov=juniper_cascor_worker --cov-report=term-missing --cov-fail-under=80
```
