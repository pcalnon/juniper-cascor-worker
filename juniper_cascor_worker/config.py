"""Configuration for the remote candidate training worker."""

import os
from dataclasses import dataclass

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
        auth_token: API key for ``X-API-Key`` header authentication.
        heartbeat_interval: Seconds between heartbeat messages.
        reconnect_backoff_base: Initial reconnection delay in seconds.
        reconnect_backoff_max: Maximum reconnection delay in seconds.
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
    heartbeat_interval: float = 10.0
    reconnect_backoff_base: float = 1.0
    reconnect_backoff_max: float = 60.0
    tls_cert: str | None = None
    tls_key: str | None = None
    tls_ca: str | None = None

    # Legacy BaseManager configuration
    manager_host: str = "127.0.0.1"
    manager_port: int = 50000
    authkey: str = ""
    num_workers: int = 1
    task_queue_timeout: float = 5.0
    stop_timeout: int = 10
    mp_context: str = "forkserver"

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        """Create config from environment variables.

        Environment variables (WebSocket mode):
            CASCOR_SERVER_URL: WebSocket URL
            CASCOR_AUTH_TOKEN: API key for authentication
            CASCOR_HEARTBEAT_INTERVAL: Heartbeat interval in seconds
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
            server_url=os.getenv("CASCOR_SERVER_URL", ""),
            auth_token=os.getenv("CASCOR_AUTH_TOKEN", ""),
            heartbeat_interval=float(os.getenv("CASCOR_HEARTBEAT_INTERVAL", "10.0")),
            tls_cert=os.getenv("CASCOR_TLS_CERT"),
            tls_key=os.getenv("CASCOR_TLS_KEY"),
            tls_ca=os.getenv("CASCOR_TLS_CA"),
            manager_host=os.getenv("CASCOR_MANAGER_HOST", "127.0.0.1"),
            manager_port=int(os.getenv("CASCOR_MANAGER_PORT", "50000")),
            authkey=os.getenv("CASCOR_AUTHKEY", ""),
            num_workers=int(os.getenv("CASCOR_NUM_WORKERS", "1")),
            mp_context=os.getenv("CASCOR_MP_CONTEXT", "forkserver"),
        )

    def validate(self, legacy: bool = False) -> None:
        """Validate configuration values.

        Args:
            legacy: If True, validate for legacy BaseManager mode.
                    If False, validate for WebSocket mode.
        """
        if legacy:
            if not self.authkey:
                raise WorkerConfigError("authkey is required — set CASCOR_AUTHKEY or pass --authkey")
            if self.num_workers < 1:
                raise WorkerConfigError(f"num_workers must be >= 1, got {self.num_workers}")
            if self.manager_port < 1 or self.manager_port > 65535:
                raise WorkerConfigError(f"manager_port must be 1-65535, got {self.manager_port}")
            if self.mp_context not in ("forkserver", "spawn", "fork"):
                raise WorkerConfigError(f"Invalid mp_context: {self.mp_context}")
        else:
            if not self.server_url:
                raise WorkerConfigError("server_url is required — set CASCOR_SERVER_URL or pass --server-url")
            if not self.server_url.startswith(("ws://", "wss://")):
                raise WorkerConfigError(f"server_url must start with ws:// or wss://, got: {self.server_url}")
            if self.heartbeat_interval <= 0:
                raise WorkerConfigError(f"heartbeat_interval must be > 0, got {self.heartbeat_interval}")
            if self.reconnect_backoff_base <= 0:
                raise WorkerConfigError(f"reconnect_backoff_base must be > 0, got {self.reconnect_backoff_base}")

    @property
    def address(self) -> tuple:
        """Return (host, port) tuple for legacy manager connection."""
        return (self.manager_host, self.manager_port)
