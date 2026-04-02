# AGENTS.md Remediation Plan — juniper-cascor-worker

**Date**: 2026-04-02
**Input**: `notes/AGENTS_MD_DRIFT_ANALYSIS_2026-04-02.md`
**Objective**: Bring AGENTS.md into full alignment with the codebase at version 0.3.0

---

## Phase 1: Critical Corrections (Blocking)

These items contain incorrect information that will cause agent failures if not corrected.

### Step 1.1: Fix Header Metadata

- **Task**: Update version from `0.1.0` to `0.3.0`
- **Task**: Update last-updated date to `2026-04-02`
- **Files**: `AGENTS.md` lines 4-5

### Step 1.2: Fix CLI Run Command

- **Task**: Replace `juniper-cascor-worker --host <manager-host> --port <manager-port>` with WebSocket-mode command as default
- **Task**: Add `--legacy` mode command as secondary
- **Files**: `AGENTS.md` line 34

### Step 1.3: Fix Environment Variable Defaults

- **Task**: Remove incorrect `juniper` default for `CASCOR_AUTHKEY`
- **Task**: Add all WebSocket environment variables
- **Task**: Label legacy-only variables explicitly
- **Files**: `AGENTS.md` lines 38-45

### Step 1.4: Fix Linting Command

- **Task**: Change `--max-line-length=120` to `--max-line-length=512`
- **Files**: `AGENTS.md` line 29

## Phase 2: Missing Core Architecture (High Priority)

These sections describe the application's primary operating mode and must be added.

### Step 2.1: Add Application Architecture Section

- **Task**: Document two-mode architecture (WebSocket default, legacy deprecated)
- **Task**: Include communication flow diagram
- **Task**: Include worker lifecycle state diagram
- **Task**: Document module dependency graph
- **Placement**: After "Project Overview" section

### Step 2.2: Add WebSocket Mode Documentation

- **Task**: Document CascorWorkerAgent class and its async event loop
- **Task**: Document WorkerConnection class and reconnection logic
- **Task**: Document binary tensor protocol (JSON + struct-encoded frames)
- **Task**: Document TLS/mTLS configuration
- **Placement**: Within Architecture section

### Step 2.3: Add Task Execution Pipeline

- **Task**: Document execute_training_task() function
- **Task**: Document CandidateUnit dynamic import from cascor codebase
- **Task**: Document `--cascor-path` CLI flag
- **Placement**: Within Architecture section

### Step 2.4: Add Public API Section

- **Task**: Document all exports from `__init__.py`
- **Task**: Document CascorWorkerAgent interface (init, run, stop)
- **Task**: Document CandidateTrainingWorker interface (init, connect, start, stop, disconnect, context manager)
- **Task**: Document WorkerConfig dataclass (fields, from_env, validate, address)
- **Task**: Document exception hierarchy (WorkerError, WorkerConnectionError, WorkerConfigError)
- **Placement**: After Architecture section

### Step 2.5: Add Complete CLI Reference

- **Task**: Document all CLI flags with modes (WebSocket vs Legacy vs Shared)
- **Task**: Document signal handling (dual SIGINT/SIGTERM, force-exit)
- **Task**: Document `--cascor-path` for dynamic imports
- **Placement**: Within or after Public API section

## Phase 3: Missing Supplementary Content (Medium Priority)

### Step 3.1: Expand Key Files Table

- **Task**: Add all Python module files with purposes
- **Task**: Add documentation files (docs/)
- **Task**: Add script files (scripts/)
- **Task**: Add CI/CD workflow files (.github/workflows/)
- **Task**: Add configuration files (.pre-commit-config.yaml, .sops.yaml, .markdownlint.yaml)
- **Files**: `AGENTS.md` Key Files section

### Step 3.2: Add Directory Layout Section

- **Task**: Include full directory tree with descriptions
- **Placement**: After Key Files, before Architecture

### Step 3.3: Update Dependencies Table

- **Task**: Add `websockets>=11.0` to runtime dependencies
- **Task**: Add dev/test dependency group
- **Task**: Document dynamic imports from cascor codebase
- **Files**: `AGENTS.md` Dependencies section

### Step 3.4: Add CI/CD Section

- **Task**: Document 6-job CI pipeline (pre-commit, tests, security, build, docs, quality-gate)
- **Task**: Document weekly security scan workflow
- **Task**: Document PyPI publish workflow
- **Task**: Document Dependabot configuration
- **Placement**: After Test Details section

### Step 3.5: Add Pre-commit Hooks Section

- **Task**: Document all configured hooks (black, isort, flake8, mypy, bandit, shellcheck, yamllint, markdownlint, SOPS)
- **Task**: Document line-length=512 convention
- **Placement**: After CI/CD or within Conventions section

### Step 3.6: Add Test Details Section

- **Task**: Document 6 test files with line counts and purposes
- **Task**: Document test markers (unit, integration)
- **Task**: Document pytest fixtures (valid_config)
- **Task**: Document coverage threshold (80%)
- **Task**: Document filter warnings configuration
- **Placement**: After Dependencies section

### Step 3.7: Add Python Requirements

- **Task**: Document `>=3.11` requirement
- **Task**: Document supported versions: 3.11, 3.12, 3.13, 3.14
- **Task**: Document PEP 561 py.typed marker
- **Placement**: In header or Conventions section

### Step 3.8: Add Documentation Section

- **Task**: Document docs/ directory and its 4 files
- **Task**: Include resource location recommendations for agents
- **Placement**: After Scripts section or within Resource Locations

### Step 3.9: Add Scripts Section

- **Task**: Document check_doc_links.py (purpose, usage, exit codes)
- **Task**: Document generate_dep_docs.sh
- **Placement**: After CI/CD section

## Phase 4: Cleanup (Low Priority)

### Step 4.1: Remove Stale References

- **Task**: Remove references to `conf/requirements_ci.txt` (file doesn't exist)
- **Task**: Remove references to `conf/conda_environment_ci.yaml` (file doesn't exist)
- **Task**: Update ecosystem compatibility version from `0.1.x` to `0.3.x`

### Step 4.2: Add Resource Location Recommendations

- **Task**: Create a section guiding agents to appropriate documentation based on task type
- **Task**: Reference docs/REFERENCE.md for API details
- **Task**: Reference docs/QUICK_START.md for setup
- **Task**: Reference docs/DEVELOPER_CHEATSHEET.md for common tasks
- **Task**: Reference notes/ for procedures and planning

## Phase 5: Validation

### Step 5.1: Internal Link Validation

- **Task**: Run `scripts/check_doc_links.py` against updated AGENTS.md
- **Task**: Verify all file paths referenced in AGENTS.md exist

### Step 5.2: Cross-Reference Validation

- **Task**: Verify all CLI flags match `cli.py` argument parser
- **Task**: Verify all environment variables match `config.py` and `cli.py`
- **Task**: Verify all class/method names match `__init__.py` exports
- **Task**: Verify directory layout matches actual filesystem
- **Task**: Verify dependencies match `pyproject.toml`

### Step 5.3: Test Suite Validation

- **Task**: Run full pytest suite to confirm no regressions
- **Task**: Run pre-commit hooks to validate formatting

---

## Estimated Scope

| Phase | Items | Priority | Risk |
|-------|-------|----------|------|
| Phase 1: Critical Corrections | 5 tasks | Blocking | Agents using wrong commands |
| Phase 2: Core Architecture | 12 tasks | High | Agents unaware of primary mode |
| Phase 3: Supplementary Content | 18 tasks | Medium | Incomplete agent guidance |
| Phase 4: Cleanup | 5 tasks | Low | Minor confusion |
| Phase 5: Validation | 7 tasks | Required | Quality assurance |
| **Total** | **47 tasks** | | |
