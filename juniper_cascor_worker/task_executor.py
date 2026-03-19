"""Task execution engine for WebSocket-based candidate training.

Imports CandidateUnit from the cascor codebase (must be on sys.path)
and trains candidates using structured data received via the wire protocol.
Returns results as dicts + numpy tensors — no pickle involved.
"""

import logging
import random
from typing import Any

import numpy as np
import torch

logger = logging.getLogger(__name__)


def execute_training_task(
    candidate_data: dict[str, Any],
    training_params: dict[str, Any],
    tensors: dict[str, np.ndarray],
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Execute a single candidate training task.

    Creates a CandidateUnit from the structured task data, trains it,
    and returns the result as a JSON-serializable dict + numpy tensors.

    Args:
        candidate_data: Candidate configuration from the server.
            Keys: input_size, activation_name, random_value_scale,
            candidate_uuid, candidate_seed, random_max_value, sequence_max_value.
        training_params: Training hyperparameters.
            Keys: epochs, learning_rate, display_frequency.
        tensors: Training data tensors (numpy float32).
            Keys: candidate_input, y, residual_error.

    Returns:
        Tuple of (result_dict, tensor_dict) where result_dict contains
        JSON-serializable fields and tensor_dict contains numpy arrays.

    Raises:
        ImportError: If CandidateUnit is not importable (cascor not on sys.path).
    """
    try:
        from candidate_unit.candidate_unit import CandidateUnit
    except ImportError as e:
        raise ImportError("CasCor codebase not found. Ensure the JuniperCascor src directory " "is on sys.path via --cascor-path. " f"Original error: {e}") from e

    candidate_index = candidate_data.get("candidate_index", 0)
    candidate_uuid = candidate_data.get("candidate_uuid", "")

    try:
        # Resolve activation function
        activation_fn = _get_activation_function(candidate_data.get("activation_name", "sigmoid"))

        # Create CandidateUnit
        candidate = CandidateUnit(
            CandidateUnit__input_size=candidate_data["input_size"],
            CandidateUnit__activation_function=activation_fn,
            CandidateUnit__epochs=training_params.get("epochs", 200),
            CandidateUnit__learning_rate=training_params.get("learning_rate", 0.01),
            CandidateUnit__display_frequency=training_params.get("display_frequency", 100),
            CandidateUnit__random_seed=candidate_data.get("candidate_seed"),
            CandidateUnit__random_value_scale=candidate_data.get("random_value_scale", 1.0),
            CandidateUnit__random_max_value=candidate_data.get("random_max_value", 1.0),
            CandidateUnit__sequence_max_value=candidate_data.get("sequence_max_value", 1.0),
            CandidateUnit__uuid=candidate_uuid,
            CandidateUnit__candidate_index=candidate_index,
            CandidateUnit__log_level_name="INFO",
        )

        # Convert numpy tensors to torch
        candidate_input = torch.tensor(tensors["candidate_input"], dtype=torch.float32)
        residual_error = torch.tensor(tensors["residual_error"], dtype=torch.float32)

        # Train
        training_result = candidate.train_detailed(
            x=candidate_input,
            epochs=training_params.get("epochs", 200),
            residual_error=residual_error,
            learning_rate=training_params.get("learning_rate", 0.01),
            display_frequency=training_params.get("display_frequency", 100),
        )

        # Clear non-picklable display callbacks
        candidate.clear_display_progress()
        candidate.clear_display_status()

        # Extract result fields
        correlation = float(training_result.correlation) if training_result.correlation is not None else 0.0
        all_correlations = training_result.all_correlations if training_result.all_correlations is not None else []
        if isinstance(all_correlations, (torch.Tensor, np.ndarray)):
            all_correlations = [float(c) for c in all_correlations]

        result_dict = {
            "candidate_id": candidate_index,
            "candidate_uuid": str(candidate_uuid),
            "correlation": correlation,
            "success": training_result.success if hasattr(training_result, "success") else True,
            "epochs_completed": training_result.epochs_completed if hasattr(training_result, "epochs_completed") else training_params.get("epochs", 200),
            "activation_name": candidate_data.get("activation_name", "sigmoid"),
            "all_correlations": all_correlations,
            "numerator": float(training_result.numerator) if hasattr(training_result, "numerator") and training_result.numerator is not None else 0.0,
            "denominator": float(training_result.denominator) if hasattr(training_result, "denominator") and training_result.denominator is not None else 1.0,
            "best_corr_idx": int(training_result.best_corr_idx) if hasattr(training_result, "best_corr_idx") and training_result.best_corr_idx is not None else -1,
            "error_message": None,
        }

        # Extract tensors — convert torch to numpy
        tensor_dict: dict[str, np.ndarray] = {}

        weights = candidate.weights if hasattr(candidate, "weights") else None
        if weights is not None:
            tensor_dict["weights"] = weights.detach().cpu().numpy().astype(np.float32)

        bias = candidate.bias if hasattr(candidate, "bias") else None
        if bias is not None:
            tensor_dict["bias"] = bias.detach().cpu().numpy().astype(np.float32)

        norm_output = training_result.norm_output if hasattr(training_result, "norm_output") and training_result.norm_output is not None else None
        if norm_output is not None:
            if isinstance(norm_output, torch.Tensor):
                norm_output = norm_output.detach().cpu().numpy()
            tensor_dict["norm_output"] = np.asarray(norm_output, dtype=np.float32)

        norm_error = training_result.norm_error if hasattr(training_result, "norm_error") and training_result.norm_error is not None else None
        if norm_error is not None:
            if isinstance(norm_error, torch.Tensor):
                norm_error = norm_error.detach().cpu().numpy()
            tensor_dict["norm_error"] = np.asarray(norm_error, dtype=np.float32)

        logger.info(
            "Task completed: candidate %d (uuid=%s) correlation=%.4f",
            candidate_index,
            candidate_uuid,
            correlation,
        )
        return result_dict, tensor_dict

    except Exception as e:
        logger.error("Training failed for candidate %d: %s", candidate_index, e)
        result_dict = {
            "candidate_id": candidate_index,
            "candidate_uuid": str(candidate_uuid),
            "correlation": 0.0,
            "success": False,
            "epochs_completed": 0,
            "activation_name": candidate_data.get("activation_name", "sigmoid"),
            "all_correlations": [],
            "numerator": 0.0,
            "denominator": 1.0,
            "best_corr_idx": -1,
            "error_message": str(e),
        }
        return result_dict, {}


def _get_activation_function(name: str):
    """Resolve an activation function by name.

    Mirrors CascadeCorrelationNetwork._get_activation_function() to produce
    the same (function, derivative) tuple expected by CandidateUnit.
    """
    activations = {
        "sigmoid": (torch.sigmoid, lambda x: torch.sigmoid(x) * (1 - torch.sigmoid(x))),
        "tanh": (torch.tanh, lambda x: 1 - torch.tanh(x) ** 2),
        "relu": (torch.relu, lambda x: (x > 0).float()),
    }
    if name not in activations:
        logger.warning("Unknown activation '%s', falling back to sigmoid", name)
        name = "sigmoid"
    return activations[name]
