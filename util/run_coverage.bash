#!/usr/bin/env bash
#####################################################################################################
# Project:       Juniper
# Sub-Project:   JuniperCascorWorker
# Application:   juniper_cascor_worker
# File Name:     util/run_coverage.bash
# Author:        Paul Calnon
# Version:       0.1.0
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Reproduce the CI coverage gate locally (full suite). Mirrors the coverage
#    invocation enforced in .github/workflows/ci.yml so a developer can verify
#    the aggregate gate before pushing. Runs the FULL suite by design (narrowing
#    the selection would lower coverage); use plain pytest for a subset.
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
python -m pytest tests/ --cov=juniper_cascor_worker --cov-report=term-missing
python -m coverage report --fail-under="${COVERAGE_FAIL_UNDER}"
# ─────────────────────────────────────────────────────────────────────────────────────
