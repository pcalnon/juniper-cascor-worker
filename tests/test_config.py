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

    def test_health_defaults(self):
        """METRICS-MON R1.3 / seed-04: health server defaults to 127.0.0.1:8210."""
        config = WorkerConfig()
        assert config.health_port == 8210
        assert config.health_bind == "127.0.0.1"

    def test_validate_invalid_health_port(self):
        """METRICS-MON R1.3 / seed-04: health_port range enforced."""
        config = WorkerConfig(server_url="ws://localhost:8200/", health_port=0)
        with pytest.raises(WorkerConfigError, match="health_port"):
            config.validate(legacy=False)
        config = WorkerConfig(server_url="ws://localhost:8200/", health_port=99999)
        with pytest.raises(WorkerConfigError, match="health_port"):
            config.validate(legacy=False)

    def test_validate_empty_health_bind(self):
        """METRICS-MON R1.3 / seed-04: health_bind cannot be empty string."""
        config = WorkerConfig(server_url="ws://localhost:8200/", health_bind="")
        with pytest.raises(WorkerConfigError, match="health_bind"):
            config.validate(legacy=False)

    def test_from_env_health_overrides(self):
        """METRICS-MON R1.3 / seed-04: env vars override health server defaults."""
        env = {"CASCOR_WORKER_HEALTH_PORT": "9999", "CASCOR_WORKER_HEALTH_BIND": "0.0.0.0"}
        with patch.dict(os.environ, env, clear=True):
            config = WorkerConfig.from_env()
            assert config.health_port == 9999
            assert config.health_bind == "0.0.0.0"

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
        assert config.auth_token == ""
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
        """from_env reads CASCOR_SERVER_URL, CASCOR_AUTH_TOKEN, etc."""
        env = {
            "CASCOR_SERVER_URL": "ws://remote:8200/ws/v1/workers",
            "CASCOR_AUTH_TOKEN": "env-api-key",
            "CASCOR_HEARTBEAT_INTERVAL": "30.0",
            "CASCOR_TLS_CERT": "/path/to/cert.pem",
            "CASCOR_TLS_KEY": "/path/to/key.pem",
            "CASCOR_TLS_CA": "/path/to/ca.pem",
        }
        with patch.dict(os.environ, env, clear=True):
            config = WorkerConfig.from_env()
            assert config.server_url == "ws://remote:8200/ws/v1/workers"
            assert config.auth_token == "env-api-key"
            assert config.heartbeat_interval == 30.0
            assert config.tls_cert == "/path/to/cert.pem"
            assert config.tls_key == "/path/to/key.pem"
            assert config.tls_ca == "/path/to/ca.pem"

    def test_from_env_ws_fields_legacy_api_key_fallback(self):
        """from_env falls back to CASCOR_API_KEY when new var is unset."""
        env = {
            "CASCOR_SERVER_URL": "ws://remote:8200/ws/v1/workers",
            "CASCOR_API_KEY": "legacy-env-key",
        }
        with patch.dict(os.environ, env, clear=True):
            config = WorkerConfig.from_env()
            assert config.auth_token == "legacy-env-key"

    def test_from_env_ws_fields_prefers_new_token_name(self):
        """CASCOR_AUTH_TOKEN takes precedence over deprecated alias."""
        env = {
            "CASCOR_SERVER_URL": "ws://remote:8200/ws/v1/workers",
            "CASCOR_AUTH_TOKEN": "new-token",
            "CASCOR_API_KEY": "legacy-env-key",
        }
        with patch.dict(os.environ, env, clear=True):
            config = WorkerConfig.from_env()
            assert config.auth_token == "new-token"

    def test_task_timeout_default(self):
        """task_timeout defaults to 3600 seconds."""
        config = WorkerConfig()
        assert config.task_timeout == 3600.0

    def test_task_timeout_custom(self):
        """task_timeout can be set explicitly."""
        config = WorkerConfig(server_url="ws://localhost:8200/ws/v1/workers", task_timeout=7200.0)
        config.validate(legacy=False)  # Should not raise
        assert config.task_timeout == 7200.0

    def test_task_timeout_invalid(self):
        """task_timeout <= 0 raises WorkerConfigError."""
        config = WorkerConfig(server_url="ws://localhost:8200/ws/v1/workers", task_timeout=0)
        with pytest.raises(WorkerConfigError, match="task_timeout"):
            config.validate(legacy=False)

    def test_task_timeout_negative(self):
        """Negative task_timeout raises WorkerConfigError."""
        config = WorkerConfig(server_url="ws://localhost:8200/ws/v1/workers", task_timeout=-1.0)
        with pytest.raises(WorkerConfigError, match="task_timeout"):
            config.validate(legacy=False)

    def test_from_env_task_timeout(self):
        """from_env reads CASCOR_TASK_TIMEOUT."""
        env = {
            "CASCOR_SERVER_URL": "ws://remote:8200/ws/v1/workers",
            "CASCOR_TASK_TIMEOUT": "1800.0",
        }
        with patch.dict(os.environ, env, clear=True):
            config = WorkerConfig.from_env()
            assert config.task_timeout == 1800.0

    def test_from_env_task_timeout_default(self):
        """from_env uses 3600 default when CASCOR_TASK_TIMEOUT unset."""
        with patch.dict(os.environ, {}, clear=True):
            config = WorkerConfig.from_env()
            assert config.task_timeout == 3600.0
