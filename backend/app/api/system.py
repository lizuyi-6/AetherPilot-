"""System status + telemetry endpoints. All data is probed live — nothing cached
beyond the telemetry ring buffer, nothing simulated."""

from __future__ import annotations

import shutil
import subprocess

from fastapi import APIRouter

from ..telemetry.collector import system_collector
from ..telemetry.gpu import get_gpu_monitor
from ..telemetry.system import docker_status, environment_record, host_info, sample_system

router = APIRouter(prefix="/api/system", tags=["system"])


def _cuda_probe() -> dict:
    nvcc = shutil.which("nvcc")
    result = {"nvcc": None, "torch_cuda": None, "torch_cuda_available": None}
    if nvcc:
        try:
            proc = subprocess.run(["nvcc", "--version"], capture_output=True, text=True, timeout=10)
            for line in proc.stdout.splitlines():
                if "release" in line:
                    result["nvcc"] = line.split("release")[-1].strip().rstrip(",")
        except (OSError, subprocess.TimeoutExpired):
            pass
    env = environment_record()
    result["torch_cuda"] = env.get("torch_cuda")
    result["torch_cuda_available"] = env.get("torch_cuda_available")
    return result


@router.get("/status")
def system_status() -> dict:
    gpu = get_gpu_monitor().status()
    host = host_info()
    disk = sample_system()
    docker = docker_status()
    return {
        "host": host.__dict__,
        "gpu": {
            "available": gpu.available,
            "source": gpu.source,
            "driver": gpu.driver_version,
            "cuda": gpu.cuda_version,
            "detail": gpu.detail,
            "gpus": [
                {
                    "index": g.index,
                    "name": g.name,
                    "mem_total_mb": round(g.memory_total_mb, 1),
                    "mem_used_mb": round(g.memory_used_mb, 1),
                    "mem_free_mb": round(g.memory_free_mb, 1),
                    "util_pct": g.utilization_pct,
                    "temp_c": g.temperature_c,
                    "power_w": g.power_w,
                }
                for g in gpu.gpus
            ],
        },
        "cuda_toolkit": _cuda_probe(),
        "docker": docker,
        "disk": {"total_gb": round(disk.disk_total_gb, 1), "free_gb": round(disk.disk_free_gb, 1)},
        "ram": {"total_gb": round(disk.ram_total_gb, 1), "used_gb": round(disk.ram_used_gb, 1)},
        "cpu_pct": disk.cpu_pct,
    }


@router.get("/telemetry")
def system_telemetry() -> dict:
    return {"latest": system_collector.latest, "history": system_collector.history()}
