"""Tests for the CLI entry point."""

import signal
import sys
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from juniper_cascor_worker.cli import main


class TestCLIMain:
    """Tests for the main() CLI function — legacy mode path."""

    @patch("juniper_cascor_worker.cli._run_legacy")
    @patch("juniper_cascor_worker.cli.argparse.ArgumentParser.parse_args")
    def test_main_default_args(self, mock_parse_args, mock_run_legacy):
        """Test main() with --legacy flag runs the legacy worker lifecycle."""
        mock_args = MagicMock()
        mock_args.legacy = True
        mock_args.log_level = "INFO"
        mock_args.cascor_path = None
        mock_parse_args.return_value = mock_args

        main()

        mock_run_legacy.assert_called_once_with(mock_args)

    @patch("juniper_cascor_worker.cli._run_legacy")
    @patch("juniper_cascor_worker.cli.argparse.ArgumentParser.parse_args")
    def test_main_with_cascor_path(self, mock_parse_args, mock_run_legacy):
        """Test main() with --cascor-path inserts the path into sys.path."""
        mock_args = MagicMock()
        mock_args.legacy = True
        mock_args.log_level = "DEBUG"
        mock_args.cascor_path = "/opt/cascor/src"
        mock_parse_args.return_value = mock_args

        with patch.object(sys, "path", new_callable=list) as mock_path:
            mock_path.extend(sys.path)
            main()
            assert "/opt/cascor/src" in mock_path

    @patch("juniper_cascor_worker.cli.signal.signal")
    @patch("juniper_cascor_worker.cli.argparse.ArgumentParser.parse_args")
    def test_main_config_values(self, mock_parse_args, mock_signal_fn):
        """Test that _run_legacy passes correct config values to WorkerConfig."""
        mock_args = MagicMock()
        mock_args.legacy = True
        mock_args.manager_host = "10.0.0.5"
        mock_args.manager_port = 9999
        mock_args.authkey = "mykey"
        mock_args.workers = 8
        mock_args.mp_context = "spawn"
        mock_args.log_level = "WARNING"
        mock_args.cascor_path = None
        mock_parse_args.return_value = mock_args

        with patch("juniper_cascor_worker.config.WorkerConfig.validate"), patch("juniper_cascor_worker.worker.CandidateTrainingWorker.__init__", return_value=None) as mock_init, patch("juniper_cascor_worker.worker.CandidateTrainingWorker.connect"), patch("juniper_cascor_worker.worker.CandidateTrainingWorker.start"), patch("juniper_cascor_worker.worker.CandidateTrainingWorker.disconnect"), patch("juniper_cascor_worker.cli.threading.Event") as mock_event_cls:
            mock_event = MagicMock()
            mock_event.wait.side_effect = KeyboardInterrupt
            mock_event_cls.return_value = mock_event

            main()

            # Verify CandidateTrainingWorker was constructed with a config
            mock_init.assert_called_once()
            config_arg = mock_init.call_args[0][0]
            assert config_arg.manager_host == "10.0.0.5"
            assert config_arg.manager_port == 9999
            assert config_arg.authkey == "mykey"
            assert config_arg.num_workers == 8
            assert config_arg.mp_context == "spawn"

    @patch("juniper_cascor_worker.cli.signal.signal")
    @patch("juniper_cascor_worker.cli.argparse.ArgumentParser.parse_args")
    def test_main_shutdown_via_flag(self, mock_parse_args, mock_signal_fn):
        """Test that the shutdown_event.wait completes and disconnect is called."""
        mock_args = MagicMock()
        mock_args.legacy = True
        mock_args.manager_host = "127.0.0.1"
        mock_args.manager_port = 50000
        mock_args.authkey = "juniper"
        mock_args.workers = 1
        mock_args.mp_context = "forkserver"
        mock_args.log_level = "INFO"
        mock_args.cascor_path = None
        mock_parse_args.return_value = mock_args

        with patch("juniper_cascor_worker.config.WorkerConfig.validate"), patch("juniper_cascor_worker.worker.CandidateTrainingWorker.__init__", return_value=None), patch("juniper_cascor_worker.worker.CandidateTrainingWorker.connect"), patch("juniper_cascor_worker.worker.CandidateTrainingWorker.start"), patch("juniper_cascor_worker.worker.CandidateTrainingWorker.disconnect") as mock_disconnect, patch("juniper_cascor_worker.cli.threading.Event") as mock_event_cls:
            mock_event = MagicMock()
            mock_event.wait.return_value = None  # Simulate shutdown_event being set
            mock_event_cls.return_value = mock_event

            main()

            mock_disconnect.assert_called_once()

    @patch("juniper_cascor_worker.cli.signal.signal")
    @patch("juniper_cascor_worker.cli.argparse.ArgumentParser.parse_args")
    def test_main_keyboard_interrupt_in_try(self, mock_parse_args, mock_signal_fn):
        """Test that KeyboardInterrupt during legacy mode is handled gracefully."""
        mock_args = MagicMock()
        mock_args.legacy = True
        mock_args.manager_host = "127.0.0.1"
        mock_args.manager_port = 50000
        mock_args.authkey = "juniper"
        mock_args.workers = 1
        mock_args.mp_context = "forkserver"
        mock_args.log_level = "INFO"
        mock_args.cascor_path = None
        mock_parse_args.return_value = mock_args

        with patch("juniper_cascor_worker.config.WorkerConfig.validate"), patch("juniper_cascor_worker.worker.CandidateTrainingWorker.__init__", return_value=None), patch("juniper_cascor_worker.worker.CandidateTrainingWorker.connect", side_effect=KeyboardInterrupt), patch("juniper_cascor_worker.worker.CandidateTrainingWorker.disconnect") as mock_disconnect:
            main()

            mock_disconnect.assert_called_once()


class TestCLISignalHandler:
    """Tests for the signal handler defined inside _run_legacy()."""

    @patch("juniper_cascor_worker.cli.argparse.ArgumentParser.parse_args")
    def test_signal_handler_first_call_sets_flag(self, mock_parse_args):
        """Test that first signal sets shutdown_event but doesn't exit."""
        mock_args = MagicMock()
        mock_args.legacy = True
        mock_args.manager_host = "127.0.0.1"
        mock_args.manager_port = 50000
        mock_args.authkey = "juniper"
        mock_args.workers = 1
        mock_args.mp_context = "forkserver"
        mock_args.log_level = "INFO"
        mock_args.cascor_path = None
        mock_parse_args.return_value = mock_args

        # Capture the signal handler that _run_legacy registers
        captured_handlers = {}

        def capture_signal(signum, handler):
            captured_handlers[signum] = handler

        with patch("juniper_cascor_worker.cli.signal.signal", side_effect=capture_signal), patch("juniper_cascor_worker.config.WorkerConfig.validate"), patch("juniper_cascor_worker.worker.CandidateTrainingWorker.__init__", return_value=None), patch("juniper_cascor_worker.worker.CandidateTrainingWorker.connect"), patch("juniper_cascor_worker.worker.CandidateTrainingWorker.start"), patch("juniper_cascor_worker.worker.CandidateTrainingWorker.disconnect"), patch("juniper_cascor_worker.cli.threading.Event") as mock_event_cls:
            mock_event = MagicMock()
            mock_event.wait.return_value = None
            mock_event.is_set.return_value = False
            mock_event_cls.return_value = mock_event

            main()

        # Both SIGINT and SIGTERM should have handlers registered
        assert signal.SIGINT in captured_handlers
        assert signal.SIGTERM in captured_handlers

        # Call the handler once - should not raise SystemExit
        handler = captured_handlers[signal.SIGINT]
        handler(signal.SIGINT, None)  # First call sets flag

    @patch("juniper_cascor_worker.cli.argparse.ArgumentParser.parse_args")
    def test_signal_handler_second_call_exits(self, mock_parse_args):
        """Test that second signal call forces sys.exit(1)."""
        mock_args = MagicMock()
        mock_args.legacy = True
        mock_args.manager_host = "127.0.0.1"
        mock_args.manager_port = 50000
        mock_args.authkey = "juniper"
        mock_args.workers = 1
        mock_args.mp_context = "forkserver"
        mock_args.log_level = "INFO"
        mock_args.cascor_path = None
        mock_parse_args.return_value = mock_args

        captured_handlers = {}

        def capture_signal(signum, handler):
            captured_handlers[signum] = handler

        import threading

        real_event = threading.Event()

        with patch("juniper_cascor_worker.cli.signal.signal", side_effect=capture_signal), patch("juniper_cascor_worker.config.WorkerConfig.validate"), patch("juniper_cascor_worker.worker.CandidateTrainingWorker.__init__", return_value=None), patch("juniper_cascor_worker.worker.CandidateTrainingWorker.connect"), patch("juniper_cascor_worker.worker.CandidateTrainingWorker.start"), patch("juniper_cascor_worker.worker.CandidateTrainingWorker.disconnect"), patch("juniper_cascor_worker.cli.threading.Event", return_value=real_event):
            # Pre-set the event so shutdown_event.wait() returns immediately
            real_event.set()

            main()

        # Reset the event so the handler can track state correctly
        real_event.clear()

        handler = captured_handlers[signal.SIGINT]
        # First call sets shutdown_event
        handler(signal.SIGINT, None)
        assert real_event.is_set()
        # Second call should force exit because is_set() is True
        with pytest.raises(SystemExit) as exc_info:
            handler(signal.SIGINT, None)
        assert exc_info.value.code == 1

    @patch("juniper_cascor_worker.cli.argparse.ArgumentParser.parse_args")
    def test_sigterm_handler_registered(self, mock_parse_args):
        """Test that SIGTERM handler is registered and works the same as SIGINT."""
        mock_args = MagicMock()
        mock_args.legacy = True
        mock_args.manager_host = "127.0.0.1"
        mock_args.manager_port = 50000
        mock_args.authkey = "juniper"
        mock_args.workers = 1
        mock_args.mp_context = "forkserver"
        mock_args.log_level = "INFO"
        mock_args.cascor_path = None
        mock_parse_args.return_value = mock_args

        captured_handlers = {}

        def capture_signal(signum, handler):
            captured_handlers[signum] = handler

        import threading

        real_event = threading.Event()

        with patch("juniper_cascor_worker.cli.signal.signal", side_effect=capture_signal), patch("juniper_cascor_worker.config.WorkerConfig.validate"), patch("juniper_cascor_worker.worker.CandidateTrainingWorker.__init__", return_value=None), patch("juniper_cascor_worker.worker.CandidateTrainingWorker.connect"), patch("juniper_cascor_worker.worker.CandidateTrainingWorker.start"), patch("juniper_cascor_worker.worker.CandidateTrainingWorker.disconnect"), patch("juniper_cascor_worker.cli.threading.Event", return_value=real_event):
            real_event.set()  # So wait() returns immediately

            main()

        real_event.clear()

        handler = captured_handlers[signal.SIGTERM]
        handler(signal.SIGTERM, None)  # First call sets the event
        with pytest.raises(SystemExit):
            handler(signal.SIGTERM, None)  # Second call exits


class TestCLILogging:
    """Tests for logging configuration in main()."""

    @patch("juniper_cascor_worker.cli.argparse.ArgumentParser.parse_args")
    def test_logging_basicconfig_called(self, mock_parse_args):
        """Test that logging.basicConfig is called with correct level."""
        mock_args = MagicMock()
        mock_args.legacy = True
        mock_args.manager_host = "127.0.0.1"
        mock_args.manager_port = 50000
        mock_args.authkey = "juniper"
        mock_args.workers = 1
        mock_args.mp_context = "forkserver"
        mock_args.log_level = "WARNING"
        mock_args.cascor_path = None
        mock_parse_args.return_value = mock_args

        import logging

        with patch("juniper_cascor_worker.cli.logging") as mock_logging, patch("juniper_cascor_worker.cli._run_legacy"):
            mock_logging.WARNING = logging.WARNING
            mock_logging.getLogger.return_value = MagicMock()

            main()
            mock_logging.basicConfig.assert_called_once()


@pytest.mark.unit
class TestCLIWebSocketMode:
    """Tests for the WebSocket mode CLI path."""

    @patch("juniper_cascor_worker.cli._run_websocket")
    @patch("juniper_cascor_worker.cli.argparse.ArgumentParser.parse_args")
    def test_websocket_mode_default(self, mock_parse_args, mock_run_ws):
        """Without --legacy, WebSocket mode is used."""
        mock_args = MagicMock()
        mock_args.legacy = False
        mock_args.log_level = "INFO"
        mock_args.cascor_path = None
        mock_parse_args.return_value = mock_args

        main()

        mock_run_ws.assert_called_once_with(mock_args)

    @patch("juniper_cascor_worker.cli._run_legacy")
    @patch("juniper_cascor_worker.cli.argparse.ArgumentParser.parse_args")
    def test_legacy_mode_flag(self, mock_parse_args, mock_run_legacy):
        """With --legacy, legacy mode is used."""
        mock_args = MagicMock()
        mock_args.legacy = True
        mock_args.log_level = "INFO"
        mock_args.cascor_path = None
        mock_parse_args.return_value = mock_args

        main()

        mock_run_legacy.assert_called_once_with(mock_args)

    @patch("juniper_cascor_worker.cli.asyncio.run")
    @patch("juniper_cascor_worker.cli.signal.signal")
    @patch("juniper_cascor_worker.cli.argparse.ArgumentParser.parse_args")
    def test_server_url_arg(self, mock_parse_args, mock_signal_fn, mock_asyncio_run):
        """--server-url passed to config."""
        mock_args = MagicMock()
        mock_args.legacy = False
        mock_args.log_level = "INFO"
        mock_args.cascor_path = None
        mock_args.server_url = "ws://myhost:9999/ws/v1/workers"
        mock_args.api_key = None
        mock_args.heartbeat_interval = 10.0
        mock_args.tls_cert = None
        mock_args.tls_key = None
        mock_args.tls_ca = None
        mock_parse_args.return_value = mock_args

        with patch("juniper_cascor_worker.config.WorkerConfig.validate"), patch("juniper_cascor_worker.worker.CascorWorkerAgent.__init__", return_value=None) as mock_init:
            main()

            # _run_websocket creates WorkerConfig with server_url from args
            # then passes it to CascorWorkerAgent — verify the agent was constructed
            mock_init.assert_called_once()
            config_arg = mock_init.call_args[0][0]
            assert config_arg.server_url == "ws://myhost:9999/ws/v1/workers"

    @patch("juniper_cascor_worker.cli.asyncio.run")
    @patch("juniper_cascor_worker.cli.signal.signal")
    @patch("juniper_cascor_worker.cli.argparse.ArgumentParser.parse_args")
    def test_api_key_arg(self, mock_parse_args, mock_signal_fn, mock_asyncio_run):
        """--api-key passed to config."""
        mock_args = MagicMock()
        mock_args.legacy = False
        mock_args.log_level = "INFO"
        mock_args.cascor_path = None
        mock_args.server_url = "ws://localhost:8200/ws/v1/workers"
        mock_args.api_key = "my-secret-key"
        mock_args.heartbeat_interval = 10.0
        mock_args.tls_cert = None
        mock_args.tls_key = None
        mock_args.tls_ca = None
        mock_parse_args.return_value = mock_args

        with patch("juniper_cascor_worker.config.WorkerConfig.validate"), patch("juniper_cascor_worker.worker.CascorWorkerAgent.__init__", return_value=None) as mock_init:
            main()

            config_arg = mock_init.call_args[0][0]
            assert config_arg.api_key == "my-secret-key"

    @patch("juniper_cascor_worker.cli._run_websocket")
    @patch("juniper_cascor_worker.cli.argparse.ArgumentParser.parse_args")
    def test_cascor_path_added_to_sys_path(self, mock_parse_args, mock_run_ws):
        """--cascor-path inserts into sys.path."""
        mock_args = MagicMock()
        mock_args.legacy = False
        mock_args.log_level = "INFO"
        mock_args.cascor_path = "/opt/juniper-cascor/src"
        mock_parse_args.return_value = mock_args

        with patch.object(sys, "path", new_callable=list) as mock_path:
            mock_path.extend(sys.path)
            main()
            assert "/opt/juniper-cascor/src" in mock_path
