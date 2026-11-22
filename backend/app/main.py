"""FastAPI application entrypoint for GStreamer Cockpit."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .api.channels import router as channels_router
from .api.connectors import router as connectors_router
from .engine.manager import EngineManager
from .models import EngineStatus, model_to_dict


def create_app(
    data_dir: Optional[Path] = None,
    recordings_dir: Optional[Path] = None,
    force_simulation: Optional[bool] = None,
) -> FastAPI:
    app = FastAPI(
        title="GStreamer Cockpit Engine",
        version="0.1.0",
        description="Virtual channel video streaming, transformation, and recording engine built on GStreamer.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    engine = EngineManager(
        data_dir=data_dir,
        recordings_dir=recordings_dir,
        force_simulation=force_simulation,
    )
    app.state.engine = engine

    app.include_router(connectors_router)
    app.include_router(channels_router)

    @app.get("/api/status", response_model=EngineStatus, tags=["system"])
    def get_status() -> EngineStatus:
        return engine.get_engine_status()

    @app.get("/api/recordings", tags=["system"])
    def list_recordings() -> List[Dict[str, Any]]:
        return engine.list_recordings()

    @app.websocket("/ws/telemetry")
    async def telemetry_ws(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                payload = {
                    "type": "telemetry",
                    "status": model_to_dict(engine.get_engine_status()),
                    "channels": [model_to_dict(snap) for snap in engine.list_snapshots()],
                }
                await websocket.send_json(payload)
                await asyncio.sleep(1.0)
        except WebSocketDisconnect:
            return
        except Exception:
            return

    @app.on_event("shutdown")
    def on_shutdown() -> None:
        engine.shutdown()

    return app


app = create_app()
