# AGENTS.md Development Roadmap — juniper-cascor-worker

**Date**: 2026-04-02
**Input**: `notes/AGENTS_MD_REMEDIATION_PLAN_2026-04-02.md`
**Scope**: Single-session implementation of all AGENTS.md corrections and additions

---

## Roadmap Overview

All work is contained in a single deliverable: a rewritten `AGENTS.md` file that accurately reflects the `juniper-cascor-worker` codebase at version 0.3.0. The roadmap is structured as a priority-ordered sequence of content blocks to be written, validated, and committed.

---

## Priority 1 — Critical Fixes (Must Ship)

| # | Task | Source of Truth | Acceptance Criteria |
|---|------|----------------|---------------------|
| 1.1 | Update header metadata (version 0.3.0, date 2026-04-02) | `pyproject.toml` line 7 | Version and date match pyproject.toml |
| 1.2 | Fix CLI run command to show WebSocket mode as default | `cli.py` lines 18-51 | Command uses `--server-url`, `--auth-token` |
| 1.3 | Fix environment variables table (add WebSocket, mark legacy) | `cli.py` lines 73-74, `config.py` | All env vars from code are documented |
| 1.4 | Fix flake8 line-length from 120 to 512 | `pyproject.toml` line 66 | Matches pyproject.toml |
| 1.5 | Fix AUTHKEY default (remove `juniper`) | `config.py` | Default shown as empty/required |
| 1.6 | Add `websockets>=11.0` to dependencies | `pyproject.toml` line 32 | All runtime deps listed |

## Priority 2 — Architecture & API (High Value)

| # | Task | Source of Truth | Acceptance Criteria |
|---|------|----------------|---------------------|
| 2.1 | Write Application Architecture section with two-mode overview | `worker.py`, `cli.py` | WebSocket (default) and legacy (deprecated) described |
| 2.2 | Write communication flow diagram | `ws_connection.py`, `worker.py` | Shows WebSocket protocol, JSON+binary framing |
| 2.3 | Write worker lifecycle state diagram | `worker.py` | States: init → configured → connecting → registered → processing → stopped |
| 2.4 | Write module dependency graph | All source files | Accurate import chain from cli.py through all modules |
| 2.5 | Write Public API section | `__init__.py` | All 7 exports documented with interfaces |
| 2.6 | Write Configuration Details section | `config.py` | All WorkerConfig fields, from_env(), validate() |
| 2.7 | Write complete CLI reference | `cli.py` lines 18-51 | All flags with mode labels and defaults |
| 2.8 | Document signal handling | `cli.py` lines 91-96, 130-134 | Dual SIGINT/SIGTERM documented |
| 2.9 | Document dynamic imports from cascor codebase | `task_executor.py`, `worker.py` | CandidateUnit, CascadeCorrelationNetwork imports documented |

## Priority 3 — Supplementary Content (Completeness)

| # | Task | Source of Truth | Acceptance Criteria |
|---|------|----------------|---------------------|
| 3.1 | Write full directory layout tree | Filesystem | All dirs and key files with descriptions |
| 3.2 | Expand Key Files table to all modules | Filesystem | Every source file, doc, script, config listed |
| 3.3 | Write Test Details section | `tests/` directory, `pyproject.toml` | 6 test files, markers, fixtures, coverage threshold |
| 3.4 | Write CI/CD section | `.github/workflows/` | 3 workflows, 6 CI jobs documented |
| 3.5 | Write Pre-commit Hooks section | `.pre-commit-config.yaml` | All hooks listed with purposes |
| 3.6 | Write Documentation section | `docs/` directory | 4 doc files with purposes and when to reference |
| 3.7 | Write Scripts section | `scripts/` directory | 2 scripts with usage |
| 3.8 | Add Python version requirements | `pyproject.toml` lines 13, 20-23 | >=3.11, supported 3.11-3.14 |
| 3.9 | Write Resource Location guide | All directories | Where to find what, by task type |

## Priority 4 — Cleanup (Polish)

| # | Task | Source of Truth | Acceptance Criteria |
|---|------|----------------|---------------------|
| 4.1 | Remove stale conf/ file references | Filesystem (conf/ is empty) | No references to non-existent files |
| 4.2 | Update ecosystem compatibility version | `pyproject.toml` | Worker version shown as 0.3.x |

## Priority 5 — Validation (Quality Gate)

| # | Task | Method | Pass Criteria |
|---|------|--------|---------------|
| 5.1 | Run `scripts/check_doc_links.py` | `python scripts/check_doc_links.py` | Exit code 0 |
| 5.2 | Verify all file paths exist | Manual/scripted check | No broken path references |
| 5.3 | Run pre-commit hooks | `pre-commit run --all-files` | All hooks pass |
| 5.4 | Run test suite | `pytest tests/ -v` | All tests pass |
| 5.5 | Cross-reference CLI flags vs cli.py | Manual review | 1:1 match |
| 5.6 | Cross-reference env vars vs config.py + cli.py | Manual review | 1:1 match |

---

## Dependency Order

```
Priority 1 (Critical Fixes)
    └── Priority 2 (Architecture & API)
            └── Priority 3 (Supplementary Content)
                    └── Priority 4 (Cleanup)
                            └── Priority 5 (Validation)
```

All priorities are sequential — each builds on the previous. The entire AGENTS.md will be rewritten as a single coherent document rather than patched incrementally.

---

## Deliverables

| Deliverable | Path | Status |
|-------------|------|--------|
| Drift Analysis | `notes/AGENTS_MD_DRIFT_ANALYSIS_2026-04-02.md` | Complete |
| Remediation Plan | `notes/AGENTS_MD_REMEDIATION_PLAN_2026-04-02.md` | Complete |
| Development Roadmap | `notes/AGENTS_MD_DEVELOPMENT_ROADMAP_2026-04-02.md` | Complete |
| Updated AGENTS.md | `AGENTS.md` | Pending |
| Validation Results | Test suite + doc link check output | Pending |
