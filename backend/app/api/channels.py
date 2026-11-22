"""Virtual Channel CRUD, graph editing, pipeline control, and live MJPEG preview routes."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from ..engine.manager import EngineManager
from ..models import (
    ChannelSnapshot,
    CreateChannelRequest,
    UpdateChannelRequest,
    UpdateGraphRequest,
    UpdateNodeParamsRequest,
)

router = APIRouter(prefix="/api/channels", tags=["channels"])


def _get_manager(request: Request) -> EngineManager:
    return request.app.state.engine


@router.get("", response_model=List[ChannelSnapshot])
def list_channels(request: Request) -> List[ChannelSnapshot]:
    return _get_manager(request).list_snapshots()


@router.post("", response_model=ChannelSnapshot, status_code=201)
def create_channel(payload: CreateChannelRequest, request: Request) -> ChannelSnapshot:
    return _get_manager(request).create_channel(
        name=payload.name,
        description=payload.description,
        preset=payload.preset,
    )


@router.get("/{channel_id}", response_model=ChannelSnapshot)
def get_channel(channel_id: str, request: Request) -> ChannelSnapshot:
    try:
        return _get_manager(request).get_snapshot(channel_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{channel_id}", response_model=ChannelSnapshot)
def update_channel(channel_id: str, payload: UpdateChannelRequest, request: Request) -> ChannelSnapshot:
    try:
        return _get_manager(request).update_channel_meta(
            channel_id=channel_id,
            name=payload.name,
            description=payload.description,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{channel_id}/graph", response_model=ChannelSnapshot)
def update_channel_graph(channel_id: str, payload: UpdateGraphRequest, request: Request) -> ChannelSnapshot:
    try:
        return _get_manager(request).update_channel_graph(
            channel_id=channel_id,
            nodes=payload.nodes,
            edges=payload.edges,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{channel_id}/nodes/{node_id}", response_model=ChannelSnapshot)
def update_node_params(
    channel_id: str,
    node_id: str,
    payload: UpdateNodeParamsRequest,
    request: Request,
) -> ChannelSnapshot:
    try:
        return _get_manager(request).update_node_params(
            channel_id=channel_id,
            node_id=node_id,
            params=payload.params,
            label=payload.label,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{channel_id}/start", response_model=ChannelSnapshot)
def start_channel(channel_id: str, request: Request) -> ChannelSnapshot:
    try:
        return _get_manager(request).start_channel(channel_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{channel_id}/stop", response_model=ChannelSnapshot)
def stop_channel(channel_id: str, request: Request) -> ChannelSnapshot:
    try:
        return _get_manager(request).stop_channel(channel_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{channel_id}/restart", response_model=ChannelSnapshot)
def restart_channel(channel_id: str, request: Request) -> ChannelSnapshot:
    try:
        return _get_manager(request).restart_channel(channel_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{channel_id}", status_code=204)
def delete_channel(channel_id: str, request: Request) -> Response:
    try:
        _get_manager(request).delete_channel(channel_id)
        return Response(status_code=204)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{channel_id}/preview.mjpeg")
async def stream_preview_mjpeg(channel_id: str, request: Request) -> StreamingResponse:
    """Stream live multipart MJPEG frames from a running channel's web_preview connector."""
    manager = _get_manager(request)
    try:
        manager.get_snapshot(channel_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    boundary = "frame"

    async def frame_generator():
        while True:
            if await request.is_disconnected():
                break
            frame = manager.get_preview_frame(channel_id)
            if frame:
                yield (
                    f"--{boundary}\r\n"
                    f"Content-Type: image/jpeg\r\n"
                    f"Content-Length: {len(frame)}\r\n\r\n"
                ).encode("ascii") + frame + b"\r\n"
            await asyncio.sleep(0.1)

    return StreamingResponse(
        frame_generator(),
        media_type=f"multipart/x-mixed-replace; boundary={boundary}",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.get("/{channel_id}/snapshot.jpg")
def get_preview_snapshot(channel_id: str, request: Request) -> Response:
    """Return a single JPEG preview frame if the channel is running."""
    manager = _get_manager(request)
    frame = manager.get_preview_frame(channel_id)
    if not frame:
        raise HTTPException(status_code=404, detail="No live preview frame available.")
    return Response(content=frame, media_type="image/jpeg")
