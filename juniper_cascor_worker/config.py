"""Configuration for the remote candidate training worker."""

import os
from dataclasses import dataclass, field
from typing import Optional

from juniper_cascor_worker.exceptions import WorkerConfigError


@dataclass
class WorkerConfig:
    """Configuration for connecting to a CasCor training manager.

    Attributes:
        manager_host: Hostname of the remote CandidateTrainingManager.
        manager_port: Port of the remote CandidateTrainingManager.
        authkey: Authentication key for the manager connection.
        num_workers: Number of local worker processes to spawn.
        task_queue_timeout: Timeout (seconds) for polling the task queue.
        stop_timeout: Timeout (seconds) for graceful worker shutdown.
        mp_context: Multiprocessing start method (forkserver, spawn, fork).
    """

    manager_host: str = "127.0.0.1"
    manager_port: int = 50000
    authkey: str = "juniper"
    num_workers: int = 1
    task_queue_timeout: float = 5.0
    stop_timeout: int = 10
    mp_context: str = "forkserver"

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        """Create config from environment variables.

        Environment variables:
            CASCOR_MANAGER_HOST: Manager hostname (default: 127.0.0.1)
            CASCOR_MANAGER_PORT: Manager port (default: 50000)
            CASCOR_AUTHKEY: Authentication key (default: juniper)
            CASCOR_NUM_WORKERS: Number of workers (default: 1)
            CASCOR_MP_CONTEXT: Multiprocessing context (default: forkserver)
        """
        return cls(
            manager_host=os.getenv("CASCOR_MANAGER_HOST", "127.0.0.1"),
            manager_port=int(os.getenv("CASCOR_MANAGER_PORT", "50000")),
            authkey=os.getenv("CASCOR_AUTHKEY", "juniper"),
            num_workers=int(os.getenv("CASCOR_NUM_WORKERS", "1")),
            mp_context=os.getenv("CASCOR_MP_CONTEXT", "forkserver"),
        )

    def validate(self) -> None:
        """Validate configuration values."""
        if self.num_workers < 1:
            raise WorkerConfigError(f"num_workers must be >= 1, got {self.num_workers}")
        if self.manager_port < 1 or self.manager_port > 65535:
            raise WorkerConfigError(f"manager_port must be 1-65535, got {self.manager_port}")
        if self.mp_context not in ("forkserver", "spawn", "fork"):
            raise WorkerConfigError(f"Invalid mp_context: {self.mp_context}")

    @property
    def address(self) -> tuple:
        """Return (host, port) tuple for manager connection."""
        return (self.manager_host, self.manager_port)
