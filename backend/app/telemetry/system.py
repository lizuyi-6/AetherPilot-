"""System (CPU/RAM/Disk/host) telemetry via psutil — real data only."""

from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import psutil


@dataclass
class SystemSample:
    cpu_pct: float
    ram_total_gb: float
    ram_used_gb: float
    disk_total_gb: float
    disk_free_gb: float
    disk_used_gb: float


@dataclass
class HostInfo:
    os: str
    kernel: str
    arch: str
    python: str
    cpu_count: int
    ram_total_gb: float


def sample_system(path: Path | None = None) -> SystemSample:
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage(str(path or Path.cwd()))
    return SystemSample(
        cpu_pct=psutil.cpu_percent(interval=None),
        ram_total_gb=vm.total / 1024**3,
        ram_used_gb=vm.used / 1024**3,
        disk_total_gb=disk.total / 1024**3,
        disk_free_gb=disk.free / 1024**3,
        disk_used_gb=disk.used / 1024**3,
    )


def host_info() -> HostInfo:
    return HostInfo(
        os=platform.system(),
        kernel=platform.release(),
        arch=platform.machine(),
        python=platform.python_version(),
        cpu_count=psutil.cpu_count(logical=True) or 0,
        ram_total_gb=psutil.virtual_memory().total / 1024**3,
    )


def docker_status() -> dict[str, str | bool]:
    """Honest Docker probe — never raises, never fakes readiness."""
    if shutil.which("docker") is None:
        return {"available": False, "detail": "docker CLI not found", "nvidia_runtime": False}
    try:
        proc = subprocess.run(
            ["docker", "info", "--format", "{{json .Runtimes}}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "detail": str(exc), "nvidia_runtime": False}
    if proc.returncode != 0:
        detail = proc.stderr.strip().splitlines()[0] if proc.stderr.strip() else "daemon unreachable"
        return {"available": False, "detail": detail, "nvidia_runtime": False}
    has_nvidia = "nvidia" in proc.stdout
    return {"available": True, "detail": "daemon reachable", "nvidia_runtime": has_nvidia}


def environment_record() -> dict[str, str | None]:
    """Versions recorded into the reproducibility package."""
    record: dict[str, str | None] = {
        "python": platform.python_version(),
        "os": f"{platform.system()} {platform.release()}",
        "arch": platform.machine(),
    }
    try:
        import torch  # type: ignore

        record["torch"] = torch.__version__
        record["torch_cuda"] = torch.version.cuda
        record["torch_cuda_available"] = str(torch.cuda.is_available())
    except ImportError:
        record["torch"] = None
    try:
        import transformers  # type: ignore

        record["transformers"] = transformers.__version__
    except ImportError:
        record["transformers"] = None
    return record
