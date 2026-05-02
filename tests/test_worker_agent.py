"""Tests for CascorWorkerAgent and module-level helpers in worker.py."""

import asyncio
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
        "auth_token": "test-key",
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
        """stop() sets the _stop_event when no loop is running."""
        config = _make_ws_config()
        agent = CascorWorkerAgent(config)

        assert not agent._stop_event.is_set()
        agent.stop()
        assert agent._stop_event.is_set()

    def test_stop_uses_call_soon_threadsafe(self):
        """stop() uses call_soon_threadsafe when loop is running."""
        config = _make_ws_config()
        agent = CascorWorkerAgent(config)

        mock_loop = MagicMock()
        mock_loop.is_running.return_value = True
        agent._loop = mock_loop

        agent.stop()

        mock_loop.call_soon_threadsafe.assert_called_once_with(agent._stop_event.set)

    def test_stop_direct_set_when_loop_not_running(self):
        """stop() calls set() directly when loop exists but is not running."""
        config = _make_ws_config()
        agent = CascorWorkerAgent(config)

        mock_loop = MagicMock()
        mock_loop.is_running.return_value = False
        agent._loop = mock_loop

        agent.stop()

        mock_loop.call_soon_threadsafe.assert_not_called()
        assert agent._stop_event.is_set()

    def test_stop_direct_set_when_no_loop(self):
        """stop() calls set() directly when _loop is None."""
        config = _make_ws_config()
        agent = CascorWorkerAgent(config)

        assert agent._loop is None
        agent.stop()
        assert agent._stop_event.is_set()


@pytest.mark.unit
class TestRunControlFlow:
    """Tests for the CascorWorkerAgent.run() control flow."""

    @pytest.mark.asyncio
    async def test_run_connects_and_registers(self):
        """run() connects, receives connection_established, sends register, starts loops."""
        # METRICS-MON R1.3 / seed-04: ``run()`` now starts a HealthServer on
        # ``health_port`` before entering the connect loop. Patch its
        # start/stop methods so the test does not bind a real port (which
        # would require a free port allocation and admit a flake on busy
        # CI runners) and so the event loop does not yield enough times
        # for ``stop_after_delay`` to fire before connect_with_retry runs.
        config = _make_ws_config()
        agent = CascorWorkerAgent(config)

        mock_conn = AsyncMock()
        # connection_established ack, then registration_ack
        mock_conn.receive_json.side_effect = [
            {"type": "connection_established"},
            {"type": "registration_ack"},
        ]
        # Make message_loop's receive() raise to trigger stop after registration
        mock_conn.receive.side_effect = WorkerConnectionError("test disconnect")

        with patch("juniper_cascor_worker.ws_connection.WorkerConnection", return_value=mock_conn), patch.object(CascorWorkerAgent, "_build_capabilities", return_value={"cpu_cores": 4}), patch("juniper_cascor_worker.worker.asyncio.sleep", new_callable=AsyncMock), patch("juniper_cascor_worker.http_health.HealthServer.start", new_callable=AsyncMock), patch("juniper_cascor_worker.http_health.HealthServer.stop", new_callable=AsyncMock):
            # Stop after first loop iteration
            async def stop_after_delay():
                await asyncio.sleep(0)
                agent._stop_event.set()

            task = asyncio.create_task(stop_after_delay())
            await agent.run()
            await task

        # Verify connection was opened
        mock_conn.connect_with_retry.assert_awaited()
        # Verify register message was sent (second call after connection_established)
        send_json_calls = mock_conn.send_json.call_args_list
        assert len(send_json_calls) >= 1
        register_msg = send_json_calls[0][0][0]
        assert register_msg["type"] == "register"
        assert register_msg["worker_id"] == agent.worker_id
        # Verify loop was stored
        assert agent._loop is not None

    @pytest.mark.asyncio
    async def test_run_stores_event_loop(self):
        """run() stores the running event loop in self._loop for thread-safe stop."""
        config = _make_ws_config()
        agent = CascorWorkerAgent(config)

        # Stop immediately
        agent._stop_event.set()

        with patch("juniper_cascor_worker.ws_connection.WorkerConnection"):
            await agent.run()

        assert agent._loop is asyncio.get_running_loop()


@pytest.mark.unit
class TestHeartbeatLoop:
    """Tests for _heartbeat_loop."""

    @pytest.mark.asyncio
    async def test_heartbeat_sends_periodically(self):
        """_heartbeat_loop sends heartbeat messages while running."""
        config = _make_ws_config(heartbeat_interval=0.01)
        agent = CascorWorkerAgent(config)

        mock_conn = AsyncMock()
        mock_conn.connected = True
        agent._connection = mock_conn

        send_count = 0
        original_send_json = mock_conn.send_json

        async def counting_send(msg):
            nonlocal send_count
            send_count += 1
            if send_count >= 2:
                agent._stop_event.set()

        mock_conn.send_json = AsyncMock(side_effect=counting_send)

        await agent._heartbeat_loop()

        assert send_count >= 2
        # Verify heartbeat message format
        first_call = mock_conn.send_json.call_args_list[0][0][0]
        assert first_call["type"] == "heartbeat"
        assert first_call["worker_id"] == agent.worker_id
        assert "timestamp" in first_call

    @pytest.mark.asyncio
    async def test_heartbeat_stops_on_connection_error(self):
        """_heartbeat_loop exits on WorkerConnectionError."""
        config = _make_ws_config(heartbeat_interval=0.01)
        agent = CascorWorkerAgent(config)

        mock_conn = AsyncMock()
        mock_conn.connected = True
        mock_conn.send_json.side_effect = WorkerConnectionError("lost")
        agent._connection = mock_conn

        # Should exit cleanly without raising
        await agent._heartbeat_loop()

    @pytest.mark.asyncio
    async def test_heartbeat_payload_carries_r4_4_training_loop_fields(self):
        """METRICS-MON R4.4: heartbeat payload includes the new training-loop
        instrumentation fields ``last_task_duration_seconds``,
        ``recent_task_durations_seconds``, ``gpu_utilization_pct`` alongside
        the R1.3 fields. Defaults must be ``None`` / ``[]`` so the payload
        round-trips cleanly when no tasks have been completed yet (cascor
        server tolerates ``None`` per the R1.3 design).
        """
        config = _make_ws_config(heartbeat_interval=0.01)
        agent = CascorWorkerAgent(config)
        # Pre-populate the sliding window so the payload is non-empty —
        # this also pins that the deque is JSON-serializable as a list.
        agent._last_task_duration_seconds = 0.5
        agent._recent_task_durations_seconds.extend([0.1, 0.2, 0.5])

        mock_conn = AsyncMock()
        mock_conn.connected = True
        agent._connection = mock_conn

        captured: list[dict] = []

        async def capture_send(msg):
            captured.append(msg)
            agent._stop_event.set()

        mock_conn.send_json = AsyncMock(side_effect=capture_send)

        # Force ``_sample_gpu_utilization_pct`` to a deterministic value
        # so the test doesn't depend on the host having a CUDA device.
        with patch("juniper_cascor_worker.worker._sample_gpu_utilization_pct", return_value=42.0):
            await agent._heartbeat_loop()

        assert len(captured) == 1
        payload = captured[0]
        assert payload["type"] == "heartbeat"
        # R1.3 baseline still present (regression guard).
        assert payload["worker_id"] == agent.worker_id
        assert "in_flight_tasks" in payload
        assert "last_task_completed_at" in payload
        assert "rss_mb" in payload
        # R4.4 new fields:
        assert payload["last_task_duration_seconds"] == 0.5
        assert payload["recent_task_durations_seconds"] == [0.1, 0.2, 0.5]
        assert payload["gpu_utilization_pct"] == 42.0

    @pytest.mark.asyncio
    async def test_heartbeat_payload_defaults_when_no_tasks_yet(self):
        """METRICS-MON R4.4: pre-task heartbeat sends ``None`` for
        ``last_task_duration_seconds`` and ``[]`` for the recent-window
        list. Cascor server treats ``None`` as no-signal per R1.3 pattern.
        """
        config = _make_ws_config(heartbeat_interval=0.01)
        agent = CascorWorkerAgent(config)

        mock_conn = AsyncMock()
        mock_conn.connected = True
        agent._connection = mock_conn

        captured: list[dict] = []

        async def capture_send(msg):
            captured.append(msg)
            agent._stop_event.set()

        mock_conn.send_json = AsyncMock(side_effect=capture_send)

        with patch("juniper_cascor_worker.worker._sample_gpu_utilization_pct", return_value=None):
            await agent._heartbeat_loop()

        payload = captured[0]
        assert payload["last_task_duration_seconds"] is None
        assert payload["recent_task_durations_seconds"] == []
        assert payload["gpu_utilization_pct"] is None


@pytest.mark.unit
class TestSampleGpuUtilizationPct:
    """METRICS-MON R4.4: GPU utilization sampling helper."""

    def test_returns_none_when_torch_unavailable(self):
        """Import error swallowed → None (matches the rss_mb defaulting pattern)."""
        import sys

        from juniper_cascor_worker.worker import _sample_gpu_utilization_pct

        with patch.dict(sys.modules, {"torch": None}):
            assert _sample_gpu_utilization_pct() is None

    def test_returns_none_when_no_cuda_device(self):
        """torch.cuda.is_available()=False → None."""
        from juniper_cascor_worker.worker import _sample_gpu_utilization_pct

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        with patch.dict("sys.modules", {"torch": mock_torch}):
            assert _sample_gpu_utilization_pct() is None

    def test_returns_float_when_cuda_available(self):
        """torch.cuda.utilization() reading is wrapped in float()."""
        from juniper_cascor_worker.worker import _sample_gpu_utilization_pct

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.utilization.return_value = 73  # NVML returns int 0-100
        with patch.dict("sys.modules", {"torch": mock_torch}):
            result = _sample_gpu_utilization_pct()
        assert result == 73.0
        assert isinstance(result, float), "must be float for stable JSON-serialized type vs rss_mb"

    def test_returns_none_when_nvml_raises(self):
        """Defensive: NVML can raise on misconfigured containers; helper must not propagate."""
        from juniper_cascor_worker.worker import _sample_gpu_utilization_pct

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.utilization.side_effect = RuntimeError("nvml not loadable")
        with patch.dict("sys.modules", {"torch": mock_torch}):
            assert _sample_gpu_utilization_pct() is None


@pytest.mark.unit
class TestRecentTaskDurationsBounded:
    """METRICS-MON R4.4: sliding window must stay bounded under sustained task load."""

    def test_recent_durations_bounded_by_window(self):
        """deque(maxlen=_RECENT_TASK_WINDOW) silently evicts older entries."""
        from juniper_cascor_worker.worker import _RECENT_TASK_WINDOW

        config = _make_ws_config()
        agent = CascorWorkerAgent(config)
        # Push 4× the window worth of entries.
        for i in range(_RECENT_TASK_WINDOW * 4):
            agent._recent_task_durations_seconds.append(float(i))
        assert len(agent._recent_task_durations_seconds) == _RECENT_TASK_WINDOW
        # Newest entries retained, oldest evicted (FIFO under maxlen).
        first = next(iter(agent._recent_task_durations_seconds))
        last = list(agent._recent_task_durations_seconds)[-1]
        assert first == float(_RECENT_TASK_WINDOW * 4 - _RECENT_TASK_WINDOW)
        assert last == float(_RECENT_TASK_WINDOW * 4 - 1)


@pytest.mark.unit
class TestMessageLoopDispatch:
    """Tests for _message_loop message dispatching."""

    @pytest.mark.asyncio
    async def test_message_loop_dispatches_task(self):
        """_message_loop dispatches task_assign messages to _handle_task_assign."""
        config = _make_ws_config()
        agent = CascorWorkerAgent(config)

        task_msg = json.dumps({"type": "task_assign", "task_id": "t1"})

        mock_conn = AsyncMock()
        call_count = 0

        async def receive_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return task_msg
            # Stop on second call
            agent._stop_event.set()
            raise WorkerConnectionError("stopped")

        mock_conn.receive.side_effect = receive_side_effect
        agent._connection = mock_conn

        with patch.object(agent, "_handle_task_assign", new_callable=AsyncMock) as mock_handle:
            try:
                await agent._message_loop()
            except WorkerConnectionError:
                pass

        mock_handle.assert_awaited_once()
        dispatched_msg = mock_handle.call_args[0][0]
        assert dispatched_msg["type"] == "task_assign"
        assert dispatched_msg["task_id"] == "t1"

    @pytest.mark.asyncio
    async def test_message_loop_ignores_heartbeat_response(self):
        """_message_loop silently handles heartbeat responses."""
        config = _make_ws_config()
        agent = CascorWorkerAgent(config)

        mock_conn = AsyncMock()
        call_count = 0

        async def receive_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return json.dumps({"type": "heartbeat"})
            agent._stop_event.set()
            raise WorkerConnectionError("stopped")

        mock_conn.receive.side_effect = receive_side_effect
        agent._connection = mock_conn

        with patch.object(agent, "_handle_task_assign", new_callable=AsyncMock) as mock_handle:
            try:
                await agent._message_loop()
            except WorkerConnectionError:
                pass

        # _handle_task_assign should NOT be called for heartbeat messages
        mock_handle.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_message_loop_emits_structured_warning_on_unrecognized_type(self, caplog):
        """METRICS-MON R4.7 / R3.6 sweep follow-up.

        ``_message_loop`` must emit a structured ``logger.warning`` line
        (``juniper_cascor_worker_unrecognized_ws_frame``) with ``type`` +
        ``worker_id`` extras when the server sends a frame whose ``type``
        is not in the worker's recognized set. R2.2.6 added the production
        emission as defense against future server-side schema drift that
        escapes the static guard in
        ``test_protocol_alignment.py::test_worker_does_not_emit_message_types_unknown_to_server``;
        this test pins the live emission path.
        """
        # ``worker_id`` is generated inside the agent constructor (uuid4),
        # not passed via WorkerConfig — pin it here so the structured-log
        # assertion below has a stable expected value.
        config = _make_ws_config()
        agent = CascorWorkerAgent(config)
        agent.worker_id = "r4-7-test-worker"

        # ``some_future_type`` is intentionally not in the
        # WorkerMessageType / cascor MessageType enum so the dispatch
        # falls through to the structured-warning branch.
        unknown_msg = json.dumps({"type": "some_future_type", "payload": "anything"})

        mock_conn = AsyncMock()
        call_count = 0

        async def receive_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return unknown_msg
            agent._stop_event.set()
            raise WorkerConnectionError("stopped")

        mock_conn.receive.side_effect = receive_side_effect
        agent._connection = mock_conn

        with caplog.at_level("WARNING", logger="juniper_cascor_worker.worker"):
            with pytest.raises(WorkerConnectionError):
                await agent._message_loop()

        # Filter to records emitted by the production emission site —
        # other WARNINGs in the loop (e.g. binary-frame-out-of-context)
        # would mask a regression here if we just searched the whole log.
        unrecognized_records = [r for r in caplog.records if r.message == "juniper_cascor_worker_unrecognized_ws_frame"]
        assert len(unrecognized_records) == 1, f"expected 1 structured warning, got {len(unrecognized_records)}: {[r.message for r in caplog.records]}"

        record = unrecognized_records[0]
        assert record.levelname == "WARNING"
        # ``extra`` keys land on the LogRecord as direct attributes.
        # Log shippers (Loki, etc.) parse these as structured fields.
        assert getattr(record, "type", None) == "some_future_type"
        assert getattr(record, "worker_id", None) == "r4-7-test-worker"


@pytest.mark.unit
class TestStopTerminatesRun:
    """Tests for stop() terminating the run() loop."""

    @pytest.mark.asyncio
    async def test_stop_terminates_run(self):
        """Calling stop() causes run() to exit cleanly."""
        config = _make_ws_config()
        agent = CascorWorkerAgent(config)

        mock_conn = AsyncMock()
        mock_conn.receive_json.side_effect = [
            {"type": "connection_established"},
            {"type": "registration_ack"},
        ]

        # Block in message_loop until stop is called
        stop_future = asyncio.get_running_loop().create_future()

        async def blocking_receive():
            await stop_future
            raise WorkerConnectionError("stopped")

        mock_conn.receive.side_effect = blocking_receive

        with patch("juniper_cascor_worker.ws_connection.WorkerConnection", return_value=mock_conn), patch.object(CascorWorkerAgent, "_build_capabilities", return_value={"cpu_cores": 4}):
            run_task = asyncio.create_task(agent.run())

            # Give run() time to start
            await asyncio.sleep(0.05)

            # Stop the agent
            agent.stop()
            stop_future.set_result(None)

            # run() should exit within a short time
            await asyncio.wait_for(run_task, timeout=2.0)

        assert agent._stop_event.is_set()


@pytest.mark.unit
class TestReconnectionOnDisconnect:
    """Tests for automatic reconnection when connection is lost."""

    @pytest.mark.asyncio
    async def test_reconnection_on_disconnect(self):
        """Agent reconnects after WorkerConnectionError from connect_with_retry."""
        config = _make_ws_config()
        agent = CascorWorkerAgent(config)

        connect_count = 0

        mock_conn_fail = AsyncMock()
        mock_conn_fail.connect_with_retry.side_effect = WorkerConnectionError("refused")
        mock_conn_fail.close = AsyncMock()

        mock_conn_ok = AsyncMock()
        mock_conn_ok.receive_json.side_effect = [
            {"type": "connection_established"},
            {"type": "registration_ack"},
        ]
        mock_conn_ok.receive.side_effect = WorkerConnectionError("disconnect after register")
        mock_conn_ok.close = AsyncMock()

        def make_connection(**kwargs):
            nonlocal connect_count
            connect_count += 1
            if connect_count == 1:
                return mock_conn_fail
            # Stop after second attempt
            agent._stop_event.set()
            return mock_conn_ok

        with patch("juniper_cascor_worker.ws_connection.WorkerConnection", side_effect=make_connection), patch.object(CascorWorkerAgent, "_build_capabilities", return_value={"cpu_cores": 4}), patch("juniper_cascor_worker.worker.asyncio.sleep", new_callable=AsyncMock):
            await agent.run()

        # First connection failed, second was created
        assert connect_count == 2
        mock_conn_fail.connect_with_retry.assert_awaited_once()
        mock_conn_fail.close.assert_awaited()


@pytest.mark.unit
class TestTaskTimeout:
    """Tests for task execution timeout handling."""

    @pytest.mark.asyncio
    async def test_task_timeout_sends_error_result(self):
        """When task exceeds timeout, an error result is sent back to server."""
        config = _make_ws_config(task_timeout=0.01)
        agent = CascorWorkerAgent(config)

        test_input = np.random.randn(5, 3).astype(np.float32)
        encoded_input = _encode_binary_frame(test_input)
        encoded_error = _encode_binary_frame(np.random.randn(5, 1).astype(np.float32))

        mock_conn = AsyncMock()
        mock_conn.receive_bytes.side_effect = [encoded_input, encoded_error]
        agent._connection = mock_conn

        task_msg = {
            "type": "task_assign",
            "task_id": "task-timeout-001",
            "candidate_index": 0,
            "candidate_data": {"input_size": 3, "activation_name": "sigmoid"},
            "training_params": {"epochs": 100},
            "tensor_manifest": {"candidate_input": {}, "residual_error": {}},
        }

        # Simulate a slow task that exceeds the timeout
        async def slow_to_thread(func, *args):
            await asyncio.sleep(10.0)
            return {}, {}

        with patch("juniper_cascor_worker.worker.asyncio.to_thread", side_effect=slow_to_thread):
            with patch("juniper_cascor_worker.worker.asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                await agent._handle_task_assign(task_msg)

        # Verify error result was sent
        send_json_calls = mock_conn.send_json.call_args_list
        assert len(send_json_calls) == 1
        error_msg = send_json_calls[0][0][0]
        assert error_msg["type"] == "task_result"
        assert error_msg["task_id"] == "task-timeout-001"
        assert error_msg["success"] is False
        assert "timed out" in error_msg["error_message"]
        assert error_msg["tensor_manifest"] == {}

        # Verify no binary frames were sent (no successful result)
        mock_conn.send_bytes.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_task_timeout_default_config(self):
        """Default task_timeout is 3600 seconds."""
        config = _make_ws_config()
        assert config.task_timeout == 3600.0


@pytest.mark.unit
class TestStopEventPassedToRetry:
    """Tests that stop_event is passed to connect_with_retry."""

    @pytest.mark.asyncio
    async def test_run_passes_stop_event(self):
        """run() passes self._stop_event to connect_with_retry."""
        config = _make_ws_config()
        agent = CascorWorkerAgent(config)

        mock_conn = AsyncMock()
        # First call to connect_with_retry will succeed, then we stop during message loop
        mock_conn.receive_json.side_effect = [
            {"type": "connection_established"},
            {"type": "registration_ack"},
        ]
        mock_conn.receive.side_effect = WorkerConnectionError("disconnect")
        mock_conn.close = AsyncMock()

        def make_conn_and_stop(**kwargs):
            # Stop after the first connection so run() exits
            agent._stop_event.set()
            return mock_conn

        with patch("juniper_cascor_worker.ws_connection.WorkerConnection", side_effect=make_conn_and_stop), patch.object(CascorWorkerAgent, "_build_capabilities", return_value={"cpu_cores": 4}), patch("juniper_cascor_worker.worker.asyncio.sleep", new_callable=AsyncMock):
            await agent.run()

        # Verify stop_event was passed to connect_with_retry
        call_kwargs = mock_conn.connect_with_retry.call_args
        assert call_kwargs.kwargs.get("stop_event") is agent._stop_event
