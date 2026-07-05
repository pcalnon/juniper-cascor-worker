"""Regression tests for ``_FILE``-suffix indirection in
``juniper_cascor_worker.config._resolve``.

Closes the gap that left worker → cascor auth silently broken under
``juniper-deploy``'s DEPLOY-09 hardening: the compose worker block sets
``CASCOR_AUTH_TOKEN_FILE=/run/secrets/cascor_auth_token`` and mounts the
secret file, but the pre-fix ``_resolve`` only read env-var **values**,
ignoring the ``_FILE`` indirection. Worker booted with ``auth_token=""``,
which combined with the empty placeholder cascor api_keys file gave the
appearance of "auth works" — it was actually "auth disabled both sides."

Properties pinned:

1. Canonical ``<name>_FILE`` wins over direct ``<name>``.
2. Missing or empty file falls through silently (no exception, no
   warning) to direct env var or default.
3. Legacy ``<name>_FILE`` emits one ``DeprecationWarning`` naming
   both legacy and canonical ``_FILE`` vars.
4. Direct legacy resolution still emits the original warning shape
   (regression: don't break the existing CFG-06 warning text).
5. File content is ``strip()``-ed (matches the docker-secrets / k8s
   secrets convention where files end with a trailing newline).
6. Production path (``env is None`` → reads ``os.environ``) honors
   ``_FILE`` identically to the test-injection path.
7. ``WorkerConfig.from_env`` end-to-end: ``CASCOR_AUTH_TOKEN_FILE``
   resolves the worker's ``auth_token`` (the original bug surface).
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Iterator

import pytest

from juniper_cascor_worker.config import WorkerConfig, _resolve
from juniper_cascor_worker.constants import (
    ENV_AUTH_TOKEN,
    ENV_AUTHKEY,
    ENV_SERVER_URL,
    LEGACY_ENV_API_KEY,
    LEGACY_ENV_AUTH_TOKEN,
    LEGACY_ENV_AUTHKEY,
    LEGACY_ENV_SERVER_URL,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def secret_file(tmp_path: Path) -> Path:
    """Path to a freshly-written secret file containing one token."""
    path = tmp_path / "secret.txt"
    path.write_text("MySecretToken123\n", encoding="utf-8")
    return path


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    """Strip every canonical + legacy + ``_FILE`` variant of the env-vars
    this module touches, so tests don't inherit shell / conda state.
    """
    for name in (
        ENV_AUTH_TOKEN,
        ENV_AUTHKEY,
        ENV_SERVER_URL,
        LEGACY_ENV_API_KEY,
        LEGACY_ENV_AUTH_TOKEN,
        LEGACY_ENV_AUTHKEY,
        LEGACY_ENV_SERVER_URL,
        f"{ENV_AUTH_TOKEN}_FILE",
        f"{ENV_AUTHKEY}_FILE",
        f"{ENV_SERVER_URL}_FILE",
        f"{LEGACY_ENV_API_KEY}_FILE",
        f"{LEGACY_ENV_AUTH_TOKEN}_FILE",
        f"{LEGACY_ENV_AUTHKEY}_FILE",
        f"{LEGACY_ENV_SERVER_URL}_FILE",
    ):
        monkeypatch.delenv(name, raising=False)
    yield monkeypatch


# ---------------------------------------------------------------------------
# Canonical ``<name>_FILE`` path
# ---------------------------------------------------------------------------


class TestCanonicalFileIndirection:
    def test_file_value_returned(self, secret_file: Path) -> None:
        env = {f"{ENV_AUTH_TOKEN}_FILE": str(secret_file)}
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _resolve(env, ENV_AUTH_TOKEN, LEGACY_ENV_AUTH_TOKEN, default="")
        assert result == "MySecretToken123"
        assert [w for w in caught if issubclass(w.category, DeprecationWarning)] == []

    def test_file_content_stripped(self, tmp_path: Path) -> None:
        """Docker-secrets / k8s secrets convention: files end with `\\n`."""
        path = tmp_path / "secret.txt"
        path.write_text("  spaced-token  \r\n", encoding="utf-8")
        env = {f"{ENV_AUTH_TOKEN}_FILE": str(path)}
        assert _resolve(env, ENV_AUTH_TOKEN, LEGACY_ENV_AUTH_TOKEN, default="") == "spaced-token"

    def test_file_wins_over_direct(self, secret_file: Path) -> None:
        """_FILE precedence is the entire point of DEPLOY-09."""
        env = {
            f"{ENV_AUTH_TOKEN}_FILE": str(secret_file),
            ENV_AUTH_TOKEN: "direct-value-should-be-ignored",
        }
        assert _resolve(env, ENV_AUTH_TOKEN, LEGACY_ENV_AUTH_TOKEN, default="") == "MySecretToken123"

    def test_missing_file_falls_through_to_direct(self, tmp_path: Path) -> None:
        env = {
            f"{ENV_AUTH_TOKEN}_FILE": str(tmp_path / "nonexistent.txt"),
            ENV_AUTH_TOKEN: "direct-fallback",
        }
        assert _resolve(env, ENV_AUTH_TOKEN, LEGACY_ENV_AUTH_TOKEN, default="") == "direct-fallback"

    def test_missing_file_falls_through_to_default(self, tmp_path: Path) -> None:
        env = {f"{ENV_AUTH_TOKEN}_FILE": str(tmp_path / "nonexistent.txt")}
        assert _resolve(env, ENV_AUTH_TOKEN, LEGACY_ENV_AUTH_TOKEN, default="default-value") == "default-value"

    def test_empty_file_falls_through(self, tmp_path: Path) -> None:
        """An empty/whitespace file is treated as 'not set' so an
        un-populated Docker secret doesn't silently disable a feature.
        """
        path = tmp_path / "empty.txt"
        path.write_text("\n   \n", encoding="utf-8")
        env = {
            f"{ENV_AUTH_TOKEN}_FILE": str(path),
            ENV_AUTH_TOKEN: "direct-fallback",
        }
        assert _resolve(env, ENV_AUTH_TOKEN, LEGACY_ENV_AUTH_TOKEN, default="") == "direct-fallback"


# ---------------------------------------------------------------------------
# Legacy ``<legacy_name>_FILE`` path — the production-bug-fix scenario
# ---------------------------------------------------------------------------


class TestLegacyFileIndirection:
    def test_legacy_file_resolves_with_warning(self, secret_file: Path) -> None:
        """The juniper-deploy compose scenario: only ``CASCOR_AUTH_TOKEN_FILE``
        is set (DEPLOY-09 hardening), no canonical, no direct legacy."""
        env = {f"{LEGACY_ENV_AUTH_TOKEN}_FILE": str(secret_file)}
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _resolve(env, ENV_AUTH_TOKEN, LEGACY_ENV_AUTH_TOKEN, default="")
        assert result == "MySecretToken123"
        deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(deprecations) == 1
        message = str(deprecations[0].message)
        assert f"{LEGACY_ENV_AUTH_TOKEN}_FILE" in message
        assert f"{ENV_AUTH_TOKEN}_FILE" in message

    def test_legacy_direct_still_emits_original_warning(self) -> None:
        """Regression: don't break the existing CFG-06 warning shape for
        non-_FILE legacy env vars."""
        env = {LEGACY_ENV_AUTH_TOKEN: "legacy-direct"}
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _resolve(env, ENV_AUTH_TOKEN, LEGACY_ENV_AUTH_TOKEN, default="")
        assert result == "legacy-direct"
        deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(deprecations) == 1
        # The "X is deprecated; use Y instead." shape, no _FILE suffix.
        assert "_FILE" not in str(deprecations[0].message)
        assert LEGACY_ENV_AUTH_TOKEN in str(deprecations[0].message)
        assert ENV_AUTH_TOKEN in str(deprecations[0].message)

    def test_canonical_file_beats_legacy_file(self, tmp_path: Path) -> None:
        canonical_path = tmp_path / "canonical.txt"
        canonical_path.write_text("canonical-value\n", encoding="utf-8")
        legacy_path = tmp_path / "legacy.txt"
        legacy_path.write_text("legacy-value\n", encoding="utf-8")
        env = {
            f"{ENV_AUTH_TOKEN}_FILE": str(canonical_path),
            f"{LEGACY_ENV_AUTH_TOKEN}_FILE": str(legacy_path),
        }
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _resolve(env, ENV_AUTH_TOKEN, LEGACY_ENV_AUTH_TOKEN, default="")
        assert result == "canonical-value"
        assert [w for w in caught if issubclass(w.category, DeprecationWarning)] == []


# ---------------------------------------------------------------------------
# Production path (``env is None`` → ``os.environ``)
# ---------------------------------------------------------------------------


class TestProductionPath:
    def test_production_honors_canonical_file(self, clean_env: pytest.MonkeyPatch, secret_file: Path) -> None:
        clean_env.setenv(f"{ENV_AUTH_TOKEN}_FILE", str(secret_file))
        assert _resolve(None, ENV_AUTH_TOKEN, LEGACY_ENV_AUTH_TOKEN, default="") == "MySecretToken123"

    def test_production_honors_legacy_file_with_warning(self, clean_env: pytest.MonkeyPatch, secret_file: Path) -> None:
        clean_env.setenv(f"{LEGACY_ENV_AUTH_TOKEN}_FILE", str(secret_file))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = _resolve(None, ENV_AUTH_TOKEN, LEGACY_ENV_AUTH_TOKEN, default="")
        assert result == "MySecretToken123"
        assert any(issubclass(w.category, DeprecationWarning) and f"{LEGACY_ENV_AUTH_TOKEN}_FILE" in str(w.message) for w in caught)


# ---------------------------------------------------------------------------
# End-to-end via ``WorkerConfig.from_env``
# ---------------------------------------------------------------------------


class TestWorkerConfigFromEnv:
    def test_auth_token_from_legacy_file(self, secret_file: Path) -> None:
        """The exact juniper-deploy compose scenario that surfaced this gap:
        only ``CASCOR_AUTH_TOKEN_FILE`` is set, and ``WorkerConfig.from_env``
        must load the token value (not ``""``).
        """
        env = {
            ENV_SERVER_URL: "ws://juniper-cascor:8200/ws/v1/workers",
            f"{LEGACY_ENV_AUTH_TOKEN}_FILE": str(secret_file),
        }
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            cfg = WorkerConfig.from_env(env)
        assert cfg.auth_token == "MySecretToken123"
        assert cfg.server_url == "ws://juniper-cascor:8200/ws/v1/workers"

    def test_auth_token_from_canonical_file(self, secret_file: Path) -> None:
        env = {
            ENV_SERVER_URL: "ws://juniper-cascor:8200/ws/v1/workers",
            f"{ENV_AUTH_TOKEN}_FILE": str(secret_file),
        }
        cfg = WorkerConfig.from_env(env)
        assert cfg.auth_token == "MySecretToken123"

    def test_auth_token_empty_when_no_source_set(self) -> None:
        """Sanity: regression of the original behaviour for the
        "no auth configured" path (empty string default)."""
        env = {ENV_SERVER_URL: "ws://juniper-cascor:8200/ws/v1/workers"}
        cfg = WorkerConfig.from_env(env)
        assert cfg.auth_token == ""


# ---------------------------------------------------------------------------
# Defensive coverage for the helper boundary
# ---------------------------------------------------------------------------


class TestSecretFileHelper:
    """Direct exercises of ``_read_secret_file`` via _resolve to keep its
    error-swallowing contract pinned (no exception escapes; missing/
    unreadable/empty all behave identically)."""

    def test_directory_instead_of_file_falls_through(self, tmp_path: Path) -> None:
        env = {
            f"{ENV_AUTH_TOKEN}_FILE": str(tmp_path),  # a directory, not a file
            ENV_AUTH_TOKEN: "direct-fallback",
        }
        assert _resolve(env, ENV_AUTH_TOKEN, LEGACY_ENV_AUTH_TOKEN, default="") == "direct-fallback"

    def test_unreadable_file_falls_through(self, tmp_path: Path) -> None:
        path = tmp_path / "unreadable.txt"
        path.write_text("secret-content\n", encoding="utf-8")
        path.chmod(0o000)
        try:
            env = {
                f"{ENV_AUTH_TOKEN}_FILE": str(path),
                ENV_AUTH_TOKEN: "direct-fallback",
            }
            # Skip when running as root — root can read 0o000 files
            if os.geteuid() == 0:
                pytest.skip("running as root: 0o000 not honored")
            assert _resolve(env, ENV_AUTH_TOKEN, LEGACY_ENV_AUTH_TOKEN, default="") == "direct-fallback"
        finally:
            path.chmod(0o600)  # so pytest tmp_path cleanup can remove it


# ---------------------------------------------------------------------------
# End-to-end via ``cli.main()`` — the production code path
# ---------------------------------------------------------------------------


class TestCliFileIndirection:
    """The production bug surface — ``cli.py:_run_websocket`` was calling
    ``env_with_legacy_alias`` directly (no ``_FILE`` support) even after
    ``config._resolve`` got the suffix fix. These tests pin that the CLI
    now resolves ``CASCOR_AUTH_TOKEN_FILE`` through ``_resolve`` so
    Docker-secrets-style indirection works at the production entry point,
    not just inside ``WorkerConfig.from_env``.
    """

    def _build_args(self) -> "object":  # noqa: ANN001
        from unittest.mock import MagicMock

        mock_args = MagicMock()
        mock_args.legacy = False
        mock_args.cascor_path = None
        mock_args.log_level = "WARNING"
        mock_args.server_url = None
        mock_args.auth_token = None
        mock_args.heartbeat_interval = 10.0
        mock_args.task_timeout = 3600.0
        mock_args.tls_cert = None
        mock_args.tls_key = None
        mock_args.tls_ca = None
        return mock_args

    def _fake_agent_factory(self) -> "tuple[type, list]":  # noqa: ANN001
        captured_config: list = []

        class _FakeAgent:
            def __init__(self, config) -> None:  # type: ignore[no-untyped-def]
                captured_config.append(config)

            def stop(self) -> None:
                pass

            async def run(self) -> None:
                return

        return _FakeAgent, captured_config

    def _drive_run_websocket(
        self,
        clean_env: pytest.MonkeyPatch,
        secret_file: Path,
        env_var_name: str,
    ) -> "object":
        """Drive ``_run_websocket`` with a fake agent + mocked signal /
        asyncio plumbing so no real event loop or signal handler leaks
        into adjacent tests."""
        from unittest.mock import patch

        from juniper_cascor_worker.cli import _run_websocket

        clean_env.setenv(ENV_SERVER_URL, "ws://juniper-cascor:8200/ws/v1/workers")
        clean_env.setenv(env_var_name, str(secret_file))

        fake_agent_cls, captured = self._fake_agent_factory()

        with patch("juniper_cascor_worker.worker.CascorWorkerAgent", fake_agent_cls), patch("juniper_cascor_worker.cli.signal.signal"), patch("juniper_cascor_worker.cli.asyncio.run"):
            _run_websocket(self._build_args())

        assert captured, "_run_websocket never reached WorkerConfig construction"
        return captured[0]

    def test_run_websocket_loads_auth_token_from_legacy_file(
        self,
        clean_env: pytest.MonkeyPatch,
        secret_file: Path,
    ) -> None:
        """The exact juniper-deploy DEPLOY-09 scenario."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            config = self._drive_run_websocket(clean_env, secret_file, f"{LEGACY_ENV_AUTH_TOKEN}_FILE")
        assert config.auth_token == "MySecretToken123", (  # type: ignore[attr-defined]
            f"cli.py did not honor {LEGACY_ENV_AUTH_TOKEN}_FILE: "
            f"got auth_token={config.auth_token!r}"  # type: ignore[attr-defined]
        )
        assert config.server_url == "ws://juniper-cascor:8200/ws/v1/workers"  # type: ignore[attr-defined]

    def test_run_websocket_loads_auth_token_from_canonical_file(
        self,
        clean_env: pytest.MonkeyPatch,
        secret_file: Path,
    ) -> None:
        """Canonical ``JUNIPER_CASCOR_WORKER_AUTH_TOKEN_FILE`` shape — no
        deprecation warning expected."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            config = self._drive_run_websocket(clean_env, secret_file, f"{ENV_AUTH_TOKEN}_FILE")

        assert config.auth_token == "MySecretToken123"  # type: ignore[attr-defined]
        # Canonical `_FILE` — no DeprecationWarning expected.
        assert [w for w in caught if issubclass(w.category, DeprecationWarning)] == []

    def test_run_websocket_loads_auth_token_from_api_key_file(
        self,
        clean_env: pytest.MonkeyPatch,
        secret_file: Path,
    ) -> None:
        """The secondary legacy alias participates in the same Docker-secrets
        indirection chain as ``CASCOR_AUTH_TOKEN_FILE``.
        """
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            config = self._drive_run_websocket(clean_env, secret_file, f"{LEGACY_ENV_API_KEY}_FILE")

        assert config.auth_token == "MySecretToken123"  # type: ignore[attr-defined]
        assert config.server_url == "ws://juniper-cascor:8200/ws/v1/workers"  # type: ignore[attr-defined]


class TestCliLegacyFileIndirection:
    """Pin ``cli.py:_run_legacy`` to the same ``_FILE`` resolution contract
    as WebSocket mode so Docker-secret authkeys work at the entry point.
    """

    def _build_args(self) -> "object":  # noqa: ANN001
        from unittest.mock import MagicMock

        mock_args = MagicMock()
        mock_args.manager_host = "127.0.0.1"
        mock_args.manager_port = 50000
        mock_args.authkey = None
        mock_args.workers = 1
        mock_args.mp_context = "forkserver"
        return mock_args

    def _fake_worker_factory(self) -> "tuple[type, list]":  # noqa: ANN001
        captured_config: list = []

        class _FakeWorker:
            def __init__(self, config) -> None:  # type: ignore[no-untyped-def]
                captured_config.append(config)

            def connect(self) -> None:
                pass

            def start(self) -> None:
                pass

            def disconnect(self) -> None:
                pass

        return _FakeWorker, captured_config

    def _drive_run_legacy(
        self,
        clean_env: pytest.MonkeyPatch,
        secret_file: Path,
        env_var_name: str,
    ) -> "object":
        from unittest.mock import MagicMock, patch

        from juniper_cascor_worker.cli import _run_legacy

        clean_env.setenv(env_var_name, str(secret_file))
        fake_worker_cls, captured = self._fake_worker_factory()
        fake_event = MagicMock()
        fake_event.wait.return_value = None

        with patch("juniper_cascor_worker.worker.CandidateTrainingWorker", fake_worker_cls), patch("juniper_cascor_worker.cli.signal.signal"), patch("juniper_cascor_worker.cli.threading.Event", return_value=fake_event):
            _run_legacy(self._build_args())

        assert captured, "_run_legacy never reached WorkerConfig construction"
        return captured[0]

    def test_run_legacy_loads_authkey_from_legacy_file(
        self,
        clean_env: pytest.MonkeyPatch,
        secret_file: Path,
    ) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            config = self._drive_run_legacy(clean_env, secret_file, f"{LEGACY_ENV_AUTHKEY}_FILE")

        assert config.authkey == "MySecretToken123"  # type: ignore[attr-defined]

    def test_run_legacy_loads_authkey_from_canonical_file(
        self,
        clean_env: pytest.MonkeyPatch,
        secret_file: Path,
    ) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            config = self._drive_run_legacy(clean_env, secret_file, f"{ENV_AUTHKEY}_FILE")

        assert config.authkey == "MySecretToken123"  # type: ignore[attr-defined]
        assert [w for w in caught if issubclass(w.category, DeprecationWarning)] == []
