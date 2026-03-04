"""Test configuration for juniper-cascor-worker."""

import pytest

from juniper_cascor_worker.config import WorkerConfig


@pytest.fixture()
def valid_config():
    """Return a WorkerConfig with a test authkey that passes validation."""
    return WorkerConfig(authkey="test-authkey")
