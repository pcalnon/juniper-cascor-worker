"""CI verification that worker protocol constants match the cascor server (XREPO-04).

The worker's ``MSG_TYPE_*`` constants in :mod:`juniper_cascor_worker.constants`
MUST be bit-identical to the values declared by the cascor server's
``MessageType`` enum in ``api/workers/protocol.py``. Drift between the two
sides is silent — neither end raises until the wire-level dispatch fails on
an unrecognized type — so this test acts as a static guard that runs on
every PR.

Per the Phase 4D / XREPO-04 plan, the test prefers Approach A (pytest-time
verification) over a separately-maintained shared package; the latter is
documented in the roadmap as the canonical Approach B once the constant set
grows beyond the half-dozen messages currently exchanged.

The test is skipped when the cascor source tree is not importable (the
worker's CI environment intentionally does not depend on the cascor
package). Locally, exporting ``CASCOR_SRC_PATH`` to the cascor ``src``
directory enables the check.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

from juniper_cascor_worker.constants import MSG_TYPE_ERROR, MSG_TYPE_HEARTBEAT, MSG_TYPE_REGISTER, MSG_TYPE_TASK_ASSIGN, MSG_TYPE_TASK_RESULT, MSG_TYPE_TOKEN_REFRESH


def _import_cascor_message_type():
    """Import the cascor server's MessageType enum, or return None if unavailable.

    Tries, in order:
    1. A direct import (cascor installed or already on sys.path).
    2. ``CASCOR_SRC_PATH`` environment override.
    3. The conventional Juniper ecosystem layout
       ``../../juniper-cascor/src`` relative to this worktree.
    """
    try:  # 1. Already importable
        from api.workers.protocol import MessageType  # type: ignore[import-not-found]

        return MessageType
    except ImportError:
        pass

    candidate_paths: list[Path] = []
    env_path = os.environ.get("CASCOR_SRC_PATH")
    if env_path:
        candidate_paths.append(Path(env_path))

    here = Path(__file__).resolve()
    # The automation runner checks this repository out directly at
    # /workspace, which is shallower than the local Juniper worktree layout.
    # Only add conventional sibling paths that exist in the current path depth.
    if len(here.parents) > 3:
        candidate_paths.append(here.parents[3] / "juniper-cascor" / "src")  # worktrees/<wt>/tests
    if len(here.parents) > 2:
        candidate_paths.append(here.parents[2] / "juniper-cascor" / "src")  # repo root layout

    for path in candidate_paths:
        protocol_file = path / "api" / "workers" / "protocol.py"
        if not protocol_file.exists():
            continue
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
        if importlib.util.find_spec("api.workers.protocol") is None:
            continue
        protocol_mod = importlib.import_module("api.workers.protocol")
        return protocol_mod.MessageType

    return None


@pytest.fixture(scope="module")
def cascor_message_type():
    enum_cls = _import_cascor_message_type()
    if enum_cls is None:
        pytest.skip("cascor server source not importable — set CASCOR_SRC_PATH or run " "from a checkout that contains a sibling juniper-cascor/src tree")
    return enum_cls


# Worker-side mapping of canonical message type names → worker constant value.
# Names are the lowercase wire-protocol values; we match them against the
# server enum members case-insensitively (server uses UPPER_CASE enum names,
# wire values are lowercase).
_WORKER_MESSAGE_TYPES: dict[str, str] = {
    "register": MSG_TYPE_REGISTER,
    "heartbeat": MSG_TYPE_HEARTBEAT,
    "task_assign": MSG_TYPE_TASK_ASSIGN,
    "task_result": MSG_TYPE_TASK_RESULT,
    "token_refresh": MSG_TYPE_TOKEN_REFRESH,
    "error": MSG_TYPE_ERROR,
}


@pytest.mark.parametrize("wire_name,worker_value", sorted(_WORKER_MESSAGE_TYPES.items()))
def test_worker_message_type_matches_server(cascor_message_type, wire_name: str, worker_value: str) -> None:
    """Each worker MSG_TYPE_* constant must equal the server's enum value bit-for-bit (XREPO-04)."""
    server_member = getattr(cascor_message_type, wire_name.upper(), None)
    assert server_member is not None, f"server MessageType has no {wire_name.upper()} member; worker uses {worker_value!r}"
    assert worker_value == server_member.value, f"worker {wire_name!r}={worker_value!r} drifted from server {server_member.value!r}"


def test_worker_does_not_emit_message_types_unknown_to_server(cascor_message_type) -> None:
    """Worker emits only message types the server knows about (no client-only sends)."""
    server_values = {m.value for m in cascor_message_type}
    # MSG_TYPE_TASK_RESULT, MSG_TYPE_HEARTBEAT, MSG_TYPE_REGISTER, MSG_TYPE_TOKEN_REFRESH
    # are the message types the worker SENDS to the server. Connection-established,
    # registration_ack, result_ack, task_assign, error are received from the server.
    worker_outbound = {
        MSG_TYPE_REGISTER,
        MSG_TYPE_HEARTBEAT,
        MSG_TYPE_TASK_RESULT,
        MSG_TYPE_TOKEN_REFRESH,
    }
    unknown = worker_outbound - server_values
    assert not unknown, f"worker would send message types unknown to the server: {unknown}"
