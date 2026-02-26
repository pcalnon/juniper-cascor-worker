# AGENTS.md - Juniper Cascor Worker

**Project**: juniper-cascor-worker — Distributed CasCor Training Worker
**Version**: 0.1.0
**License**: MIT License
**Author**: Paul Calnon
**Last Updated**: 2026-02-25

---

## Quick Reference

### Essential Commands

```bash
# Install in development mode
pip install -e ".[dev]"

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=juniper_cascor_worker --cov-report=term-missing --cov-fail-under=80

# Type checking
mypy juniper_cascor_worker --ignore-missing-imports

# Linting
flake8 juniper_cascor_worker --max-line-length=120
black --check --diff juniper_cascor_worker
isort --check-only --diff juniper_cascor_worker

# Run worker CLI
juniper-cascor-worker --host <manager-host> --port <manager-port>
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CASCOR_MANAGER_HOST` | Manager hostname | `localhost` |
| `CASCOR_MANAGER_PORT` | Manager port | `50000` |
| `CASCOR_AUTHKEY` | Authentication key | `juniper-cascor` |
| `CASCOR_NUM_WORKERS` | Number of worker processes | CPU count |
| `CASCOR_MP_CONTEXT` | Multiprocessing context | `spawn` |

### Key Files

| File | Purpose |
|------|---------|
| `juniper_cascor_worker/cli.py` | CLI entry point |
| `juniper_cascor_worker/__init__.py` | Package init |
| `pyproject.toml` | Package config, dependencies |
| `tests/` | Test suite (pytest) |

---

## Project Overview

`juniper-cascor-worker` is a distributed candidate training worker for the JuniperCascor neural network platform. It connects to a JuniperCascor manager process and trains candidate units in parallel across remote hardware.

### Dependencies

| Library | Purpose |
|---------|---------|
| `numpy` | Numerical computations |
| `torch` | Neural network operations |

---

## Ecosystem Context

Part of the Juniper ecosystem. See the parent directory's `CLAUDE.md` at `/home/pcalnon/Development/python/Juniper/CLAUDE.md` for the full project map, dependency graph, shared conventions, and conda environment details.

### Position in Dependency Graph

```
juniper-ml[worker] --> juniper-cascor-worker --> JuniperCascor (manager)
```

---

## Worktree Procedures (Mandatory — Task Isolation)

> **OPERATING INSTRUCTION**: All feature, bugfix, and task work SHOULD use git worktrees for isolation. Worktrees keep the main working directory on the default branch while task work proceeds in a separate checkout.

### What This Is

Git worktrees allow multiple branches of a repository to be checked out simultaneously in separate directories. For the Juniper ecosystem, all worktrees are centralized in **`/home/pcalnon/Development/python/Juniper/worktrees/`** using a standardized naming convention.

The full setup and cleanup procedures are defined in:
- **`notes/WORKTREE_SETUP_PROCEDURE.md`** — Creating a worktree for a new task
- **`notes/WORKTREE_CLEANUP_PROCEDURE.md`** — Merging, removing, and pushing after task completion

Read the appropriate file when starting or completing a task.

### Worktree Directory Naming

Format: `<repo-name>--<branch-name>--<YYYYMMDD-HHMM>--<short-hash>`

Example: `juniper-cascor-worker--feature--add-gpu-support--20260225-1430--047c3f61`

- Slashes in branch names are replaced with `--`
- All worktrees reside in `/home/pcalnon/Development/python/Juniper/worktrees/`

### When to Use Worktrees

| Scenario | Use Worktree? |
| -------- | ------------- |
| Feature development (new feature branch) | **Yes** |
| Bug fix requiring a dedicated branch | **Yes** |
| Quick single-file documentation fix on main | No |
| Exploratory work that may be discarded | **Yes** |
| Hotfix requiring immediate merge | **Yes** |

### Quick Reference

**Setup** (full procedure in `notes/WORKTREE_SETUP_PROCEDURE.md`):
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

**Cleanup** (full procedure in `notes/WORKTREE_CLEANUP_PROCEDURE.md`):
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

### Rules

- **Centralized location**: All worktrees go in `/home/pcalnon/Development/python/Juniper/worktrees/`. Never create worktrees inside the repo directory.
- **Clean before you start**: Ensure the main working directory is clean before creating a worktree.
- **Push before you merge**: Always push the working branch to remote before merging (backup).
- **Prune after cleanup**: Run `git worktree prune` after removing a worktree to clean metadata.
- **Do not leave stale worktrees**: Clean up worktrees promptly after merging.

---

## Thread Handoff (Mandatory — Replaces Thread Compaction)

> **CRITICAL OPERATING INSTRUCTION**: Thread handoff MUST be performed instead of thread compaction. This section defines mandatory behavior that overrides Claude Code's default compaction process.

### What This Is

When a long-running conversation approaches context limits, Claude Code normally performs **thread compaction** — summarizing prior context to free token capacity. This introduces information loss. Instead, Claude Code instances working on this project MUST perform a **proactive thread handoff**: transferring a curated, high-signal summary to a fresh thread with full context capacity.

The full handoff protocol is defined in **`notes/THREAD_HANDOFF_PROCEDURE.md`**. Read that file when a handoff is triggered.

### When to Trigger a Handoff

**Automatic trigger (pre-compaction threshold):** Initiate a thread handoff when token utilization reaches **95% to 99%** of the level at which thread compaction would normally be triggered.

**Additional triggers**:

| Condition | Indicator |
| --------- | --------- |
| **Context saturation** | Thread has performed 15+ tool calls or edited 5+ files |
| **Phase boundary** | A logical phase of work is complete |
| **Degraded recall** | Re-reading a file already read, or re-asking a resolved question |
| **Multi-module transition** | Moving between major components |
| **User request** | User says "hand off", "new thread", or similar |

**Do NOT handoff** when:
- The task is nearly complete (< 2 remaining steps)
- The current thread is still sharp and producing correct output
- The work is tightly coupled and splitting would lose critical in-flight state

### How to Execute a Handoff

1. **Checkpoint**: Inventory what was done, what remains, what was discovered, and what files are in play
2. **Compose the handoff goal**: Write a concise, actionable summary (see templates in `notes/THREAD_HANDOFF_PROCEDURE.md`)
3. **Present to user**: Output the handoff goal to the user and recommend starting a new thread with that goal as the initial prompt
4. **Include verification commands**: Always specify how the new thread should verify its starting state
5. **State git status**: Mention branch, staged files, and any uncommitted work

### Rules

- **This is not optional.** Every Claude Code instance on this project must follow these rules.
- **Handoff early, not late.** A handoff at 70% context usage is better than compaction at 95%.
- **Do not duplicate CLAUDE.md content** in the handoff goal — the new thread reads CLAUDE.md automatically.
- **Be specific** in the handoff goal: include file paths, decisions made, and test status.
