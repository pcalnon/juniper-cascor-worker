# Worktree Cleanup Procedure

**Purpose**: Standardized procedure for merging, cleaning up, and pushing after completing a task in a worktree
**Project**: juniper-cascor-worker
**Last Updated**: 2026-02-25

---

## Why Proper Cleanup Matters

Stale worktrees consume disk space and clutter the centralized `worktrees/` directory. Orphan branches pollute the branch namespace locally and on the remote. Proper cleanup after each task ensures a clean, predictable development environment.

---

## Prerequisites

- All work in the worktree is committed
- Tests pass in the worktree

### Pre-Merge Verification

```bash
cd <worktree-dir>
conda activate JuniperPython
pytest tests/ -v
```

---

## Cleanup Protocol

### Step 1: Ensure All Work Is Committed

```bash
cd "$WORKTREE_DIR"
git status
```

### Step 2: Push Working Branch to Remote

```bash
git push origin "$BRANCH_NAME"
```

### Step 3: Switch to the Main Repo Directory

```bash
cd /home/pcalnon/Development/python/Juniper/juniper-cascor-worker
```

### Step 4: Update the Merge Target

```bash
MERGE_TARGET="main"
git checkout "$MERGE_TARGET"
git pull origin "$MERGE_TARGET"
```

### Step 5: Merge the Working Branch

```bash
git merge "$BRANCH_NAME"
```

### Step 6: Push the Merged Branch to Remote

```bash
git push origin "$MERGE_TARGET"
```

### Step 7: Remove the Worktree

```bash
git worktree remove "$WORKTREE_DIR"
```

### Step 8: Delete the Working Branch (Local and Remote)

```bash
git branch -d "$BRANCH_NAME"
git push origin --delete "$BRANCH_NAME"
```

### Step 9: Prune and Verify

```bash
git worktree prune
git worktree list
git branch
```

---

## Alternate Merge Targets

```bash
MERGE_TARGET="develop"
```

---

## Edge Cases

### Merge Conflicts

```bash
git merge --abort
gh pr create --base "$MERGE_TARGET" --head "$BRANCH_NAME" \
  --title "Merge $BRANCH_NAME into $MERGE_TARGET"
```

### Worktree Removal Fails

```bash
git worktree remove --force "$WORKTREE_DIR"
git worktree prune
```

---

## Quick Reference (Copy-Paste)

```bash
cd "$WORKTREE_DIR" && git push origin "$BRANCH_NAME"
cd /home/pcalnon/Development/python/Juniper/juniper-cascor-worker
git checkout main && git pull origin main
git merge "$BRANCH_NAME"
git push origin main
git worktree remove "$WORKTREE_DIR"
git branch -d "$BRANCH_NAME"
git push origin --delete "$BRANCH_NAME"
git worktree prune
```
