"""Contract validation beyond pydantic shape checks."""

from __future__ import annotations

from .models import ExperimentContract


class ContractError(ValueError):
    pass


def validate_contract(contract: ExperimentContract) -> list[str]:
    """Return a list of warnings (not errors) for a contract; raise on hard violations."""
    warnings: list[str] = []

    if contract.constraints.max_vram_gb > 512:
        warnings.append("max_vram_gb unusually high for a single-node experiment")
    if not contract.recovery.allow_checkpoint_rollback and contract.recovery.max_auto_recovery_attempts > 0:
        raise ContractError(
            "recovery.max_auto_recovery_attempts > 0 requires allow_checkpoint_rollback=true"
        )
    if contract.permissions.delete_user_files:
        raise ContractError("permissions.delete_user_files must be false — not supported")
    if contract.permissions.kill_external_processes:
        raise ContractError("permissions.kill_external_processes must be false — not supported")
    if contract.goal.type == "finetune" and not contract.goal.dataset:
        warnings.append("finetune goal without dataset — assuming demo dataset")
    return warnings
