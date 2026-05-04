"""Tests for METRICS-MON R1.3 / seed-04 worker-side instrumentation.

Covers:
- Liveness counter / is_alive-style tick semantics
- Readiness tick (registration handshake + WS connection)
- Enriched heartbeat payload contents
- Task accounting (in_flight_tasks / counters / last_task_completed_at)
- Disconnect resets ``_registered`` so readiness flips to 503
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from juniper_cascor_worker.config import WorkerConfig
from juniper_cascor_worker.constants import MSG_TYPE_HEARTBEAT
from juniper_cascor_worker.exceptions import WorkerConnectionError
from juniper_cascor_worker.worker import CascorWorkerAgent


def _agent() -> CascorWorkerAgent:
    cfg = WorkerConfig(server_url="ws://localhost:8200/ws/v1/workers", heartbeat_interval=1.0)
    return CascorWorkerAgent(cfg)


@pytest.mark.unit
class TestLivenessTick:
    def test_tick_raises_when_no_connection(self):
        agent = _agent()
        agent._connection = None
        with pytest.raises(RuntimeError, match="websocket connection not bound"):
            agent._liveness_tick()

    def test_tick_raises_when_connection_disconnected(self):
        agent = _agent()
        agent._connection = MagicMock()
        agent._connection.connected = False
        with pytest.raises(RuntimeError, match="websocket connection not bound"):
            agent._liveness_tick()

    def test_tick_passes_when_connection_active_and_fresh_bump(self):
        agent = _agent()
        agent._connection = MagicMock()
        agent._connection.connected = True
        agent._bump_liveness()
        agent._liveness_tick()  # must not raise

    def test_tick_raises_when_heartbeat_stale(self):
        agent = _agent()
        agent._connection = MagicMock()
        agent._connection.connected = True
        # Force the timestamp far enough into the past to exceed 2 * heartbeat_interval (= 2 s)
        agent._liveness_last_tick_at = time.monotonic() - 100.0
        with pytest.raises(RuntimeError, match="stale"):
            agent._liveness_tick()

    def test_bump_advances_counter_and_timestamp(self):
        agent = _agent()
        before_counter = agent._liveness_counter
        before_ts = agent._liveness_last_tick_at
        time.sleep(0.001)
        agent._bump_liveness()
        assert agent._liveness_counter == before_counter + 1
        assert agent._liveness_last_tick_at > before_ts


@pytest.mark.unit
class TestReadinessTick:
    def test_readiness_raises_when_not_registered(self):
        agent = _agent()
        agent._connection = MagicMock()
        agent._connection.connected = True
        agent._registered = False
        with pytest.raises(RuntimeError, match="registration"):
            agent._readiness_tick()

    def test_readiness_raises_when_no_connection(self):
        agent = _agent()
        agent._connection = None
        agent._registered = True
        with pytest.raises(RuntimeError, match="websocket connection"):
            agent._readiness_tick()

    def test_readiness_passes_when_connection_active_and_registered(self):
        agent = _agent()
        agent._connection = MagicMock()
        agent._connection.connected = True
        agent._registered = True
        agent._readiness_tick()  # must not raise

    @pytest.mark.asyncio
    async def test_disconnect_resets_registered_flag_after_registered_loop_teardown(self, monkeypatch):
        """A closed WS loop must make readiness fail until the next register ack."""
        agent = _agent()

        mock_conn = AsyncMock()
        mock_conn.receive_json.side_effect = [
            {"type": "connection_established"},
            {"type": "registration_ack"},
        ]
        mock_conn.receive.side_effect = WorkerConnectionError("socket closed")

        async def _stop_after_reconnect_delay(_seconds):
            agent._stop_event.set()

        monkeypatch.setattr(asyncio, "sleep", _stop_after_reconnect_delay)

        await agent._run_inner(lambda **_kwargs: mock_conn)

        assert agent._registered is False
        mock_conn.close.assert_awaited_once()
        with pytest.raises(RuntimeError, match="registration"):
            agent._readiness_tick()


@pytest.mark.unit
class TestHeartbeatEnrichment:
    @pytest.mark.asyncio
    async def test_heartbeat_payload_includes_enriched_fields(self, monkeypatch):
        """One iteration of the heartbeat loop sends an enriched payload."""
        agent = _agent()
        agent._connection = MagicMock()
        agent._connection.connected = True
        agent._connection.send_json = AsyncMock()

        agent._in_flight_tasks = 2
        agent._last_task_completed_at = 1745816350.0
        agent._tasks_completed = 11
        agent._tasks_failed = 1

        # Avoid pulling real getrusage into the assertion: stub sample_rss_mb.
        import juniper_cascor_worker.http_health as hh

        monkeypatch.setattr(hh, "sample_rss_mb", lambda: 256.5)

        # Drive ONE iteration of _heartbeat_loop by patching asyncio.sleep
        # to set the stop event after the first sleep. This avoids
        # re-implementing the loop here while still exercising the live
        # send-payload path.
        async def _fake_sleep(_):
            agent._stop_event.set()

        monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
        await agent._heartbeat_loop()

        agent._connection.send_json.assert_called_once()
        msg = agent._connection.send_json.call_args.args[0]
        assert msg["type"] == MSG_TYPE_HEARTBEAT
        assert msg["worker_id"] == agent.worker_id
        assert msg["in_flight_tasks"] == 2
        assert msg["last_task_completed_at"] == 1745816350.0
        assert msg["rss_mb"] == 256.5
        assert msg["tasks_completed"] == 11
        assert msg["tasks_failed"] == 1


@pytest.mark.unit
class TestTaskAccounting:
    """Verify the success/failure flag flow through ``_handle_task_assign``.

    We don't drive the full WS protocol path (that lives in
    ``test_worker_agent.py``); instead we exercise the wrapper directly.
    """

    @pytest.mark.asyncio
    async def test_successful_task_increments_completed_counter(self):
        agent = _agent()
        agent._handle_task_assign_body = AsyncMock(return_value=True)
        agent._connection = MagicMock()

        await agent._handle_task_assign({"task_id": "t-1"})

        assert agent._in_flight_tasks == 0
        assert agent._tasks_completed == 1
        assert agent._tasks_failed == 0
        assert agent._last_task_completed_at is not None

    @pytest.mark.asyncio
    async def test_successful_task_records_duration_for_next_heartbeat(self, monkeypatch):
        agent = _agent()
        agent._handle_task_assign_body = AsyncMock(return_value=True)
        agent._connection = MagicMock()

        monotonic_values = iter([100.0, 100.25])
        monkeypatch.setattr("juniper_cascor_worker.worker.time.monotonic", lambda: next(monotonic_values))
        monkeypatch.setattr("juniper_cascor_worker.worker.time.time", lambda: 2000.0)

        await agent._handle_task_assign({"task_id": "t-duration"})

        assert agent._last_task_completed_at == 2000.0
        assert agent._last_task_duration_seconds == pytest.approx(0.25)
        assert list(agent._recent_task_durations_seconds) == [pytest.approx(0.25)]

    @pytest.mark.asyncio
    async def test_failed_task_increments_failed_counter(self):
        agent = _agent()
        agent._handle_task_assign_body = AsyncMock(return_value=False)
        agent._connection = MagicMock()

        await agent._handle_task_assign({"task_id": "t-2"})

        assert agent._in_flight_tasks == 0
        assert agent._tasks_completed == 0
        assert agent._tasks_failed == 1

    @pytest.mark.asyncio
    async def test_exception_in_body_still_decrements_in_flight(self):
        """A raised exception during task handling must not leak the in-flight count."""
        agent = _agent()
        agent._handle_task_assign_body = AsyncMock(side_effect=RuntimeError("boom"))
        agent._connection = MagicMock()

        with pytest.raises(RuntimeError, match="boom"):
            await agent._handle_task_assign({"task_id": "t-3"})

        assert agent._in_flight_tasks == 0
        assert agent._tasks_failed == 1
