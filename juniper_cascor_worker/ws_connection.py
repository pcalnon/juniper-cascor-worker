"""WebSocket connection management for remote worker communication.

Handles connection lifecycle, TLS configuration, and exponential backoff
reconnection. No cascor imports — this is a pure WebSocket client layer.
"""

import asyncio
import json
import logging
import ssl
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

from juniper_cascor_worker.exceptions import WorkerConnectionError

logger = logging.getLogger(__name__)


class WorkerConnection:
    """Manages a WebSocket connection to the juniper-cascor worker endpoint.

    Handles:
    - Connection with API key authentication (``X-API-Key`` header)
    - TLS/mTLS when certificate paths are provided
    - Sending JSON messages and binary frames
    - Receiving text and binary messages
    - Exponential backoff reconnection
    """

    def __init__(
        self,
        server_url: str,
        api_key: str = "",
        tls_cert: str | None = None,
        tls_key: str | None = None,
        tls_ca: str | None = None,
        receive_timeout: float | None = None,
    ) -> None:
        self._server_url = server_url
        self._api_key = api_key
        self._tls_cert = tls_cert
        self._tls_key = tls_key
        self._tls_ca = tls_ca
        self._receive_timeout = receive_timeout
        self._ws: ClientConnection | None = None

    @property
    def connected(self) -> bool:
        """Whether the WebSocket is currently open."""
        return self._ws is not None and self._ws.protocol.state.name == "OPEN"

    async def connect(self) -> None:
        """Open a WebSocket connection to the server.

        Sends the ``X-API-Key`` header for authentication and suppresses
        the ``Origin`` header (machine-to-machine only).

        Raises:
            WorkerConnectionError: If connection fails.
        """
        headers: dict[str, str] = {}
        if self._api_key:
            headers["X-API-Key"] = self._api_key

        ssl_context = self._build_ssl_context()

        try:
            self._ws = await websockets.connect(
                self._server_url,
                additional_headers=headers,
                origin=None,
                ssl=ssl_context,
            )
            logger.info("Connected to %s", self._server_url)
        except Exception as e:
            raise WorkerConnectionError(f"Failed to connect to {self._server_url}: {e}") from e

    async def connect_with_retry(
        self,
        backoff_base: float = 1.0,
        backoff_max: float = 60.0,
        max_retries: int | None = None,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        """Connect with exponential backoff retry.

        Args:
            backoff_base: Initial delay between retries in seconds.
            backoff_max: Maximum delay between retries in seconds.
            max_retries: Maximum number of retries. None for unlimited.
            stop_event: Optional event checked between retries for
                responsive shutdown.  When set, the retry loop exits
                immediately by raising :exc:`WorkerConnectionError`.

        Raises:
            WorkerConnectionError: If max_retries exceeded or stop_event is set.
        """
        delay = backoff_base
        attempt = 0

        while True:
            if stop_event is not None and stop_event.is_set():
                raise WorkerConnectionError("Stop event set — aborting connection retry")

            try:
                await self.connect()
                return
            except WorkerConnectionError:
                attempt += 1
                if max_retries is not None and attempt >= max_retries:
                    raise

                logger.warning("Connection attempt %d failed, retrying in %.1fs", attempt, delay)

                # Sleep interruptibly — wake early if stop_event is set
                if stop_event is not None:
                    stop_task = asyncio.create_task(stop_event.wait())
                    sleep_task = asyncio.create_task(asyncio.sleep(delay))
                    done, pending = await asyncio.wait(
                        {stop_task, sleep_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in pending:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                    if stop_event.is_set():
                        raise WorkerConnectionError("Stop event set — aborting connection retry")
                else:
                    await asyncio.sleep(delay)

                delay = min(delay * 2, backoff_max)

    async def send_json(self, msg: dict[str, Any]) -> None:
        """Send a JSON message."""
        if not self.connected:
            raise WorkerConnectionError("Not connected")
        await self._ws.send(json.dumps(msg))

    async def send_bytes(self, data: bytes) -> None:
        """Send a binary frame."""
        if not self.connected:
            raise WorkerConnectionError("Not connected")
        await self._ws.send(data)

    async def receive(self) -> str | bytes:
        """Receive the next message (text or binary).

        If ``receive_timeout`` was set on construction, the recv is wrapped
        with :func:`asyncio.wait_for`.  On timeout, :exc:`asyncio.TimeoutError`
        propagates so the caller can trigger reconnection.

        Returns:
            str for text messages, bytes for binary messages.

        Raises:
            WorkerConnectionError: If not connected or connection closed.
            asyncio.TimeoutError: If receive_timeout expires.
        """
        if not self.connected:
            raise WorkerConnectionError("Not connected")
        try:
            if self._receive_timeout is not None:
                return await asyncio.wait_for(self._ws.recv(), timeout=self._receive_timeout)
            return await self._ws.recv()
        except websockets.ConnectionClosed as e:
            self._ws = None
            raise WorkerConnectionError(f"Connection closed: {e}") from e

    async def receive_json(self) -> dict[str, Any]:
        """Receive and parse a JSON text message.

        Raises:
            WorkerConnectionError: If message is not valid JSON text.
        """
        msg = await self.receive()
        if isinstance(msg, bytes):
            raise WorkerConnectionError("Expected text message, got binary")
        return json.loads(msg)

    async def receive_bytes(self) -> bytes:
        """Receive a binary frame.

        Raises:
            WorkerConnectionError: If message is not binary.
        """
        msg = await self.receive()
        if isinstance(msg, str):
            raise WorkerConnectionError("Expected binary message, got text")
        return msg

    async def close(self) -> None:
        """Close the WebSocket connection."""
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                logger.debug("Error during WebSocket close (ignored)", exc_info=True)
            self._ws = None
            logger.info("Connection closed")

    def _build_ssl_context(self) -> ssl.SSLContext | None:
        """Build SSL context for TLS/mTLS connections."""
        if not self._server_url.startswith("wss://"):
            return None

        ctx = ssl.create_default_context()

        if self._tls_ca:
            ctx.load_verify_locations(self._tls_ca)

        if self._tls_cert and self._tls_key:
            ctx.load_cert_chain(certfile=self._tls_cert, keyfile=self._tls_key)

        return ctx
