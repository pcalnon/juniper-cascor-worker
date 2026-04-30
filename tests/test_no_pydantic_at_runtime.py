"""METRICS-MON R2.2.6 / seed-05 — worker stays Pydantic-free at runtime.

The R2 exit-gate decision (juniper-ml#168) committed to keeping
Pydantic out of the worker container: numpy + torch + websockets only.
R2.2.6 introduced a runtime dep on ``juniper-cascor-protocol``, which
ships Pydantic as an envelope-subpackage dependency on disk. The
worker imports **only** ``juniper_cascor_protocol.worker.*`` (the
StrEnum + numpy ``BinaryFrame``) so Pydantic stays dormant on disk
and never enters ``sys.modules`` at runtime.

This file pins that invariant. If a future refactor accidentally
crosses the envelope subpackage, the test fails before the slim-image
guarantee is silently lost.
"""

from __future__ import annotations

import subprocess  # nosec B404 — running sys.executable with hardcoded inline code (no untrusted input)
import sys

import pytest


@pytest.mark.unit
def test_worker_constants_does_not_load_pydantic():
    """Importing ``juniper_cascor_worker.constants`` does not pull Pydantic.

    Runs in a subprocess so the test isn't influenced by other test
    files that may have already imported Pydantic (test_worker_agent.py
    doesn't, but many pytest plugins do).
    """
    code = "import sys, juniper_cascor_worker.constants;" "assert 'pydantic' not in sys.modules, 'pydantic in sys.modules'"
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)  # nosec B603 — sys.executable + hardcoded inline code, no shell, no untrusted input
    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"


@pytest.mark.unit
def test_worker_module_does_not_load_pydantic():
    """Importing ``juniper_cascor_worker.worker`` does not pull Pydantic."""
    code = "import sys, juniper_cascor_worker.worker;" "assert 'pydantic' not in sys.modules, 'pydantic in sys.modules'"
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)  # nosec B603 — sys.executable + hardcoded inline code, no shell, no untrusted input
    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"


@pytest.mark.unit
def test_full_worker_package_does_not_load_pydantic():
    """``import juniper_cascor_worker`` (top-level) does not pull Pydantic."""
    code = "import sys, juniper_cascor_worker;" "import juniper_cascor_worker.cli;" "import juniper_cascor_worker.config;" "import juniper_cascor_worker.exceptions;" "import juniper_cascor_worker.http_health;" "import juniper_cascor_worker.task_executor;" "import juniper_cascor_worker.worker;" "import juniper_cascor_worker.ws_connection;" "assert 'pydantic' not in sys.modules, sorted(m for m in sys.modules if 'pydantic' in m)"
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)  # nosec B603 — sys.executable + hardcoded inline code, no shell, no untrusted input
    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"


@pytest.mark.unit
def test_worker_message_type_constants_alias_shared_strenum():
    """The ``MSG_TYPE_*`` literals must equal the canonical ``WorkerMessageType`` values."""
    from juniper_cascor_protocol.worker import WorkerMessageType

    from juniper_cascor_worker.constants import MSG_TYPE_CONNECTION_ESTABLISHED, MSG_TYPE_ERROR, MSG_TYPE_HEARTBEAT, MSG_TYPE_REGISTER, MSG_TYPE_REGISTRATION_ACK, MSG_TYPE_RESULT_ACK, MSG_TYPE_TASK_ASSIGN, MSG_TYPE_TASK_RESULT, MSG_TYPE_TOKEN_REFRESH

    assert MSG_TYPE_REGISTER == WorkerMessageType.REGISTER.value == "register"
    assert MSG_TYPE_HEARTBEAT == WorkerMessageType.HEARTBEAT.value == "heartbeat"
    assert MSG_TYPE_TASK_ASSIGN == WorkerMessageType.TASK_ASSIGN.value == "task_assign"
    assert MSG_TYPE_TASK_RESULT == WorkerMessageType.TASK_RESULT.value == "task_result"
    assert MSG_TYPE_REGISTRATION_ACK == WorkerMessageType.REGISTRATION_ACK.value == "registration_ack"
    assert MSG_TYPE_RESULT_ACK == WorkerMessageType.RESULT_ACK.value == "result_ack"
    assert MSG_TYPE_TOKEN_REFRESH == WorkerMessageType.TOKEN_REFRESH.value == "token_refresh"
    assert MSG_TYPE_ERROR == WorkerMessageType.ERROR.value == "error"
    assert MSG_TYPE_CONNECTION_ESTABLISHED == WorkerMessageType.CONNECTION_ESTABLISHED.value == "connection_established"


@pytest.mark.unit
def test_encode_binary_frame_uses_shared_codec():
    """``_encode_binary_frame`` must produce bytes byte-identical to the shared encoder."""
    import numpy as np
    from juniper_cascor_protocol.worker import BinaryFrame as SharedBinaryFrame

    from juniper_cascor_worker.worker import _encode_binary_frame

    arr = np.arange(24, dtype="float32").reshape(4, 6)
    assert _encode_binary_frame(arr) == SharedBinaryFrame.encode(arr)


@pytest.mark.unit
def test_local_decoder_still_round_trips_with_shared_encoder():
    """The local SEC-18-hardened decoder accepts bytes from the shared encoder."""
    import numpy as np
    from juniper_cascor_protocol.worker import BinaryFrame as SharedBinaryFrame

    from juniper_cascor_worker.worker import _decode_binary_frame

    arr = np.arange(24, dtype="float64").reshape(2, 3, 4)
    encoded = SharedBinaryFrame.encode(arr)
    decoded = _decode_binary_frame(encoded)
    np.testing.assert_array_equal(decoded, arr)
    assert decoded.shape == arr.shape
    assert decoded.dtype == arr.dtype
