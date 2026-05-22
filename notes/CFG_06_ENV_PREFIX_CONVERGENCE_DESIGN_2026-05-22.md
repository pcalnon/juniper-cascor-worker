# CFG-06 Design: juniper-cascor-worker env-var prefix convergence

**Status**: Draft — design discussion before implementation
**Author**: Paul Calnon
**Date**: 2026-05-22
**Roadmap reference**: [juniper-ml v7 roadmap CFG-06 (§20)](https://github.com/pcalnon/juniper-ml/blob/main/notes/JUNIPER_OUTSTANDING_DEVELOPMENT_ITEMS_V7_IMPLEMENTATION_ROADMAP.md#cfg-06-cascor_-env-prefix-inconsistent-with-juniper_-convention)
**Related shipped patterns**: CFG-03 (juniper-cascor PR #287), CFG-05 (juniper-cascor PR #289), CFG-04 (juniper-cascor PR #297), CFG-16 (juniper-canopy PR #312)

---

## 1. Problem statement

`juniper_cascor_worker/constants.py:151–165` declares 15 `ENV_*` constants that name the env vars the worker reads. Their string values are mixed-convention:

| Constant | Current name | Convention |
|---|---|---|
| `ENV_SERVER_URL` | `CASCOR_SERVER_URL` | legacy bare-`CASCOR_*` |
| `ENV_AUTH_TOKEN` | `CASCOR_AUTH_TOKEN` | legacy bare-`CASCOR_*` |
| `ENV_API_KEY` | `CASCOR_API_KEY` | legacy bare-`CASCOR_*` |
| `ENV_HEARTBEAT_INTERVAL` | `CASCOR_HEARTBEAT_INTERVAL` | legacy bare-`CASCOR_*` |
| `ENV_HEALTH_PORT` | `CASCOR_WORKER_HEALTH_PORT` | partial service-scope |
| `ENV_HEALTH_BIND` | `CASCOR_WORKER_HEALTH_BIND` | partial service-scope |
| `ENV_TASK_TIMEOUT` | `CASCOR_TASK_TIMEOUT` | legacy bare-`CASCOR_*` |
| `ENV_TLS_CERT` | `CASCOR_TLS_CERT` | legacy bare-`CASCOR_*` |
| `ENV_TLS_KEY` | `CASCOR_TLS_KEY` | legacy bare-`CASCOR_*` |
| `ENV_TLS_CA` | `CASCOR_TLS_CA` | legacy bare-`CASCOR_*` |
| `ENV_MANAGER_HOST` | `CASCOR_MANAGER_HOST` | legacy bare-`CASCOR_*` |
| `ENV_MANAGER_PORT` | `CASCOR_MANAGER_PORT` | legacy bare-`CASCOR_*` |
| `ENV_AUTHKEY` | `CASCOR_AUTHKEY` | legacy bare-`CASCOR_*` |
| `ENV_NUM_WORKERS` | `CASCOR_NUM_WORKERS` | legacy bare-`CASCOR_*` |
| `ENV_MP_CONTEXT` | `CASCOR_MP_CONTEXT` | legacy bare-`CASCOR_*` |

(The v7 roadmap text says 13 vars; the actual count is 15. Recorded as a coordinate correction in [juniper-ml#317 §2.2 status pass](https://github.com/pcalnon/juniper-ml/pull/317).)

The ecosystem convention — established across cascor server (`JUNIPER_CASCOR_*`), canopy (`JUNIPER_CANOPY_*`), and data (`JUNIPER_DATA_*`) — is `JUNIPER_<SERVICE>_<NAME>`. cascor-worker predates this convention. Two vars (`HEALTH_PORT`, `HEALTH_BIND`) were added later under METRICS-MON R1.3 with a `CASCOR_WORKER_*` prefix that points at the right shape but still lacks the ecosystem `JUNIPER_` root.

Consumer scope is narrow: every `ENV_*` is read in exactly one place — `juniper_cascor_worker/config.py::WorkerConfig.from_env()` (lines 119–134) — via `os.getenv(ENV_*)`. `config.py:145, 154` reference two of them in error messages. Tests touch them via `monkeypatch.setenv("CASCOR_*", ...)` and the `WorkerConfig.from_env()` happy path.

## 2. Goals & non-goals

**Goals**:

- Rename all 15 env vars to `JUNIPER_CASCOR_WORKER_*` so the worker is consistent with the rest of the ecosystem.
- Preserve full backward compatibility — every existing `CASCOR_*` (and `CASCOR_WORKER_*`) env var continues to work.
- Emit a `DeprecationWarning` on first use of any legacy name per process, with the new name in the message.
- Update operator-facing docs (worker AGENTS.md, README, `juniper-deploy/docker-compose.yml`) with the new names.

**Non-goals**:

- Replace the dataclass `WorkerConfig` + `from_env()` factory with `pydantic-settings` `BaseSettings`. Sibling services use `BaseSettings`, but introducing it here is a structural refactor that should be a separate item (e.g. a hypothetical CFG-XX in a future roadmap revision). This design intentionally leaves the factory shape alone.
- Rename non-env-var public APIs of the worker (CLI flags, log labels, etc.).
- Touch `juniper-deploy` in the same PR — that's a follow-up PR once the worker accepts both names.

## 3. Approaches

### Approach A — Helper-based deprecation (mirror CFG-03 / CFG-05)

Add a tiny helper that reads the new name first and falls back to the legacy name with a `DeprecationWarning`:

```python
# juniper_cascor_worker/constants.py (or new juniper_cascor_worker/_env_helpers.py)
import os
import warnings
from typing import Optional

def env_with_legacy_alias(
    new_name: str,
    legacy_name: Optional[str],
    default: Optional[str] = None,
) -> Optional[str]:
    """Read ``new_name`` first; fall back to ``legacy_name`` with a
    DeprecationWarning; return ``default`` if neither is set."""
    val = os.environ.get(new_name)
    if val is not None:
        return val
    if legacy_name is not None:
        legacy_val = os.environ.get(legacy_name)
        if legacy_val is not None:
            warnings.warn(
                f"{legacy_name} is deprecated; use {new_name} instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            return legacy_val
    return default
```

Constants split into canonical + legacy:

```python
# Canonical (new)
ENV_SERVER_URL: Final[str] = "JUNIPER_CASCOR_WORKER_SERVER_URL"
ENV_AUTH_TOKEN: Final[str] = "JUNIPER_CASCOR_WORKER_AUTH_TOKEN"  # nosec B105
# ... 13 more ...

# Legacy aliases (kept for one minor cycle; tests pin the deprecation path)
LEGACY_ENV_SERVER_URL: Final[str] = "CASCOR_SERVER_URL"
LEGACY_ENV_AUTH_TOKEN: Final[str] = "CASCOR_AUTH_TOKEN"  # nosec B105
# ... 13 more ...
```

`config.py::from_env()` calls the helper for each var:

```python
server_url = env_with_legacy_alias(ENV_SERVER_URL, LEGACY_ENV_SERVER_URL, "")
```

**Strengths**:

- Mirrors the proven CFG-03 / CFG-05 pattern on cascor (already merged and battle-tested).
- Minimal structural change — `WorkerConfig` dataclass + `from_env()` shape preserved.
- Each call site is grep-able; CI can pin "no raw `os.getenv("CASCOR_*")` in `config.py`" the same way CFG-16's source-level guard works.
- Per-call deprecation warning sites are precise: operators see exactly which legacy var triggered.

**Weaknesses**:

- 15 pairs of constants in `constants.py` (now 30 entries). Double the line count of the env-var section, plus the helper.
- Helper function is duplicated logic vs. what the cascor `Settings._check_legacy_*` validators already do. Could be lifted to `juniper-observability` (or new `juniper-config-tools`) later, but that's scope creep here.

**Risks**:

- If `warnings.simplefilter` is set to `"error"` in some downstream test environment, deprecation warning would raise. Mitigation: existing pattern in cascor + canopy hasn't broken anything; we'll cap stacklevel to 2 and document.

### Approach B — Single-source-of-truth aliasing table

Define a mapping table and iterate:

```python
ENV_ALIASES: Final[dict[str, str]] = {
    "JUNIPER_CASCOR_WORKER_SERVER_URL": "CASCOR_SERVER_URL",
    "JUNIPER_CASCOR_WORKER_AUTH_TOKEN": "CASCOR_AUTH_TOKEN",
    # ... 13 more ...
}

def env(new_name: str, default: Optional[str] = None) -> Optional[str]:
    val = os.environ.get(new_name)
    if val is not None:
        return val
    legacy = ENV_ALIASES.get(new_name)
    if legacy is not None and (legacy_val := os.environ.get(legacy)) is not None:
        warnings.warn(f"{legacy} is deprecated; use {new_name} instead.", DeprecationWarning, stacklevel=2)
        return legacy_val
    return default
```

**Strengths**: terser; one canonical lookup table; easy to enumerate (e.g. for a `juniper-cascor-worker doctor` command).

**Weaknesses**: couples the factory to a dict; per-var customisation (e.g. type conversion) leaks into the call site. Less idiomatic with sibling repos' helper-style pattern.

**Why not recommended**: convergence with sibling-repo style (Approach A) outweighs the line-count saving.

### Approach C — Introduce pydantic-settings `BaseSettings`

Replace the `@dataclass WorkerConfig` with `BaseSettings(env_prefix="JUNIPER_CASCOR_WORKER_")` + `AliasChoices(("JUNIPER_CASCOR_WORKER_SERVER_URL", "CASCOR_SERVER_URL"))` for each field, mirroring canopy / data / cascor.

**Strengths**: idiomatic with the rest of the ecosystem; automatic validation, `.env` support, `model_dump()` for diagnostics.

**Weaknesses**:

- Structural refactor: `WorkerConfig` is consumed across `worker.py`, `cli.py`, tests as a dataclass. Migrating to `BaseSettings` changes the constructor signature, mutability semantics, and validation timing.
- Adds `pydantic` + `pydantic-settings` as runtime deps for cascor-worker (currently neither is in `pyproject.toml`). Worker is intentionally lean — adding ~2 MB of deps for the env-prefix fix is disproportionate.
- Out of CFG-06 scope as stated in the roadmap (Approach A in the roadmap is alias-helper-based; the roadmap does not propose a Settings migration).

**Why not recommended**: scope expansion. A separate "migrate cascor-worker to BaseSettings" item could be filed for v8 if Paul wants ecosystem-wide Settings parity.

## 4. Sub-decision: new-prefix shape

| Option | Form | Argument |
|---|---|---|
| **A** | `JUNIPER_CASCOR_WORKER_*` | Strictly follows `JUNIPER_<SERVICE>_<NAME>`. Distinguishes worker from cascor server unambiguously. Operators see "this is the worker's auth token" at a glance. Mirrors the `CASCOR_WORKER_HEALTH_*` precedent already in the codebase. |
| **B** | `JUNIPER_WORKER_*` | Shorter, no redundant nesting. But ambiguous in a future world with multiple worker types (data worker, etc.); doesn't tie back to cascor. |
| **C** | `JUNIPER_CASCOR_*` (same as cascor server) | Reuses cascor server's prefix. Avoids any new prefix entirely. **Risk**: collisions — `JUNIPER_CASCOR_API_KEY` is already used by cascor server settings; reusing it for the worker creates an ambiguous read. Hard no. |

**Recommendation: Option A (`JUNIPER_CASCOR_WORKER_*`)**. It's the only one that's collision-free and matches the partial-precedent already in `constants.py` (HEALTH_PORT, HEALTH_BIND already use `CASCOR_WORKER_*` — they become `JUNIPER_CASCOR_WORKER_HEALTH_*` under this scheme).

## 5. Recommendation

**Approach A** (helper-based deprecation) **+ Option A** (`JUNIPER_CASCOR_WORKER_*` prefix).

Rationale:

- Highest pattern-fidelity to CFG-03 / CFG-05 (already-merged sibling-repo pattern).
- Minimal structural change to `WorkerConfig` shape.
- Backward-compatible by construction.
- Easy CI guard via source-level scope test (mirror CFG-16 pattern: assert `config.py` no longer contains raw `os.getenv("CASCOR_*")` for the 15 legacy names).
- Sub-decision A keeps the worker's namespace ecosystem-consistent without any collisions.

## 6. Impact

### Files changed (proposed PR)

- `juniper_cascor_worker/constants.py` — split each `ENV_*` into canonical + `LEGACY_ENV_*`; add the helper (or import it from a new `_env_helpers.py`).
- `juniper_cascor_worker/config.py` — `from_env()` uses the helper; error messages at lines 145, 154 use canonical names.
- `juniper_cascor_worker/cli.py` — if it references env-var names in `--help` text, update those references.
- New: `tests/test_cfg_06_env_prefix_aliases.py` — parametrized 15 × 4 cases (new alone / legacy alone / both / neither), plus a source-level scope guard.
- `AGENTS.md` — update the env-var section with both names + deprecation note.
- `README.md` — operator-facing env-var table.
- `CHANGELOG.md` — `### Changed` entry under `## [Unreleased]`.

### Files NOT changed in this PR (deferred follow-ups)

- `juniper-deploy/docker-compose.yml` — switches to the new names in a separate PR after this one merges (legacy still works during the transition window).
- Sibling-service env-var refs (if any deploy/CI script reads worker env vars) — same follow-up.

### Backward compatibility

Full. Every existing `CASCOR_*` env name continues to read; only the warning surface changes.

### Deprecation timeline

- v0.4.x (this PR): both names accepted; legacy emits `DeprecationWarning`.
- v0.5.x (next minor, no fixed date): legacy still works but warning escalates to `FutureWarning` (visible by default to end users) — only flip if operator adoption is slow.
- v1.0.0 (no committed date): legacy support removed. Tests for the legacy path moved to an `xfail` / removal-marker.

This matches the CFG-03 / CFG-05 timeline shape.

## 7. Rollout plan

1. **Worker PR** (this design): land the alias machinery in juniper-cascor-worker. New + legacy names both work; legacy warns.
2. **Deploy PR**: update `juniper-deploy/docker-compose.yml` (and any sibling compose files) to use new names. Legacy continues to function; this PR just stops emitting the warnings in default deploys.
3. **Docs sweep PR**: update operator-facing examples in `juniper-cascor-worker/README.md` and `notes/`; ensure cross-repo docs (`juniper-deploy/AGENTS.md`, `juniper-canopy/docs/REFERENCE.md`) cite the canonical names.

The three PRs are independent in scope but ordered (worker first, then deploy, then docs).

## 8. Test strategy

### Per-var behaviour (parametrized × 15)

For each `(canonical, legacy)` pair:

| Env state | Expected |
|---|---|
| canonical set, legacy unset | returns canonical value, no warning |
| canonical unset, legacy set | returns legacy value, exactly one `DeprecationWarning` whose message names both old + new |
| both set (canonical and legacy) | returns canonical value, no warning (legacy silently ignored) |
| neither set | returns the documented default |

### Source-level scope guard (mirror CFG-16's `_strip_comments_and_docstrings` test)

Assert that `juniper_cascor_worker/config.py` (post-docstring/comment strip) contains zero `os.getenv("CASCOR_*")` patterns for the 15 legacy names. This pins that future edits don't reintroduce raw legacy reads bypassing the deprecation helper.

### Integration smoke

A single end-to-end test that constructs a `WorkerConfig.from_env()` under a mixed-legacy-and-new env (e.g. `JUNIPER_CASCOR_WORKER_SERVER_URL` set, `CASCOR_AUTH_TOKEN` set legacy, rest unset). Confirms the resulting `WorkerConfig` has the expected fields and exactly one deprecation warning is captured.

## 9. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Operator scripts grep for `CASCOR_*` in their own config and break when warned | Low | Warning is `DeprecationWarning` (silent by default in production); README / AGENTS.md updates show both names side-by-side during the transition |
| Test environment with `simplefilter("error")` raises on the warning | Low | Same risk pattern as CFG-03 / CFG-05 in cascor — has not bitten in 4 weeks of shipped code |
| Helper module location bike-shedding (`constants.py` vs `_env_helpers.py`) | None | See Open Questions §10.1 |
| Operator confusion during the transition window | Low | Single CHANGELOG entry + AGENTS.md table mapping legacy → canonical names |

## 10. Open questions

### 10.1 Helper module location

Put the helper in `constants.py` (next to the `ENV_*` constants) or in a new `juniper_cascor_worker/_env_helpers.py`?

Argument for `constants.py`: locality of reference; one fewer module; matches the file the user will touch when changing names.

Argument for `_env_helpers.py`: separates pure-data (constants) from behaviour (helper); easier to mock in tests.

**Recommended default**: `constants.py`. Move to `_env_helpers.py` only if it grows beyond one function. Aligns with CFG-03 / CFG-05's "keep the helper near the names" choice in cascor.

### 10.2 Warning frequency

`warnings.warn(..., DeprecationWarning)` defaults to "once per location" — which means once-per-file-line, not once-per-process. If `from_env()` is called once at startup, this is moot. If it's called repeatedly (e.g. in test fixtures), each test will warn.

**Recommended default**: leave it once-per-location (the warnings module default). The test suite catches warnings explicitly via `warnings.catch_warnings(record=True)` in the CFG-06 regression tests, so test-side noise is contained.

### 10.3 Shared helper across repos?

CFG-03 (cascor), CFG-05 (cascor), CFG-16 (canopy), and now CFG-06 (cascor-worker) all reinvent the same alias-with-deprecation helper. Should this be lifted to a shared package (juniper-observability? a new juniper-config-tools?)?

**Recommended default**: **defer**. Lifting now means a new package + cross-repo coordination + an extra dep — disproportionate for what's a 10-line helper. Revisit when a 5th repo hits the same pattern.

### 10.4 Renaming `WorkerConfig.from_env()` parameter contract

`from_env()` currently always reads from `os.environ`. Should this PR also add a `from_env(env: Mapping[str, str] | None = None)` parameter so tests don't need to monkeypatch?

**Recommended default**: out of scope. The deprecation helper reads via `os.environ.get` directly; the test pattern is already `monkeypatch.setenv(...)` which is well-established in sibling repos. Filing this as a separate cleanup item if Paul wants the cleaner test surface.

## 11. Acceptance criteria

The implementation PR (separate from this design doc PR) closes CFG-06 when:

- [ ] All 15 `ENV_*` constants in `constants.py` use the `JUNIPER_CASCOR_WORKER_*` canonical name.
- [ ] All 15 `LEGACY_ENV_*` constants exist with the matching `CASCOR_*` legacy name.
- [ ] `config.py::WorkerConfig.from_env()` reads via the alias helper for every field.
- [ ] Per-var parametrized regression tests pass (15 × 4 cases minimum).
- [ ] Source-level scope guard passes (no raw `os.getenv("CASCOR_*")` in `config.py`).
- [ ] CHANGELOG entry under `## [Unreleased] → ### Changed`.
- [ ] AGENTS.md env-var section updated with both names + deprecation note.
- [ ] `juniper-ml/notes/JUNIPER_OUTSTANDING_DEVELOPMENT_ITEMS_V7_IMPLEMENTATION_ROADMAP.md` §2.2 status pass updated to mark CFG-06 ✅ shipped.

The two follow-up PRs (deploy + docs sweep) are not part of CFG-06's acceptance — they're tracked separately.

## 12. References

- v7 roadmap CFG-06 entry: [`notes/JUNIPER_OUTSTANDING_DEVELOPMENT_ITEMS_V7_IMPLEMENTATION_ROADMAP.md:13699`](https://github.com/pcalnon/juniper-ml/blob/main/notes/JUNIPER_OUTSTANDING_DEVELOPMENT_ITEMS_V7_IMPLEMENTATION_ROADMAP.md#cfg-06-cascor_-env-prefix-inconsistent-with-juniper_-convention) (juniper-ml)
- §2.2 status pass (in flight as juniper-ml#317).
- Sibling-repo precedent — helper-based deprecation:
  - juniper-cascor PR #287 (CFG-03 — `SENTRY_SDK_DSN` → `JUNIPER_CASCOR_SENTRY_DSN`)
  - juniper-cascor PR #289 (CFG-05 — `CASCOR_LOG_LEVEL` → `JUNIPER_CASCOR_LOG_LEVEL`)
- Sibling-repo precedent — Settings-validator deprecation (Approach C reference, not chosen here):
  - juniper-cascor PR #297 (CFG-04 — `JUNIPER_DATA_URL` consolidation)
  - juniper-canopy PR #312 (CFG-16 — `CASCOR_DEMO_MODE` / `CASCOR_SERVICE_URL` consolidation)
