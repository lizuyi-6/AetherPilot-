"""Command execution policy and filesystem jail.

Two deterministic gates stand between any agent intention and the OS:

1. CommandPolicy — classifies every command (argv list; shell=True is never used)
   as READ_ONLY / SAFE_WRITE / PRIVILEGED / FORBIDDEN.
2. PathGuard — resolves paths and enforces that writes stay inside the experiment
   workspace; reads must be inside explicitly granted roots.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from enum import StrEnum
from pathlib import Path, PurePath


class CommandClass(StrEnum):
    READ_ONLY = "READ_ONLY"
    SAFE_WRITE = "SAFE_WRITE"
    PRIVILEGED = "PRIVILEGED"
    FORBIDDEN = "FORBIDDEN"


class PolicyViolation(PermissionError):
    pass


# Executables that only observe the system.
_READ_ONLY_BINARIES = {
    "nvidia-smi", "nvcc", "python", "python3", "pip", "pip3",
    "docker", "git", "uname", "lsb_release", "df", "free", "lscpu",
    "cat", "ls", "dir", "type", "where", "which", "echo", "hostname",
}

_PRIVILEGED_BINARIES = {"systemctl", "service", "apt", "apt-get", "yum", "dnf", "snap", "sudo"}

# Substrings that make any command forbidden regardless of binary.
_FORBIDDEN_PATTERNS = [
    re.compile(r"\brm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)?/(\s|$)"),       # rm -rf /
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\b.*\bof=/dev/"),
    re.compile(r":\(\)\s*\{"),                                          # fork bomb
    re.compile(r"\bshutdown\b|\breboot\b|\bhalt\b"),
    re.compile(r"\b(del|erase)\b.*[/\\]\*", re.IGNORECASE),            # del C:\*
]


def _binary_name(argv0: str) -> str:
    name = PurePath(argv0).name.lower()
    return name[:-4] if name.endswith(".exe") else name


class CommandPolicy:
    """Deterministic classification of command argv lists."""

    def classify(self, argv: list[str]) -> CommandClass:
        if not argv:
            raise PolicyViolation("empty command")
        joined = " ".join(argv)
        for pattern in _FORBIDDEN_PATTERNS:
            if pattern.search(joined):
                return CommandClass.FORBIDDEN
        binary = _binary_name(argv[0])
        if binary in _PRIVILEGED_BINARIES:
            return CommandClass.PRIVILEGED
        if binary in _READ_ONLY_BINARIES:
            return CommandClass.READ_ONLY
        # Unknown binaries are treated as SAFE_WRITE only inside the workspace;
        # the launcher additionally constrains cwd/env.
        return CommandClass.SAFE_WRITE

    def check(self, argv: list[str], allow: set[CommandClass]) -> CommandClass:
        cls = self.classify(argv)
        if cls not in allow:
            raise PolicyViolation(f"command class {cls} not permitted (allowed: {sorted(allow)})")
        return cls


class PathGuard:
    """Confines writes to allowed roots; validates granted read paths."""

    def __init__(self, write_roots: list[Path], read_roots: list[Path] | None = None) -> None:
        self._write_roots = [r.resolve() for r in write_roots]
        self._read_roots = [r.resolve() for r in (read_roots or [])]

    @staticmethod
    def _within(path: Path, roots: list[Path]) -> bool:
        resolved = path.resolve()
        return any(resolved == root or root in resolved.parents for root in roots)

    def check_write(self, path: Path) -> Path:
        if not self._within(path, self._write_roots):
            raise PolicyViolation(f"write outside workspace denied: {path}")
        return path.resolve()

    def check_read(self, path: Path) -> Path:
        if self._within(path, self._write_roots) or self._within(path, self._read_roots):
            return path.resolve()
        raise PolicyViolation(f"read outside granted roots denied: {path}")


def run_command(argv: list[str], timeout_s: float = 30.0) -> subprocess.CompletedProcess[str]:
    """Policy-checked, shell-free, read-only command execution helper."""
    policy = CommandPolicy()
    policy.check(argv, {CommandClass.READ_ONLY})
    if shutil.which(argv[0]) is None:
        raise FileNotFoundError(argv[0])
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s, check=False)
