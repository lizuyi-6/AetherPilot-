"""GPU detection and telemetry.

Sources, in priority order:
  1. pynvml (nvidia-ml-py) — fast, no subprocess.
  2. nvidia-smi CLI (READ_ONLY) — fallback.
  3. Unavailable — reported honestly as GPU UNAVAILABLE.

No GPU data is ever fabricated. status() carries a short TTL cache so the
multiple collectors polling in parallel do not multiply NVML round-trips.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass, field

try:  # optional dependency
    import pynvml  # type: ignore

    _HAS_PYNVML = True
except Exception:  # pragma: no cover - depends on host
    pynvml = None  # type: ignore
    _HAS_PYNVML = False


@dataclass
class GPUInfo:
    index: int
    name: str
    memory_total_mb: float
    memory_used_mb: float
    memory_free_mb: float
    utilization_pct: float
    temperature_c: float | None
    power_w: float | None
    driver_version: str | None = None
    cuda_version: str | None = None


@dataclass
class GPUStatus:
    available: bool
    source: str  # "pynvml" | "nvidia-smi" | "unavailable"
    gpus: list[GPUInfo] = field(default_factory=list)
    driver_version: str | None = None
    cuda_version: str | None = None
    detail: str = ""


class GPUMonitor:
    def __init__(self, status_ttl_s: float = 1.0) -> None:
        self._pynvml_ready = False
        if _HAS_PYNVML:
            try:
                pynvml.nvmlInit()
                self._pynvml_ready = True
            except Exception:
                self._pynvml_ready = False
        self._status_ttl_s = status_ttl_s
        self._cached_status: GPUStatus | None = None
        self._cached_at: float = 0.0

    # ------------------------------------------------------------------ pynvml
    def _via_pynvml(self) -> GPUStatus:
        gpus: list[GPUInfo] = []
        count = pynvml.nvmlDeviceGetCount()
        driver = pynvml.nvmlSystemGetDriverVersion()
        driver = driver.decode() if isinstance(driver, bytes) else str(driver)
        cuda: str | None = None
        try:
            cuda_raw = pynvml.nvmlSystemGetCudaDriverVersion_v2()
            cuda = f"{cuda_raw // 1000}.{(cuda_raw % 1000) // 10}"
        except Exception:
            pass
        for i in range(count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(handle)
            name = name.decode() if isinstance(name, bytes) else str(name)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            try:
                temp = float(pynvml.nvmlDeviceGetTemperature(handle, 0))
            except Exception:
                temp = None
            try:
                power = float(pynvml.nvmlDeviceGetPowerUsage(handle)) / 1000.0
            except Exception:
                power = None
            gpus.append(
                GPUInfo(
                    index=i,
                    name=name,
                    memory_total_mb=mem.total / 1024**2,
                    memory_used_mb=mem.used / 1024**2,
                    memory_free_mb=mem.free / 1024**2,
                    utilization_pct=float(util.gpu),
                    temperature_c=temp,
                    power_w=power,
                )
            )
        return GPUStatus(True, "pynvml", gpus, driver, cuda)

    # -------------------------------------------------------------- nvidia-smi
    def _via_nvidia_smi(self) -> GPUStatus:
        if shutil.which("nvidia-smi") is None:
            return GPUStatus(False, "unavailable", detail="nvidia-smi not found on PATH")
        try:
            proc = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=index,name,memory.total,memory.used,memory.free,"
                    "utilization.gpu,temperature.gpu,power.draw,driver_version",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return GPUStatus(False, "unavailable", detail=str(exc))
        if proc.returncode != 0:
            return GPUStatus(False, "unavailable", detail=proc.stderr.strip() or "nvidia-smi failed")
        gpus: list[GPUInfo] = []
        driver: str | None = None
        for line in proc.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 8:
                continue

            def num(x: str) -> float | None:
                try:
                    return float(x)
                except ValueError:
                    return None

            total = num(parts[2]) or 0.0
            used = num(parts[3]) or 0.0
            free = num(parts[4]) or 0.0
            driver = parts[8] if len(parts) > 8 and parts[8] not in ("N/A", "") else driver
            gpus.append(
                GPUInfo(
                    index=int(float(parts[0])),
                    name=parts[1],
                    memory_total_mb=total,
                    memory_used_mb=used,
                    memory_free_mb=free,
                    utilization_pct=num(parts[5]) or 0.0,
                    temperature_c=num(parts[6]),
                    power_w=num(parts[7]) if parts[7] not in ("N/A", "") else None,
                )
            )
        if not gpus:
            return GPUStatus(False, "unavailable", detail="nvidia-smi returned no GPUs")
        return GPUStatus(True, "nvidia-smi", gpus, driver, None)

    def status(self) -> GPUStatus:
        """Cached snapshot: system + experiment collectors share one NVML poll per TTL."""
        now = time.monotonic()
        if self._cached_status is not None and now - self._cached_at < self._status_ttl_s:
            return self._cached_status
        if self._pynvml_ready:
            try:
                status = self._via_pynvml()
            except Exception:
                status = self._via_nvidia_smi()
        else:
            status = self._via_nvidia_smi()
        self._cached_status = status
        self._cached_at = now
        return status


_monitor: GPUMonitor | None = None


def get_gpu_monitor() -> GPUMonitor:
    global _monitor
    if _monitor is None:
        _monitor = GPUMonitor()
    return _monitor
