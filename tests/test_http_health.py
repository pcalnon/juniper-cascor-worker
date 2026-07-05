"""Tests for the worker's HTTP health probe surface (METRICS-MON R1.3 / seed-04).

Covers:
- HealthServer happy path on each endpoint (200 + body shape)
- 503 on liveness tick failure / budget exceedance
- 503 on readiness tick failure
- Malformed-request rejection without crashing the listener
- Method-not-allowed (POST/PUT/DELETE)
- 404 on unknown paths
- Concurrent probe requests
- sample_rss_mb() Linux + macOS code paths via sys.platform monkeypatch
"""

from __future__ import annotations

import asyncio
import json
import socket
import sys
from typing import Optional, Tuple

import pytest
import pytest_asyncio

from juniper_cascor_worker.constants import HEALTH_REQUEST_MAX_BYTES, HEALTH_REQUEST_READ_TIMEOUT_S, LIVENESS_TICK_BUDGET_MS
from juniper_cascor_worker.http_health import HealthProbeError, HealthServer, sample_rss_mb


def _free_port() -> int:
    """Find a free port for the test server."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


async def _http_get(host: str, port: int, path: str, *, raw: Optional[bytes] = None) -> Tuple[int, dict[str, str], bytes]:
    """Send a GET (or raw bytes) and return (status, headers, body)."""
    reader, writer = await asyncio.open_connection(host, port)
    try:
        if raw is not None:
            writer.write(raw)
        else:
            writer.write(f"GET {path} HTTP/1.1\r\nHost: {host}\r\n\r\n".encode("ascii"))
        await writer.drain()
        data = await reader.read(8192)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass

    head, _, body = data.partition(b"\r\n\r\n")
    head_lines = head.decode("ascii", errors="replace").split("\r\n")
    status_line = head_lines[0] if head_lines else ""
    parts = status_line.split(" ", 2)
    status = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
    headers: dict[str, str] = {}
    for line in head_lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return status, headers, body


@pytest_asyncio.fixture
async def server_factory():
    """Yield a function that builds + starts a HealthServer; tears down after."""
    started: list[HealthServer] = []

    async def _make(*, liveness_tick=lambda: None, readiness_tick=lambda: None, worker_id="w1", git_sha=None, build_date=None) -> Tuple[HealthServer, int]:
        port = _free_port()
        srv = HealthServer(
            liveness_tick=liveness_tick,
            readiness_tick=readiness_tick,
            worker_id_provider=lambda: worker_id,
            version="1.2.3",
            host="127.0.0.1",
            port=port,
            git_sha=git_sha,
            build_date=build_date,
        )
        await srv.start()
        started.append(srv)
        return srv, port

    yield _make

    for srv in started:
        await srv.stop()


@pytest.mark.asyncio
async def test_health_endpoint_returns_200_with_worker_id(server_factory):
    _srv, port = await server_factory()
    status, _h, body = await _http_get("127.0.0.1", port, "/v1/health")
    assert status == 200
    payload = json.loads(body)
    assert payload["status"] == "ok"
    assert payload["worker_id"] == "w1"
    assert payload["version"] == "1.2.3"
    # Build provenance absent (built bare / local) → fields present but null.
    assert payload["git_sha"] is None
    assert payload["build_date"] is None


@pytest.mark.asyncio
async def test_health_endpoint_includes_build_provenance(server_factory):
    """When the image baked a git SHA + build date into the worker's env, the
    /v1/health body surfaces them (build provenance / stale-image detection)."""
    _srv, port = await server_factory(git_sha="abc1234", build_date="2026-06-14T00:00:00Z")
    status, _h, body = await _http_get("127.0.0.1", port, "/v1/health")
    assert status == 200
    payload = json.loads(body)
    assert payload["git_sha"] == "abc1234"
    assert payload["build_date"] == "2026-06-14T00:00:00Z"


@pytest.mark.asyncio
async def test_liveness_200_on_success(server_factory):
    _srv, port = await server_factory(liveness_tick=lambda: None)
    status, _h, body = await _http_get("127.0.0.1", port, "/v1/health/live")
    assert status == 200
    payload = json.loads(body)
    assert payload["status"] == "alive"
    assert payload["tick"] == "juniper-cascor-worker"
    assert isinstance(payload["duration_ms"], int)


@pytest.mark.asyncio
async def test_liveness_503_when_tick_raises(server_factory):
    def _raises():
        raise HealthProbeError("websocket connection not bound")

    _srv, port = await server_factory(liveness_tick=_raises)
    status, _h, body = await _http_get("127.0.0.1", port, "/v1/health/live")
    assert status == 503
    payload = json.loads(body)
    assert payload["status"] == "unresponsive"
    assert "websocket" in payload["error"]


@pytest.mark.asyncio
async def test_liveness_503_when_tick_exceeds_budget(server_factory):
    import time as _t

    def _slow():
        # Block for longer than LIVENESS_TICK_BUDGET_MS
        _t.sleep((LIVENESS_TICK_BUDGET_MS + 50) / 1000)

    _srv, port = await server_factory(liveness_tick=_slow)
    status, _h, body = await _http_get("127.0.0.1", port, "/v1/health/live")
    assert status == 503
    payload = json.loads(body)
    assert payload["status"] == "unresponsive"
    assert "exceeded budget" in payload["error"]
    assert payload["duration_ms"] > LIVENESS_TICK_BUDGET_MS


@pytest.mark.asyncio
async def test_readiness_200_on_success(server_factory):
    _srv, port = await server_factory(readiness_tick=lambda: None)
    status, headers, body = await _http_get("127.0.0.1", port, "/v1/health/ready")
    assert status == 200
    assert headers.get("x-juniper-readiness") == "ready"
    payload = json.loads(body)
    assert payload["status"] == "ready"


@pytest.mark.asyncio
async def test_readiness_503_when_tick_raises(server_factory):
    def _raises():
        raise HealthProbeError("worker registration handshake not complete")

    _srv, port = await server_factory(readiness_tick=_raises)
    status, headers, body = await _http_get("127.0.0.1", port, "/v1/health/ready")
    assert status == 503
    assert headers.get("x-juniper-readiness") == "not_ready"
    payload = json.loads(body)
    assert payload["status"] == "not_ready"
    assert "registration" in payload["error"]


@pytest.mark.asyncio
async def test_unknown_path_returns_404(server_factory):
    _srv, port = await server_factory()
    status, _h, _b = await _http_get("127.0.0.1", port, "/v1/nope")
    assert status == 404


@pytest.mark.asyncio
async def test_post_method_rejected_405(server_factory):
    _srv, port = await server_factory()
    raw = b"POST /v1/health/live HTTP/1.1\r\nHost: x\r\n\r\n"
    status, _h, _b = await _http_get("127.0.0.1", port, "/", raw=raw)
    assert status == 405


@pytest.mark.asyncio
async def test_malformed_request_line_400(server_factory):
    _srv, port = await server_factory()
    raw = b"GARBAGE\r\n\r\n"
    status, _h, _b = await _http_get("127.0.0.1", port, "/", raw=raw)
    assert status == 400


@pytest.mark.asyncio
async def test_oversize_request_rejected(server_factory):
    _srv, port = await server_factory()
    raw = b"GET /v1/health HTTP/1.1\r\n" + (b"X-Filler: " + b"a" * 5000 + b"\r\n") + b"\r\n"
    status, _h, _b = await _http_get("127.0.0.1", port, "/", raw=raw)
    assert status == 400


@pytest.mark.asyncio
async def test_listener_survives_after_bad_request(server_factory):
    """One malformed connection must not kill subsequent good probes."""
    _srv, port = await server_factory()
    bad_status, _h, _b = await _http_get("127.0.0.1", port, "/", raw=b"BAD\r\n\r\n")
    assert bad_status == 400
    good_status, _h, body = await _http_get("127.0.0.1", port, "/v1/health")
    assert good_status == 200
    assert json.loads(body)["status"] == "ok"


@pytest.mark.asyncio
async def test_concurrent_probes_complete_within_budget(server_factory):
    """Five concurrent /live probes all return 200 — the listener handles concurrent connections."""
    _srv, port = await server_factory(liveness_tick=lambda: None)
    results = await asyncio.gather(*[_http_get("127.0.0.1", port, "/v1/health/live") for _ in range(5)])
    statuses = [r[0] for r in results]
    assert statuses == [200] * 5


@pytest.mark.asyncio
async def test_query_string_stripped_before_path_match(server_factory):
    """Query strings on probe paths must not break the route lookup."""
    _srv, port = await server_factory(liveness_tick=lambda: None)
    status, _h, _b = await _http_get("127.0.0.1", port, "/v1/health/live?probe=k8s")
    assert status == 200


@pytest.mark.asyncio
async def test_start_is_idempotent(server_factory):
    """Calling start() twice must not raise or rebind the port."""
    srv, _port = await server_factory()
    await srv.start()  # second call must be a no-op
    assert srv.started is True


# ---------------------------------------------------------------------------
# sample_rss_mb cross-platform tests
# ---------------------------------------------------------------------------


def test_sample_rss_mb_returns_non_negative_float():
    """The Linux/macOS happy path returns a non-negative float."""
    rss = sample_rss_mb()
    assert isinstance(rss, float)
    assert rss >= 0.0


def test_sample_rss_mb_linux_path(monkeypatch):
    """Linux: ru_maxrss is kilobytes → divide by 1024."""
    import juniper_cascor_worker.http_health as hh

    fake_rusage = type("R", (), {"ru_maxrss": 4096})()  # 4 MB in kilobytes
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr("resource.getrusage", lambda _what: fake_rusage)
    rss = hh._sample_rss_mb_impl()
    assert rss == pytest.approx(4.0)


def test_sample_rss_mb_macos_path(monkeypatch):
    """macOS: ru_maxrss is bytes → divide by 1024 ** 2."""
    import juniper_cascor_worker.http_health as hh

    fake_rusage = type("R", (), {"ru_maxrss": 4 * 1024 * 1024})()  # 4 MB in bytes
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr("resource.getrusage", lambda _what: fake_rusage)
    rss = hh._sample_rss_mb_impl()
    assert rss == pytest.approx(4.0)


def test_sample_rss_mb_handles_resource_error(monkeypatch):
    """A failed getrusage() must return 0.0, never raise."""
    import juniper_cascor_worker.http_health as hh

    def _raises(_what):
        raise OSError("rusage unavailable")

    monkeypatch.setattr("resource.getrusage", _raises)
    rss = hh._sample_rss_mb_impl()
    assert rss == 0.0


# ---------------------------------------------------------------------------
# Connection-handler error branches + resource-import fallback.
# Per-file coverage rollout C-5 (juniper-ml
# notes/JUNIPER_ECOSYSTEM_PER_FILE_COVERAGE_ROLLOUT_SCOPING_2026-06-30.md):
# lift http_health.py to the ratified >=90% per-file statement bar by
# exercising the timeout, malformed-request, and never-crash outer-handler
# paths that the happy-path suite above does not reach.
# ---------------------------------------------------------------------------


async def _raw_exchange(host: str, port: int, *, send: Optional[bytes], eof: bool = False, hold: float = 0.0) -> int:
    """Open a connection, optionally write ``send``, optionally half-close
    (EOF) or hold the connection open for ``hold`` seconds, then read and
    return the HTTP status code from the response."""
    reader, writer = await asyncio.open_connection(host, port)
    try:
        if send is not None:
            writer.write(send)
            await writer.drain()
        if eof:
            writer.write_eof()
        if hold:
            await asyncio.sleep(hold)
        data = await reader.read(8192)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass

    head, _, _body = data.partition(b"\r\n\r\n")
    status_line = head.decode("ascii", errors="replace").split("\r\n")[0]
    parts = status_line.split(" ", 2)
    return int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0


@pytest.mark.asyncio
async def test_stop_is_noop_when_never_started():
    """stop() on an unstarted server is a safe no-op (idempotent teardown)."""
    srv = HealthServer(
        liveness_tick=lambda: None,
        readiness_tick=lambda: None,
        worker_id_provider=lambda: "w1",
        version="1.2.3",
        host="127.0.0.1",
        port=_free_port(),
    )
    assert srv.started is False
    await srv.stop()  # must not raise
    assert srv.started is False


@pytest.mark.asyncio
async def test_empty_request_rejected_400(server_factory):
    """A client that half-closes without sending a request line -> 400."""
    _srv, port = await server_factory()
    status = await _raw_exchange("127.0.0.1", port, send=None, eof=True)
    assert status == 400


@pytest.mark.asyncio
async def test_oversize_request_line_rejected_400(server_factory):
    """A request line exceeding HEALTH_REQUEST_MAX_BYTES -> 400 (distinct from
    the oversize-header path already covered above)."""
    _srv, port = await server_factory()
    huge = b"GET /" + b"a" * (HEALTH_REQUEST_MAX_BYTES + 10) + b" HTTP/1.1\r\n\r\n"
    status = await _raw_exchange("127.0.0.1", port, send=huge)
    assert status == 400


@pytest.mark.asyncio
async def test_non_ascii_request_line_rejected_400(server_factory):
    """A request line carrying non-ASCII bytes -> 400 without crashing the listener."""
    _srv, port = await server_factory()
    status = await _raw_exchange("127.0.0.1", port, send=b"GET /\xff\xfe HTTP/1.1\r\n\r\n")
    assert status == 400


@pytest.mark.asyncio
async def test_request_line_read_timeout_408(server_factory):
    """Connecting without sending anything trips the request-line read timeout -> 408."""
    _srv, port = await server_factory()
    status = await _raw_exchange("127.0.0.1", port, send=None, hold=HEALTH_REQUEST_READ_TIMEOUT_S + 0.5)
    assert status == 408


@pytest.mark.asyncio
async def test_header_read_timeout_408(server_factory):
    """Sending a request line but never the terminating blank line trips the
    header read timeout -> 408."""
    _srv, port = await server_factory()
    status = await _raw_exchange("127.0.0.1", port, send=b"GET /v1/health HTTP/1.1\r\n", hold=HEALTH_REQUEST_READ_TIMEOUT_S + 0.5)
    assert status == 408


@pytest.mark.asyncio
async def test_handler_returns_500_when_response_build_raises():
    """An unexpected error while building a response must be caught by the outer
    handler and surfaced as 500 — one bad request never kills the listener."""

    def _boom() -> str:
        raise RuntimeError("provider blew up")

    port = _free_port()
    srv = HealthServer(
        liveness_tick=lambda: None,
        readiness_tick=lambda: None,
        worker_id_provider=_boom,
        version="1.2.3",
        host="127.0.0.1",
        port=port,
    )
    await srv.start()
    try:
        status = await _raw_exchange("127.0.0.1", port, send=b"GET /v1/health HTTP/1.1\r\nHost: x\r\n\r\n")
        assert status == 500
    finally:
        await srv.stop()


def test_sample_rss_mb_handles_missing_resource_module(monkeypatch):
    """On a platform without the ``resource`` module the sampler returns 0.0."""
    import juniper_cascor_worker.http_health as hh

    monkeypatch.setitem(sys.modules, "resource", None)
    assert hh._sample_rss_mb_impl() == 0.0
