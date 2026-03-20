"""JuniperCascor Worker - Remote candidate training worker for distributed CasCor training.

This package provides a standalone worker that connects to a JuniperCascor
training server and processes candidate training tasks.

Two worker implementations are available:
- ``CascorWorkerAgent`` (default): WebSocket-based, no pickle.
- ``CandidateTrainingWorker`` (legacy): BaseManager-based, deprecated.
"""

from juniper_cascor_worker.config import WorkerConfig
from juniper_cascor_worker.exceptions import WorkerConfigError, WorkerConnectionError, WorkerError
from juniper_cascor_worker.worker import CandidateTrainingWorker, CascorWorkerAgent

__version__ = "0.3.0"

__all__ = [
    "CascorWorkerAgent",
    "CandidateTrainingWorker",
    "WorkerConfig",
    "WorkerError",
    "WorkerConnectionError",
    "WorkerConfigError",
    "__version__",
]
