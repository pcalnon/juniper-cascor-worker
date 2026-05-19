#!/usr/bin/env bash
#####################################################################################################################################################################################################
# Project:       Juniper
# File Name:     generate_dep_docs.sh
# Author:        Paul Calnon
#
# License:       MIT License
# Copyright:     Copyright (c) 2024-2026 Paul Calnon
#
# Description:
#    Generates dependency documentation files for CI/CD.
#    - requirements_ci.txt (pip freeze with header)
#    - conda_environment_ci.yaml (conda env export --no-builds with header)
#    - Preserves existing files with timestamped backups
#
# Usage:
#    bash scripts/generate_dep_docs.sh
#
#####################################################################################################################################################################################################

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
CONF_DIR="conf"
NOTES_DIR="notes"

TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
DATE=$(date +"%Y-%m-%d")
YEAR=$(date +"%Y")
CONDA_DATE=$(date +"%Y.%m.%d")
PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
PIP_VERSION=$(pip --version 2>&1 | awk '{print $2}')

# Extract version from pyproject.toml
REPO_VERSION=$(python -c "
try:
    import tomllib
except ImportError:
    import tomli as tomllib
with open('pyproject.toml', 'rb') as f:
    data = tomllib.load(f)
print(data['project']['version'])
")

echo "╔════════════════════════════════════════════════════════════╗"
echo "║       Juniper - Generate Dependency Documentation          ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "  Repo Version:   ${REPO_VERSION}"
echo "  Python Version: ${PYTHON_VERSION}"
echo "  Pip Version:    ${PIP_VERSION}"
echo "  Timestamp:      ${TIMESTAMP}"
echo ""

mkdir -p "${CONF_DIR}"

# ── Pip Requirements ──────────────────────────────────────────────────────────
PIP_FILE="${CONF_DIR}/requirements_ci.txt"
PIP_HEADER="${NOTES_DIR}/PIP_DEPENDENCY_FILE_HEADER.md"

# Preserve existing file with timestamp infix
if [ -f "${PIP_FILE}" ]; then
    BACKUP_PIP="${CONF_DIR}/requirements_ci_${TIMESTAMP}.txt"
    echo "  Backing up existing pip requirements to: ${BACKUP_PIP}"
    cp "${PIP_FILE}" "${BACKUP_PIP}"
fi

# Generate pip requirements with header
if [ -f "${PIP_HEADER}" ]; then
    sed \
        -e "s|<X.Y.Z  Major, Minor, Point Version for Repo>|${REPO_VERSION}|g" \
        -e "s|<YYYY-MM-dd for Current date>|${DATE}|g" \
        -e "s|<YYYY-MM-dd for current date>|${DATE}|g" \
        -e "s|<YYYY for Current Year>|${YEAR}|g" \
        -e "s|<YYYY for current year>|${YEAR}|g" \
        -e "s|<Python Version>|${PYTHON_VERSION}|g" \
        -e "s|<Pip Version>|${PIP_VERSION}|g" \
        "${PIP_HEADER}" > "${PIP_FILE}"
else
    echo "# requirements_ci.txt - Generated ${DATE}" > "${PIP_FILE}"
    echo "# Python: ${PYTHON_VERSION}" >> "${PIP_FILE}"
    echo "" >> "${PIP_FILE}"
fi

# Append pip freeze output
pip list --format=freeze >> "${PIP_FILE}"

echo "  Generated: ${PIP_FILE}"

# ── Conda Environment ────────────────────────────────────────────────────────
CONDA_FILE="${CONF_DIR}/conda_environment_ci.yaml"
CONDA_HEADER="${NOTES_DIR}/CONDA_DEPENDENCY_FILE_HEADER.md"

# Preserve existing file with timestamp infix
if [ -f "${CONDA_FILE}" ]; then
    BACKUP_CONDA="${CONF_DIR}/conda_environment_ci_${TIMESTAMP}.yaml"
    echo "  Backing up existing conda environment to: ${BACKUP_CONDA}"
    cp "${CONDA_FILE}" "${BACKUP_CONDA}"
fi

# Generate conda environment with header
if command -v conda &> /dev/null; then
    if [ -f "${CONDA_HEADER}" ]; then
        sed \
            -e "s|<X.Y.Z  Major, Minor, Point Version for .*>|${REPO_VERSION}|g" \
            -e "s|<YYYY-MM-dd for current date>|${DATE}|g" \
            -e "s|<YYYY-MM-dd for Current date>|${DATE}|g" \
            -e "s|<YYYY for current year>|${YEAR}|g" \
            -e "s|<YYYY for Current Year>|${YEAR}|g" \
            -e "s|<YYYY.MM.dd for current date>|${CONDA_DATE}|g" \
            -e "s|<Python Version>|${PYTHON_VERSION}|g" \
            "${CONDA_HEADER}" > "${CONDA_FILE}"
    else
        echo "# conda_environment_ci.yaml - Generated ${DATE}" > "${CONDA_FILE}"
        echo "# Python: ${PYTHON_VERSION}" >> "${CONDA_FILE}"
        echo "" >> "${CONDA_FILE}"
    fi

    # Append conda dependencies with proper YAML indentation (two-space prefix).
    # conda env export --no-builds produces valid YAML; extract only the
    # dependency lines (between "dependencies:" and the next top-level key)
    # to merge with our custom header which already contains "dependencies:".
    conda env export --no-builds \
        | sed -n '/^dependencies:$/,/^[a-z]/{ /^dependencies:$/d; /^[a-z]/d; p; }' \
        >> "${CONDA_FILE}"

    # Validate generated YAML syntax
    if command -v python &> /dev/null; then
        if python -c "import yaml; yaml.safe_load(open('${CONDA_FILE}'))" 2>/dev/null; then
            echo "  Validated: ${CONDA_FILE} YAML syntax OK"
        else
            echo "  ERROR: Generated ${CONDA_FILE} has invalid YAML syntax"
            exit 1
        fi
    fi

    echo "  Generated: ${CONDA_FILE}"
else
    echo "  WARNING: conda not available, skipping conda environment documentation"
    echo "           Install miniforge/miniconda to generate conda_environment_ci.yaml"
fi

echo ""
echo "  Dependency documentation generation complete."
