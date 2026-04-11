"""Configuration for the remote candidate training worker."""

import os
from dataclasses import dataclass

from juniper_cascor_worker.constants import (
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
    ENV_API_KEY,
    ENV_AUTH_TOKEN,
    ENV_AUTHKEY,
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
    MAX_PORT,
    MIN_NUM_WORKERS,
    MIN_PORT,
    VALID_MP_CONTEXTS,
    VALID_WS_SCHEMES,
)
from juniper_cascor_worker.exceptions import WorkerConfigError


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

    # Legacy BaseManager configuration
    manager_host: str = DEFAULT_MANAGER_HOST
    manager_port: int = DEFAULT_MANAGER_PORT
    authkey: str = ""
    num_workers: int = DEFAULT_NUM_WORKERS
    task_queue_timeout: float = DEFAULT_TASK_QUEUE_TIMEOUT
    stop_timeout: int = DEFAULT_STOP_TIMEOUT
    mp_context: str = DEFAULT_MP_CONTEXT

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        """Create config from environment variables.

        Environment variables (WebSocket mode):
            CASCOR_SERVER_URL: WebSocket URL
            CASCOR_AUTH_TOKEN: API key for authentication
            CASCOR_API_KEY: Deprecated alias for CASCOR_AUTH_TOKEN
            CASCOR_HEARTBEAT_INTERVAL: Heartbeat interval in seconds
            CASCOR_TASK_TIMEOUT: Maximum seconds for a single training task
            CASCOR_TLS_CERT: Client certificate path
            CASCOR_TLS_KEY: Client key path
            CASCOR_TLS_CA: CA certificate path

        Environment variables (Legacy mode):
            CASCOR_MANAGER_HOST: Manager hostname (default: 127.0.0.1)
            CASCOR_MANAGER_PORT: Manager port (default: 50000)
            CASCOR_AUTHKEY: Authentication key (required for legacy mode)
            CASCOR_NUM_WORKERS: Number of workers (default: 1)
            CASCOR_MP_CONTEXT: Multiprocessing context (default: forkserver)
        """
        return cls(
            server_url=os.getenv(ENV_SERVER_URL, ""),
            auth_token=os.getenv(ENV_AUTH_TOKEN) or os.getenv(ENV_API_KEY, ""),
            heartbeat_interval=float(os.getenv(ENV_HEARTBEAT_INTERVAL, str(DEFAULT_HEARTBEAT_INTERVAL))),
            task_timeout=float(os.getenv(ENV_TASK_TIMEOUT, str(DEFAULT_TASK_TIMEOUT))),
            tls_cert=os.getenv(ENV_TLS_CERT),
            tls_key=os.getenv(ENV_TLS_KEY),
            tls_ca=os.getenv(ENV_TLS_CA),
            manager_host=os.getenv(ENV_MANAGER_HOST, DEFAULT_MANAGER_HOST),
            manager_port=int(os.getenv(ENV_MANAGER_PORT, str(DEFAULT_MANAGER_PORT))),
            authkey=os.getenv(ENV_AUTHKEY, ""),
            num_workers=int(os.getenv(ENV_NUM_WORKERS, str(DEFAULT_NUM_WORKERS))),
            mp_context=os.getenv(ENV_MP_CONTEXT, DEFAULT_MP_CONTEXT),
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

    @property
    def address(self) -> tuple:
        """Return (host, port) tuple for legacy manager connection."""
        return (self.manager_host, self.manager_port)
