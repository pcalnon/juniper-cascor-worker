"""Tests for CandidateTrainingWorker."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from juniper_cascor_worker.config import WorkerConfig
from juniper_cascor_worker.exceptions import WorkerConnectionError, WorkerError
from juniper_cascor_worker.worker import CandidateTrainingWorker


class TestWorkerInit:
    def test_default_config(self):
        worker = CandidateTrainingWorker()
        assert worker.config.manager_host == "127.0.0.1"
        assert worker._connected is False
        assert worker.workers == []

    def test_custom_config(self):
        config = WorkerConfig(manager_host="10.0.0.1", num_workers=4)
        worker = CandidateTrainingWorker(config)
        assert worker.config.manager_host == "10.0.0.1"
        assert worker.config.num_workers == 4

    def test_invalid_config_raises(self):
        config = WorkerConfig(num_workers=0)
        with pytest.raises(Exception):
            CandidateTrainingWorker(config)


class TestWorkerState:
    def test_is_running_false_when_no_workers(self):
        worker = CandidateTrainingWorker()
        assert worker.is_running is False

    def test_worker_count_zero_when_no_workers(self):
        worker = CandidateTrainingWorker()
        assert worker.worker_count == 0

    def test_is_running_with_alive_worker(self):
        worker = CandidateTrainingWorker()
        mock_process = MagicMock()
        mock_process.is_alive.return_value = True
        worker.workers = [mock_process]
        assert worker.is_running is True

    def test_worker_count_with_mixed(self):
        worker = CandidateTrainingWorker()
        alive = MagicMock()
        alive.is_alive.return_value = True
        dead = MagicMock()
        dead.is_alive.return_value = False
        worker.workers = [alive, dead, alive]
        assert worker.worker_count == 2


class TestWorkerConnect:
    def test_connect_without_cascor_raises(self):
        worker = CandidateTrainingWorker()
        # CasCor is not importable in this test context
        with pytest.raises(WorkerError, match="CasCor codebase not found"):
            worker.connect()

    def test_connect_success_with_str_authkey(self):
        """Test connect() success path with string authkey (lines 56-71)."""
        mock_manager_instance = MagicMock()
        mock_task_queue = MagicMock()
        mock_result_queue = MagicMock()
        mock_manager_instance.get_task_queue.return_value = mock_task_queue
        mock_manager_instance.get_result_queue.return_value = mock_result_queue

        mock_manager_cls = MagicMock(return_value=mock_manager_instance)

        # Create a mock module that contains CandidateTrainingManager
        mock_module = MagicMock()
        mock_module.CandidateTrainingManager = mock_manager_cls

        worker = CandidateTrainingWorker(WorkerConfig(authkey="testkey"))

        with patch.dict(sys.modules, {"cascade_correlation.cascade_correlation": mock_module}):
            worker.connect()

        assert worker._connected is True
        assert worker.task_queue is mock_task_queue
        assert worker.result_queue is mock_result_queue
        assert worker.manager is mock_manager_instance
        mock_manager_cls.assert_called_once_with(
            address=("127.0.0.1", 50000),
            authkey=b"testkey",
        )
        mock_manager_instance.connect.assert_called_once()

    def test_connect_success_with_bytes_authkey(self):
        """Test connect() with bytes authkey skips encoding."""
        mock_manager_instance = MagicMock()
        mock_manager_instance.get_task_queue.return_value = MagicMock()
        mock_manager_instance.get_result_queue.return_value = MagicMock()

        mock_manager_cls = MagicMock(return_value=mock_manager_instance)
        mock_module = MagicMock()
        mock_module.CandidateTrainingManager = mock_manager_cls

        config = WorkerConfig(authkey="rawbytes")
        worker = CandidateTrainingWorker(config)
        # Manually set authkey to bytes to test the isinstance branch
        worker.config.authkey = b"rawbytes"

        with patch.dict(sys.modules, {"cascade_correlation.cascade_correlation": mock_module}):
            worker.connect()

        mock_manager_cls.assert_called_once_with(
            address=("127.0.0.1", 50000),
            authkey=b"rawbytes",
        )

    def test_connect_manager_failure_raises_connection_error(self):
        """Test connect() raises WorkerConnectionError when manager.connect() fails."""
        mock_manager_instance = MagicMock()
        mock_manager_instance.connect.side_effect = ConnectionRefusedError("Connection refused")

        mock_manager_cls = MagicMock(return_value=mock_manager_instance)
        mock_module = MagicMock()
        mock_module.CandidateTrainingManager = mock_manager_cls

        worker = CandidateTrainingWorker()

        with patch.dict(sys.modules, {"cascade_correlation.cascade_correlation": mock_module}):
            with pytest.raises(WorkerConnectionError, match="Failed to connect"):
                worker.connect()

    def test_start_without_connect_raises(self):
        worker = CandidateTrainingWorker()
        with pytest.raises(WorkerError, match="Not connected"):
            worker.start()

    def test_start_success_spawns_processes(self):
        """Test start() success path with mocked CasCor imports (lines 82-99)."""
        mock_network_cls = MagicMock()
        mock_network_cls._worker_loop = MagicMock()

        mock_module = MagicMock()
        mock_module.CascadeCorrelationNetwork = mock_network_cls

        worker = CandidateTrainingWorker(WorkerConfig(num_workers=3))
        worker._connected = True
        worker.task_queue = MagicMock()
        worker.result_queue = MagicMock()

        mock_process = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.Process.return_value = mock_process
        worker.ctx = mock_ctx

        with patch.dict(sys.modules, {"cascade_correlation.cascade_correlation": mock_module}):
            worker.start()

        assert mock_ctx.Process.call_count == 3
        assert mock_process.start.call_count == 3
        assert len(worker.workers) == 3

    def test_start_with_num_workers_override(self):
        """Test start() with explicit num_workers parameter override."""
        mock_network_cls = MagicMock()
        mock_network_cls._worker_loop = MagicMock()

        mock_module = MagicMock()
        mock_module.CascadeCorrelationNetwork = mock_network_cls

        worker = CandidateTrainingWorker(WorkerConfig(num_workers=1))
        worker._connected = True
        worker.task_queue = MagicMock()
        worker.result_queue = MagicMock()

        mock_process = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.Process.return_value = mock_process
        worker.ctx = mock_ctx

        with patch.dict(sys.modules, {"cascade_correlation.cascade_correlation": mock_module}):
            worker.start(num_workers=5)

        assert mock_ctx.Process.call_count == 5
        assert len(worker.workers) == 5

    def test_start_without_cascor_raises(self):
        """Test start() raises WorkerError when CasCor is not importable."""
        worker = CandidateTrainingWorker()
        worker._connected = True

        with pytest.raises(WorkerError, match="CasCor codebase not found"):
            worker.start()


class TestWorkerStop:
    def test_stop_no_workers(self):
        worker = CandidateTrainingWorker()
        worker.stop()  # Should not raise

    def test_stop_sends_sentinels(self):
        worker = CandidateTrainingWorker()
        worker._connected = True
        mock_queue = MagicMock()
        worker.task_queue = mock_queue

        mock_process = MagicMock()
        mock_process.is_alive.return_value = False
        worker.workers = [mock_process, mock_process]

        worker.stop()
        assert mock_queue.put.call_count == 2
        assert worker.workers == []

    def test_stop_terminates_unresponsive(self):
        worker = CandidateTrainingWorker()
        worker._connected = True
        mock_queue = MagicMock()
        worker.task_queue = mock_queue

        mock_process = MagicMock()
        mock_process.is_alive.return_value = True
        worker.workers = [mock_process]

        worker.stop(timeout=1)
        mock_process.terminate.assert_called_once()

    def test_stop_sentinel_send_failure(self):
        """Test stop() handles exception when sending sentinel to queue (lines 116-117)."""
        worker = CandidateTrainingWorker()
        worker._connected = True
        mock_queue = MagicMock()
        mock_queue.put.side_effect = OSError("Broken pipe")
        worker.task_queue = mock_queue

        mock_process = MagicMock()
        mock_process.is_alive.return_value = False
        worker.workers = [mock_process]

        # Should not raise even though put() fails
        worker.stop()
        assert worker.workers == []
        mock_queue.put.assert_called_once_with(None)


class TestWorkerDisconnect:
    def test_disconnect_clears_state(self):
        worker = CandidateTrainingWorker()
        worker._connected = True
        worker.manager = MagicMock()
        worker.task_queue = MagicMock()
        worker.result_queue = MagicMock()

        worker.disconnect()
        assert worker.manager is None
        assert worker.task_queue is None
        assert worker.result_queue is None
        assert worker._connected is False

    def test_disconnect_stops_workers_first(self):
        worker = CandidateTrainingWorker()
        worker._connected = True
        worker.task_queue = MagicMock()

        mock_process = MagicMock()
        mock_process.is_alive.return_value = False
        worker.workers = [mock_process]

        worker.disconnect()
        assert worker.workers == []


class TestWorkerContextManager:
    """Tests for __enter__ and __exit__ context manager protocol (lines 149-154)."""

    def test_enter_calls_connect(self):
        """Test __enter__ calls connect() and returns self (lines 150-151)."""
        worker = CandidateTrainingWorker()
        with patch.object(worker, "connect") as mock_connect:
            result = worker.__enter__()
        mock_connect.assert_called_once()
        assert result is worker

    def test_exit_calls_disconnect(self):
        """Test __exit__ calls disconnect() (line 154)."""
        worker = CandidateTrainingWorker()
        with patch.object(worker, "disconnect") as mock_disconnect:
            worker.__exit__(None, None, None)
        mock_disconnect.assert_called_once()

    def test_context_manager_with_statement(self):
        """Test full with-statement usage of context manager."""
        mock_manager_instance = MagicMock()
        mock_manager_instance.get_task_queue.return_value = MagicMock()
        mock_manager_instance.get_result_queue.return_value = MagicMock()

        mock_manager_cls = MagicMock(return_value=mock_manager_instance)
        mock_module = MagicMock()
        mock_module.CandidateTrainingManager = mock_manager_cls

        with patch.dict(sys.modules, {"cascade_correlation.cascade_correlation": mock_module}):
            with CandidateTrainingWorker() as w:
                assert w._connected is True
                assert w.manager is mock_manager_instance
            # After exiting context, state should be cleared
            assert w._connected is False
            assert w.manager is None

    def test_exit_with_exception(self):
        """Test __exit__ still calls disconnect when exception occurred."""
        worker = CandidateTrainingWorker()
        with patch.object(worker, "disconnect") as mock_disconnect:
            worker.__exit__(ValueError, ValueError("test"), None)
        mock_disconnect.assert_called_once()
