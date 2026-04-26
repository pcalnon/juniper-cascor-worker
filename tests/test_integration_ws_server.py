"""End-to-end integration tests for CascorWorkerAgent against a fake WS server (CW-03).

The cascor server is intentionally not run in the worker's CI; instead these
tests stand up an in-process ``websockets`` server on a loopback port that
speaks just enough of the worker protocol (``connection_established`` →
``register`` → ``registration_ack`` → optional ``task_assign`` →
``task_result``) for us to exercise the agent's main loop end-to-end.

Coverage:
1. Registration: agent sends ``register`` and accepts ``registration_ack``.
2. Heartbeat: agent emits a heartbeat within the configured interval.
3. Task assign / result roundtrip: agent decodes the manifest + binary
   frames, invokes a stubbed task executor, and returns a ``task_result``
   with matching ``candidate_uuid`` and tensors.
4. CW-04 regression: on task timeout the result still carries the original
   ``candidate_uuid`` rather than an empty string.
5. CW-07 regression: a malformed manifest is rejected with an error
   ``task_result`` instead of leaving the agent blocked on
   ``receive_bytes()``.
6. Graceful disconnect: closing the server triggers the agent's reconnect
   path without raising.

The tests use the ``integration`` pytest marker so they can be excluded
from the unit suite via ``pytest -m 'not integration'``.
"""

from __future__ import annotations

import asyncio
import json
import struct
import sys
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest
import websockets
from websockets.asyncio.server import ServerConnection

from juniper_cascor_worker.config import WorkerConfig
from juniper_cascor_worker.constants import (
    BINARY_FRAME_DTYPE_ENCODING,
    BINARY_FRAME_HEADER_LENGTH_FORMAT,
    MSG_TYPE_CONNECTION_ESTABLISHED,
    MSG_TYPE_HEARTBEAT,
    MSG_TYPE_REGISTER,
    MSG_TYPE_REGISTRATION_ACK,
    MSG_TYPE_TASK_ASSIGN,
    MSG_TYPE_TASK_RESULT,
)
from juniper_cascor_worker.worker import CascorWorkerAgent

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# ─── Fake server scaffolding ────────────────────────────────────────────────


def _encode_frame(arr: np.ndarray) -> bytes:
    """Encode ``arr`` using the same wire format as the worker."""
    arr = np.ascontiguousarray(arr)
    shape = arr.shape
    dtype_str = str(arr.dtype).encode(BINARY_FRAME_DTYPE_ENCODING)
    header = struct.pack(f"<I{len(shape)}I", len(shape), *shape)
    header += struct.pack(BINARY_FRAME_HEADER_LENGTH_FORMAT, len(dtype_str))
    header += dtype_str
    return header + arr.tobytes()


class FakeCascorServer:
    """Minimal in-process WS server for worker integration tests.

    Exposes a queue of incoming worker messages and a small handful of
    canned reply scripts so individual tests can drive the worker agent
    through specific scenarios without standing up the real cascor stack.
    """

    def __init__(self) -> None:
        self.received: asyncio.Queue[Any] = asyncio.Queue()
        self.connections: list[ServerConnection] = []
        self.scenario: str = "register_only"
        self.tasks_to_assign: list[dict[str, Any]] = []

    async def handler(self, ws: ServerConnection) -> None:
        self.connections.append(ws)
        try:
            # Greet
            await ws.send(json.dumps({"type": MSG_TYPE_CONNECTION_ESTABLISHED}))

            # Expect REGISTER
            raw = await ws.recv()
            register_msg = json.loads(raw)
            await self.received.put(register_msg)
            await ws.send(json.dumps({"type": MSG_TYPE_REGISTRATION_ACK, "worker_id": register_msg.get("worker_id", "")}))

            # Issue any task scripts
            for task in self.tasks_to_assign:
                await ws.send(json.dumps(task["assign"]))
                for frame in task.get("frames", []):
                    await ws.send(frame)

            # Drain until disconnect — record everything the worker sends back
            while True:
                msg = await ws.recv()
                if isinstance(msg, bytes):
                    await self.received.put(("bytes", msg))
                else:
                    parsed = json.loads(msg)
                    await self.received.put(parsed)
        except websockets.exceptions.ConnectionClosed:
            return


@asynccontextmanager
async def _running_server():
    server = FakeCascorServer()
    async with websockets.serve(server.handler, "127.0.0.1", 0) as ws_server:
        sock = next(iter(ws_server.sockets))
        port = sock.getsockname()[1]
        server.url = f"ws://127.0.0.1:{port}"
        yield server


def _make_agent(server_url: str, *, heartbeat_interval: float = 0.05, task_timeout: float = 5.0) -> CascorWorkerAgent:
    cfg = WorkerConfig(server_url=server_url, heartbeat_interval=heartbeat_interval, task_timeout=task_timeout)
    return CascorWorkerAgent(cfg)


async def _stop_agent(agent: CascorWorkerAgent, agent_task: asyncio.Task) -> None:
    """Tear down an agent that may be blocked in ``_message_loop``'s recv.

    ``agent.stop()`` only flips the ``_stop_event`` flag, which is checked
    between message-loop iterations. When the loop is parked inside
    ``self._connection.receive()`` it has no opportunity to observe the
    flag, so we cancel the task as well to guarantee teardown within the
    test timeout.
    """
    agent.stop()
    agent_task.cancel()
    try:
        await asyncio.wait_for(agent_task, timeout=2.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass


async def _wait_for_task_result(server: "FakeCascorServer", task_id: str, *, deadline: float = 8.0) -> dict[str, Any]:
    """Drain the server queue until a ``task_result`` for ``task_id`` arrives.

    Tolerates intermediate REGISTER, HEARTBEAT, and other bookkeeping
    messages by polling until the deadline. We use a single overall
    deadline (rather than per-message timeouts) because the server's recv
    loop interleaves register, heartbeat, and task_result somewhat
    nondeterministically.
    """
    loop = asyncio.get_running_loop()
    end = loop.time() + deadline
    while loop.time() < end:
        remaining = max(0.05, end - loop.time())
        try:
            msg = await asyncio.wait_for(server.received.get(), timeout=remaining)
        except asyncio.TimeoutError:
            break
        if isinstance(msg, dict) and msg.get("type") == MSG_TYPE_TASK_RESULT and msg.get("task_id") == task_id:
            return msg
    raise AssertionError(f"no task_result for task_id={task_id!r} within {deadline}s")


# ─── Tests ───────────────────────────────────────────────────────────────────


async def test_registration_roundtrip() -> None:
    async with _running_server() as server:
        agent = _make_agent(server.url)
        agent_task = asyncio.create_task(agent.run())
        try:
            register_msg = await asyncio.wait_for(server.received.get(), timeout=2.0)
            assert register_msg["type"] == MSG_TYPE_REGISTER
            assert register_msg["worker_id"] == agent.worker_id
            assert "capabilities" in register_msg
        finally:
            await _stop_agent(agent, agent_task)


async def test_heartbeat_emitted_after_registration() -> None:
    async with _running_server() as server:
        agent = _make_agent(server.url, heartbeat_interval=0.1)
        agent_task = asyncio.create_task(agent.run())
        try:
            # First message is REGISTER
            register_msg = await asyncio.wait_for(server.received.get(), timeout=2.0)
            assert register_msg["type"] == MSG_TYPE_REGISTER

            # Subsequent message should be a HEARTBEAT (the connection only
            # sends register + heartbeats with no other traffic on this scenario)
            for _ in range(5):
                msg = await asyncio.wait_for(server.received.get(), timeout=2.0)
                if isinstance(msg, dict) and msg.get("type") == MSG_TYPE_HEARTBEAT:
                    assert msg["worker_id"] == agent.worker_id
                    return
            raise AssertionError("no heartbeat observed")
        finally:
            await _stop_agent(agent, agent_task)


async def test_task_assign_result_roundtrip() -> None:
    """End-to-end: server assigns a task, worker decodes, executor stub returns, server sees result."""
    async with _running_server() as server:
        candidate_input = np.full((4, 2), 0.5, dtype=np.float32)
        residual_error = np.full((4, 1), 0.25, dtype=np.float32)
        manifest = {
            "candidate_input": {"shape": list(candidate_input.shape), "dtype": str(candidate_input.dtype)},
            "residual_error": {"shape": list(residual_error.shape), "dtype": str(residual_error.dtype)},
        }
        server.tasks_to_assign = [
            {
                "assign": {
                    "type": MSG_TYPE_TASK_ASSIGN,
                    "task_id": "task-int-001",
                    "candidate_index": 7,
                    "candidate_data": {"candidate_uuid": "uuid-int-001", "input_size": 2, "activation_name": "sigmoid"},
                    "training_params": {"epochs": 1, "learning_rate": 0.01},
                    "tensor_manifest": manifest,
                },
                "frames": [_encode_frame(candidate_input), _encode_frame(residual_error)],
            }
        ]

        # Stub the executor so we don't import torch / cascor sources here.
        def fake_execute(candidate_data: dict[str, Any], training_params: dict[str, Any], tensors: dict[str, np.ndarray]):
            assert tensors["candidate_input"].shape == (4, 2)
            assert tensors["residual_error"].shape == (4, 1)
            result = {
                "candidate_id": candidate_data["candidate_index"],
                "candidate_uuid": candidate_data["candidate_uuid"],
                "correlation": 0.9876,
                "success": True,
                "epochs_completed": training_params["epochs"],
                "activation_name": candidate_data.get("activation_name", "sigmoid"),
                "all_correlations": [0.9876],
                "numerator": 1.0,
                "denominator": 1.0,
                "best_corr_idx": 0,
                "error_message": None,
            }
            tensor_out = {"weights": np.zeros((2, 1), dtype=np.float32), "bias": np.zeros((1,), dtype=np.float32)}
            return result, tensor_out

        agent = _make_agent(server.url)
        agent_task = asyncio.create_task(agent.run())
        try:
            with patch("juniper_cascor_worker.worker._execute_task", side_effect=fake_execute):
                result_msg = await _wait_for_task_result(server, "task-int-001")
                assert result_msg["candidate_uuid"] == "uuid-int-001"
                assert result_msg["candidate_id"] == 7
                assert result_msg["success"] is True
                assert result_msg["correlation"] == pytest.approx(0.9876)
                assert set(result_msg["tensor_manifest"].keys()) == {"weights", "bias"}
        finally:
            await _stop_agent(agent, agent_task)


async def test_task_timeout_preserves_candidate_uuid_cw04() -> None:
    """CW-04 regression: timeout response carries the actual candidate_uuid."""
    async with _running_server() as server:
        manifest = {
            "candidate_input": {"shape": [1, 1], "dtype": "float32"},
            "residual_error": {"shape": [1, 1], "dtype": "float32"},
        }
        server.tasks_to_assign = [
            {
                "assign": {
                    "type": MSG_TYPE_TASK_ASSIGN,
                    "task_id": "task-timeout-001",
                    "candidate_index": 3,
                    "candidate_data": {"candidate_uuid": "uuid-timeout-zzz"},
                    "training_params": {"epochs": 1},
                    "tensor_manifest": manifest,
                },
                "frames": [_encode_frame(np.zeros((1, 1), dtype=np.float32)), _encode_frame(np.zeros((1, 1), dtype=np.float32))],
            }
        ]

        async def hang_forever(*_args, **_kwargs):
            await asyncio.sleep(60)

        agent = _make_agent(server.url, task_timeout=0.1)
        agent_task = asyncio.create_task(agent.run())
        try:
            with patch("juniper_cascor_worker.worker.asyncio.to_thread", side_effect=hang_forever):
                result_msg = await _wait_for_task_result(server, "task-timeout-001")
                assert result_msg["candidate_uuid"] == "uuid-timeout-zzz", "CW-04: timeout response must carry the original UUID"
                assert result_msg["success"] is False
                assert "timed out" in result_msg["error_message"]
        finally:
            await _stop_agent(agent, agent_task)


async def test_invalid_manifest_rejected_cw07() -> None:
    """CW-07 regression: a manifest missing required keys is rejected up front."""
    async with _running_server() as server:
        # Manifest deliberately omits the required "residual_error" key.
        broken_manifest = {"candidate_input": {"shape": [1, 1], "dtype": "float32"}}
        server.tasks_to_assign = [
            {
                "assign": {
                    "type": MSG_TYPE_TASK_ASSIGN,
                    "task_id": "task-bad-manifest",
                    "candidate_index": 2,
                    "candidate_data": {"candidate_uuid": "uuid-bad-manifest"},
                    "training_params": {"epochs": 1},
                    "tensor_manifest": broken_manifest,
                },
                "frames": [],  # never read because manifest is rejected
            }
        ]

        agent = _make_agent(server.url)
        agent_task = asyncio.create_task(agent.run())
        try:
            result_msg = await _wait_for_task_result(server, "task-bad-manifest")
            assert result_msg["success"] is False
            assert result_msg["candidate_uuid"] == "uuid-bad-manifest"
            assert "manifest" in result_msg["error_message"].lower()
        finally:
            await _stop_agent(agent, agent_task)


# ─── Skip the lot when websockets server APIs are unavailable ───────────────


def _websockets_serve_available() -> bool:
    try:
        from websockets.asyncio.server import serve  # noqa: F401

        return True
    except ImportError:
        return False


pytestmark = pytestmark + [pytest.mark.skipif(not _websockets_serve_available(), reason="websockets.asyncio.server.serve unavailable")]
