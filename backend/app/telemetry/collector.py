"""Background telemetry collectors.

Two collectors:
  - SystemTelemetryCollector: global, samples host CPU/RAM/Disk/GPU into memory
    (ring buffer) for /api/system/telemetry and the dashboard.
  - ExperimentTelemetryCollector: per-experiment, additionally writes JSONL into
    the experiment workspace (telemetry/gpu.jsonl, telemetry/system.jsonl).
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from pathlib import Path
from typing import Any

from ..core.config import settings
from ..core.events import Event, EventType, bus
from .gpu import get_gpu_monitor
from .system import sample_system


def _gpu_snapshot() -> dict[str, Any]:
    status = get_gpu_monitor().status()
    return {
        "available": status.available,
        "source": status.source,
        "driver": status.driver_version,
        "cuda": status.cuda_version,
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
            for g in status.gpus
        ],
    }


class SystemTelemetryCollector:
    def __init__(self, max_samples: int = 900) -> None:
        self._samples: deque[dict[str, Any]] = deque(maxlen=max_samples)
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    @property
    def latest(self) -> dict[str, Any] | None:
        return self._samples[-1] if self._samples else None

    def history(self, limit: int = 120) -> list[dict[str, Any]]:
        items = list(self._samples)
        return items[-limit:]

    async def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await asyncio.gather(self._task, return_exceptions=True)

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                sys_sample = sample_system()
                gpu = _gpu_snapshot()
                record = {
                    "ts": time.time(),
                    "cpu_pct": sys_sample.cpu_pct,
                    "ram_used_gb": round(sys_sample.ram_used_gb, 2),
                    "ram_total_gb": round(sys_sample.ram_total_gb, 2),
                    "disk_free_gb": round(sys_sample.disk_free_gb, 1),
                    "gpu": gpu,
                }
                self._samples.append(record)
                await bus.emit(
                    Event(type=EventType.TELEMETRY_SAMPLE, experiment_id=None, payload=record)
                )
            except Exception:
                pass  # telemetry must never crash the app
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=settings.telemetry_system_interval_s)
            except asyncio.TimeoutError:
                pass


class ExperimentTelemetryCollector:
    """Per-experiment JSONL telemetry writer."""

    def __init__(self, experiment_id: str, workspace: Path) -> None:
        self.experiment_id = experiment_id
        self.telemetry_dir = workspace / "telemetry"
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        self.telemetry_dir.mkdir(parents=True, exist_ok=True)
        self._stop.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await asyncio.gather(self._task, return_exceptions=True)

    def _append(self, filename: str, record: dict[str, Any]) -> None:
        with (self.telemetry_dir / filename).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                sys_sample = sample_system()
                self._append(
                    "system.jsonl",
                    {
                        "ts": time.time(),
                        "cpu_pct": sys_sample.cpu_pct,
                        "ram_used_gb": round(sys_sample.ram_used_gb, 2),
                        "disk_free_gb": round(sys_sample.disk_free_gb, 1),
                    },
                )
                gpu = _gpu_snapshot()
                self._append("gpu.jsonl", {"ts": time.time(), **gpu})
            except Exception:
                pass
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=settings.telemetry_gpu_interval_s)
            except asyncio.TimeoutError:
                pass


system_collector = SystemTelemetryCollector()
