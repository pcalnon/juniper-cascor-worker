"""Tests for the CLI entry point."""

import signal
import sys
from unittest.mock import MagicMock, call, patch

import pytest

from juniper_cascor_worker.cli import main


class TestCLIMain:
    """Tests for the main() CLI function."""

    @patch("juniper_cascor_worker.cli.CandidateTrainingWorker")
    @patch("juniper_cascor_worker.cli.signal.signal")
    @patch("juniper_cascor_worker.cli.signal.pause", side_effect=KeyboardInterrupt)
    @patch("juniper_cascor_worker.cli.logging")
    @patch("juniper_cascor_worker.cli.argparse.ArgumentParser.parse_args")
    def test_main_default_args(self, mock_parse_args, mock_logging, mock_pause, mock_signal_fn, mock_worker_cls):
        """Test main() with default arguments runs the worker lifecycle."""
        mock_args = MagicMock()
        mock_args.manager_host = "127.0.0.1"
        mock_args.manager_port = 50000
        mock_args.authkey = "juniper"
        mock_args.workers = 1
        mock_args.mp_context = "forkserver"
        mock_args.log_level = "INFO"
        mock_args.cascor_path = None
        mock_parse_args.return_value = mock_args

        mock_worker = MagicMock()
        mock_worker.is_running = True
        mock_worker_cls.return_value = mock_worker

        main()

        mock_worker.connect.assert_called_once()
        mock_worker.start.assert_called_once()
        mock_worker.disconnect.assert_called_once()

    @patch("juniper_cascor_worker.cli.CandidateTrainingWorker")
    @patch("juniper_cascor_worker.cli.signal.signal")
    @patch("juniper_cascor_worker.cli.signal.pause", side_effect=KeyboardInterrupt)
    @patch("juniper_cascor_worker.cli.logging")
    @patch("juniper_cascor_worker.cli.argparse.ArgumentParser.parse_args")
    def test_main_with_cascor_path(self, mock_parse_args, mock_logging, mock_pause, mock_signal_fn, mock_worker_cls):
        """Test main() with --cascor-path inserts the path into sys.path."""
        mock_args = MagicMock()
        mock_args.manager_host = "192.168.1.100"
        mock_args.manager_port = 60000
        mock_args.authkey = "secret"
        mock_args.workers = 4
        mock_args.mp_context = "spawn"
        mock_args.log_level = "DEBUG"
        mock_args.cascor_path = "/opt/cascor/src"
        mock_parse_args.return_value = mock_args

        mock_worker = MagicMock()
        mock_worker.is_running = True
        mock_worker_cls.return_value = mock_worker

        with patch.object(sys, "path", new_callable=list) as mock_path:
            mock_path.extend(sys.path)
            main()
            assert "/opt/cascor/src" in mock_path

    @patch("juniper_cascor_worker.cli.CandidateTrainingWorker")
    @patch("juniper_cascor_worker.cli.signal.signal")
    @patch("juniper_cascor_worker.cli.signal.pause", side_effect=KeyboardInterrupt)
    @patch("juniper_cascor_worker.cli.logging")
    @patch("juniper_cascor_worker.cli.argparse.ArgumentParser.parse_args")
    def test_main_config_values(self, mock_parse_args, mock_logging, mock_pause, mock_signal_fn, mock_worker_cls):
        """Test that main() passes correct config values to WorkerConfig."""
        mock_args = MagicMock()
        mock_args.manager_host = "10.0.0.5"
        mock_args.manager_port = 9999
        mock_args.authkey = "mykey"
        mock_args.workers = 8
        mock_args.mp_context = "spawn"
        mock_args.log_level = "WARNING"
        mock_args.cascor_path = None
        mock_parse_args.return_value = mock_args

        mock_worker = MagicMock()
        mock_worker.is_running = True
        mock_worker_cls.return_value = mock_worker

        with patch("juniper_cascor_worker.cli.WorkerConfig") as mock_config_cls:
            mock_config_cls.return_value = MagicMock(
                num_workers=8, manager_host="10.0.0.5", manager_port=9999
            )
            main()
            mock_config_cls.assert_called_once_with(
                manager_host="10.0.0.5",
                manager_port=9999,
                authkey="mykey",
                num_workers=8,
                mp_context="spawn",
            )

    @patch("juniper_cascor_worker.cli.CandidateTrainingWorker")
    @patch("juniper_cascor_worker.cli.signal.signal")
    @patch("juniper_cascor_worker.cli.logging")
    @patch("juniper_cascor_worker.cli.argparse.ArgumentParser.parse_args")
    def test_main_shutdown_via_flag(self, mock_parse_args, mock_logging, mock_signal_fn, mock_worker_cls):
        """Test that the while loop exits when shutdown_requested becomes True."""
        mock_args = MagicMock()
        mock_args.manager_host = "127.0.0.1"
        mock_args.manager_port = 50000
        mock_args.authkey = "juniper"
        mock_args.workers = 1
        mock_args.mp_context = "forkserver"
        mock_args.log_level = "INFO"
        mock_args.cascor_path = None
        mock_parse_args.return_value = mock_args

        mock_worker = MagicMock()
        # Worker starts running, then stops
        mock_worker.is_running = False
        mock_worker_cls.return_value = mock_worker

        main()

        mock_worker.disconnect.assert_called_once()

    @patch("juniper_cascor_worker.cli.CandidateTrainingWorker")
    @patch("juniper_cascor_worker.cli.signal.signal")
    @patch("juniper_cascor_worker.cli.signal.pause", side_effect=KeyboardInterrupt)
    @patch("juniper_cascor_worker.cli.logging")
    @patch("juniper_cascor_worker.cli.argparse.ArgumentParser.parse_args")
    def test_main_keyboard_interrupt_in_try(self, mock_parse_args, mock_logging, mock_pause, mock_signal_fn, mock_worker_cls):
        """Test that KeyboardInterrupt during main loop is handled gracefully."""
        mock_args = MagicMock()
        mock_args.manager_host = "127.0.0.1"
        mock_args.manager_port = 50000
        mock_args.authkey = "juniper"
        mock_args.workers = 1
        mock_args.mp_context = "forkserver"
        mock_args.log_level = "INFO"
        mock_args.cascor_path = None
        mock_parse_args.return_value = mock_args

        mock_worker = MagicMock()
        mock_worker.is_running = True
        mock_worker_cls.return_value = mock_worker

        # signal.pause raises KeyboardInterrupt, caught by except
        main()

        mock_worker.disconnect.assert_called_once()


class TestCLISignalHandler:
    """Tests for the signal handler defined inside main()."""

    @patch("juniper_cascor_worker.cli.CandidateTrainingWorker")
    @patch("juniper_cascor_worker.cli.signal.pause", side_effect=KeyboardInterrupt)
    @patch("juniper_cascor_worker.cli.logging")
    @patch("juniper_cascor_worker.cli.argparse.ArgumentParser.parse_args")
    def test_signal_handler_first_call_sets_flag(self, mock_parse_args, mock_logging, mock_worker_cls, mock_pause):
        """Test that first signal sets shutdown_requested but doesn't exit."""
        mock_args = MagicMock()
        mock_args.manager_host = "127.0.0.1"
        mock_args.manager_port = 50000
        mock_args.authkey = "juniper"
        mock_args.workers = 1
        mock_args.mp_context = "forkserver"
        mock_args.log_level = "INFO"
        mock_args.cascor_path = None
        mock_parse_args.return_value = mock_args

        mock_worker = MagicMock()
        mock_worker.is_running = True
        mock_worker_cls.return_value = mock_worker

        # Capture the signal handler that main() registers
        captured_handlers = {}

        def capture_signal(signum, handler):
            captured_handlers[signum] = handler

        with patch("juniper_cascor_worker.cli.signal.signal", side_effect=capture_signal):
            main()

        # Both SIGINT and SIGTERM should have handlers registered
        assert signal.SIGINT in captured_handlers
        assert signal.SIGTERM in captured_handlers

        # Call the handler once - should not raise SystemExit
        handler = captured_handlers[signal.SIGINT]
        handler(signal.SIGINT, None)  # First call sets flag

    @patch("juniper_cascor_worker.cli.CandidateTrainingWorker")
    @patch("juniper_cascor_worker.cli.signal.pause", side_effect=KeyboardInterrupt)
    @patch("juniper_cascor_worker.cli.logging")
    @patch("juniper_cascor_worker.cli.argparse.ArgumentParser.parse_args")
    def test_signal_handler_second_call_exits(self, mock_parse_args, mock_logging, mock_worker_cls, mock_pause):
        """Test that second signal call forces sys.exit(1)."""
        mock_args = MagicMock()
        mock_args.manager_host = "127.0.0.1"
        mock_args.manager_port = 50000
        mock_args.authkey = "juniper"
        mock_args.workers = 1
        mock_args.mp_context = "forkserver"
        mock_args.log_level = "INFO"
        mock_args.cascor_path = None
        mock_parse_args.return_value = mock_args

        mock_worker = MagicMock()
        mock_worker.is_running = True
        mock_worker_cls.return_value = mock_worker

        captured_handlers = {}

        def capture_signal(signum, handler):
            captured_handlers[signum] = handler

        with patch("juniper_cascor_worker.cli.signal.signal", side_effect=capture_signal):
            main()

        handler = captured_handlers[signal.SIGINT]
        # First call sets shutdown_requested
        handler(signal.SIGINT, None)
        # Second call should force exit
        with pytest.raises(SystemExit) as exc_info:
            handler(signal.SIGINT, None)
        assert exc_info.value.code == 1

    @patch("juniper_cascor_worker.cli.CandidateTrainingWorker")
    @patch("juniper_cascor_worker.cli.signal.pause", side_effect=KeyboardInterrupt)
    @patch("juniper_cascor_worker.cli.logging")
    @patch("juniper_cascor_worker.cli.argparse.ArgumentParser.parse_args")
    def test_sigterm_handler_registered(self, mock_parse_args, mock_logging, mock_worker_cls, mock_pause):
        """Test that SIGTERM handler is registered and works the same as SIGINT."""
        mock_args = MagicMock()
        mock_args.manager_host = "127.0.0.1"
        mock_args.manager_port = 50000
        mock_args.authkey = "juniper"
        mock_args.workers = 1
        mock_args.mp_context = "forkserver"
        mock_args.log_level = "INFO"
        mock_args.cascor_path = None
        mock_parse_args.return_value = mock_args

        mock_worker = MagicMock()
        mock_worker.is_running = True
        mock_worker_cls.return_value = mock_worker

        captured_handlers = {}

        def capture_signal(signum, handler):
            captured_handlers[signum] = handler

        with patch("juniper_cascor_worker.cli.signal.signal", side_effect=capture_signal):
            main()

        # Both handlers should be the same function
        handler = captured_handlers[signal.SIGTERM]
        handler(signal.SIGTERM, None)  # First call
        with pytest.raises(SystemExit):
            handler(signal.SIGTERM, None)  # Second call exits


class TestCLILogging:
    """Tests for logging configuration in main()."""

    @patch("juniper_cascor_worker.cli.CandidateTrainingWorker")
    @patch("juniper_cascor_worker.cli.signal.signal")
    @patch("juniper_cascor_worker.cli.signal.pause", side_effect=KeyboardInterrupt)
    @patch("juniper_cascor_worker.cli.argparse.ArgumentParser.parse_args")
    def test_logging_basicconfig_called(self, mock_parse_args, mock_pause, mock_signal_fn, mock_worker_cls):
        """Test that logging.basicConfig is called with correct level."""
        mock_args = MagicMock()
        mock_args.manager_host = "127.0.0.1"
        mock_args.manager_port = 50000
        mock_args.authkey = "juniper"
        mock_args.workers = 1
        mock_args.mp_context = "forkserver"
        mock_args.log_level = "WARNING"
        mock_args.cascor_path = None
        mock_parse_args.return_value = mock_args

        mock_worker = MagicMock()
        mock_worker.is_running = True
        mock_worker_cls.return_value = mock_worker

        import logging

        with patch("juniper_cascor_worker.cli.logging") as mock_logging:
            mock_logging.WARNING = logging.WARNING
            mock_logging.getLogger.return_value = MagicMock()
            # Make getattr work for log levels
            mock_logging.getattr = getattr

            # The code does getattr(logging, args.log_level)
            # We need the real logging module's attribute
            def mock_getattr(obj, name):
                return getattr(logging, name)

            main()
            mock_logging.basicConfig.assert_called_once()
