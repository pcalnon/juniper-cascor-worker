"""Test configuration for juniper-cascor-worker."""

import os
import sys
import sysconfig

# Free-threading interpreter guard (PEP 703 / 3.14t).
# tests/test_task_executor.py imports torch directly. The torch wheel pinned
# by the conda env is built for the regular CPython 3.14 ABI; loading it
# under the free-threading interpreter (python3.14t) raises an opaque
# "Failed to load PyTorch C extensions" error during collection. Other
# native deps (psutil, _brotli, ...) have similar ABI-mismatch failure
# modes. Bail out early with actionable instructions.
#
# Override with JUNIPER_CASCOR_WORKER_ALLOW_FREE_THREADING=1 if the env's
# native deps have been rebuilt for the cpython-314t ABI.
if sysconfig.get_config_var("Py_GIL_DISABLED") and not os.environ.get("JUNIPER_CASCOR_WORKER_ALLOW_FREE_THREADING"):
    sys.stderr.write(
        "\n"
        "ERROR: pytest is running under a free-threading CPython build (Py_GIL_DISABLED=1).\n"
        "       The active conda env's native deps (torch, psutil, _brotli, ...) are\n"
        "       built for the regular CPython ABI and fail to load under the 3.14t\n"
        "       interpreter due to PEP 703 PyObject layout changes.\n"
        "\n"
        "       Use a regular (GIL) CPython env, e.g.:\n"
        "         conda create -n JuniperCascor python=3.13 -c conda-forge -y\n"
        "         conda activate JuniperCascor && pip install -e .\n"
        "\n"
        "       To override this guard at your own risk, set\n"
        "       JUNIPER_CASCOR_WORKER_ALLOW_FREE_THREADING=1.\n"
        "\n"
    )
    raise SystemExit(2)

import pytest

from juniper_cascor_worker.config import WorkerConfig


@pytest.fixture()
def valid_config():
    """Return a WorkerConfig with a test authkey that passes validation."""
    return WorkerConfig(authkey="test-authkey")
