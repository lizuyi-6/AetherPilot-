"""Command policy + filesystem jail tests."""

from __future__ import annotations

import pytest

from app.core.security import CommandClass, CommandPolicy, PathGuard, PolicyViolation


@pytest.fixture()
def policy() -> CommandPolicy:
    return CommandPolicy()


@pytest.mark.parametrize("argv,expected", [
    (["nvidia-smi"], CommandClass.READ_ONLY),
    (["nvidia-smi", "--query-gpu=name", "--format=csv"], CommandClass.READ_ONLY),
    (["docker", "info"], CommandClass.READ_ONLY),
    (["python", "train.py"], CommandClass.READ_ONLY),
    (["systemctl", "restart", "docker"], CommandClass.PRIVILEGED),
    (["apt", "install", "vim"], CommandClass.PRIVILEGED),
    (["sudo", "ls"], CommandClass.PRIVILEGED),
    (["rm", "-rf", "/"], CommandClass.FORBIDDEN),
    (["rm", "-rf", "/ "], CommandClass.FORBIDDEN),
    (["mkfs", "/dev/sda"], CommandClass.FORBIDDEN),
    (["shutdown", "-h", "now"], CommandClass.FORBIDDEN),
    (["dd", "if=/dev/zero", "of=/dev/sda"], CommandClass.FORBIDDEN),
])
def test_classification(policy: CommandPolicy, argv: list[str], expected: CommandClass) -> None:
    assert policy.classify(argv) == expected


def test_empty_command_rejected(policy: CommandPolicy) -> None:
    with pytest.raises(PolicyViolation):
        policy.classify([])


def test_check_denies_unpermitted_class(policy: CommandPolicy) -> None:
    with pytest.raises(PolicyViolation):
        policy.check(["systemctl", "restart", "docker"], {CommandClass.READ_ONLY})


def test_path_guard_write_jail(tmp_path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    guard = PathGuard(write_roots=[workspace])
    assert guard.check_write(workspace / "configs" / "x.yaml").is_absolute()
    with pytest.raises(PolicyViolation):
        guard.check_write(tmp_path / "outside.txt")
    with pytest.raises(PolicyViolation):
        guard.check_write(workspace / ".." / "escape.txt")


def test_path_guard_granted_read(tmp_path) -> None:
    workspace = tmp_path / "ws"
    dataset = tmp_path / "datasets"
    workspace.mkdir()
    dataset.mkdir()
    guard = PathGuard(write_roots=[workspace], read_roots=[dataset])
    assert guard.check_read(dataset / "a.jsonl").is_absolute()
    with pytest.raises(PolicyViolation):
        guard.check_read(tmp_path / "secret.txt")
