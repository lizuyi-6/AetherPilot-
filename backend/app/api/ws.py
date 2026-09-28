"""WebSocket streams: per-experiment events and global system telemetry."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.events import bus
from ..telemetry.collector import system_collector

router = APIRouter()


@router.websocket("/ws/experiments/{experiment_id}")
async def experiment_events(ws: WebSocket, experiment_id: str) -> None:
    await ws.accept()
    queue = bus.subscribe(experiment_id)
    try:
        while True:
            event = await queue.get()
            await ws.send_text(event.model_dump_json())
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(queue)


@router.websocket("/ws/system")
async def system_stream(ws: WebSocket) -> None:
    await ws.accept()
    queue = bus.subscribe(None)
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=5.0)
                if event.type == "TELEMETRY_SAMPLE" and event.experiment_id is None:
                    await ws.send_text(json.dumps({"type": "telemetry", "data": event.payload}))
            except asyncio.TimeoutError:
                latest = system_collector.latest
                if latest:
                    await ws.send_text(json.dumps({"type": "telemetry", "data": latest}))
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(queue)
