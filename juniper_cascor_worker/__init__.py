"""JuniperCascor Worker - Remote candidate training worker for distributed CasCor training.

This package provides a standalone worker that connects to a JuniperCascor
training server and processes candidate training tasks.

Two worker implementations are available:
- ``CascorWorkerAgent`` (default): WebSocket-based, no pickle.
- ``CandidateTrainingWorker`` (legacy): BaseManager-based, deprecated.
"""

import importlib.metadata

from juniper_cascor_worker.config import WorkerConfig
from juniper_cascor_worker.exceptions import WorkerConfigError, WorkerConnectionError, WorkerError
from juniper_cascor_worker.worker import CandidateTrainingWorker, CascorWorkerAgent

# Single source of truth: the installed distribution's metadata, matching
# juniper_data/__init__.py and juniper_canopy/__init__.py. The literal below is a
# fallback for a bare source checkout only.
#
# It was NOT a fallback before this change -- it was the only value, and it had drifted
# two releases: `__version__` read 0.4.0 while pyproject.toml and the published wheel
# metadata both said 0.6.0. juniper-cascor-worker 0.5.0 and 0.6.0 therefore shipped a
# package that misreported its own version to anything importing it, and `__version__`
# is in `__all__`, so that is public API. Found 2026-09-21 by running the PUBLISHED
# image and comparing `__version__` against `importlib.metadata.version()` -- a source
# read would not have shown it, because pyproject.toml alone looks correct.
#
# juniper-data's copy of this comment records the same drift there (0.7.1 at pyproject
# 0.12.0), which is why the installed path is the source of truth. Bump the literal with
# the version; only the fallback can drift now.
try:
    __version__ = importlib.metadata.version("juniper-cascor-worker")
except importlib.metadata.PackageNotFoundError:  # pragma: no cover - source checkout
    __version__ = "0.6.0"

__all__ = [
    "CascorWorkerAgent",
    "CandidateTrainingWorker",
    "WorkerConfig",
    "WorkerError",
    "WorkerConnectionError",
    "WorkerConfigError",
    "__version__",
]
