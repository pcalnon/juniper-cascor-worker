"""JuniperCascor Worker - Remote candidate training worker for distributed CasCor training.

This package provides a standalone worker process that connects to a JuniperCascor
training manager and processes candidate training tasks from a shared queue.
"""

from juniper_cascor_worker.config import WorkerConfig
from juniper_cascor_worker.exceptions import (
    WorkerConfigError,
    WorkerConnectionError,
    WorkerError,
)
from juniper_cascor_worker.worker import CandidateTrainingWorker

__version__ = "0.1.0"

__all__ = [
    "CandidateTrainingWorker",
    "WorkerConfig",
    "WorkerError",
    "WorkerConnectionError",
    "WorkerConfigError",
    "__version__",
]
