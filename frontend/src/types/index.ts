export type ConnectorCategory = "input" | "transform" | "output";
export type ChannelState = "stopped" | "starting" | "running" | "error";
export type LogLevel = "info" | "warning" | "error" | "debug";

export interface ParamOption {
  label: string;
  value: string;
}

export interface ParamSpec {
  name: string;
  label: string;
  type: "string" | "integer" | "number" | "boolean" | "select";
  default: string | number | boolean;
  options?: ParamOption[] | null;
  min?: number | null;
  max?: number | null;
  step?: number | null;
  placeholder?: string | null;
  description?: string | null;
  live_updatable: boolean;
}

export interface PortSpec {
  id: string;
  label: string;
  media_type: string;
}

export interface ConnectorDefinition {
  type: string;
  label: string;
  category: ConnectorCategory;
  description: string;
  gst_elements: string[];
  inputs: PortSpec[];
  outputs: PortSpec[];
  params: ParamSpec[];
}

export interface Position {
  x: number;
  y: number;
}

export interface ConnectorNodeData {
  id: string;
  type: string;
  label: string;
  params: Record<string, string | number | boolean>;
  position: Position;
}

export interface ConnectorEdgeData {
  id: string;
  source: string;
  source_handle: string;
  target: string;
  target_handle: string;
}

export interface VirtualChannel {
  id: string;
  name: string;
  description: string;
  nodes: ConnectorNodeData[];
  edges: ConnectorEdgeData[];
  created_at: string;
  updated_at: string;
}

export interface ChannelTelemetry {
  state: ChannelState;
  uptime_sec: number;
  fps: number;
  bitrate_kbps: number;
  frames_processed: number;
  dropped_frames: number;
  active_outputs: number;
  has_preview: boolean;
  error_message?: string | null;
}

export interface LogEntry {
  timestamp: string;
  level: LogLevel;
  source: string;
  message: string;
}

export interface ChannelSnapshot {
  channel: VirtualChannel;
  telemetry: ChannelTelemetry;
  pipeline_description: string;
  validation_errors: string[];
  recent_logs: LogEntry[];
}

export interface EngineStatus {
  backend_mode: "gstreamer" | "simulation";
  gstreamer_version?: string | null;
  total_channels: number;
  running_channels: number;
  recordings_dir: string;
}

export interface RecordingFile {
  name: string;
  size_bytes: number;
  modified_at: number;
}

export interface TelemetryMessage {
  type: "telemetry";
  status: EngineStatus;
  channels: ChannelSnapshot[];
}
