#!/usr/bin/env bash
#####################################################################################################
# Project:       Juniper
# Sub-Project:   JuniperCascorWorker
# Application:   juniper_cascor_worker
# File Name:     util/run_coverage.bash
# Author:        Paul Calnon
# Version:       0.2.0
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Reproduce the CI coverage gates locally (full suite). Mirrors the coverage
#    invocation enforced in .github/workflows/ci.yml so a developer can verify
#    both the aggregate >=80% gate AND the per-file coverage rollout C-5 gate
#    (statement >=90 per file / pooled >=95 per sub-module) before pushing. Runs
#    the FULL suite by design (narrowing the selection would lower coverage);
#    use plain pytest for a subset.
#
# Usage:
#    bash util/run_coverage.bash                          # full suite + gate
#    make coverage                                        # equivalent wrapper
#    COVERAGE_FAIL_UNDER=90 bash util/run_coverage.bash   # override the gate
#
# References:
#    - https://pytest-cov.readthedocs.io/
#####################################################################################################
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

COVERAGE_FAIL_UNDER="${COVERAGE_FAIL_UNDER:-80}"

echo "==> Coverage (reproduces CI gate: ${COVERAGE_FAIL_UNDER}% aggregate) — ${REPO_ROOT}"

# ── Reproduce the CI coverage sequence (keep in sync with .github/workflows/ci.yml) ──
mkdir -p reports
python -m pytest tests/ --cov=juniper_cascor_worker --cov-report=term-missing --cov-report=json:reports/coverage.json
python -m coverage report --fail-under="${COVERAGE_FAIL_UNDER}"

# Per-file coverage rollout C-5 (juniper-ml
# notes/JUNIPER_ECOSYSTEM_PER_FILE_COVERAGE_ROLLOUT_SCOPING_2026-06-30.md):
# statement >=90 per file / pooled >=95 per sub-module. Additive to the aggregate
# gate above. Requires juniper-ci-tools>=0.6.0,<0.7.0; skipped with a hint if the
# console script is absent so `make coverage` still works without it installed.
if command -v juniper-coverage-gap-map >/dev/null 2>&1; then
    juniper-coverage-gap-map --coverage-json reports/coverage.json --enforce
else
    echo "==> NOTE: juniper-coverage-gap-map not found — skipping the per-file gate."
    echo "         Install it with: pip install \"juniper-ci-tools>=0.6.0,<0.7.0\""
fi
# ─────────────────────────────────────────────────────────────────────────────────────
