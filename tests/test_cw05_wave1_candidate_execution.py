"""Regression tests for the CW-05 Wave 1 worker fixes (juniper-cascor-worker#97).

These drive the REAL ``execute_training_task`` with a cascor-style task to lock in the three
worker-side fixes that let the dual-path remote tier actually execute candidates:

  - ``candidate_unit`` imports from the ``juniper-cascor-core`` package (no ``--cascor-path``
    / cascor source mount);
  - activation resolves the TitleCase names cascor dispatches (e.g. ``'Tanh'``) via the core
    ``ACTIVATION_MAP``, instead of silently falling back to a different activation (gap #4);
  - int-valued params that cascor ``float()``-coerces over the wire
    (``random_max_value`` / ``sequence_max_value``) do not crash candidate training with
    ``'float' object cannot be interpreted as an integer`` (gap #5).

Skipped when ``juniper-cascor-core`` (the top-level ``candidate_unit`` package) is not
importable, so worker CI stays green until the package is published; run locally with
``juniper-cascor-core`` on the path to validate end-to-end.
"""

import numpy as np
import pytest

pytest.importorskip("torch")
pytest.importorskip("candidate_unit.candidate_unit", reason="juniper-cascor-core not installed")

from juniper_cascor_worker.task_executor import _get_activation_function, execute_training_task  # noqa: E402


def _cascor_style_task(activation_name: str = "Tanh"):
    rng = np.random.default_rng(42)
    candidate_data = {
        "input_size": 2,
        "activation_name": activation_name,  # gap #4: cascor sends TitleCase
        "candidate_index": 0,
        "candidate_uuid": "cw05-wave1-test",
        "candidate_seed": 7,
        "random_value_scale": 1.0,
        # gap #5: cascor's _dispatch_to_remote_workers float()-coerces these int-valued params.
        "random_max_value": 5.0,
        "sequence_max_value": 3.0,
    }
    training_params = {"epochs": 5, "learning_rate": 0.01, "display_frequency": 100}
    tensors = {
        "candidate_input": rng.standard_normal((16, 2)).astype(np.float32),
        "y": rng.standard_normal((16, 1)).astype(np.float32),
        "residual_error": rng.standard_normal((16, 1)).astype(np.float32),
    }
    return candidate_data, training_params, tensors


def test_execute_training_task_titlecase_activation_and_float_params():
    """The full worker execution path succeeds on a cascor-style task (all three fixes)."""
    candidate_data, training_params, tensors = _cascor_style_task("Tanh")

    result, out_tensors = execute_training_task(candidate_data, training_params, tensors)

    # gap #5: no "'float' object ..." crash -> not routed into the failure branch.
    assert result["error_message"] is None, result["error_message"]
    assert result["success"] is True
    # gap #4: trained with the dispatched activation, not a silent fallback.
    assert result["activation_name"] == "Tanh"
    assert result["epochs_completed"] >= 1
    assert isinstance(result["correlation"], float)
    assert isinstance(out_tensors, dict)


def test_get_activation_function_resolves_titlecase_and_lowercase():
    """gap #4: both casings resolve to a callable from the core ACTIVATION_MAP."""
    for name in ("Tanh", "tanh", "Sigmoid", "sigmoid", "ReLU", "relu"):
        assert callable(_get_activation_function(name)), name
