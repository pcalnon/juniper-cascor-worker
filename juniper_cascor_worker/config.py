"""Configuration for the remote candidate training worker."""

import warnings
from dataclasses import dataclass
from typing import Mapping

from juniper_config_tools import env_with_legacy_alias

from juniper_cascor_worker.constants import (
    DEFAULT_HEALTH_BIND,
    DEFAULT_HEALTH_PORT,
    DEFAULT_HEARTBEAT_INTERVAL,
    DEFAULT_MANAGER_HOST,
    DEFAULT_MANAGER_PORT,
    DEFAULT_MP_CONTEXT,
    DEFAULT_NUM_WORKERS,
    DEFAULT_RECONNECT_BACKOFF_BASE,
    DEFAULT_RECONNECT_BACKOFF_MAX,
    DEFAULT_STOP_TIMEOUT,
    DEFAULT_TASK_QUEUE_TIMEOUT,
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
    MAX_PORT,
    MIN_NUM_WORKERS,
    MIN_PORT,
    VALID_MP_CONTEXTS,
    VALID_WS_SCHEMES,
)
from juniper_cascor_worker.exceptions import WorkerConfigError


def _resolve(
    env: Mapping[str, str] | None,
    new_name: str,
    legacy_name: str | None,
    default: str | None = None,
) -> str | None:
    """Resolve an env var via canonical/legacy/default chain.

    Production path (``env is None``) delegates to
    :func:`juniper_config_tools.env_with_legacy_alias`, which reads
    :data:`os.environ`. Test-injection path (``env`` provided) uses an
    inline mapping-aware resolver that mirrors the helper's semantics
    (same warning text, same ``stacklevel=2``, same once-per-location
    behaviour). Both paths emit one :class:`DeprecationWarning` when
    only the legacy name is set.

    The duplication is deliberate: the shared
    :mod:`juniper_config_tools` 0.1.0 helper reads :data:`os.environ`
    directly and a future 0.2.0 will likely add an ``env`` kwarg —
    when that happens, this adapter can collapse to a single
    delegation. Until then the local copy avoids forcing every
    cascor-worker consumer onto a moving juniper-config-tools floor.
    """
    if env is None:
        return env_with_legacy_alias(new_name, legacy_name, default)
    val = env.get(new_name)
    if val is not None:
        return val
    if legacy_name is not None:
        legacy_val = env.get(legacy_name)
        if legacy_val is not None:
            warnings.warn(
                f"{legacy_name} is deprecated; use {new_name} instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            return legacy_val
    return default


@dataclass
class WorkerConfig:
    """Configuration for connecting to a CasCor training service.

    Supports two modes:
    - **WebSocket mode** (default): Set ``server_url`` to connect via WebSocket.
    - **Legacy mode** (``--legacy``): Set ``manager_host``/``manager_port``/``authkey``
      to connect via the deprecated BaseManager path.

    Attributes:
        server_url: WebSocket URL (e.g., ``ws://host:8200/ws/v1/workers``).
        auth_token: Auth token for ``X-API-Key`` header authentication.
        heartbeat_interval: Seconds between heartbeat messages.
        reconnect_backoff_base: Initial reconnection delay in seconds.
        reconnect_backoff_max: Maximum reconnection delay in seconds.
        task_timeout: Maximum seconds for a single training task (default: 3600).
        tls_cert: Client certificate path (for mTLS, Phase 4).
        tls_key: Client key path (for mTLS, Phase 4).
        tls_ca: CA certificate path (for mTLS, Phase 4).
        manager_host: Legacy — hostname of the remote CandidateTrainingManager.
        manager_port: Legacy — port of the remote CandidateTrainingManager.
        authkey: Legacy — authentication key for the manager connection.
        num_workers: Number of local worker processes to spawn (legacy mode).
        task_queue_timeout: Timeout (seconds) for polling the task queue (legacy).
        stop_timeout: Timeout (seconds) for graceful worker shutdown (legacy).
        mp_context: Multiprocessing start method (legacy).
    """

    # WebSocket mode configuration
    server_url: str = ""
    auth_token: str = ""
    heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL
    reconnect_backoff_base: float = DEFAULT_RECONNECT_BACKOFF_BASE
    reconnect_backoff_max: float = DEFAULT_RECONNECT_BACKOFF_MAX
    task_timeout: float = DEFAULT_TASK_TIMEOUT
    tls_cert: str | None = None
    tls_key: str | None = None
    tls_ca: str | None = None

    # METRICS-MON R1.3 / seed-04: HTTP health server. Localhost-only by
    # default to avoid exposing the probe surface unintentionally; set
    # CASCOR_WORKER_HEALTH_BIND=0.0.0.0 explicitly when running under k8s
    # so httpGet probes from kubelet reach it.
    health_port: int = DEFAULT_HEALTH_PORT
    health_bind: str = DEFAULT_HEALTH_BIND

    # Legacy BaseManager configuration
    manager_host: str = DEFAULT_MANAGER_HOST
    manager_port: int = DEFAULT_MANAGER_PORT
    authkey: str = ""
    num_workers: int = DEFAULT_NUM_WORKERS
    task_queue_timeout: float = DEFAULT_TASK_QUEUE_TIMEOUT
    stop_timeout: int = DEFAULT_STOP_TIMEOUT
    mp_context: str = DEFAULT_MP_CONTEXT

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "WorkerConfig":
        """Create config from environment variables.

        Args:
            env: Optional explicit env Mapping (typically used by tests).
                When ``None`` (the default), reads from :data:`os.environ`
                via :func:`juniper_config_tools.env_with_legacy_alias`.
                When provided, reads from the mapping via the local
                :func:`_resolve` adapter. Both paths emit a single
                :class:`DeprecationWarning` per legacy var consulted.

        Canonical env vars (WebSocket mode):
            JUNIPER_CASCOR_WORKER_SERVER_URL: WebSocket URL
            JUNIPER_CASCOR_WORKER_AUTH_TOKEN: API key for authentication
            JUNIPER_CASCOR_WORKER_HEARTBEAT_INTERVAL: Heartbeat interval (s)
            JUNIPER_CASCOR_WORKER_TASK_TIMEOUT: Per-task timeout (s)
            JUNIPER_CASCOR_WORKER_TLS_CERT: Client certificate path
            JUNIPER_CASCOR_WORKER_TLS_KEY: Client key path
            JUNIPER_CASCOR_WORKER_TLS_CA: CA certificate path
            JUNIPER_CASCOR_WORKER_HEALTH_PORT: Health probe port
            JUNIPER_CASCOR_WORKER_HEALTH_BIND: Health probe bind address

        Canonical env vars (Legacy mode):
            JUNIPER_CASCOR_WORKER_MANAGER_HOST: Manager hostname
            JUNIPER_CASCOR_WORKER_MANAGER_PORT: Manager port
            JUNIPER_CASCOR_WORKER_AUTHKEY: Authentication key (required)
            JUNIPER_CASCOR_WORKER_NUM_WORKERS: Number of workers
            JUNIPER_CASCOR_WORKER_MP_CONTEXT: Multiprocessing context

        Legacy ``CASCOR_*`` and ``CASCOR_WORKER_*`` env vars from
        pre-CFG-06 deployments still work; each emits one
        :class:`DeprecationWarning` per process. ``JUNIPER_CASCOR_WORKER_
        AUTH_TOKEN`` has two legacy aliases (``CASCOR_AUTH_TOKEN`` and
        ``CASCOR_API_KEY``) — the dual-fallback chain from pre-CFG-06
        is preserved.
        """
        # ENV_AUTH_TOKEN has TWO legacy aliases; chain canonical-only
        # first, then each legacy in turn. Python ``or`` short-circuits
        # on truthy values; the second + third calls re-check the
        # (cheap) canonical lookup, so only the legacy each is targeting
        # ends up emitting at most one warning.
        auth_token = _resolve(env, ENV_AUTH_TOKEN, None) or _resolve(env, ENV_AUTH_TOKEN, LEGACY_ENV_AUTH_TOKEN) or _resolve(env, ENV_AUTH_TOKEN, LEGACY_ENV_API_KEY, "")
        return cls(
            server_url=_resolve(env, ENV_SERVER_URL, LEGACY_ENV_SERVER_URL, ""),
            auth_token=auth_token,
            heartbeat_interval=float(_resolve(env, ENV_HEARTBEAT_INTERVAL, LEGACY_ENV_HEARTBEAT_INTERVAL, str(DEFAULT_HEARTBEAT_INTERVAL))),
            task_timeout=float(_resolve(env, ENV_TASK_TIMEOUT, LEGACY_ENV_TASK_TIMEOUT, str(DEFAULT_TASK_TIMEOUT))),
            tls_cert=_resolve(env, ENV_TLS_CERT, LEGACY_ENV_TLS_CERT),
            tls_key=_resolve(env, ENV_TLS_KEY, LEGACY_ENV_TLS_KEY),
            tls_ca=_resolve(env, ENV_TLS_CA, LEGACY_ENV_TLS_CA),
            health_port=int(_resolve(env, ENV_HEALTH_PORT, LEGACY_ENV_HEALTH_PORT, str(DEFAULT_HEALTH_PORT))),
            health_bind=_resolve(env, ENV_HEALTH_BIND, LEGACY_ENV_HEALTH_BIND, DEFAULT_HEALTH_BIND),
            manager_host=_resolve(env, ENV_MANAGER_HOST, LEGACY_ENV_MANAGER_HOST, DEFAULT_MANAGER_HOST),
            manager_port=int(_resolve(env, ENV_MANAGER_PORT, LEGACY_ENV_MANAGER_PORT, str(DEFAULT_MANAGER_PORT))),
            authkey=_resolve(env, ENV_AUTHKEY, LEGACY_ENV_AUTHKEY, ""),
            num_workers=int(_resolve(env, ENV_NUM_WORKERS, LEGACY_ENV_NUM_WORKERS, str(DEFAULT_NUM_WORKERS))),
            mp_context=_resolve(env, ENV_MP_CONTEXT, LEGACY_ENV_MP_CONTEXT, DEFAULT_MP_CONTEXT),
        )

    def validate(self, legacy: bool = False) -> None:
        """Validate configuration values.

        Args:
            legacy: If True, validate for legacy BaseManager mode.
                    If False, validate for WebSocket mode.
        """
        if legacy:
            if not self.authkey:
                raise WorkerConfigError(f"authkey is required — set {ENV_AUTHKEY} or pass --authkey")
            if self.num_workers < MIN_NUM_WORKERS:
                raise WorkerConfigError(f"num_workers must be >= {MIN_NUM_WORKERS}, got {self.num_workers}")
            if self.manager_port < MIN_PORT or self.manager_port > MAX_PORT:
                raise WorkerConfigError(f"manager_port must be {MIN_PORT}-{MAX_PORT}, got {self.manager_port}")
            if self.mp_context not in VALID_MP_CONTEXTS:
                raise WorkerConfigError(f"Invalid mp_context: {self.mp_context}")
        else:
            if not self.server_url:
                raise WorkerConfigError(f"server_url is required — set {ENV_SERVER_URL} or pass --server-url")
            if not self.server_url.startswith(VALID_WS_SCHEMES):
                raise WorkerConfigError(f"server_url must start with ws:// or wss://, got: {self.server_url}")
            if self.heartbeat_interval <= 0:
                raise WorkerConfigError(f"heartbeat_interval must be > 0, got {self.heartbeat_interval}")
            if self.reconnect_backoff_base <= 0:
                raise WorkerConfigError(f"reconnect_backoff_base must be > 0, got {self.reconnect_backoff_base}")
            if self.task_timeout <= 0:
                raise WorkerConfigError(f"task_timeout must be > 0, got {self.task_timeout}")
            if self.health_port < MIN_PORT or self.health_port > MAX_PORT:
                raise WorkerConfigError(f"health_port must be {MIN_PORT}-{MAX_PORT}, got {self.health_port}")
            if not self.health_bind:
                raise WorkerConfigError("health_bind must be a non-empty hostname/IP")

    @property
    def address(self) -> tuple:
        """Return (host, port) tuple for legacy manager connection."""
        return (self.manager_host, self.manager_port)
