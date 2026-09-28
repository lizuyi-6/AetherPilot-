"""Experiment Contract validation tests."""

from __future__ import annotations

import pytest

from app.contracts.models import ExperimentContract, MetricTarget
from app.contracts.validator import ContractError, validate_contract


def test_contract_defaults_are_safe() -> None:
    c = ExperimentContract.model_validate({"experiment": {"name": "x"}})
    assert c.permissions.kill_external_processes is False
    assert c.permissions.delete_user_files is False
    assert c.recovery.max_auto_recovery_attempts == 3
    assert c.constraints.max_vram_gb == 100.0


def test_contract_rejects_dangerous_permissions() -> None:
    c = ExperimentContract.model_validate({
        "experiment": {"name": "x"},
        "permissions": {"delete_user_files": True},
    })
    with pytest.raises(ContractError):
        validate_contract(c)


def test_contract_rejects_recovery_without_rollback() -> None:
    c = ExperimentContract.model_validate({
        "experiment": {"name": "x"},
        "recovery": {"allow_checkpoint_rollback": False, "max_auto_recovery_attempts": 3},
    })
    with pytest.raises(ContractError):
        validate_contract(c)


@pytest.mark.parametrize("op,target,value,expected", [
    (">=", 0.92, 0.93, True),
    (">=", 0.92, 0.91, False),
    ("<=", 0.5, 0.4, True),
    (">", 0.9, 0.9, False),
    ("==", 1.0, 1.0, True),
])
def test_metric_target_operators(op: str, target: float, value: float, expected: bool) -> None:
    metric = MetricTarget(target=target, operator=op)  # type: ignore[arg-type]
    assert metric.satisfied_by(value) is expected


def test_metric_name_validation() -> None:
    with pytest.raises(ValueError):
        ExperimentContract.model_validate({
            "experiment": {"name": "x"},
            "metrics": {"bad name!": {"target": 1.0, "operator": ">="}},
        })
