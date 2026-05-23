"""Regression tests for CFG-06 — env-var prefix convergence.

See ``notes/CFG_06_ENV_PREFIX_CONVERGENCE_DESIGN_2026-05-22.md`` in
juniper-cascor-worker for the design rationale, and §2.2 of the
v7 roadmap in juniper-ml for the cross-cutting status pass.

The 15 canonical/legacy env-var pairs in
``juniper_cascor_worker/constants.py`` are resolved via
``juniper_cascor_worker.config._resolve``, which delegates to
``juniper_config_tools.env_with_legacy_alias`` on the production
path and uses an inline mapping-aware variant on the test-injection
path. Both paths are exercised here.

Properties pinned:

1. **Per-field × 4-env-state matrix** (14 unique canonical vars × 4 =
   56 cases) — canonical alone / legacy alone / both / neither.
   ``ENV_AUTH_TOKEN`` has dual legacy (``CASCOR_AUTH_TOKEN`` +
   ``CASCOR_API_KEY``) covered separately.
2. ``WorkerConfig.from_env(env: Mapping)`` — explicit mapping
   injection bypasses ``os.environ`` (Open Q §10.4 resolution).
3. **Source-level scope guard** — ``config.py`` and ``cli.py``
   contain no raw ``os.getenv("CASCOR_*")`` / ``os.environ.get
   ("CASCOR_*")`` calls (mirrors CFG-16's stripped-source guard).
4. **No-pydantic-at-runtime invariant preserved** — importing
   ``config`` after the CFG-06 changes still does not pull
   ``pydantic`` into ``sys.modules`` (R2 exit-gate juniper-ml#168).
"""

from __future__ import annotations

import inspect
import re
import subprocess  # nosec B404 — hardcoded args
import sys
import warnings
from typing import Any

import pytest

from juniper_cascor_worker.config import WorkerConfig, _resolve
from juniper_cascor_worker.constants import (
    DEFAULT_HEALTH_BIND,
    DEFAULT_HEALTH_PORT,
    DEFAULT_HEARTBEAT_INTERVAL,
    DEFAULT_MANAGER_HOST,
    DEFAULT_MANAGER_PORT,
    DEFAULT_MP_CONTEXT,
    DEFAULT_NUM_WORKERS,
    DEFAULT_TASK_TIMEOUT,
    ENV_AUTH_TOKEN,
    ENV_AUTHKEY,
    ENV_HEALTH_BIND,
    ENV_HEALTH_PORT,
    ENV_HEARTBEAT_INTERVAL,
    ENV_MANAGER_HOST,
    ENV_MANAGER_PORT,
    ENV_MP_CONTEXT,
    ENV_NUM_WORKERS,
    ENV_SERVER_URL,
    ENV_TASK_TIMEOUT,
    ENV_TLS_CA,
    ENV_TLS_CERT,
    ENV_TLS_KEY,
    LEGACY_ENV_API_KEY,
    LEGACY_ENV_AUTH_TOKEN,
    LEGACY_ENV_AUTHKEY,
    LEGACY_ENV_HEALTH_BIND,
    LEGACY_ENV_HEALTH_PORT,
    LEGACY_ENV_HEARTBEAT_INTERVAL,
    LEGACY_ENV_MANAGER_HOST,
    LEGACY_ENV_MANAGER_PORT,
    LEGACY_ENV_MP_CONTEXT,
    LEGACY_ENV_NUM_WORKERS,
    LEGACY_ENV_SERVER_URL,
    LEGACY_ENV_TASK_TIMEOUT,
    LEGACY_ENV_TLS_CA,
    LEGACY_ENV_TLS_CERT,
    LEGACY_ENV_TLS_KEY,
)

# ----------------------------------------------------------------------------
# Per-field matrix metadata
# ----------------------------------------------------------------------------
# (canonical_name, legacy_name, attr_on_WorkerConfig, default_value_for_resolve)
#
# 14 unique canonical names. ENV_AUTH_TOKEN has TWO legacy aliases
# (``CASCOR_AUTH_TOKEN`` + ``CASCOR_API_KEY``); it appears once here
# bound to its primary legacy alias. The secondary alias is covered
# in :class:`TestAuthTokenDualLegacy`.
PER_FIELD: list[tuple[str, str, str | None, str | None]] = [
    (ENV_SERVER_URL, LEGACY_ENV_SERVER_URL, "server_url", ""),
    (ENV_AUTH_TOKEN, LEGACY_ENV_AUTH_TOKEN, "auth_token", ""),
    (ENV_HEARTBEAT_INTERVAL, LEGACY_ENV_HEARTBEAT_INTERVAL, "heartbeat_interval", "10.0"),
    (ENV_HEALTH_PORT, LEGACY_ENV_HEALTH_PORT, "health_port", str(DEFAULT_HEALTH_PORT)),
    (ENV_HEALTH_BIND, LEGACY_ENV_HEALTH_BIND, "health_bind", DEFAULT_HEALTH_BIND),
    (ENV_TASK_TIMEOUT, LEGACY_ENV_TASK_TIMEOUT, "task_timeout", str(DEFAULT_TASK_TIMEOUT)),
    (ENV_TLS_CERT, LEGACY_ENV_TLS_CERT, "tls_cert", None),
    (ENV_TLS_KEY, LEGACY_ENV_TLS_KEY, "tls_key", None),
    (ENV_TLS_CA, LEGACY_ENV_TLS_CA, "tls_ca", None),
    (ENV_MANAGER_HOST, LEGACY_ENV_MANAGER_HOST, "manager_host", DEFAULT_MANAGER_HOST),
    (ENV_MANAGER_PORT, LEGACY_ENV_MANAGER_PORT, "manager_port", str(DEFAULT_MANAGER_PORT)),
    (ENV_AUTHKEY, LEGACY_ENV_AUTHKEY, "authkey", ""),
    (ENV_NUM_WORKERS, LEGACY_ENV_NUM_WORKERS, "num_workers", str(DEFAULT_NUM_WORKERS)),
    (ENV_MP_CONTEXT, LEGACY_ENV_MP_CONTEXT, "mp_context", DEFAULT_MP_CONTEXT),
]


@pytest.fixture()
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Delete every canonical + legacy env var so each test starts clean.

    The cascor-worker test environment may inherit ``CASCOR_*`` legacy
    vars from the shell or the conda activation hooks; this fixture
    scrubs them before the test runs.
    """
    for canonical, legacy, _attr, _default in PER_FIELD:
        monkeypatch.delenv(canonical, raising=False)
        monkeypatch.delenv(legacy, raising=False)
    # Dual-legacy second alias.
    monkeypatch.delenv(LEGACY_ENV_API_KEY, raising=False)
    return monkeypatch


# ----------------------------------------------------------------------------
# Per-field matrix — 14 × 4 = 56 cases
# ----------------------------------------------------------------------------


class TestResolveCanonicalOnly:
    """Canonical name set, legacy unset — return canonical, no warning."""

    @pytest.mark.parametrize("canonical,legacy,_attr,default", PER_FIELD)
    def test_returns_canonical_value(self, clean_env, canonical, legacy, _attr, default):
        clean_env.setenv(canonical, "canonical-value")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _resolve(None, canonical, legacy, default)
        assert result == "canonical-value"
        assert [w for w in caught if issubclass(w.category, DeprecationWarning)] == []


class TestResolveLegacyOnly:
    """Legacy alone — return legacy value + emit one DeprecationWarning."""

    @pytest.mark.parametrize("canonical,legacy,_attr,default", PER_FIELD)
    def test_returns_legacy_value(self, clean_env, canonical, legacy, _attr, default):
        clean_env.setenv(legacy, "legacy-value")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _resolve(None, canonical, legacy, default)
        assert result == "legacy-value"
        deprecation = [w for w in caught if issubclass(w.category, DeprecationWarning) and legacy in str(w.message)]
        assert len(deprecation) == 1

    @pytest.mark.parametrize("canonical,legacy,_attr,default", PER_FIELD)
    def test_warning_names_both_envvars(self, clean_env, canonical, legacy, _attr, default):
        clean_env.setenv(legacy, "legacy-value")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _resolve(None, canonical, legacy, default)
        deprecation = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(deprecation) == 1
        msg = str(deprecation[0].message)
        assert canonical in msg, f"canonical {canonical!r} missing from warning: {msg!r}"
        assert legacy in msg, f"legacy {legacy!r} missing from warning: {msg!r}"


class TestResolveBothSet:
    """Both set — canonical wins, no warning."""

    @pytest.mark.parametrize("canonical,legacy,_attr,default", PER_FIELD)
    def test_canonical_wins(self, clean_env, canonical, legacy, _attr, default):
        clean_env.setenv(canonical, "canonical-value")
        clean_env.setenv(legacy, "legacy-value")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _resolve(None, canonical, legacy, default)
        assert result == "canonical-value"
        assert [w for w in caught if issubclass(w.category, DeprecationWarning)] == []


class TestResolveNeitherSet:
    """Neither set — return default, no warning."""

    @pytest.mark.parametrize("canonical,legacy,_attr,default", PER_FIELD)
    def test_returns_default(self, clean_env, canonical, legacy, _attr, default):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _resolve(None, canonical, legacy, default)
        assert result == default
        assert [w for w in caught if issubclass(w.category, DeprecationWarning)] == []


# ----------------------------------------------------------------------------
# ENV_AUTH_TOKEN dual-legacy chain
# ----------------------------------------------------------------------------


class TestAuthTokenDualLegacy:
    """ENV_AUTH_TOKEN has two legacy aliases: CASCOR_AUTH_TOKEN (primary)
    and CASCOR_API_KEY (secondary). Preserves pre-CFG-06 from_env behaviour."""

    def test_canonical_wins_over_both_legacies(self, clean_env):
        clean_env.setenv(ENV_AUTH_TOKEN, "canonical-token")
        clean_env.setenv(LEGACY_ENV_AUTH_TOKEN, "primary-legacy")
        clean_env.setenv(LEGACY_ENV_API_KEY, "secondary-legacy")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            cfg = WorkerConfig.from_env()
        assert cfg.auth_token == "canonical-token"
        # Neither legacy fired because canonical was set.
        assert [w for w in caught if issubclass(w.category, DeprecationWarning)] == []

    def test_primary_legacy_alone_wins(self, clean_env):
        clean_env.setenv(LEGACY_ENV_AUTH_TOKEN, "primary-legacy")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            cfg = WorkerConfig.from_env()
        assert cfg.auth_token == "primary-legacy"
        depmsgs = [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]
        # Exactly one warning naming CASCOR_AUTH_TOKEN; CASCOR_API_KEY
        # is not consulted because the primary legacy provided a value.
        assert any(LEGACY_ENV_AUTH_TOKEN in m for m in depmsgs)
        assert not any(LEGACY_ENV_API_KEY in m for m in depmsgs)

    def test_secondary_legacy_only(self, clean_env):
        clean_env.setenv(LEGACY_ENV_API_KEY, "secondary-legacy")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            cfg = WorkerConfig.from_env()
        assert cfg.auth_token == "secondary-legacy"
        depmsgs = [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]
        # CASCOR_API_KEY warning fires. (Whether CASCOR_AUTH_TOKEN
        # warning also fires depends on chain shape — it might if
        # the empty-string canonical re-check is interpreted as
        # "absent". Just assert the API_KEY one.)
        assert any(LEGACY_ENV_API_KEY in m for m in depmsgs)

    def test_both_legacies_set_primary_wins(self, clean_env):
        clean_env.setenv(LEGACY_ENV_AUTH_TOKEN, "primary-legacy")
        clean_env.setenv(LEGACY_ENV_API_KEY, "secondary-legacy")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            cfg = WorkerConfig.from_env()
        assert cfg.auth_token == "primary-legacy"
        depmsgs = [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]
        # Primary legacy warns; secondary doesn't because primary
        # short-circuited the chain.
        assert any(LEGACY_ENV_AUTH_TOKEN in m for m in depmsgs)


# ----------------------------------------------------------------------------
# from_env(env: Mapping) — test-injection contract
# ----------------------------------------------------------------------------


class TestFromEnvMappingInjection:
    """``WorkerConfig.from_env(env: Mapping)`` reads from the explicit
    mapping rather than ``os.environ`` (Open Q §10.4 resolution)."""

    def test_explicit_mapping_replaces_os_environ(self, clean_env):
        # os.environ has neither canonical nor legacy set (clean_env);
        # the injected mapping provides values.
        cfg = WorkerConfig.from_env(
            env={
                ENV_SERVER_URL: "ws://injected:8200/ws/v1/workers",
                ENV_AUTHKEY: "injected-key",
                ENV_NUM_WORKERS: "4",
            }
        )
        assert cfg.server_url == "ws://injected:8200/ws/v1/workers"
        assert cfg.authkey == "injected-key"
        assert cfg.num_workers == 4

    def test_explicit_mapping_does_not_read_os_environ(self, clean_env):
        # Put a contradicting value in os.environ; the explicit mapping
        # must win.
        clean_env.setenv(ENV_SERVER_URL, "ws://os-environ:8200/")
        cfg = WorkerConfig.from_env(env={ENV_SERVER_URL: "ws://injected:8200/"})
        assert cfg.server_url == "ws://injected:8200/"

    def test_explicit_mapping_legacy_still_warns(self, clean_env):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            cfg = WorkerConfig.from_env(env={LEGACY_ENV_SERVER_URL: "ws://legacy:8200/"})
        assert cfg.server_url == "ws://legacy:8200/"
        assert any(issubclass(w.category, DeprecationWarning) and LEGACY_ENV_SERVER_URL in str(w.message) for w in caught)

    def test_empty_mapping_returns_all_defaults(self, clean_env):
        cfg = WorkerConfig.from_env(env={})
        assert cfg.server_url == ""
        assert cfg.heartbeat_interval == DEFAULT_HEARTBEAT_INTERVAL
        assert cfg.task_timeout == DEFAULT_TASK_TIMEOUT
        assert cfg.manager_host == DEFAULT_MANAGER_HOST
        assert cfg.manager_port == DEFAULT_MANAGER_PORT
        assert cfg.authkey == ""
        assert cfg.num_workers == DEFAULT_NUM_WORKERS
        assert cfg.mp_context == DEFAULT_MP_CONTEXT

    def test_default_env_none_reads_os_environ(self, clean_env):
        clean_env.setenv(ENV_SERVER_URL, "ws://os-environ:8200/")
        cfg = WorkerConfig.from_env()  # env=None default
        assert cfg.server_url == "ws://os-environ:8200/"


# ----------------------------------------------------------------------------
# Integration smoke — mixed canonical + legacy
# ----------------------------------------------------------------------------


class TestIntegrationSmoke:
    """End-to-end across multiple fields with mixed canonical + legacy."""

    def test_mixed_env_state_resolves_correctly(self, clean_env):
        clean_env.setenv(ENV_SERVER_URL, "ws://canonical:8200/ws/v1/workers")  # canonical
        clean_env.setenv(LEGACY_ENV_AUTH_TOKEN, "legacy-token")  # legacy
        clean_env.setenv(ENV_HEARTBEAT_INTERVAL, "5.0")  # canonical
        clean_env.setenv(LEGACY_ENV_HEALTH_PORT, "9999")  # legacy
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            cfg = WorkerConfig.from_env()
        assert cfg.server_url == "ws://canonical:8200/ws/v1/workers"
        assert cfg.auth_token == "legacy-token"
        assert cfg.heartbeat_interval == 5.0
        assert cfg.health_port == 9999
        # Two legacy warnings, one each.
        depmsgs = [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]
        assert any(LEGACY_ENV_AUTH_TOKEN in m for m in depmsgs)
        assert any(LEGACY_ENV_HEALTH_PORT in m for m in depmsgs)


# ----------------------------------------------------------------------------
# Source-level scope guard
# ----------------------------------------------------------------------------


def _strip_comments_and_docstrings(source: str) -> str:
    """Drop comment lines and triple-quoted docstring blocks so the
    scope guard only fires on executable references to the env vars.
    Mirrors the CFG-16 guard helper.
    """
    # Triple-quoted strings (greedy across newlines).
    no_docstrings = re.sub(r'"""[\s\S]*?"""', "", source)
    no_docstrings = re.sub(r"'''[\s\S]*?'''", "", no_docstrings)
    # Drop full-line comments.
    lines = [line for line in no_docstrings.splitlines() if not line.lstrip().startswith("#")]
    return "\n".join(lines)


class TestSourceScopeGuard:
    """``config.py`` and ``cli.py`` must not read legacy env-var names
    via raw ``os.getenv``/``os.environ.get``. They must go through
    :func:`juniper_config_tools.env_with_legacy_alias` (cli) or
    :func:`juniper_cascor_worker.config._resolve` (config)."""

    def test_config_module_has_no_raw_legacy_env_reads(self):
        from juniper_cascor_worker import config as config_module

        executable = _strip_comments_and_docstrings(inspect.getsource(config_module))
        # Match os.getenv("CASCOR_…") or os.environ.get("CASCOR_…")
        bad = re.findall(r'os\.(?:getenv|environ\.get)\(["\']CASCOR_', executable)
        assert bad == [], f"config.py reintroduced raw legacy env reads: {bad!r}; " f"use _resolve(env, ENV_X, LEGACY_ENV_X, default) instead."

    def test_cli_module_has_no_raw_legacy_env_reads(self):
        from juniper_cascor_worker import cli as cli_module

        executable = _strip_comments_and_docstrings(inspect.getsource(cli_module))
        bad = re.findall(r'os\.(?:getenv|environ\.get)\(["\']CASCOR_', executable)
        assert bad == [], f"cli.py reintroduced raw legacy env reads: {bad!r}; " f"use env_with_legacy_alias(ENV_X, LEGACY_ENV_X, default) instead."


# ----------------------------------------------------------------------------
# No-pydantic-at-runtime invariant — CFG-06 must not regress
# ----------------------------------------------------------------------------


class TestNoPydanticAtRuntimeAfterCfg06:
    """Importing config.py (or cli.py) after the CFG-06 changes must
    still leave ``pydantic`` out of ``sys.modules``. juniper-config-tools
    is stdlib-only, so this should hold by construction — but pin it
    explicitly so a future refactor that adds a pydantic-bringing
    helper to juniper-config-tools fails loudly."""

    @pytest.mark.unit
    def test_config_import_does_not_load_pydantic(self):
        code = "import sys, juniper_cascor_worker.config;" "assert 'pydantic' not in sys.modules, sorted(m for m in sys.modules if 'pydantic' in m)"
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)  # nosec B603
        assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"

    @pytest.mark.unit
    def test_cli_import_does_not_load_pydantic(self):
        code = "import sys, juniper_cascor_worker.cli;" "assert 'pydantic' not in sys.modules, sorted(m for m in sys.modules if 'pydantic' in m)"
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)  # nosec B603
        assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"

    @pytest.mark.unit
    def test_juniper_config_tools_import_does_not_load_pydantic(self):
        code = "import sys, juniper_config_tools;" "assert 'pydantic' not in sys.modules, sorted(m for m in sys.modules if 'pydantic' in m)"
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)  # nosec B603
        assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
