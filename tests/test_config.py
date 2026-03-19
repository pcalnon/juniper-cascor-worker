"""Tests for WorkerConfig."""

import os
from unittest.mock import patch

import pytest

from juniper_cascor_worker.config import WorkerConfig
from juniper_cascor_worker.exceptions import WorkerConfigError


@pytest.mark.unit
class TestWorkerConfig:
    def test_defaults(self):
        config = WorkerConfig()
        assert config.manager_host == "127.0.0.1"
        assert config.manager_port == 50000
        assert config.authkey == ""
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
        config = WorkerConfig(authkey="test-key")
        config.validate(legacy=True)  # Should not raise

    def test_validate_missing_authkey(self):
        config = WorkerConfig()
        with pytest.raises(WorkerConfigError, match="authkey"):
            config.validate(legacy=True)

    def test_validate_invalid_workers(self):
        config = WorkerConfig(authkey="test-key", num_workers=0)
        with pytest.raises(WorkerConfigError, match="num_workers"):
            config.validate(legacy=True)

    def test_validate_invalid_port_low(self):
        config = WorkerConfig(authkey="test-key", manager_port=0)
        with pytest.raises(WorkerConfigError, match="manager_port"):
            config.validate(legacy=True)

    def test_validate_invalid_port_high(self):
        config = WorkerConfig(authkey="test-key", manager_port=70000)
        with pytest.raises(WorkerConfigError, match="manager_port"):
            config.validate(legacy=True)

    def test_validate_invalid_context(self):
        config = WorkerConfig(authkey="test-key", mp_context="invalid")
        with pytest.raises(WorkerConfigError, match="mp_context"):
            config.validate(legacy=True)

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


@pytest.mark.unit
class TestWorkerConfigWebSocket:
    """Tests for WebSocket mode configuration fields and validation."""

    def test_ws_defaults(self):
        """New WebSocket fields have correct defaults."""
        config = WorkerConfig()
        assert config.server_url == ""
        assert config.api_key == ""
        assert config.heartbeat_interval == 10.0
        assert config.reconnect_backoff_base == 1.0
        assert config.reconnect_backoff_max == 60.0
        assert config.tls_cert is None
        assert config.tls_key is None
        assert config.tls_ca is None

    def test_validate_ws_mode_valid(self):
        """Valid server_url passes validation."""
        config = WorkerConfig(server_url="ws://localhost:8200/ws/v1/workers")
        config.validate(legacy=False)  # Should not raise

    def test_validate_ws_mode_valid_wss(self):
        """Valid wss:// server_url passes validation."""
        config = WorkerConfig(server_url="wss://secure.example.com/ws/v1/workers")
        config.validate(legacy=False)  # Should not raise

    def test_validate_ws_mode_missing_url(self):
        """Empty server_url raises WorkerConfigError."""
        config = WorkerConfig(server_url="")
        with pytest.raises(WorkerConfigError, match="server_url"):
            config.validate(legacy=False)

    def test_validate_ws_mode_bad_scheme(self):
        """Non-ws:// URL raises WorkerConfigError."""
        config = WorkerConfig(server_url="http://localhost:8200/ws/v1/workers")
        with pytest.raises(WorkerConfigError, match="server_url must start with ws://"):
            config.validate(legacy=False)

    def test_validate_ws_mode_bad_heartbeat(self):
        """heartbeat_interval <= 0 raises WorkerConfigError."""
        config = WorkerConfig(server_url="ws://localhost:8200/ws/v1/workers", heartbeat_interval=0)
        with pytest.raises(WorkerConfigError, match="heartbeat_interval"):
            config.validate(legacy=False)

    def test_validate_ws_mode_bad_heartbeat_negative(self):
        """Negative heartbeat_interval raises WorkerConfigError."""
        config = WorkerConfig(server_url="ws://localhost:8200/ws/v1/workers", heartbeat_interval=-5.0)
        with pytest.raises(WorkerConfigError, match="heartbeat_interval"):
            config.validate(legacy=False)

    def test_validate_ws_mode_bad_backoff(self):
        """reconnect_backoff_base <= 0 raises WorkerConfigError."""
        config = WorkerConfig(server_url="ws://localhost:8200/ws/v1/workers", reconnect_backoff_base=0)
        with pytest.raises(WorkerConfigError, match="reconnect_backoff_base"):
            config.validate(legacy=False)

    def test_validate_legacy_mode(self):
        """Legacy validation still works (authkey required)."""
        config = WorkerConfig(authkey="secret-key")
        config.validate(legacy=True)  # Should not raise

    def test_validate_legacy_mode_missing_authkey(self):
        """Legacy mode without authkey raises."""
        config = WorkerConfig()
        with pytest.raises(WorkerConfigError, match="authkey"):
            config.validate(legacy=True)

    def test_from_env_ws_fields(self):
        """from_env reads CASCOR_SERVER_URL, CASCOR_API_KEY, etc."""
        env = {
            "CASCOR_SERVER_URL": "ws://remote:8200/ws/v1/workers",
            "CASCOR_API_KEY": "env-api-key",
            "CASCOR_HEARTBEAT_INTERVAL": "30.0",
            "CASCOR_TLS_CERT": "/path/to/cert.pem",
            "CASCOR_TLS_KEY": "/path/to/key.pem",
            "CASCOR_TLS_CA": "/path/to/ca.pem",
        }
        with patch.dict(os.environ, env, clear=True):
            config = WorkerConfig.from_env()
            assert config.server_url == "ws://remote:8200/ws/v1/workers"
            assert config.api_key == "env-api-key"
            assert config.heartbeat_interval == 30.0
            assert config.tls_cert == "/path/to/cert.pem"
            assert config.tls_key == "/path/to/key.pem"
            assert config.tls_ca == "/path/to/ca.pem"
