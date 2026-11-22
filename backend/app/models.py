"""Pydantic data models for Virtual Channels, Connectors, and Telemetry."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


def model_to_dict(model: BaseModel) -> Dict[str, Any]:
    """Serialize a Pydantic model compatibly across Pydantic v1 and v2."""
    if hasattr(model, "model_dump"):
        return model.model_dump()  # type: ignore[attr-defined]
    return model.dict()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConnectorCategory(str, Enum):
    INPUT = "input"
    TRANSFORM = "transform"
    OUTPUT = "output"


class ChannelState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


class LogLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    DEBUG = "debug"


class ParamOption(BaseModel):
    label: str
    value: str


class ParamSpec(BaseModel):
    name: str
    label: str
    type: str  # "string" | "integer" | "number" | "boolean" | "select"
    default: Any
    options: Optional[List[ParamOption]] = None
    min: Optional[Union[int, float]] = None
    max: Optional[Union[int, float]] = None
    step: Optional[Union[int, float]] = None
    placeholder: Optional[str] = None
    description: Optional[str] = None
    live_updatable: bool = False


class PortSpec(BaseModel):
    id: str
    label: str
    media_type: str = "video"


class ConnectorDefinition(BaseModel):
    type: str
    label: str
    category: ConnectorCategory
    description: str
    gst_elements: List[str] = Field(default_factory=list)
    inputs: List[PortSpec] = Field(default_factory=list)
    outputs: List[PortSpec] = Field(default_factory=list)
    params: List[ParamSpec] = Field(default_factory=list)


class Position(BaseModel):
    x: float = 0.0
    y: float = 0.0


class ConnectorNode(BaseModel):
    id: str
    type: str
    label: str
    params: Dict[str, Any] = Field(default_factory=dict)
    position: Position = Field(default_factory=Position)


class ConnectorEdge(BaseModel):
    id: str
    source: str
    source_handle: str = "out"
    target: str
    target_handle: str = "in"


class VirtualChannel(BaseModel):
    id: str
    name: str
    description: str = ""
    nodes: List[ConnectorNode] = Field(default_factory=list)
    edges: List[ConnectorEdge] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class ChannelTelemetry(BaseModel):
    state: ChannelState = ChannelState.STOPPED
    uptime_sec: float = 0.0
    fps: float = 0.0
    bitrate_kbps: float = 0.0
    frames_processed: int = 0
    dropped_frames: int = 0
    active_outputs: int = 0
    has_preview: bool = False
    preview_width: Optional[int] = None
    preview_height: Optional[int] = None
    error_message: Optional[str] = None


class LogEntry(BaseModel):
    timestamp: str = Field(default_factory=utc_now_iso)
    level: LogLevel = LogLevel.INFO
    source: str = "engine"
    message: str


class ChannelSnapshot(BaseModel):
    channel: VirtualChannel
    telemetry: ChannelTelemetry
    pipeline_description: str
    validation_errors: List[str] = Field(default_factory=list)
    recent_logs: List[LogEntry] = Field(default_factory=list)


class CreateChannelRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = ""
    preset: Optional[str] = None  # "blank" | "test_record" | "rtsp_rtmp" | "pip_switcher"


class UpdateChannelRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = None


class UpdateGraphRequest(BaseModel):
    nodes: List[ConnectorNode]
    edges: List[ConnectorEdge]


class UpdateNodeParamsRequest(BaseModel):
    label: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)


class EngineStatus(BaseModel):
    backend_mode: str  # "gstreamer" | "simulation"
    gstreamer_version: Optional[str] = None
    total_channels: int
    running_channels: int
    recordings_dir: str
