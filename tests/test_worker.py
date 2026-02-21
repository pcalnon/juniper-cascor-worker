"""Tests for CandidateTrainingWorker."""

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

    def test_start_without_connect_raises(self):
        worker = CandidateTrainingWorker()
        with pytest.raises(WorkerError, match="Not connected"):
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
