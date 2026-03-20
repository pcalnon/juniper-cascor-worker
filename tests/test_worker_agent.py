"""Tests for CascorWorkerAgent and module-level helpers in worker.py."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from juniper_cascor_worker.config import WorkerConfig
from juniper_cascor_worker.exceptions import WorkerConfigError, WorkerConnectionError
from juniper_cascor_worker.worker import CascorWorkerAgent, _decode_binary_frame, _encode_binary_frame, _parse_json


def _make_ws_config(**overrides):
    """Return a WorkerConfig for WebSocket mode that passes validation."""
    defaults = {
        "server_url": "ws://localhost:8200/ws/v1/workers",
        "api_key": "test-key",
    }
    defaults.update(overrides)
    return WorkerConfig(**defaults)


@pytest.mark.unit
class TestCascorWorkerAgentInit:
    def test_init_validates_config(self):
        """Invalid config raises WorkerConfigError."""
        config = WorkerConfig(server_url="")  # Missing server_url
        with pytest.raises(WorkerConfigError, match="server_url"):
            CascorWorkerAgent(config)

    def test_init_bad_scheme_raises(self):
        """Non-ws:// URL raises WorkerConfigError."""
        config = WorkerConfig(server_url="http://localhost:8200/ws/v1/workers")
        with pytest.raises(WorkerConfigError, match="server_url must start with ws://"):
            CascorWorkerAgent(config)

    def test_init_success(self):
        """Valid config creates agent with worker_id and stop event."""
        config = _make_ws_config()
        agent = CascorWorkerAgent(config)
        assert agent.config is config
        assert agent.worker_id  # Non-empty UUID string
        assert not agent._stop_event.is_set()


@pytest.mark.unit
class TestBuildCapabilities:
    def test_build_capabilities(self):
        """Returns dict with cpu_cores, python_version, torch_version, etc."""
        import torch as real_torch

        # _build_capabilities does a local `import torch` inside the method,
        # so we patch the torch module that's already imported at the top of worker.py
        # plus mock the local import via sys.modules.
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        mock_torch.__version__ = "2.1.0"

        with patch.dict("sys.modules", {"torch": mock_torch}), patch("juniper_cascor_worker.worker.os.cpu_count", return_value=8), patch("juniper_cascor_worker.worker.platform.python_version", return_value="3.12.0"), patch("juniper_cascor_worker.worker.platform.system", return_value="Linux"):
            caps = CascorWorkerAgent._build_capabilities()

        assert caps["cpu_cores"] == 8
        assert caps["python_version"] == "3.12.0"
        assert caps["torch_version"] == "2.1.0"
        assert caps["os"] == "Linux"
        assert caps["gpu"] is False
        assert caps["gpu_name"] is None


@pytest.mark.unit
class TestParseJson:
    def test_parse_json_valid(self):
        """Returns parsed dict."""
        result = _parse_json('{"type": "ack", "status": "ok"}')
        assert result == {"type": "ack", "status": "ok"}

    def test_parse_json_invalid(self):
        """Returns None for invalid JSON."""
        result = _parse_json("not json at all {{{")
        assert result is None

    def test_parse_json_none_input(self):
        """Returns None for None input."""
        result = _parse_json(None)
        assert result is None

    def test_parse_json_empty_string(self):
        """Returns None for empty string."""
        result = _parse_json("")
        assert result is None


@pytest.mark.unit
class TestBinaryFrame:
    def test_binary_frame_roundtrip(self):
        """Encode then decode a 1D numpy array."""
        original = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float32)
        encoded = _encode_binary_frame(original)
        decoded = _decode_binary_frame(encoded)

        assert isinstance(encoded, bytes)
        assert isinstance(decoded, np.ndarray)
        np.testing.assert_array_equal(original, decoded)
        assert decoded.dtype == np.float32

    def test_binary_frame_2d(self):
        """2D array roundtrip."""
        original = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]], dtype=np.float32)
        encoded = _encode_binary_frame(original)
        decoded = _decode_binary_frame(encoded)

        assert decoded.shape == (3, 2)
        np.testing.assert_array_equal(original, decoded)
        assert decoded.dtype == np.float32

    def test_binary_frame_float64(self):
        """Float64 array roundtrip preserves dtype."""
        original = np.array([1.0, 2.0, 3.0], dtype=np.float64)
        encoded = _encode_binary_frame(original)
        decoded = _decode_binary_frame(encoded)

        np.testing.assert_array_equal(original, decoded)
        assert decoded.dtype == np.float64


@pytest.mark.unit
class TestRegister:
    @pytest.mark.asyncio
    async def test_register_sends_message(self):
        """Mock connection, verify register message sent."""
        config = _make_ws_config()
        agent = CascorWorkerAgent(config)

        mock_conn = AsyncMock()
        mock_conn.receive_json.return_value = {"type": "registration_ack"}
        agent._connection = mock_conn

        with patch.object(CascorWorkerAgent, "_build_capabilities", return_value={"cpu_cores": 4}):
            await agent._register()

        mock_conn.send_json.assert_awaited_once()
        sent_msg = mock_conn.send_json.call_args[0][0]
        assert sent_msg["type"] == "register"
        assert sent_msg["worker_id"] == agent.worker_id
        assert sent_msg["capabilities"] == {"cpu_cores": 4}

    @pytest.mark.asyncio
    async def test_register_failure_raises(self):
        """Non-ack response raises WorkerConnectionError."""
        config = _make_ws_config()
        agent = CascorWorkerAgent(config)

        mock_conn = AsyncMock()
        mock_conn.receive_json.return_value = {"type": "error", "error": "rejected"}
        agent._connection = mock_conn

        with patch.object(CascorWorkerAgent, "_build_capabilities", return_value={"cpu_cores": 4}):
            with pytest.raises(WorkerConnectionError, match="Registration failed"):
                await agent._register()


@pytest.mark.unit
class TestHandleTaskAssign:
    @pytest.mark.asyncio
    async def test_handle_task_assign(self):
        """Mock connection receive for tensors, mock _execute_task, verify result message sent."""
        config = _make_ws_config()
        agent = CascorWorkerAgent(config)

        # Create a small test tensor and encode it
        test_weights = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        test_input = np.random.randn(5, 3).astype(np.float32)
        encoded_input = _encode_binary_frame(test_input)
        encoded_error = _encode_binary_frame(np.random.randn(5, 1).astype(np.float32))

        mock_conn = AsyncMock()
        mock_conn.receive_bytes.side_effect = [encoded_input, encoded_error]
        agent._connection = mock_conn

        task_msg = {
            "type": "task_assign",
            "task_id": "task-001",
            "candidate_index": 0,
            "candidate_data": {"input_size": 3, "activation_name": "sigmoid"},
            "training_params": {"epochs": 100},
            "tensor_manifest": {"candidate_input": {}, "residual_error": {}},
        }

        mock_result_dict = {
            "candidate_id": 0,
            "candidate_uuid": "test-uuid",
            "correlation": 0.9,
            "success": True,
            "epochs_completed": 100,
            "activation_name": "sigmoid",
            "all_correlations": [0.9],
            "numerator": 0.9,
            "denominator": 1.0,
            "best_corr_idx": 0,
            "error_message": None,
        }
        mock_tensors = {"weights": test_weights}

        with patch("juniper_cascor_worker.worker.asyncio.to_thread", new_callable=AsyncMock, return_value=(mock_result_dict, mock_tensors)):
            await agent._handle_task_assign(task_msg)

        # Verify result JSON was sent
        send_json_calls = mock_conn.send_json.call_args_list
        assert len(send_json_calls) == 1
        result_msg = send_json_calls[0][0][0]
        assert result_msg["type"] == "task_result"
        assert result_msg["task_id"] == "task-001"
        assert result_msg["correlation"] == 0.9
        assert result_msg["success"] is True
        assert "weights" in result_msg["tensor_manifest"]

        # Verify binary frame was sent for weights
        send_bytes_calls = mock_conn.send_bytes.call_args_list
        assert len(send_bytes_calls) == 1


@pytest.mark.unit
class TestStop:
    def test_stop_sets_event(self):
        """stop() sets the _stop_event."""
        config = _make_ws_config()
        agent = CascorWorkerAgent(config)

        assert not agent._stop_event.is_set()
        agent.stop()
        assert agent._stop_event.is_set()
