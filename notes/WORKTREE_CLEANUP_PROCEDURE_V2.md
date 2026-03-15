# Worktree Cleanup Procedure V2

**Purpose**: Standardized procedure for completing work in a worktree, merging, creating PRs, and transitioning to a new worktree — without trapping the Claude Code session in an invalid CWD
**Project**: juniper-cascor-worker
**Last Updated**: 2026-03-15

---

## Why This Procedure Exists

Claude Code sessions run with their CWD set to a worktree directory. The V1 procedure removed the worktree directory without first creating a replacement, leaving the session trapped in a non-existent path. This V2 procedure creates a new worktree and switches the CWD **before** removing the old one.

---

## Prerequisites

- All work in the worktree is committed
- The `gh` CLI is authenticated (`gh auth status`)
- The main repo directory is accessible at `/home/pcalnon/Development/python/Juniper/juniper-cascor-worker`

---

## Variables Reference

Set these at the start of cleanup:

```bash
# Old worktree (the one being cleaned up)
OLD_WORKTREE_DIR="<current worktree path>"
OLD_BRANCH="<current worktree branch name>"
PARENT_BRANCH="<branch that was active when worktree was created>"

# Main repo
MAIN_REPO="/home/pcalnon/Development/python/Juniper/juniper-cascor-worker"
```

---

## Phase 1: Save & Push Current Work

### Step 1: Verify Clean State

```bash
cd "$OLD_WORKTREE_DIR"
git status
```

**GATE**: Working tree must be clean. If dirty, commit remaining changes:

```bash
git add <files>
git commit -m "<final commit message>"
```

### Step 2: Push Worktree Branch to Remote

```bash
git push origin "$OLD_BRANCH"
```

---

## Phase 2: Create New Worktree (Session Continuity)

This phase MUST complete before Phase 4 (old worktree removal).

### Step 3: Fetch Latest and Generate New Worktree Metadata

```bash
git fetch origin
NEW_BRANCH="worktree-<claude-session-name>"
NEW_WORKTREE_DIR="${MAIN_REPO}/.claude/worktrees/<claude-session-name>"
```

### Step 4: Create New Worktree

```bash
git worktree add "$NEW_WORKTREE_DIR" -b "$NEW_BRANCH" origin/main
```

### Step 5: Switch CWD to New Worktree

```bash
cd "$NEW_WORKTREE_DIR"
```

### Step 6: Verify New CWD

```bash
pwd
git status
git branch --show-current
```

**GATE**: CWD must be inside the new worktree. `pwd` must match `$NEW_WORKTREE_DIR`. Do NOT proceed to Phase 4 until this is confirmed.

---

## Phase 3: Merge & Pull Request

### Step 7: Determine Merge Strategy

| Parent Branch | Strategy |
|---------------|----------|
| `main` | Create PR directly: `old-branch -> main` |
| Not `main` | Merge `old-branch -> parent`, then create PR: `parent -> main` |

### Step 8a: If Parent Is `main`

Create a pull request (do NOT merge directly):

```bash
gh pr create \
  --repo pcalnon/juniper-cascor-worker \
  --base main \
  --head "$OLD_BRANCH" \
  --title "<short descriptive title>" \
  --body "<PR description>"
```

### Step 8b: If Parent Is NOT `main`

First merge the worktree branch into the parent branch:

```bash
cd "$MAIN_REPO"
git checkout "$PARENT_BRANCH"
git pull origin "$PARENT_BRANCH"
git merge "$OLD_BRANCH"
git push origin "$PARENT_BRANCH"
cd "$NEW_WORKTREE_DIR"
```

Then create a PR from parent to main:

```bash
gh pr create \
  --repo pcalnon/juniper-cascor-worker \
  --base main \
  --head "$PARENT_BRANCH" \
  --title "<short descriptive title>" \
  --body "<PR description>"
```

### Step 8c: Merge Conflict Handling

If the merge in Step 8b produces conflicts:

```bash
git merge --abort
```

Create a PR instead and resolve conflicts there:

```bash
gh pr create \
  --repo pcalnon/juniper-cascor-worker \
  --base "$PARENT_BRANCH" \
  --head "$OLD_BRANCH" \
  --title "Merge $OLD_BRANCH into $PARENT_BRANCH"
```

---

## Phase 4: Remove Old Worktree

**PREREQUISITE**: CWD must be in the new worktree (verified in Step 6).

### Step 9: Remove Old Worktree Directory

```bash
git worktree remove "$OLD_WORKTREE_DIR"
```

If removal fails (uncommitted changes):

```bash
git worktree remove --force "$OLD_WORKTREE_DIR"
```

### Step 10: Delete Old Branch (Local)

```bash
git branch -d "$OLD_BRANCH"
```

If the branch is not fully merged (e.g., PR pending):

```bash
git branch -D "$OLD_BRANCH"
```

### Step 11: Delete Old Branch (Remote)

> **IMPORTANT**: If a PR is open for this branch, do NOT delete the remote branch.
> Deleting the remote branch will close/invalidate the PR. The PR merge process
> on GitHub will handle remote branch cleanup automatically.

Only delete after the PR is merged or the branch is no longer needed:

```bash
# First check for open PRs
gh pr list --head "$OLD_BRANCH" --state open

# Only if no open PRs:
git push origin --delete "$OLD_BRANCH"
```

### Step 12: Prune

```bash
git worktree prune
```

---

## Phase 5: Verify

### Step 13: Final Verification

```bash
# CWD is valid
pwd && ls

# Worktree list is clean
git worktree list

# Branch list is clean
git branch

# Working tree is clean
git status
```

---

## Quick Reference (Copy-Paste)

```bash
# --- Phase 1: Save & Push ---
cd "$OLD_WORKTREE_DIR"
git status  # must be clean
git push origin "$OLD_BRANCH"

# --- Phase 2: New Worktree (MUST complete before Phase 4) ---
git fetch origin
git worktree add "$NEW_WORKTREE_DIR" -b "$NEW_BRANCH" origin/main
cd "$NEW_WORKTREE_DIR"    # CRITICAL: CWD must move here before old worktree is removed
pwd && git status          # verify CWD is valid

# --- Phase 3: PR (if parent is main — do NOT merge directly) ---
gh pr create --repo pcalnon/juniper-cascor-worker --base main --head "$OLD_BRANCH" \
  --title "<title>" --body "<body>"

# --- Phase 4: Cleanup ---
git worktree remove "$OLD_WORKTREE_DIR"
git branch -D "$OLD_BRANCH"    # -D because branch is not merged locally (PR pending)
# Do NOT delete remote branch if PR is open — GitHub handles this after merge
git worktree prune

# --- Phase 5: Verify ---
pwd && git worktree list && git branch && git status
```

---

## Edge Cases

### PR Already Exists for Branch

Check before creating:

```bash
gh pr list --head "$OLD_BRANCH" --state open
```

### Multiple Worktrees Needing Cleanup

Run the cleanup procedure for each worktree individually.

### Worktree Removal Fails

```bash
git worktree remove --force "$OLD_WORKTREE_DIR"
git worktree prune
```

### Parent Branch Has Diverged

Rebase before merging:

```bash
cd "$OLD_WORKTREE_DIR"
git fetch origin
git rebase "origin/$PARENT_BRANCH"
git push origin "$OLD_BRANCH" --force-with-lease
```

---

## Supersedes

This procedure replaces `notes/WORKTREE_CLEANUP_PROCEDURE.md` (V1).
The V1 file has been moved to `notes/history/WORKTREE_CLEANUP_PROCEDURE_V1.md`.
