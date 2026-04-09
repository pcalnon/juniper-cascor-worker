"""Tests for WorkerConnection WebSocket client."""

import asyncio
import json
import ssl
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from juniper_cascor_worker.exceptions import WorkerConnectionError
from juniper_cascor_worker.ws_connection import WorkerConnection


def _make_mock_ws(state_name="OPEN"):
    """Create a mock WebSocket connection with protocol state."""
    mock_ws = AsyncMock()
    mock_ws.protocol = MagicMock()
    mock_ws.protocol.state = MagicMock()
    mock_ws.protocol.state.name = state_name
    return mock_ws


@pytest.mark.unit
class TestConnect:
    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Mock websockets.connect, verify headers include X-API-Key."""
        mock_ws = _make_mock_ws()
        conn = WorkerConnection("ws://localhost:8200/ws/v1/workers", api_key="test-key-123")

        with patch("juniper_cascor_worker.ws_connection.websockets.connect", new_callable=AsyncMock, return_value=mock_ws) as mock_connect:
            await conn.connect()

        assert conn.connected is True
        call_kwargs = mock_connect.call_args
        assert call_kwargs.kwargs["additional_headers"]["X-API-Key"] == "test-key-123"
        assert call_kwargs.kwargs["origin"] is None

    @pytest.mark.asyncio
    async def test_connect_failure_raises(self):
        """Mock connect to raise, verify WorkerConnectionError."""
        conn = WorkerConnection("ws://localhost:8200/ws/v1/workers")

        with patch("juniper_cascor_worker.ws_connection.websockets.connect", new_callable=AsyncMock, side_effect=ConnectionRefusedError("refused")):
            with pytest.raises(WorkerConnectionError, match="Failed to connect"):
                await conn.connect()


@pytest.mark.unit
class TestConnectWithRetry:
    @pytest.mark.asyncio
    async def test_connect_with_retry_success(self):
        """Fail first attempt, succeed on second."""
        mock_ws = _make_mock_ws()
        conn = WorkerConnection("ws://localhost:8200/ws/v1/workers")

        call_count = 0

        async def connect_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionRefusedError("refused")
            return mock_ws

        with patch("juniper_cascor_worker.ws_connection.websockets.connect", new_callable=AsyncMock, side_effect=connect_side_effect):
            with patch("juniper_cascor_worker.ws_connection.asyncio.sleep", new_callable=AsyncMock):
                await conn.connect_with_retry(backoff_base=0.01, backoff_max=0.1, max_retries=3)

        assert conn.connected is True
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_connect_with_retry_max_retries_exceeded(self):
        """All attempts fail, raises WorkerConnectionError."""
        conn = WorkerConnection("ws://localhost:8200/ws/v1/workers")

        with patch("juniper_cascor_worker.ws_connection.websockets.connect", new_callable=AsyncMock, side_effect=ConnectionRefusedError("refused")):
            with patch("juniper_cascor_worker.ws_connection.asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(WorkerConnectionError, match="Failed to connect"):
                    await conn.connect_with_retry(backoff_base=0.01, backoff_max=0.1, max_retries=2)


@pytest.mark.unit
class TestSend:
    @pytest.mark.asyncio
    async def test_send_json(self):
        """Mock ws.send, verify JSON encoding."""
        mock_ws = _make_mock_ws()
        conn = WorkerConnection("ws://localhost:8200/ws/v1/workers")
        conn._ws = mock_ws

        msg = {"type": "register", "worker_id": "abc"}
        await conn.send_json(msg)

        mock_ws.send.assert_awaited_once_with(json.dumps(msg))

    @pytest.mark.asyncio
    async def test_send_bytes(self):
        """Mock ws.send, verify bytes sent."""
        mock_ws = _make_mock_ws()
        conn = WorkerConnection("ws://localhost:8200/ws/v1/workers")
        conn._ws = mock_ws

        data = b"\x00\x01\x02\x03"
        await conn.send_bytes(data)

        mock_ws.send.assert_awaited_once_with(data)

    @pytest.mark.asyncio
    async def test_send_when_disconnected_raises(self):
        """Not connected -> WorkerConnectionError."""
        conn = WorkerConnection("ws://localhost:8200/ws/v1/workers")

        with pytest.raises(WorkerConnectionError, match="Not connected"):
            await conn.send_json({"type": "test"})

        with pytest.raises(WorkerConnectionError, match="Not connected"):
            await conn.send_bytes(b"data")


@pytest.mark.unit
class TestReceive:
    @pytest.mark.asyncio
    async def test_receive_text(self):
        """Mock ws.recv returning string."""
        mock_ws = _make_mock_ws()
        mock_ws.recv.return_value = '{"type": "ack"}'
        conn = WorkerConnection("ws://localhost:8200/ws/v1/workers")
        conn._ws = mock_ws

        result = await conn.receive()
        assert result == '{"type": "ack"}'
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_receive_bytes(self):
        """Mock ws.recv returning bytes."""
        mock_ws = _make_mock_ws()
        mock_ws.recv.return_value = b"\x00\x01\x02"
        conn = WorkerConnection("ws://localhost:8200/ws/v1/workers")
        conn._ws = mock_ws

        result = await conn.receive()
        assert result == b"\x00\x01\x02"
        assert isinstance(result, bytes)

    @pytest.mark.asyncio
    async def test_receive_json(self):
        """Mock ws.recv returning JSON string."""
        mock_ws = _make_mock_ws()
        mock_ws.recv.return_value = '{"type": "registration_ack", "status": "ok"}'
        conn = WorkerConnection("ws://localhost:8200/ws/v1/workers")
        conn._ws = mock_ws

        result = await conn.receive_json()
        assert result == {"type": "registration_ack", "status": "ok"}

    @pytest.mark.asyncio
    async def test_receive_json_binary_raises(self):
        """Binary message -> WorkerConnectionError."""
        mock_ws = _make_mock_ws()
        mock_ws.recv.return_value = b"\x00\x01\x02"
        conn = WorkerConnection("ws://localhost:8200/ws/v1/workers")
        conn._ws = mock_ws

        with pytest.raises(WorkerConnectionError, match="Expected text message, got binary"):
            await conn.receive_json()

    @pytest.mark.asyncio
    async def test_receive_bytes_text_raises(self):
        """Text message -> WorkerConnectionError."""
        mock_ws = _make_mock_ws()
        mock_ws.recv.return_value = "some text"
        conn = WorkerConnection("ws://localhost:8200/ws/v1/workers")
        conn._ws = mock_ws

        with pytest.raises(WorkerConnectionError, match="Expected binary message, got text"):
            await conn.receive_bytes()


@pytest.mark.unit
class TestClose:
    @pytest.mark.asyncio
    async def test_close(self):
        """Verify close is called on the underlying WebSocket."""
        mock_ws = _make_mock_ws()
        conn = WorkerConnection("ws://localhost:8200/ws/v1/workers")
        conn._ws = mock_ws

        await conn.close()

        mock_ws.close.assert_awaited_once()
        assert conn._ws is None


@pytest.mark.unit
class TestSSLContext:
    def test_ssl_context_wss(self):
        """wss:// URL builds SSLContext."""
        conn = WorkerConnection("wss://secure.example.com/ws/v1/workers")

        with patch("juniper_cascor_worker.ws_connection.ssl.create_default_context") as mock_create:
            mock_ctx = MagicMock(spec=ssl.SSLContext)
            mock_create.return_value = mock_ctx

            result = conn._build_ssl_context()

        assert result is mock_ctx
        mock_create.assert_called_once()

    def test_ssl_context_ws_none(self):
        """ws:// URL returns None."""
        conn = WorkerConnection("ws://localhost:8200/ws/v1/workers")
        result = conn._build_ssl_context()
        assert result is None


@pytest.mark.unit
class TestReceiveTimeout:
    """Tests for the receive_timeout feature."""

    @pytest.mark.asyncio
    async def test_receive_timeout_none_by_default(self):
        """Default receive_timeout is None (no timeout)."""
        conn = WorkerConnection("ws://localhost:8200/ws/v1/workers")
        assert conn._receive_timeout is None

    @pytest.mark.asyncio
    async def test_receive_timeout_configured(self):
        """receive_timeout is stored when passed to constructor."""
        conn = WorkerConnection("ws://localhost:8200/ws/v1/workers", receive_timeout=30.0)
        assert conn._receive_timeout == 30.0

    @pytest.mark.asyncio
    async def test_receive_with_timeout_success(self):
        """receive() returns data normally when timeout is set and recv completes."""
        mock_ws = _make_mock_ws()
        mock_ws.recv.return_value = '{"type": "ack"}'
        conn = WorkerConnection("ws://localhost:8200/ws/v1/workers", receive_timeout=5.0)
        conn._ws = mock_ws

        result = await conn.receive()
        assert result == '{"type": "ack"}'

    @pytest.mark.asyncio
    async def test_receive_with_timeout_expires(self):
        """receive() raises asyncio.TimeoutError when recv does not complete in time."""
        mock_ws = _make_mock_ws()

        async def slow_recv():
            await asyncio.sleep(10.0)

        mock_ws.recv = slow_recv
        conn = WorkerConnection("ws://localhost:8200/ws/v1/workers", receive_timeout=0.01)
        conn._ws = mock_ws

        with pytest.raises(asyncio.TimeoutError):
            await conn.receive()

    @pytest.mark.asyncio
    async def test_receive_without_timeout_no_wrap(self):
        """receive() does not wrap with wait_for when timeout is None."""
        mock_ws = _make_mock_ws()
        mock_ws.recv.return_value = b"\x00\x01"
        conn = WorkerConnection("ws://localhost:8200/ws/v1/workers")  # No timeout
        conn._ws = mock_ws

        result = await conn.receive()
        assert result == b"\x00\x01"


@pytest.mark.unit
class TestConnectWithRetryStopEvent:
    """Tests for stop_event in connect_with_retry."""

    @pytest.mark.asyncio
    async def test_stop_event_already_set_before_retry(self):
        """connect_with_retry raises immediately when stop_event is pre-set."""
        conn = WorkerConnection("ws://localhost:8200/ws/v1/workers")
        stop = asyncio.Event()
        stop.set()

        with pytest.raises(WorkerConnectionError, match="Stop event set"):
            await conn.connect_with_retry(stop_event=stop)

    @pytest.mark.asyncio
    async def test_stop_event_set_during_backoff_sleep(self):
        """connect_with_retry exits when stop_event fires during sleep."""
        conn = WorkerConnection("ws://localhost:8200/ws/v1/workers")
        stop = asyncio.Event()

        call_count = 0

        async def failing_connect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise WorkerConnectionError("refused")

        with patch.object(conn, "connect", side_effect=failing_connect):

            async def set_stop_soon():
                await asyncio.sleep(0.02)
                stop.set()

            task = asyncio.create_task(set_stop_soon())
            with pytest.raises(WorkerConnectionError, match="Stop event set"):
                await conn.connect_with_retry(backoff_base=5.0, backoff_max=10.0, stop_event=stop)
            await task

        # Should have failed at least once before stop triggered
        assert call_count >= 1

    @pytest.mark.asyncio
    async def test_stop_event_none_behaves_normally(self):
        """connect_with_retry works as before when stop_event is None."""
        mock_ws = _make_mock_ws()
        conn = WorkerConnection("ws://localhost:8200/ws/v1/workers")

        with patch("juniper_cascor_worker.ws_connection.websockets.connect", new_callable=AsyncMock, return_value=mock_ws):
            await conn.connect_with_retry(stop_event=None)

        assert conn.connected is True

    @pytest.mark.asyncio
    async def test_stop_event_with_successful_connect(self):
        """connect_with_retry succeeds normally even with stop_event provided (not set)."""
        mock_ws = _make_mock_ws()
        conn = WorkerConnection("ws://localhost:8200/ws/v1/workers")
        stop = asyncio.Event()  # Not set

        with patch("juniper_cascor_worker.ws_connection.websockets.connect", new_callable=AsyncMock, return_value=mock_ws):
            await conn.connect_with_retry(stop_event=stop)

        assert conn.connected is True
