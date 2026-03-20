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
    from juniper_cascor_worker.ws_connection import WorkerConnection

import numpy as np

from juniper_cascor_worker.config import WorkerConfig
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

    async def run(self) -> None:
        """Main entry point — connect, register, and process tasks.

        Runs until ``stop()`` is called or the connection is lost
        (with automatic reconnection).
        """
        from juniper_cascor_worker.ws_connection import WorkerConnection

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
                )

                # Wait for connection_established
                ack = await self._connection.receive_json()
                if ack.get("type") != "connection_established":
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

        logger.info("Worker agent stopped")

    def stop(self) -> None:
        """Signal the agent to stop."""
        self._stop_event.set()

    async def _register(self) -> None:
        """Send registration message and wait for acknowledgment."""
        capabilities = self._build_capabilities()
        msg = {
            "type": "register",
            "worker_id": self.worker_id,
            "capabilities": capabilities,
        }
        await self._connection.send_json(msg)

        ack = await self._connection.receive_json()
        if ack.get("type") != "registration_ack":
            raise WorkerConnectionError(f"Registration failed: {ack}")

        logger.info("Registered as worker %s", self.worker_id)

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat messages."""
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(self.config.heartbeat_interval)
                if self._connection and self._connection.connected:
                    msg = {
                        "type": "heartbeat",
                        "worker_id": self.worker_id,
                        "timestamp": time.time(),
                    }
                    await self._connection.send_json(msg)
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

            if msg_type == "task_assign":
                await self._handle_task_assign(msg)
            elif msg_type == "heartbeat":
                pass  # Server heartbeat response — no action needed
            elif msg_type == "result_ack":
                status = msg.get("status", "unknown")
                logger.debug("Result ack: task %s — %s", msg.get("task_id"), status)
            elif msg_type == "error":
                logger.error("Server error: %s", msg.get("error"))
            else:
                logger.warning("Unknown message type: %s", msg_type)

    async def _handle_task_assign(self, msg: dict[str, Any]) -> None:
        """Handle a task_assign message: receive tensors, train, send result."""
        task_id = msg.get("task_id", "")
        manifest = msg.get("tensor_manifest", {})

        # Receive binary tensor frames
        tensors: dict[str, np.ndarray] = {}
        for tensor_name in manifest:
            raw_bytes = await self._connection.receive_bytes()
            tensors[tensor_name] = _decode_binary_frame(raw_bytes)

        logger.info("Received task %s (%d tensors)", task_id, len(tensors))

        # Execute training in a thread to avoid blocking the event loop
        candidate_data = msg.get("candidate_data", {})
        candidate_data["candidate_index"] = msg.get("candidate_index", 0)
        training_params = msg.get("training_params", {})

        result_dict, result_tensors = await asyncio.to_thread(_execute_task, candidate_data, training_params, tensors)

        # Build tensor manifest for result
        tensor_manifest = {}
        frames = []
        for name, arr in result_tensors.items():
            tensor_manifest[name] = {"shape": list(arr.shape), "dtype": str(arr.dtype)}
            frames.append(_encode_binary_frame(arr))

        # Send result JSON
        result_msg = {
            "type": "task_result",
            "task_id": task_id,
            "candidate_id": result_dict.get("candidate_id", 0),
            "candidate_uuid": result_dict.get("candidate_uuid", ""),
            "correlation": result_dict.get("correlation", 0.0),
            "success": result_dict.get("success", False),
            "epochs_completed": result_dict.get("epochs_completed", 0),
            "activation_name": result_dict.get("activation_name", ""),
            "all_correlations": result_dict.get("all_correlations", []),
            "numerator": result_dict.get("numerator", 0.0),
            "denominator": result_dict.get("denominator", 1.0),
            "best_corr_idx": result_dict.get("best_corr_idx", -1),
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
            result_dict.get("correlation", 0.0),
            result_dict.get("success", False),
        )

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


def _parse_json(raw: str) -> dict[str, Any] | None:
    """Parse a JSON text message, returning None on failure."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.error("Invalid JSON message: %s", raw[:200] if raw else "")
        return None


def _encode_binary_frame(array: np.ndarray) -> bytes:
    """Encode a numpy array as a binary frame (matches Phase 1b BinaryFrame.encode)."""
    arr = np.ascontiguousarray(array)
    shape = arr.shape
    dtype_str = str(arr.dtype).encode("utf-8")
    header = struct.pack(f"<I{len(shape)}I", len(shape), *shape)
    header += struct.pack("<I", len(dtype_str))
    header += dtype_str
    return header + arr.tobytes()


def _decode_binary_frame(data: bytes) -> np.ndarray:
    """Decode a binary frame into a numpy array (matches Phase 1b BinaryFrame.decode)."""
    offset = 0
    (ndim,) = struct.unpack_from("<I", data, offset)
    offset += 4
    shape = struct.unpack_from(f"<{ndim}I", data, offset)
    offset += ndim * 4
    (dtype_len,) = struct.unpack_from("<I", data, offset)
    offset += 4
    dtype_str = data[offset : offset + dtype_len].decode("utf-8")
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
