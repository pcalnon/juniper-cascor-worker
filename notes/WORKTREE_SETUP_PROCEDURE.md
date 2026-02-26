# Worktree Setup Procedure

**Purpose**: Standardized procedure for creating a git worktree when beginning a new task
**Project**: juniper-cascor-worker
**Last Updated**: 2026-02-25

---

## Why Worktrees

Git worktrees provide task isolation by allowing multiple branches to be checked out simultaneously in separate directories. This keeps the main working directory on the default branch while task work proceeds in a dedicated checkout, preventing accidental commits to `main` and enabling easy context switching between tasks.

For the Juniper ecosystem, all worktrees are centralized in `/home/pcalnon/Development/python/Juniper/worktrees/`.

---

## Prerequisites

- You must be in the repo's primary working directory (not already in a worktree)
- The working tree must be clean (no uncommitted changes)
- The target branch must not already be checked out in another worktree

---

## Setup Protocol

### Step 1: Ensure Clean State

```bash
cd /home/pcalnon/Development/python/Juniper/juniper-cascor-worker
git status
```

### Step 2: Fetch and Update Parent Branch

```bash
git fetch origin
git checkout main
git pull origin main
```

### Step 3: Create the Working Branch

```bash
BRANCH_NAME="feature/my-task-name"
PARENT_BRANCH="main"

git branch "$BRANCH_NAME" "$PARENT_BRANCH"
```

### Step 4: Compute the Worktree Directory Name

```bash
REPO_NAME=$(basename "$(pwd)")
SAFE_BRANCH=$(echo "$BRANCH_NAME" | sed 's|/|--|g')
TIMESTAMP=$(date +%Y%m%d-%H%M)
SHORT_HASH=$(git rev-parse --short=8 HEAD)
WORKTREE_BASE="/home/pcalnon/Development/python/Juniper/worktrees"
WORKTREE_DIR="${WORKTREE_BASE}/${REPO_NAME}--${SAFE_BRANCH}--${TIMESTAMP}--${SHORT_HASH}"
```

### Step 5: Create the Worktree

```bash
git worktree add "$WORKTREE_DIR" "$BRANCH_NAME"
```

### Step 6: Verify and Begin Work

```bash
git worktree list
cd "$WORKTREE_DIR"
git branch --show-current
git log --oneline -3
```

---

## Naming Convention

**Format**: `<repo-name>--<branch-name>--<YYYYMMDD-HHMM>--<short-hash>`

**Full example**: `juniper-cascor-worker--feature--add-gpu-support--20260225-1430--047c3f61`

**Location**: All worktrees reside in `/home/pcalnon/Development/python/Juniper/worktrees/`

---

## Edge Cases

### Branch Already Exists

```bash
git branch --list "$BRANCH_NAME"
git branch -d "$BRANCH_NAME"
git branch "$BRANCH_NAME" "$PARENT_BRANCH"
```

### Working from a Remote Branch

```bash
git checkout -b "$BRANCH_NAME" "origin/$BRANCH_NAME"
```

---

## Project-Specific Notes

```bash
cd "$WORKTREE_DIR"
conda activate JuniperPython
pip install -e ".[dev]"
pytest tests/ -v
```

---

## Quick Reference (Copy-Paste)

```bash
cd /home/pcalnon/Development/python/Juniper/juniper-cascor-worker
git fetch origin && git checkout main && git pull origin main
BRANCH_NAME="feature/my-task"
git branch "$BRANCH_NAME" main
REPO_NAME=$(basename "$(pwd)")
SAFE_BRANCH=$(echo "$BRANCH_NAME" | sed 's|/|--|g')
WORKTREE_DIR="/home/pcalnon/Development/python/Juniper/worktrees/${REPO_NAME}--${SAFE_BRANCH}--$(date +%Y%m%d-%H%M)--$(git rev-parse --short=8 HEAD)"
git worktree add "$WORKTREE_DIR" "$BRANCH_NAME"
cd "$WORKTREE_DIR"
```
