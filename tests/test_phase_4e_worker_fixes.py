"""Unit tests for Phase 4E worker fixes (CW-04, CW-07, CW-08).

These tests focus on the new helper functions and behavioural guarantees
introduced in Phase 4E without standing up a full WS server. The end-to-end
integration coverage lives in :mod:`tests.test_integration_ws_server`.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from juniper_cascor_worker import worker as worker_mod
from juniper_cascor_worker.constants import DEFAULT_CORRELATION, MSG_TYPE_TASK_RESULT, NO_BEST_CORR_IDX, NO_EPOCHS_COMPLETED


# ─── _validate_tensor_manifest (CW-07) ──────────────────────────────────────


class TestValidateTensorManifest:
    def test_accepts_well_formed_manifest(self) -> None:
        manifest = {
            "candidate_input": {"shape": [4, 2], "dtype": "float32"},
            "residual_error": {"shape": [4, 1], "dtype": "float32"},
        }
        assert worker_mod._validate_tensor_manifest(manifest) is None

    def test_rejects_non_dict_manifest(self) -> None:
        err = worker_mod._validate_tensor_manifest(["candidate_input"])
        assert err is not None and "not a dict" in err

    def test_rejects_empty_manifest(self) -> None:
        err = worker_mod._validate_tensor_manifest({})
        assert err is not None and "empty" in err

    def test_rejects_manifest_missing_required_key(self) -> None:
        manifest = {"candidate_input": {"shape": [1, 1], "dtype": "float32"}}
        err = worker_mod._validate_tensor_manifest(manifest)
        assert err is not None and "residual_error" in err


# ─── _build_task_failure_message (CW-04 + CW-07) ───────────────────────────


class TestBuildTaskFailureMessage:
    def test_payload_shape_matches_task_result_envelope(self) -> None:
        msg = worker_mod._build_task_failure_message(
            task_id="t-1",
            candidate_data={"candidate_index": 4, "candidate_uuid": "uuid-4", "activation_name": "relu"},
            error_message="boom",
        )
        assert msg["type"] == MSG_TYPE_TASK_RESULT
        assert msg["task_id"] == "t-1"
        assert msg["candidate_id"] == 4
        assert msg["candidate_uuid"] == "uuid-4"  # CW-04
        assert msg["activation_name"] == "relu"
        assert msg["success"] is False
        assert msg["correlation"] == DEFAULT_CORRELATION
        assert msg["epochs_completed"] == NO_EPOCHS_COMPLETED
        assert msg["best_corr_idx"] == NO_BEST_CORR_IDX
        assert msg["error_message"] == "boom"
        assert msg["tensor_manifest"] == {}

    def test_missing_candidate_data_falls_back_to_safe_defaults(self) -> None:
        msg = worker_mod._build_task_failure_message(task_id="t-2", candidate_data={}, error_message="x")
        assert msg["candidate_id"] == 0
        assert msg["candidate_uuid"] == ""
        assert msg["activation_name"] == ""


# ─── _handle_task_assign error paths ────────────────────────────────────────


def _make_agent_with_fake_connection() -> tuple[worker_mod.CascorWorkerAgent, MagicMock]:
    from juniper_cascor_worker.config import WorkerConfig

    cfg = WorkerConfig(server_url="ws://localhost:0", task_timeout=0.1)
    agent = worker_mod.CascorWorkerAgent(cfg)
    fake_conn = MagicMock()
    fake_conn.send_json = AsyncMock()
    fake_conn.receive_bytes = AsyncMock()
    agent._connection = fake_conn  # type: ignore[assignment]
    return agent, fake_conn


@pytest.mark.asyncio
async def test_handle_task_assign_rejects_invalid_manifest_cw07() -> None:
    agent, fake_conn = _make_agent_with_fake_connection()
    bad_msg: dict[str, Any] = {
        "task_id": "t-bad",
        "candidate_index": 1,
        "candidate_data": {"candidate_uuid": "uuid-bad"},
        "training_params": {},
        "tensor_manifest": {},  # empty -> rejected by _validate_tensor_manifest
    }

    await agent._handle_task_assign(bad_msg)

    fake_conn.send_json.assert_awaited_once()
    sent = fake_conn.send_json.await_args[0][0]
    assert sent["type"] == MSG_TYPE_TASK_RESULT
    assert sent["candidate_uuid"] == "uuid-bad"
    assert sent["success"] is False
    assert "manifest" in sent["error_message"].lower()
    fake_conn.receive_bytes.assert_not_called()


@pytest.mark.asyncio
async def test_handle_task_assign_timeout_carries_uuid_cw04(monkeypatch: pytest.MonkeyPatch) -> None:
    agent, fake_conn = _make_agent_with_fake_connection()

    candidate_input = np.zeros((1, 1), dtype=np.float32)
    residual_error = np.zeros((1, 1), dtype=np.float32)

    async def fake_receive_bytes() -> bytes:
        # Encode a valid binary frame via the worker's own helper.
        if not fake_conn._frame_idx:  # type: ignore[attr-defined]
            fake_conn._frame_idx = 0  # type: ignore[attr-defined]
        idx = fake_conn._frame_idx  # type: ignore[attr-defined]
        fake_conn._frame_idx = idx + 1  # type: ignore[attr-defined]
        arrays = [candidate_input, residual_error]
        return worker_mod._encode_binary_frame(arrays[idx])

    fake_conn._frame_idx = 0  # type: ignore[attr-defined]
    fake_conn.receive_bytes = AsyncMock(side_effect=fake_receive_bytes)

    async def hang_forever(*_args: Any, **_kwargs: Any) -> Any:
        await asyncio.sleep(60)

    monkeypatch.setattr(worker_mod.asyncio, "to_thread", hang_forever)

    msg = {
        "task_id": "t-timeout",
        "candidate_index": 9,
        "candidate_data": {"candidate_uuid": "uuid-timeout-9", "activation_name": "tanh"},
        "training_params": {"epochs": 1},
        "tensor_manifest": {
            "candidate_input": {"shape": [1, 1], "dtype": "float32"},
            "residual_error": {"shape": [1, 1], "dtype": "float32"},
        },
    }

    await agent._handle_task_assign(msg)

    sent = fake_conn.send_json.await_args[0][0]
    assert sent["type"] == MSG_TYPE_TASK_RESULT
    assert sent["task_id"] == "t-timeout"
    assert sent["candidate_uuid"] == "uuid-timeout-9"  # CW-04
    assert sent["success"] is False
    assert "timed out" in sent["error_message"].lower()


# ─── CW-08: torch is not imported until task_executor functions run ────────


def test_task_executor_module_import_does_not_load_torch() -> None:
    """CW-08: importing task_executor must not pull torch into sys.modules.

    We run the check in a subprocess to keep ``sys.modules`` of the parent
    test process pristine — torch's C-extension registration is global and
    deleting it from a long-running process breaks every subsequent torch
    import in the same session.
    """
    import subprocess

    script = (
        "import sys; "
        "import juniper_cascor_worker.task_executor; "
        "torch_loaded = any(k == 'torch' or k.startswith('torch.') for k in sys.modules); "
        "print('LOADED' if torch_loaded else 'NOT_LOADED')"
    )
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "NOT_LOADED", "task_executor must not import torch at module load time (CW-08)"


def test_task_executor_get_activation_function_invokes_torch() -> None:
    """CW-08: ``_get_activation_function`` resolves real torch ops on first call.

    Documents the behavioural side of CW-08: torch IS expected to load when
    activation functions are needed, just not at module-import time. We use
    the real torch here (rather than monkey-patching ``sys.modules``) so we
    don't perturb the test session's torch cache.
    """
    pytest.importorskip("torch")
    from juniper_cascor_worker import task_executor

    fn, deriv = task_executor._get_activation_function("sigmoid")
    assert callable(fn) and callable(deriv)
