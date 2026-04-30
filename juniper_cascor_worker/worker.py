"""Remote candidate training workers for distributed CasCor training.

Two worker implementations:
- ``CascorWorkerAgent`` (default): WebSocket-based worker using the Phase 1b
  wire protocol. Connects to ``/ws/v1/workers`` on the juniper-cascor server.
- ``CandidateTrainingWorker`` (legacy): BaseManager-based worker using
  multiprocessing queues. Deprecated — use ``--legacy`` CLI flag.
"""

from __future__ import annotations

import asyncio
import json
import logging
import multiprocessing as mp
import os
import platform
import struct
import time
import uuid
import warnings
from multiprocessing.context import BaseContext
from typing import TYPE_CHECKING, Any, Optional, Union

if TYPE_CHECKING:
    from juniper_cascor_worker.http_health import HealthServer
    from juniper_cascor_worker.ws_connection import WorkerConnection

import numpy as np

from juniper_cascor_worker.config import WorkerConfig
from juniper_cascor_worker.constants import BINARY_FRAME_DTYPE_ENCODING, BINARY_FRAME_HEADER_LENGTH_BYTES, BINARY_FRAME_HEADER_LENGTH_FORMAT, DEFAULT_CORRELATION, DEFAULT_DENOMINATOR, DEFAULT_NUMERATOR, MAX_JSON_ERROR_PREVIEW_LENGTH, MSG_TYPE_CONNECTION_ESTABLISHED, MSG_TYPE_ERROR, MSG_TYPE_HEARTBEAT, MSG_TYPE_REGISTER, MSG_TYPE_REGISTRATION_ACK, MSG_TYPE_RESULT_ACK, MSG_TYPE_TASK_ASSIGN, MSG_TYPE_TASK_RESULT, NO_BEST_CORR_IDX, NO_EPOCHS_COMPLETED
from juniper_cascor_worker.exceptions import WorkerConnectionError, WorkerError

logger = logging.getLogger(__name__)


class CascorWorkerAgent:
    """WebSocket-based remote worker for distributed candidate training.

    Connects to a juniper-cascor server's ``/ws/v1/workers`` endpoint and
    processes candidate training tasks using the structured JSON + binary
    numpy wire protocol (no pickle).

    The agent runs an async event loop with:
    - A message loop for receiving tasks and sending results
    - A heartbeat loop for keepalive
    - Training execution offloaded to a thread pool

    Example:
        >>> config = WorkerConfig(server_url="ws://localhost:8200/ws/v1/workers")
        >>> agent = CascorWorkerAgent(config)
        >>> asyncio.run(agent.run())
    """

    def __init__(self, config: WorkerConfig) -> None:
        config.validate(legacy=False)
        self.config = config
        self.worker_id = str(uuid.uuid4())
        self._stop_event = asyncio.Event()
        self._connection: WorkerConnection | None = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        # METRICS-MON R1.3 / seed-04: task accounting + liveness counter for
        # the enriched heartbeat payload and the HTTP probe tick.
        self._in_flight_tasks: int = 0
        self._last_task_completed_at: float | None = None
        self._tasks_completed: int = 0
        self._tasks_failed: int = 0
        self._liveness_counter: int = 0
        self._liveness_last_tick_at: float = time.monotonic()
        self._registered: bool = False
        # The HTTP health server is built lazily in ``run()`` so tests can
        # construct an agent without binding a port.
        self._health_server: Optional["HealthServer"] = None

    def _bump_liveness(self) -> None:
        """Record forward progress for the liveness probe."""
        self._liveness_counter += 1
        self._liveness_last_tick_at = time.monotonic()

    def _liveness_tick(self) -> None:
        """METRICS-MON R1.3 / seed-04: probe-side liveness check.

        Pure in-process work (no awaits, no I/O): WS connection bound and
        last bump within ``2 * heartbeat_interval`` seconds. Raises on any
        violation; the HTTP handler converts the exception into 503.
        """
        if self._connection is None or not self._connection.connected:
            raise RuntimeError("websocket connection not bound")
        stale_after = 2.0 * self.config.heartbeat_interval
        if (time.monotonic() - self._liveness_last_tick_at) > stale_after:
            raise RuntimeError(f"heartbeat counter stale (> {stale_after:.1f}s)")

    def _readiness_tick(self) -> None:
        """METRICS-MON R1.3 / seed-04: probe-side readiness check.

        Required deps: WS connected AND registration handshake complete.
        Raises with a precise reason; the HTTP handler converts into 503.
        """
        if self._connection is None or not self._connection.connected:
            raise RuntimeError("websocket connection not bound")
        if not self._registered:
            raise RuntimeError("worker registration handshake not complete")

    async def run(self) -> None:
        """Main entry point — connect, register, and process tasks.

        Runs until ``stop()`` is called or the connection is lost
        (with automatic reconnection).
        """
        from juniper_cascor_worker.http_health import HealthServer
        from juniper_cascor_worker.ws_connection import WorkerConnection

        self._loop = asyncio.get_running_loop()

        # METRICS-MON R1.3 / seed-04: bring up the HTTP health server
        # before we connect to cascor so k8s liveness probes work even
        # while the WS connection is being established (the tick will
        # 503 until the connection is up — exactly what the contract
        # specifies for "not yet ready").
        self._health_server = HealthServer(
            liveness_tick=self._liveness_tick,
            readiness_tick=self._readiness_tick,
            worker_id_provider=lambda: self.worker_id if self._registered else None,
            version=_resolve_version(),
            host=self.config.health_bind,
            port=self.config.health_port,
        )
        await self._health_server.start()

        try:
            await self._run_inner(WorkerConnection)
        finally:
            await self._health_server.stop()

    async def _run_inner(self, WorkerConnection: type) -> None:
        """Connect/register/process loop, with HTTP probes already up."""
        while not self._stop_event.is_set():
            self._connection = WorkerConnection(
                server_url=self.config.server_url,
                api_key=self.config.auth_token,
                tls_cert=self.config.tls_cert,
                tls_key=self.config.tls_key,
                tls_ca=self.config.tls_ca,
            )

            try:
                await self._connection.connect_with_retry(
                    backoff_base=self.config.reconnect_backoff_base,
                    backoff_max=self.config.reconnect_backoff_max,
                    stop_event=self._stop_event,
                )

                # Wait for connection_established
                ack = await self._connection.receive_json()
                if ack.get("type") != MSG_TYPE_CONNECTION_ESTABLISHED:
                    logger.warning("Unexpected first message: %s", ack)

                # Register
                await self._register()

                # Run heartbeat and message loop concurrently
                heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                try:
                    await self._message_loop()
                finally:
                    heartbeat_task.cancel()
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass

            except WorkerConnectionError as e:
                if self._stop_event.is_set():
                    break
                logger.warning("Connection lost: %s — reconnecting", e)
                await asyncio.sleep(self.config.reconnect_backoff_base)
            except Exception:
                if self._stop_event.is_set():
                    break
                logger.exception("Unexpected error in worker agent")
                await asyncio.sleep(self.config.reconnect_backoff_base)
            finally:
                if self._connection:
                    await self._connection.close()
                # METRICS-MON R1.3 / seed-04: a closed WS means readiness
                # 503 until the next register-ack lands. Make the flag
                # cycle visible to the probe layer.
                self._registered = False

        logger.info("Worker agent stopped")

    def stop(self) -> None:
        """Signal the agent to stop.

        Uses ``call_soon_threadsafe`` when the event loop is running on
        another thread (e.g. when invoked from a signal handler on the
        main thread) so that ``asyncio.Event.set()`` is scheduled safely.
        """
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._stop_event.set)
        else:
            self._stop_event.set()

    async def _register(self) -> None:
        """Send registration message and wait for acknowledgment."""
        capabilities = self._build_capabilities()
        msg = {
            "type": MSG_TYPE_REGISTER,
            "worker_id": self.worker_id,
            "capabilities": capabilities,
        }
        await self._connection.send_json(msg)

        ack = await self._connection.receive_json()
        if ack.get("type") != MSG_TYPE_REGISTRATION_ACK:
            raise WorkerConnectionError(f"Registration failed: {ack}")

        # METRICS-MON R1.3 / seed-04: readiness anchor — once the ack lands
        # the worker is eligible to receive tasks.
        self._registered = True
        self._bump_liveness()
        logger.info("Registered as worker %s", self.worker_id)

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat messages.

        METRICS-MON R1.3 / seed-04: payload is enriched with
        ``in_flight_tasks``, ``last_task_completed_at``, ``rss_mb``, and
        the running task counters so cascor's ``WorkerRegistration`` and
        ``/v1/workers`` route can surface diagnostic state.
        """
        from juniper_cascor_worker.http_health import sample_rss_mb

        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(self.config.heartbeat_interval)
                if self._connection and self._connection.connected:
                    msg = {
                        "type": MSG_TYPE_HEARTBEAT,
                        "worker_id": self.worker_id,
                        "timestamp": time.time(),
                        # R1.3 enriched fields:
                        "in_flight_tasks": self._in_flight_tasks,
                        "last_task_completed_at": self._last_task_completed_at,
                        "rss_mb": sample_rss_mb(),
                        "tasks_completed": self._tasks_completed,
                        "tasks_failed": self._tasks_failed,
                    }
                    await self._connection.send_json(msg)
                    self._bump_liveness()
            except WorkerConnectionError:
                break
            except asyncio.CancelledError:
                break

    async def _message_loop(self) -> None:
        """Process incoming messages from the server."""
        while not self._stop_event.is_set():
            raw = await self._connection.receive()

            if isinstance(raw, bytes):
                logger.warning("Unexpected binary frame outside task context")
                continue

            msg = _parse_json(raw)
            if msg is None:
                continue

            msg_type = msg.get("type")

            if msg_type == MSG_TYPE_TASK_ASSIGN:
                await self._handle_task_assign(msg)
            elif msg_type == MSG_TYPE_HEARTBEAT:
                pass  # Server heartbeat response — no action needed
            elif msg_type == MSG_TYPE_RESULT_ACK:
                status = msg.get("status", "unknown")
                logger.debug("Result ack: task %s — %s", msg.get("task_id"), status)
            elif msg_type == MSG_TYPE_ERROR:
                logger.error("Server error: %s", msg.get("error"))
            else:
                # METRICS-MON R2.2.6 / seed-05: structured WARNING line so log
                # shippers (Loki, etc.) can count unrecognized inbound frames
                # without the worker depending on prometheus_client. The
                # ``worker_id`` extra correlates the diagnostic with a
                # specific worker pod even when many workers share a
                # log stream.
                logger.warning(
                    "juniper_cascor_worker_unrecognized_ws_frame",
                    extra={"type": msg_type, "worker_id": self.worker_id},
                )

    async def _handle_task_assign(self, msg: dict[str, Any]) -> None:
        """Handle a task_assign message: receive tensors, train, send result."""
        # METRICS-MON R1.3 / seed-04: task accounting wraps the entire
        # task lifecycle — protocol-level rejections, timeouts, and
        # successful completions all flow through the finally block so
        # ``in_flight_tasks`` and ``last_task_completed_at`` stay
        # accurate regardless of where execution exits.
        self._in_flight_tasks += 1
        success = False
        try:
            success = await self._handle_task_assign_body(msg)
        finally:
            self._in_flight_tasks -= 1
            self._last_task_completed_at = time.time()
            if success:
                self._tasks_completed += 1
            else:
                self._tasks_failed += 1
            self._bump_liveness()

    async def _handle_task_assign_body(self, msg: dict[str, Any]) -> bool:
        """Inner task handler — returns True on training success, False otherwise."""
        task_id = msg.get("task_id", "")
        manifest = msg.get("tensor_manifest", {})

        # CW-07: validate that the manifest declares the tensors the
        # task_executor depends on before we start blocking on
        # ``receive_bytes()``. A malformed manifest would otherwise leave the
        # worker waiting on frames that never arrive (silent deadlock) or
        # raise a late ``KeyError`` once execution reaches
        # ``tensors["candidate_input"]``. Failing fast here lets us surface a
        # clear protocol violation back to the server.
        candidate_data = msg.get("candidate_data", {})
        candidate_data["candidate_index"] = msg.get("candidate_index", 0)
        manifest_validation_error = _validate_tensor_manifest(manifest)
        if manifest_validation_error is not None:
            logger.error("Tensor manifest invalid for task %s: %s", task_id, manifest_validation_error)
            await self._connection.send_json(
                _build_task_failure_message(
                    task_id=task_id,
                    candidate_data=candidate_data,
                    error_message=f"Tensor manifest invalid: {manifest_validation_error}",
                )
            )
            return False

        # Receive binary tensor frames
        tensors: dict[str, np.ndarray] = {}
        for tensor_name in manifest:
            raw_bytes = await self._connection.receive_bytes()
            tensors[tensor_name] = _decode_binary_frame(raw_bytes)

        # CW-07 (defence-in-depth): once decoded, verify the populated tensor
        # set still matches the declared manifest. This will only flag a
        # mismatch if the receive loop above is ever changed to short-circuit
        # — but the cost is negligible and the assertion documents the
        # invariant explicitly.
        missing = set(manifest.keys()) - set(tensors.keys())
        extra = set(tensors.keys()) - set(manifest.keys())
        if missing or extra:
            logger.error(
                "Tensor manifest/frame mismatch for task %s: missing=%s extra=%s",
                task_id,
                sorted(missing),
                sorted(extra),
            )
            await self._connection.send_json(
                _build_task_failure_message(
                    task_id=task_id,
                    candidate_data=candidate_data,
                    error_message=f"Tensor manifest/frame mismatch: missing={sorted(missing)} extra={sorted(extra)}",
                )
            )
            return False

        logger.info("Received task %s (%d tensors)", task_id, len(tensors))

        # Execute training in a thread to avoid blocking the event loop
        training_params = msg.get("training_params", {})

        try:
            result_dict, result_tensors = await asyncio.wait_for(
                asyncio.to_thread(_execute_task, candidate_data, training_params, tensors),
                timeout=self.config.task_timeout,
            )
        except asyncio.TimeoutError:
            logger.error("Task %s timed out after %.0fs", task_id, self.config.task_timeout)
            # CW-04: thread the actual candidate_uuid through so the server can
            # correlate the timeout error with the assigned candidate. The
            # previous code unconditionally sent ``""`` which broke server-side
            # correlation logging.
            error_msg = {
                "type": MSG_TYPE_TASK_RESULT,
                "task_id": task_id,
                "candidate_id": candidate_data.get("candidate_index", 0),
                "candidate_uuid": candidate_data.get("candidate_uuid", ""),
                "correlation": DEFAULT_CORRELATION,
                "success": False,
                "epochs_completed": NO_EPOCHS_COMPLETED,
                "activation_name": candidate_data.get("activation_name", ""),
                "all_correlations": [],
                "numerator": DEFAULT_NUMERATOR,
                "denominator": DEFAULT_DENOMINATOR,
                "best_corr_idx": NO_BEST_CORR_IDX,
                "error_message": f"Task timed out after {self.config.task_timeout:.0f}s",
                "tensor_manifest": {},
            }
            await self._connection.send_json(error_msg)
            return False

        # Build tensor manifest for result
        tensor_manifest = {}
        frames = []
        for name, arr in result_tensors.items():
            tensor_manifest[name] = {"shape": list(arr.shape), "dtype": str(arr.dtype)}
            frames.append(_encode_binary_frame(arr))

        # Send result JSON
        result_msg = {
            "type": MSG_TYPE_TASK_RESULT,
            "task_id": task_id,
            "candidate_id": result_dict.get("candidate_id", 0),
            "candidate_uuid": result_dict.get("candidate_uuid", ""),
            "correlation": result_dict.get("correlation", DEFAULT_CORRELATION),
            "success": result_dict.get("success", False),
            "epochs_completed": result_dict.get("epochs_completed", NO_EPOCHS_COMPLETED),
            "activation_name": result_dict.get("activation_name", ""),
            "all_correlations": result_dict.get("all_correlations", []),
            "numerator": result_dict.get("numerator", DEFAULT_NUMERATOR),
            "denominator": result_dict.get("denominator", DEFAULT_DENOMINATOR),
            "best_corr_idx": result_dict.get("best_corr_idx", NO_BEST_CORR_IDX),
            "error_message": result_dict.get("error_message"),
            "tensor_manifest": tensor_manifest,
        }
        await self._connection.send_json(result_msg)

        # Send binary tensor frames
        for frame in frames:
            await self._connection.send_bytes(frame)

        logger.info(
            "Sent result for task %s (corr=%.4f, success=%s)",
            task_id,
            result_dict.get("correlation", DEFAULT_CORRELATION),
            result_dict.get("success", False),
        )
        # METRICS-MON R1.3: a returned-with-success result counts toward
        # ``tasks_completed``; everything else (timeout, manifest reject,
        # exception) counts as failed via the surrounding try/finally.
        return bool(result_dict.get("success", False))

    @staticmethod
    def _build_capabilities() -> dict[str, Any]:
        """Collect worker capability metadata."""
        import torch

        gpu = torch.cuda.is_available()
        return {
            "cpu_cores": os.cpu_count() or 1,
            "gpu": gpu,
            "gpu_name": torch.cuda.get_device_name(0) if gpu else None,
            "python_version": platform.python_version(),
            "torch_version": torch.__version__,
            "numpy_version": np.__version__,
            "os": platform.system(),
        }


# ---------------------------------------------------------------------------
# Module-level helpers (used by CascorWorkerAgent, testable independently)
# ---------------------------------------------------------------------------


def _execute_task(
    candidate_data: dict[str, Any],
    training_params: dict[str, Any],
    tensors: dict[str, np.ndarray],
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Wrapper for task_executor.execute_training_task (called in thread)."""
    from juniper_cascor_worker.task_executor import execute_training_task

    return execute_training_task(candidate_data, training_params, tensors)


def _resolve_version() -> str:
    """Return the installed package version, or "0.0.0+unknown" on failure.

    Used by the HTTP health endpoint's ``/v1/health`` body. Never raises —
    a probe surface failing to import metadata must not 500 on the operator.
    """
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("juniper-cascor-worker")
        except PackageNotFoundError:
            return "0.0.0+unknown"
    except Exception:  # noqa: BLE001
        return "0.0.0+unknown"


def _parse_json(raw: str) -> dict[str, Any] | None:
    """Parse a JSON text message, returning None on failure."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.error("Invalid JSON message: JSON Decode or Type Error: %s", raw[:MAX_JSON_ERROR_PREVIEW_LENGTH] if raw else "")
    return None


# CW-07: tensor names the task executor unconditionally dereferences via
# ``tensors[name]``. Any task_assign manifest that omits one of these is a
# protocol violation and will deadlock or KeyError if accepted blindly.
REQUIRED_TENSOR_NAMES: tuple[str, ...] = ("candidate_input", "residual_error")


def _validate_tensor_manifest(manifest: Any) -> str | None:
    """Validate a ``tensor_manifest`` payload, returning an error string or None.

    CW-07 (Phase 4E): the cascor server sends a tensor_manifest dict
    declaring the binary frames it intends to follow with. If the manifest is
    not a dict, is empty, or omits a required tensor name, the worker has no
    safe way to receive frames and must reject the task instead of blocking
    forever on ``receive_bytes()``.
    """
    if not isinstance(manifest, dict):
        return f"manifest is not a dict (got {type(manifest).__name__})"
    if not manifest:
        return "manifest is empty"
    missing_required = [name for name in REQUIRED_TENSOR_NAMES if name not in manifest]
    if missing_required:
        return f"manifest missing required tensor(s): {missing_required}"
    return None


def _build_task_failure_message(
    *,
    task_id: str,
    candidate_data: dict[str, Any],
    error_message: str,
) -> dict[str, Any]:
    """Build a ``task_result`` payload describing a pre-execution failure.

    Centralises the failure envelope used when the worker rejects a task
    before any training runs (e.g. invalid manifest, CW-07). Mirrors the
    timeout-path payload so the server sees a consistent shape regardless of
    where the failure originated, and threads through the actual
    ``candidate_uuid`` so failures can be correlated server-side (CW-04).
    """
    return {
        "type": MSG_TYPE_TASK_RESULT,
        "task_id": task_id,
        "candidate_id": candidate_data.get("candidate_index", 0),
        "candidate_uuid": candidate_data.get("candidate_uuid", ""),
        "correlation": DEFAULT_CORRELATION,
        "success": False,
        "epochs_completed": NO_EPOCHS_COMPLETED,
        "activation_name": candidate_data.get("activation_name", ""),
        "all_correlations": [],
        "numerator": DEFAULT_NUMERATOR,
        "denominator": DEFAULT_DENOMINATOR,
        "best_corr_idx": NO_BEST_CORR_IDX,
        "error_message": error_message,
        "tensor_manifest": {},
    }


def _encode_binary_frame(array: np.ndarray) -> bytes:
    """Encode a numpy array as a binary frame.

    METRICS-MON R2.2.6 / seed-05: delegates to the canonical encoder in
    :class:`juniper_cascor_protocol.worker.BinaryFrame` so the wire
    format is single-sourced with the cascor server. The local
    constants (``BINARY_FRAME_HEADER_LENGTH_FORMAT`` etc.) remain in
    ``constants.py`` for use by ``_decode_binary_frame`` which keeps
    SEC-18 stricter bounds (``BINARY_FRAME_MAX_TOTAL_ELEMENTS``,
    ``BINARY_FRAME_MAX_DTYPE_LEN=32``) that the shared lib's decoder
    does not enforce.

    Importing :class:`juniper_cascor_protocol.worker.BinaryFrame` does
    not load Pydantic — the worker subpackage is numpy-only by design.
    """
    from juniper_cascor_protocol.worker import BinaryFrame as _SharedBinaryFrame

    return _SharedBinaryFrame.encode(array)


# SEC-18: Bounds for attacker-controlled binary-frame headers. A crafted
# frame could otherwise make ``np.frombuffer().reshape(shape)`` attempt a
# huge allocation and exhaust worker memory. The limits here are generous
# enough for realistic CasCor tensor shapes (ndim<=10, ~100M elements,
# dtype strings like "complex128") while still shutting the door on DoS.
BINARY_FRAME_MAX_NDIM = 10
BINARY_FRAME_MAX_TOTAL_ELEMENTS = 100_000_000
BINARY_FRAME_MAX_DTYPE_LEN = 32


class BinaryFrameProtocolError(Exception):
    """Raised when a binary frame header violates declared bounds."""


def _decode_binary_frame(data: bytes) -> np.ndarray:
    """Decode a binary frame into a numpy array (matches Phase 1b BinaryFrame.decode).

    Validates every attacker-controlled field in the header (ndim, shape
    extents, dtype length) before calling ``np.frombuffer`` so a malformed
    or malicious frame cannot trigger an OOM allocation (SEC-18).
    """
    offset = 0
    (ndim,) = struct.unpack_from(BINARY_FRAME_HEADER_LENGTH_FORMAT, data, offset)
    if ndim < 0 or ndim > BINARY_FRAME_MAX_NDIM:
        raise BinaryFrameProtocolError(f"binary frame ndim={ndim} exceeds maximum {BINARY_FRAME_MAX_NDIM}")
    offset += BINARY_FRAME_HEADER_LENGTH_BYTES
    shape = struct.unpack_from(f"<{ndim}I", data, offset)
    offset += ndim * BINARY_FRAME_HEADER_LENGTH_BYTES

    total_elements = 1
    for dim in shape:
        if dim < 0:
            raise BinaryFrameProtocolError(f"binary frame shape dimension negative: {dim}")
        total_elements *= dim
        if total_elements > BINARY_FRAME_MAX_TOTAL_ELEMENTS:
            raise BinaryFrameProtocolError(f"binary frame total_elements>{BINARY_FRAME_MAX_TOTAL_ELEMENTS} (shape={shape})")

    (dtype_len,) = struct.unpack_from(BINARY_FRAME_HEADER_LENGTH_FORMAT, data, offset)
    if dtype_len < 0 or dtype_len > BINARY_FRAME_MAX_DTYPE_LEN:
        raise BinaryFrameProtocolError(f"binary frame dtype_len={dtype_len} exceeds maximum {BINARY_FRAME_MAX_DTYPE_LEN}")
    offset += BINARY_FRAME_HEADER_LENGTH_BYTES
    dtype_str = data[offset : offset + dtype_len].decode(BINARY_FRAME_DTYPE_ENCODING)
    offset += dtype_len
    dtype = np.dtype(dtype_str)
    array = np.frombuffer(data[offset:], dtype=dtype).reshape(shape)
    return array.copy()


# ---------------------------------------------------------------------------
# Legacy worker (deprecated — use CascorWorkerAgent instead)
# ---------------------------------------------------------------------------


class CandidateTrainingWorker:
    """Remote worker that processes candidate training tasks via BaseManager.

    .. deprecated:: 0.3.0
        Use :class:`CascorWorkerAgent` with WebSocket mode instead.
        This class is retained for backward compatibility with ``--legacy``.

    Connects to a CasCor CandidateTrainingManager server and spawns
    local worker processes that consume tasks from the shared queue.
    """

    def __init__(self, config: Optional[WorkerConfig] = None) -> None:
        warnings.warn("CandidateTrainingWorker is deprecated. Use CascorWorkerAgent with WebSocket mode instead.", DeprecationWarning, stacklevel=2)
        self.config = config or WorkerConfig(authkey="placeholder")
        self.config.validate(legacy=True)
        self.ctx: BaseContext = mp.get_context(self.config.mp_context)
        self.manager: Any = None
        self.task_queue: Any = None
        self.result_queue: Any = None
        self.workers: list = []
        self._connected = False

    def connect(self) -> None:
        """Connect to the remote CandidateTrainingManager."""
        try:
            from cascade_correlation.cascade_correlation import CandidateTrainingManager
        except ImportError as e:
            raise WorkerError("CasCor codebase not found. Ensure the JuniperCascor src directory " "is on sys.path or installed in the environment. " f"Original error: {e}") from e

        raw_authkey: Union[str, bytes] = self.config.authkey
        authkey: bytes = raw_authkey.encode("utf-8") if isinstance(raw_authkey, str) else raw_authkey

        try:
            self.manager = CandidateTrainingManager(
                address=self.config.address,
                authkey=authkey,
            )
            self.manager.connect()
            self.task_queue = self.manager.get_task_queue()
            self.result_queue = self.manager.get_result_queue()
            self._connected = True
            logger.info("Connected to manager at %s:%d", self.config.manager_host, self.config.manager_port)
        except Exception as e:
            raise WorkerConnectionError(f"Failed to connect to manager at {self.config.address}: {e}") from e

    def start(self, num_workers: Optional[int] = None) -> None:
        """Start local worker processes."""
        if not self._connected:
            raise WorkerError("Not connected. Call connect() first.")

        n = num_workers or self.config.num_workers

        try:
            from cascade_correlation.cascade_correlation import CascadeCorrelationNetwork
        except ImportError as e:
            raise WorkerError(f"CasCor codebase not found: {e}") from e

        for i in range(n):
            worker = self.ctx.Process(  # type: ignore[attr-defined]
                target=CascadeCorrelationNetwork._worker_loop,
                args=(self.task_queue, self.result_queue, True),
                daemon=True,
                name=f"CascorRemoteWorker-{i}",
            )
            worker.start()
            self.workers.append(worker)

        logger.info("Started %d worker processes", len(self.workers))

    def stop(self, timeout: Optional[int] = None) -> None:
        """Stop all worker processes gracefully."""
        if not self.workers:
            return

        t = timeout or self.config.stop_timeout

        for _ in self.workers:
            try:
                self.task_queue.put(None)
            except Exception as e:
                logger.error("Failed to send sentinel: %s", e)

        for worker in self.workers:
            worker.join(timeout=t)
            if worker.is_alive():
                logger.warning("Worker %s did not stop gracefully, terminating", worker.name)
                worker.terminate()

        self.workers.clear()
        logger.info("All worker processes stopped")

    def disconnect(self) -> None:
        """Disconnect from the remote manager."""
        if self.workers:
            self.stop()
        self.manager = None
        self.task_queue = None
        self.result_queue = None
        self._connected = False
        logger.info("Disconnected from manager")

    @property
    def is_running(self) -> bool:
        """Check if any workers are running."""
        return any(w.is_alive() for w in self.workers)

    @property
    def worker_count(self) -> int:
        """Number of active worker processes."""
        return sum(1 for w in self.workers if w.is_alive())

    def __enter__(self) -> "CandidateTrainingWorker":
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.disconnect()
