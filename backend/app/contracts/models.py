"""Experiment Contract: the binding agreement between user and agent.

Every agent action is checked against the contract. The contract is fixed at
creation time (CONTRACTING state) and travels with the experiment forever —
it is included verbatim in the reproducibility package.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class GoalType(StrEnum):
    FINETUNE = "finetune"
    EVAL = "eval"
    CUSTOM = "custom"


class Permission(StrEnum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class ExperimentMeta(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class Goal(BaseModel):
    type: GoalType = GoalType.FINETUNE
    model: str = "demo-small"
    dataset: str | None = None
    description: str = ""


class Constraints(BaseModel):
    max_vram_gb: float = Field(default=100.0, gt=0)
    max_duration_hours: float = Field(default=6.0, gt=0)
    max_disk_gb: float = Field(default=500.0, gt=0)


class Permissions(BaseModel):
    restart_training: bool = True
    modify_training_config: bool = True
    install_python_packages: bool = False
    install_system_packages: Permission = Permission.ASK
    modify_docker_daemon: Permission = Permission.ASK
    kill_external_processes: bool = False
    delete_user_files: bool = False


class MetricTarget(BaseModel):
    target: float
    operator: Literal[">=", "<=", ">", "<", "=="] = ">="

    def satisfied_by(self, value: float) -> bool:
        return {
            ">=": value >= self.target,
            "<=": value <= self.target,
            ">": value > self.target,
            "<": value < self.target,
            "==": value == self.target,
        }[self.operator]


class ReproducibilitySpec(BaseModel):
    record_git_commit: bool = True
    record_environment: bool = True
    dataset_hash: bool = True
    model_hash: bool = True
    random_seed: bool = True


class RecoverySpec(BaseModel):
    allow_checkpoint_rollback: bool = True
    max_auto_recovery_attempts: int = Field(default=3, ge=0, le=10)


class ExperimentContract(BaseModel):
    experiment: ExperimentMeta
    goal: Goal = Goal()
    constraints: Constraints = Constraints()
    permissions: Permissions = Permissions()
    metrics: dict[str, MetricTarget] = Field(default_factory=dict)
    reproducibility: ReproducibilitySpec = ReproducibilitySpec()
    recovery: RecoverySpec = RecoverySpec()

    @model_validator(mode="after")
    def _check_metric_names(self) -> "ExperimentContract":
        for name in self.metrics:
            if not name.replace("_", "").isalnum():
                raise ValueError(f"invalid metric name: {name!r}")
        return self
