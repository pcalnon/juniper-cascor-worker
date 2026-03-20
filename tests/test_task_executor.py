"""Tests for task_executor.execute_training_task."""

import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch

from juniper_cascor_worker.task_executor import execute_training_task


def _make_candidate_data():
    """Return minimal candidate_data for testing."""
    return {
        "input_size": 3,
        "activation_name": "sigmoid",
        "random_value_scale": 1.0,
        "candidate_uuid": "test-uuid-001",
        "candidate_seed": 42,
        "candidate_index": 0,
        "random_max_value": 1.0,
        "sequence_max_value": 1.0,
    }


def _make_training_params():
    """Return minimal training_params for testing."""
    return {
        "epochs": 100,
        "learning_rate": 0.01,
        "display_frequency": 50,
    }


def _make_tensors():
    """Return minimal tensors dict for testing."""
    return {
        "candidate_input": np.random.randn(10, 3).astype(np.float32),
        "residual_error": np.random.randn(10, 1).astype(np.float32),
    }


def _make_mock_training_result(correlation=0.85, success=True, epochs_completed=100):
    """Create a mock training result with all expected fields."""
    result = MagicMock()
    result.correlation = correlation
    result.all_correlations = [0.1, 0.5, correlation]
    result.numerator = 0.85
    result.denominator = 1.0
    result.best_corr_idx = 2
    result.norm_output = torch.randn(10, 1)
    result.norm_error = torch.randn(10, 1)
    result.success = success
    result.epochs_completed = epochs_completed
    return result


def _make_mock_candidate_unit(training_result=None):
    """Create a mock CandidateUnit class and instance."""
    if training_result is None:
        training_result = _make_mock_training_result()

    mock_instance = MagicMock()
    mock_instance.train_detailed.return_value = training_result
    mock_instance.weights = torch.nn.Parameter(torch.randn(3))
    mock_instance.bias = torch.nn.Parameter(torch.tensor([0.5]))
    mock_instance.clear_display_progress = MagicMock()
    mock_instance.clear_display_status = MagicMock()

    mock_cls = MagicMock(return_value=mock_instance)
    return mock_cls, mock_instance


@pytest.mark.unit
class TestSuccessfulTraining:
    def test_successful_training(self):
        """Mock CandidateUnit.train_detailed to return a result with correlation=0.85."""
        mock_cls, mock_instance = _make_mock_candidate_unit()
        mock_module = MagicMock()
        mock_module.CandidateUnit = mock_cls

        candidate_data = _make_candidate_data()
        training_params = _make_training_params()
        tensors = _make_tensors()

        with patch.dict(sys.modules, {"candidate_unit": MagicMock(), "candidate_unit.candidate_unit": mock_module}):
            result_dict, tensor_dict = execute_training_task(candidate_data, training_params, tensors)

        # Verify result_dict fields
        assert result_dict["candidate_id"] == 0
        assert result_dict["candidate_uuid"] == "test-uuid-001"
        assert result_dict["correlation"] == pytest.approx(0.85)
        assert result_dict["success"] is True
        assert result_dict["epochs_completed"] == 100
        assert result_dict["activation_name"] == "sigmoid"
        assert result_dict["error_message"] is None
        assert isinstance(result_dict["all_correlations"], list)
        assert result_dict["numerator"] == pytest.approx(0.85)
        assert result_dict["denominator"] == pytest.approx(1.0)
        assert result_dict["best_corr_idx"] == 2

        # Verify tensor_dict has weights and bias
        assert "weights" in tensor_dict
        assert "bias" in tensor_dict

        # Verify CandidateUnit was instantiated and trained
        mock_cls.assert_called_once()
        mock_instance.train_detailed.assert_called_once()
        mock_instance.clear_display_progress.assert_called_once()
        mock_instance.clear_display_status.assert_called_once()


@pytest.mark.unit
class TestTrainingFailure:
    def test_training_failure_returns_error(self):
        """Mock train_detailed to raise. Verify success=False, error_message set."""
        mock_instance = MagicMock()
        mock_instance.train_detailed.side_effect = RuntimeError("CUDA out of memory")
        mock_cls = MagicMock(return_value=mock_instance)
        mock_module = MagicMock()
        mock_module.CandidateUnit = mock_cls

        candidate_data = _make_candidate_data()
        training_params = _make_training_params()
        tensors = _make_tensors()

        with patch.dict(sys.modules, {"candidate_unit": MagicMock(), "candidate_unit.candidate_unit": mock_module}):
            result_dict, tensor_dict = execute_training_task(candidate_data, training_params, tensors)

        assert result_dict["success"] is False
        assert "CUDA out of memory" in result_dict["error_message"]
        assert result_dict["correlation"] == 0.0
        assert result_dict["epochs_completed"] == 0
        assert tensor_dict == {}


@pytest.mark.unit
class TestImportError:
    def test_import_error_raises(self):
        """Mock the import to fail. Verify ImportError raised."""
        candidate_data = _make_candidate_data()
        training_params = _make_training_params()
        tensors = _make_tensors()

        with patch.dict(sys.modules, {"candidate_unit": None, "candidate_unit.candidate_unit": None}):
            with pytest.raises(ImportError, match="CasCor codebase not found"):
                execute_training_task(candidate_data, training_params, tensors)


@pytest.mark.unit
class TestTensorConversion:
    def test_tensor_conversion_numpy_to_torch(self):
        """Verify input tensors are passed as torch.Tensor to train_detailed."""
        mock_cls, mock_instance = _make_mock_candidate_unit()
        mock_module = MagicMock()
        mock_module.CandidateUnit = mock_cls

        candidate_data = _make_candidate_data()
        training_params = _make_training_params()
        tensors = _make_tensors()

        with patch.dict(sys.modules, {"candidate_unit": MagicMock(), "candidate_unit.candidate_unit": mock_module}):
            execute_training_task(candidate_data, training_params, tensors)

        # Verify that train_detailed received torch.Tensor arguments
        call_kwargs = mock_instance.train_detailed.call_args
        assert isinstance(call_kwargs.kwargs["x"], torch.Tensor)
        assert isinstance(call_kwargs.kwargs["residual_error"], torch.Tensor)
        assert call_kwargs.kwargs["x"].dtype == torch.float32
        assert call_kwargs.kwargs["residual_error"].dtype == torch.float32

    def test_result_tensors_are_numpy_float32(self):
        """Verify output tensors are numpy float32."""
        mock_cls, mock_instance = _make_mock_candidate_unit()
        mock_module = MagicMock()
        mock_module.CandidateUnit = mock_cls

        candidate_data = _make_candidate_data()
        training_params = _make_training_params()
        tensors = _make_tensors()

        with patch.dict(sys.modules, {"candidate_unit": MagicMock(), "candidate_unit.candidate_unit": mock_module}):
            result_dict, tensor_dict = execute_training_task(candidate_data, training_params, tensors)

        for name, arr in tensor_dict.items():
            assert isinstance(arr, np.ndarray), f"Tensor '{name}' is not a numpy array"
            assert arr.dtype == np.float32, f"Tensor '{name}' dtype is {arr.dtype}, expected float32"
