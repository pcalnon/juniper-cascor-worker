"""Minimal HTTP/1.1 health-probe server for the cascor-worker.

METRICS-MON R1.3 / seed-04: workers run unattended in Kubernetes; the prior
``exec: kill -0 1`` Helm probe only catches process death and misses every
event-loop wedge, deadlocked task, and stuck reconnect loop. This module
exposes ``/v1/health``, ``/v1/health/live``, and ``/v1/health/ready`` over
HTTP/1.1 on a configurable port (default 8210, localhost-only) so the
orchestrator can drive restart decisions from the same R1.2 contract that
juniper-data, juniper-cascor, and juniper-canopy already implement.

The implementation is hand-rolled on top of ``asyncio.start_server`` to
avoid pulling FastAPI/uvicorn into the slim worker image (Option C from the
R1.3 design doc). The handler accepts only ``GET`` on three exact paths,
caps total request bytes, and applies a strict read timeout so a malformed
or oversize request cannot wedge the worker.

See: notes/code-review/METRICS_MONITORING_R1.3_WORKER_HEARTBEAT_DESIGN_2026-04-27.md
in juniper-ml.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Callable

from juniper_cascor_worker.constants import HEALTH_REQUEST_MAX_BYTES, HEALTH_REQUEST_READ_TIMEOUT_S, LIVENESS_TICK_BUDGET_MS

logger = logging.getLogger(__name__)


# Body status / endpoint identity constants — kept here (not constants.py)
# because they are public HTTP contract surface and live with the handler
# that emits them.
TICK_NAME = "juniper-cascor-worker"
READINESS_HEADER = "X-Juniper-Readiness"


class HealthProbeError(RuntimeError):
    """Raised by the liveness or readiness tick to signal probe failure.

    The handler converts this into an HTTP 503 with the exception message
    in the body's ``error`` field.
    """


# Type alias: synchronous probe callbacks returning None on success / raising
# on failure. Probes are pure in-process work (no awaits, no I/O) per R1.3
# §4.2 — keeps the budget meaningful and avoids cancellation surprises.
ProbeFn = Callable[[], None]
ReadinessFn = Callable[[], None]


class HealthServer:
    """asyncio.start_server-backed HTTP/1.1 health endpoint.

    Hosts three GET endpoints:

      * ``GET /v1/health``       — backwards-compatible no-op (200 always)
      * ``GET /v1/health/live``  — runs the liveness tick within the budget
      * ``GET /v1/health/ready`` — runs the readiness tick

    Liveness and readiness tick callbacks are passed in by the worker so
    the server stays decoupled from the worker's internal state.

    The server binds to ``host``/``port`` when ``start()`` is called and
    serves until ``stop()`` is awaited.
    """

    def __init__(
        self,
        *,
        liveness_tick: ProbeFn,
        readiness_tick: ReadinessFn,
        worker_id_provider: Callable[[], str | None],
        version: str,
        host: str,
        port: int,
    ) -> None:
        self._liveness_tick = liveness_tick
        self._readiness_tick = readiness_tick
        self._worker_id_provider = worker_id_provider
        self._version = version
        self._host = host
        self._port = port
        self._server: asyncio.base_events.Server | None = None

    @property
    def started(self) -> bool:
        return self._server is not None and self._server.is_serving()

    async def start(self) -> None:
        """Bind the listener. Idempotent — calling twice is a no-op."""
        if self._server is not None:
            return
        self._server = await asyncio.start_server(self._handle_connection, self._host, self._port)
        logger.info("worker health server listening on %s:%d", self._host, self._port)

    async def stop(self) -> None:
        """Close the listener and wait for in-flight handlers to finish."""
        if self._server is None:
            return
        self._server.close()
        try:
            await self._server.wait_closed()
        finally:
            self._server = None
            logger.info("worker health server stopped")

    async def _handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Per-connection handler. Reads one request, writes one response, closes."""
        try:
            try:
                method, path = await asyncio.wait_for(self._read_request_line(reader), timeout=HEALTH_REQUEST_READ_TIMEOUT_S)
            except asyncio.TimeoutError:
                await self._write_simple(writer, 408, "request line read timeout")
                return
            except _MalformedRequest as exc:
                await self._write_simple(writer, 400, str(exc))
                return

            # Drain headers (we ignore them but must consume so the client
            # half-close doesn't fire mid-read on a misbehaving probe).
            try:
                await asyncio.wait_for(self._drain_headers(reader), timeout=HEALTH_REQUEST_READ_TIMEOUT_S)
            except asyncio.TimeoutError:
                await self._write_simple(writer, 408, "header read timeout")
                return
            except _MalformedRequest as exc:
                await self._write_simple(writer, 400, str(exc))
                return

            if method != "GET":
                await self._write_simple(writer, 405, "method not allowed")
                return

            await self._dispatch(writer, path)
        except Exception:  # noqa: BLE001 — never crash the listener; one bad request must not kill all probes
            logger.exception("unhandled error in health-probe connection handler")
            try:
                await self._write_simple(writer, 500, "internal error")
            except Exception:  # noqa: BLE001  # nosec B110 — best-effort error reply; client may have already disconnected
                pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:  # noqa: BLE001  # nosec B110 — best-effort cleanup; close errors are not actionable
                pass

    async def _read_request_line(self, reader: asyncio.StreamReader) -> tuple[str, str]:
        line = await reader.readline()
        if not line:
            raise _MalformedRequest("empty request")
        if len(line) > HEALTH_REQUEST_MAX_BYTES:
            raise _MalformedRequest("request line exceeds maximum size")
        try:
            text = line.rstrip(b"\r\n").decode("ascii")
        except UnicodeDecodeError as exc:
            raise _MalformedRequest("non-ASCII request line") from exc
        parts = text.split(" ")
        if len(parts) != 3:
            raise _MalformedRequest("malformed request line")
        method, path, _proto = parts
        # Strip any query string — we don't honor params on probe paths.
        if "?" in path:
            path = path.split("?", 1)[0]
        return method, path

    async def _drain_headers(self, reader: asyncio.StreamReader) -> None:
        """Read header lines until a blank line. Caps total bytes."""
        bytes_read = 0
        while True:
            line = await reader.readline()
            bytes_read += len(line)
            if bytes_read > HEALTH_REQUEST_MAX_BYTES:
                raise _MalformedRequest("headers exceed maximum size")
            if line in (b"\r\n", b"\n", b""):
                return

    async def _dispatch(self, writer: asyncio.StreamWriter, path: str) -> None:
        if path == "/v1/health":
            await self._write_json(writer, 200, {"status": "ok", "worker_id": self._worker_id_provider(), "version": self._version})
            return
        if path == "/v1/health/live":
            await self._handle_liveness(writer)
            return
        if path == "/v1/health/ready":
            await self._handle_readiness(writer)
            return
        await self._write_simple(writer, 404, "not found")

    async def _handle_liveness(self, writer: asyncio.StreamWriter) -> None:
        started = time.perf_counter()
        try:
            self._liveness_tick()
        except Exception as exc:  # noqa: BLE001 — health probe must surface every failure
            duration_ms = int((time.perf_counter() - started) * 1000)
            await self._write_json(
                writer,
                503,
                {
                    "status": "unresponsive",
                    "tick": TICK_NAME,
                    "error": str(exc),
                    "duration_ms": duration_ms,
                },
            )
            return

        duration_ms = int((time.perf_counter() - started) * 1000)
        if duration_ms > LIVENESS_TICK_BUDGET_MS:
            await self._write_json(
                writer,
                503,
                {
                    "status": "unresponsive",
                    "tick": TICK_NAME,
                    "error": f"tick exceeded budget: {duration_ms}ms > {LIVENESS_TICK_BUDGET_MS}ms",
                    "duration_ms": duration_ms,
                },
            )
            return

        await self._write_json(
            writer,
            200,
            {
                "status": "alive",
                "tick": TICK_NAME,
                "duration_ms": duration_ms,
            },
        )

    async def _handle_readiness(self, writer: asyncio.StreamWriter) -> None:
        try:
            self._readiness_tick()
        except Exception as exc:  # noqa: BLE001 — probe must report every reason
            await self._write_json(
                writer,
                503,
                {"status": "not_ready", "service": TICK_NAME, "error": str(exc)},
                extra_headers=[(READINESS_HEADER, "not_ready")],
            )
            return
        await self._write_json(
            writer,
            200,
            {"status": "ready", "service": TICK_NAME},
            extra_headers=[(READINESS_HEADER, "ready")],
        )

    async def _write_json(
        self,
        writer: asyncio.StreamWriter,
        status: int,
        body: dict,
        *,
        extra_headers: list[tuple[str, str]] | None = None,
    ) -> None:
        payload = json.dumps(body).encode("utf-8")
        await self._write_response(writer, status, payload, content_type="application/json", extra_headers=extra_headers)

    async def _write_simple(self, writer: asyncio.StreamWriter, status: int, message: str) -> None:
        payload = message.encode("utf-8")
        await self._write_response(writer, status, payload, content_type="text/plain; charset=utf-8")

    async def _write_response(
        self,
        writer: asyncio.StreamWriter,
        status: int,
        body: bytes,
        *,
        content_type: str,
        extra_headers: list[tuple[str, str]] | None = None,
    ) -> None:
        reason = _STATUS_REASONS.get(status, "")
        lines = [
            f"HTTP/1.1 {status} {reason}".rstrip(),
            f"Content-Type: {content_type}",
            f"Content-Length: {len(body)}",
            "Connection: close",
        ]
        if extra_headers:
            for name, value in extra_headers:
                lines.append(f"{name}: {value}")
        head = ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")
        writer.write(head + body)
        try:
            await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass


class _MalformedRequest(Exception):
    """Internal sentinel for protocol-level violations."""


_STATUS_REASONS: dict[int, str] = {
    200: "OK",
    400: "Bad Request",
    404: "Not Found",
    405: "Method Not Allowed",
    408: "Request Timeout",
    500: "Internal Server Error",
    503: "Service Unavailable",
}


# ---------------------------------------------------------------------------
# Resource sampling — needed by the worker to populate ``rss_mb`` in the
# enriched heartbeat. Lives here because the HTTP server module is the only
# observability-adjacent module already; keeping it co-located avoids
# spreading platform branches.
# ---------------------------------------------------------------------------


def sample_rss_mb() -> float:
    """Return the current process's resident set size, in megabytes.

    METRICS-MON R1.3 §5.3:

      * Linux: ``ru_maxrss`` is reported in **kilobytes** → divide by 1024.
      * macOS / Darwin: ``ru_maxrss`` is reported in **bytes** → divide by
        1024 ** 2.

    Falls back to ``0.0`` on platforms where the resource module is not
    available (e.g. Windows). Never raises.
    """
    return _sample_rss_mb_impl()


def _sample_rss_mb_impl() -> float:
    """Concrete implementation; split out so unit tests can monkeypatch
    ``sys.platform`` without re-importing the module.
    """
    import sys

    try:
        import resource
    except ImportError:
        return 0.0

    try:
        rusage = resource.getrusage(resource.RUSAGE_SELF)
    except (OSError, ValueError):
        return 0.0

    raw = float(rusage.ru_maxrss)
    if sys.platform == "darwin":
        # macOS reports bytes
        return raw / (1024.0 * 1024.0)
    # Linux (and BSDs that follow Linux convention) report kilobytes
    return raw / 1024.0
