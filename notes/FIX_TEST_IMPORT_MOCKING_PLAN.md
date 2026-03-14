# Fix Plan: Test Import Mocking for CasCor Dependencies

**Date**: 2026-03-13
**Branch**: `fix/test-cascor-import-mocking`
**Status**: Implementation

---

## Problem Statement

Two tests in `tests/test_worker.py` fail when run in the JuniperCascor conda environment:

| Test | Error |
|------|-------|
| `TestWorkerConnect::test_connect_without_cascor_raises` | `AssertionError: Regex pattern did not match` — expected "CasCor codebase not found", got `WorkerConnectionError` |
| `TestWorkerConnect::test_start_without_cascor_raises` | `Failed: DID NOT RAISE` — expected `WorkerError`, nothing raised |

**44 of 46 tests pass.** Coverage is 97.84% but lines 50-51 and 82-83 (the ImportError handlers) are uncovered.

## Root Cause

Both tests assume `cascade_correlation` is **not importable** in the test environment. This assumption is violated when tests run in the `JuniperCascor` conda environment where the `cascade_correlation` package **is installed**.

### Test 1: `test_connect_without_cascor_raises` (line 65)

1. `worker.connect()` calls `from cascade_correlation.cascade_correlation import CandidateTrainingManager`
2. Import **succeeds** (package is installed) — the `except ImportError` handler is skipped
3. Code proceeds to `self.manager.connect()` which attempts a real TCP connection to `127.0.0.1:50000`
4. No manager is running → `ConnectionRefusedError`
5. Caught by `except Exception` on line 66 → wrapped as `WorkerConnectionError`
6. `pytest.raises(WorkerError, match="CasCor codebase not found")` catches it (WorkerConnectionError IS a WorkerError subclass) but the regex doesn't match the actual message

### Test 2: `test_start_without_cascor_raises` (line 192)

1. Test sets `worker._connected = True`, bypassing the "Not connected" guard
2. `worker.start()` calls `from cascade_correlation.cascade_correlation import CascadeCorrelationNetwork`
3. Import **succeeds** — the `except ImportError` handler is skipped
4. Code enters the process-spawning loop, creates real forkserver processes
5. `start()` returns normally without raising
6. `pytest.raises(WorkerError)` fails: `DID NOT RAISE`

## Fix

Add `patch.dict(sys.modules, {"cascade_correlation": None, "cascade_correlation.cascade_correlation": None})` to both tests, forcing `ImportError` on the import statement regardless of environment.

This matches the existing pattern used by **6 other tests** in the same file (lines 87, 115, 134, 161, 186, 307) which use `patch.dict(sys.modules, ...)` to control the `cascade_correlation` import.

Setting a `sys.modules` key to `None` causes Python's import machinery to raise `ImportError: import of <module> halted; None in sys.modules`. Verified on Python 3.14.3.

### Changes

**File: `tests/test_worker.py`**

1. **`test_connect_without_cascor_raises`** (line 65-69): Wrap the `worker.connect()` call in `patch.dict(sys.modules, {"cascade_correlation": None, "cascade_correlation.cascade_correlation": None})`

2. **`test_start_without_cascor_raises`** (line 192-198): Wrap the `worker.start()` call in `patch.dict(sys.modules, {"cascade_correlation": None, "cascade_correlation.cascade_correlation": None})`

### No Other Issues Found

- All other 44 tests are environment-independent (properly mocked or no CasCor dependency)
- Source code (`worker.py`, `config.py`, `cli.py`, `exceptions.py`) is correct
- No new tests needed — the existing tests cover the intended behavior, they just need proper mocking

## Validation

```bash
conda activate JuniperCascor
cd <worktree>
pip install -e ".[test]"
pytest tests/ -v --cov=juniper_cascor_worker --cov-report=term-missing --cov-branch --cov-fail-under=80
```

Expected: 46 passed, 0 failed. Lines 50-51 and 82-83 now covered.
