# Documentation Overview

## Navigation Guide to juniper-cascor-worker Documentation

**Version:** 0.1.0
**Status:** Active
**Last Updated:** March 3, 2026
**Project:** Juniper - Distributed CasCor Training Worker

---

## Table of Contents

- [Quick Navigation](#quick-navigation)
- [Document Index](#document-index)
- [Ecosystem Context](#ecosystem-context)
- [Related Documentation](#related-documentation)

---

## Quick Navigation

### I Want To

| Goal | Document | Location |
|------|----------|----------|
| **Install and run a worker** | [QUICK_START.md](QUICK_START.md) | docs/ |
| **See the full API and CLI reference** | [REFERENCE.md](REFERENCE.md) | docs/ |
| **Understand the project** | [README.md](../README.md) | Root |
| **See development conventions** | [AGENTS.md](../AGENTS.md) | Root |
| **See version history** | [CHANGELOG.md](../CHANGELOG.md) | Root |
| **Quick-reference dev tasks** | [DEVELOPER_CHEATSHEET.md](DEVELOPER_CHEATSHEET.md) | docs/ |
| **Run tests** | [AGENTS.md](../AGENTS.md) | Root |

---

## Document Index

### docs/ Directory

| File | Lines | Type | Purpose |
|------|-------|------|---------|
| **DOCUMENTATION_OVERVIEW.md** | ~90 | Overview | This file -- navigation index |
| **QUICK_START.md** | ~100 | Tutorial | Install, configure, and run a worker in 5 minutes |
| **REFERENCE.md** | ~230 | Reference | Complete Python API, CLI, configuration, and exception reference |

### notes/ Directory

| File | Lines | Type | Purpose |
|------|-------|------|---------|
| **DEVELOPER_CHEATSHEET.md** | ~100 | Cheatsheet | Quick-reference card for common development tasks |

### Root Directory

| File | Lines | Type | Purpose |
|------|-------|------|---------|
| **README.md** | ~170 | Overview | Project overview and quick examples |
| **AGENTS.md** | ~200 | Guide | Development conventions, commands, worktree setup |
| **CHANGELOG.md** | ~30 | History | Version history and release notes |

---

## Ecosystem Context

`juniper-cascor-worker` is a distributed training worker that connects to a juniper-cascor manager process and spawns local worker processes to accelerate candidate training.

### Dependency Graph

```
juniper-cascor-worker ──IPC (multiprocessing queues)──> juniper-cascor (manager, port 50000)
juniper-ml ──meta-package──> juniper-cascor-worker
```

### Compatibility

| juniper-cascor-worker | juniper-cascor | juniper-data | juniper-canopy |
|-----------------------|----------------|--------------|----------------|
| 0.1.x | 0.3.x | 0.4.x | 0.2.x |

---

## Related Documentation

### Upstream Service

- **juniper-cascor** -- [Training Service](https://github.com/pcalnon/juniper-cascor) (provides the `CandidateTrainingManager` that this worker connects to)

### Meta-Package

- **juniper-ml** -- `pip install juniper-ml[worker]` installs this package automatically

---

**Last Updated:** March 3, 2026
**Version:** 0.1.0
**Maintainer:** Paul Calnon
