"""Tests for WorkerConfig."""

import os
from unittest.mock import patch

import pytest

from juniper_cascor_worker.config import WorkerConfig
from juniper_cascor_worker.exceptions import WorkerConfigError


class TestWorkerConfig:
    def test_defaults(self):
        config = WorkerConfig()
        assert config.manager_host == "127.0.0.1"
        assert config.manager_port == 50000
        assert config.authkey == "juniper"
        assert config.num_workers == 1
        assert config.mp_context == "forkserver"

    def test_custom_values(self):
        config = WorkerConfig(
            manager_host="192.168.1.100",
            manager_port=60000,
            authkey="secret",
            num_workers=4,
        )
        assert config.manager_host == "192.168.1.100"
        assert config.manager_port == 60000
        assert config.num_workers == 4

    def test_address_property(self):
        config = WorkerConfig(manager_host="10.0.0.1", manager_port=5555)
        assert config.address == ("10.0.0.1", 5555)

    def test_validate_valid(self):
        config = WorkerConfig()
        config.validate()  # Should not raise

    def test_validate_invalid_workers(self):
        config = WorkerConfig(num_workers=0)
        with pytest.raises(WorkerConfigError, match="num_workers"):
            config.validate()

    def test_validate_invalid_port_low(self):
        config = WorkerConfig(manager_port=0)
        with pytest.raises(WorkerConfigError, match="manager_port"):
            config.validate()

    def test_validate_invalid_port_high(self):
        config = WorkerConfig(manager_port=70000)
        with pytest.raises(WorkerConfigError, match="manager_port"):
            config.validate()

    def test_validate_invalid_context(self):
        config = WorkerConfig(mp_context="invalid")
        with pytest.raises(WorkerConfigError, match="mp_context"):
            config.validate()

    def test_from_env_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            config = WorkerConfig.from_env()
            assert config.manager_host == "127.0.0.1"
            assert config.manager_port == 50000

    def test_from_env_custom(self):
        env = {
            "CASCOR_MANAGER_HOST": "10.0.0.5",
            "CASCOR_MANAGER_PORT": "9999",
            "CASCOR_AUTHKEY": "mykey",
            "CASCOR_NUM_WORKERS": "8",
            "CASCOR_MP_CONTEXT": "spawn",
        }
        with patch.dict(os.environ, env, clear=True):
            config = WorkerConfig.from_env()
            assert config.manager_host == "10.0.0.5"
            assert config.manager_port == 9999
            assert config.authkey == "mykey"
            assert config.num_workers == 8
            assert config.mp_context == "spawn"
