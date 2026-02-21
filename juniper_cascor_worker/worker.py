"""Remote candidate training worker for distributed CasCor training.

Connects to a remote CandidateTrainingManager and processes candidate
training tasks from the shared task queue.
"""

import logging
import multiprocessing as mp
from multiprocessing.context import BaseContext
from typing import Any, Optional, Union

from juniper_cascor_worker.config import WorkerConfig
from juniper_cascor_worker.exceptions import WorkerConnectionError, WorkerError

logger = logging.getLogger(__name__)


class CandidateTrainingWorker:
    """Remote worker that processes candidate training tasks.

    Connects to a CasCor CandidateTrainingManager server and spawns
    local worker processes that consume tasks from the shared queue.

    Requires the CasCor codebase to be importable (either installed or
    on sys.path) because the worker processes execute CasCor's
    train_candidate_worker function locally.

    Example:
        >>> config = WorkerConfig(manager_host="192.168.1.100", manager_port=50000)
        >>> with CandidateTrainingWorker(config) as worker:
        ...     worker.start()
        ...     # Workers process tasks until stopped
        ...     worker.stop()
    """

    def __init__(self, config: Optional[WorkerConfig] = None) -> None:
        self.config = config or WorkerConfig()
        self.config.validate()
        self.ctx: BaseContext = mp.get_context(self.config.mp_context)
        self.manager: Any = None
        self.task_queue: Any = None
        self.result_queue: Any = None
        self.workers: list = []
        self._connected = False

    def connect(self) -> None:
        """Connect to the remote CandidateTrainingManager."""
        try:
            from cascade_correlation.cascade_correlation import CandidateTrainingManager
        except ImportError as e:
            raise WorkerError(
                "CasCor codebase not found. Ensure the JuniperCascor src directory "
                "is on sys.path or installed in the environment. "
                f"Original error: {e}"
            ) from e

        raw_authkey: Union[str, bytes] = self.config.authkey
        authkey: bytes = raw_authkey.encode("utf-8") if isinstance(raw_authkey, str) else raw_authkey

        try:
            self.manager = CandidateTrainingManager(
                address=self.config.address,
                authkey=authkey,
            )
            self.manager.connect()
            self.task_queue = self.manager.get_task_queue()
            self.result_queue = self.manager.get_result_queue()
            self._connected = True
            logger.info("Connected to manager at %s:%d", self.config.manager_host, self.config.manager_port)
        except Exception as e:
            raise WorkerConnectionError(f"Failed to connect to manager at {self.config.address}: {e}") from e

    def start(self, num_workers: Optional[int] = None) -> None:
        """Start local worker processes.

        Args:
            num_workers: Override number of workers (default: from config).
        """
        if not self._connected:
            raise WorkerError("Not connected. Call connect() first.")

        n = num_workers or self.config.num_workers

        try:
            from cascade_correlation.cascade_correlation import CascadeCorrelationNetwork
        except ImportError as e:
            raise WorkerError(f"CasCor codebase not found: {e}") from e

        for i in range(n):
            worker = self.ctx.Process(  # type: ignore[attr-defined]
                target=CascadeCorrelationNetwork._worker_loop,
                args=(self.task_queue, self.result_queue, True),
                daemon=True,
                name=f"CascorRemoteWorker-{i}",
            )
            worker.start()
            self.workers.append(worker)

        logger.info("Started %d worker processes", len(self.workers))

    def stop(self, timeout: Optional[int] = None) -> None:
        """Stop all worker processes gracefully.

        Args:
            timeout: Seconds to wait per worker (default: from config).
        """
        if not self.workers:
            return

        t = timeout or self.config.stop_timeout

        # Send sentinel to each worker
        for _ in self.workers:
            try:
                self.task_queue.put(None)
            except Exception as e:
                logger.error("Failed to send sentinel: %s", e)

        # Wait for workers
        for worker in self.workers:
            worker.join(timeout=t)
            if worker.is_alive():
                logger.warning("Worker %s did not stop gracefully, terminating", worker.name)
                worker.terminate()

        self.workers.clear()
        logger.info("All worker processes stopped")

    def disconnect(self) -> None:
        """Disconnect from the remote manager."""
        if self.workers:
            self.stop()
        self.manager = None
        self.task_queue = None
        self.result_queue = None
        self._connected = False
        logger.info("Disconnected from manager")

    @property
    def is_running(self) -> bool:
        """Check if any workers are running."""
        return any(w.is_alive() for w in self.workers)

    @property
    def worker_count(self) -> int:
        """Number of active worker processes."""
        return sum(1 for w in self.workers if w.is_alive())

    def __enter__(self) -> "CandidateTrainingWorker":
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.disconnect()
