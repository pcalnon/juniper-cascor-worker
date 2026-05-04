# Documentation Overview

## Navigation Guide to juniper-cascor-worker Documentation

**Version:** 0.2.0
**Status:** Active
**Last Updated:** May 4, 2026
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
| **DOCUMENTATION_OVERVIEW.md** | ~100 | Overview | This file -- navigation index |
| **QUICK_START.md** | ~100 | Tutorial | Install, configure, and run a worker in 5 minutes |
| **REFERENCE.md** | ~230 | Reference | Complete Python API, CLI, configuration, and exception reference |
| **DEVELOPER_CHEATSHEET.md** | ~210 | Cheatsheet | Quick-reference card for common development tasks and CI automation |

### Root Directory

| File | Lines | Type | Purpose |
|------|-------|------|---------|
| **README.md** | ~170 | Overview | Project overview and quick examples |
| **AGENTS.md** | ~200 | Guide | Development conventions, commands, worktree setup |
| **CHANGELOG.md** | ~30 | History | Version history and release notes |

---

## Ecosystem Context

`juniper-cascor-worker` is a distributed training worker that connects remote training hardware to the `juniper-cascor` service.

The default path is WebSocket-based: `CascorWorkerAgent` connects to `/ws/v1/workers`, registers worker capabilities, receives JSON task metadata plus binary tensor frames, runs candidate training locally, and returns `task_result` messages with output tensors. The legacy `CandidateTrainingWorker` path still exists for deprecated BaseManager deployments and is only active when the CLI is run with `--legacy`.

### Dependency Graph

```text
juniper-ml[worker] --> juniper-cascor-worker --WebSocket--> juniper-cascor
                                                |
                                                +-- legacy BaseManager mode with --legacy
```

### Compatibility

| juniper-cascor-worker | juniper-cascor | juniper-data | juniper-canopy |
|-----------------------|----------------|--------------|----------------|
| 0.3.x | 0.3.x | 0.4.x | 0.2.x |

---

## Related Documentation

### Upstream Service

- **juniper-cascor** -- [Training Service](https://github.com/pcalnon/juniper-cascor) (provides the `/ws/v1/workers` endpoint and the deprecated `CandidateTrainingManager` legacy path)

### Meta-Package

- **juniper-ml** -- `pip install juniper-ml[worker]` installs this package automatically

---

**Last Updated:** May 4, 2026
**Version:** 0.2.0
**Maintainer:** Paul Calnon

> See the [Juniper Ecosystem Guide](https://github.com/pcalnon/juniper-ml/blob/main/CLAUDE.md) for the full project map and dependency graph.
