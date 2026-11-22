import type {
  ChannelSnapshot,
  ConnectorDefinition,
  ConnectorEdgeData,
  ConnectorNodeData,
  EngineStatus,
  RecordingFile,
  TelemetryMessage,
} from "../types";

const API_BASE = "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    ...init,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      // ignore parse failure
    }
    throw new Error(detail);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

export const api = {
  getStatus: () => request<EngineStatus>("/api/status"),
  getConnectors: () => request<ConnectorDefinition[]>("/api/connectors"),
  getChannels: () => request<ChannelSnapshot[]>("/api/channels"),
  getChannel: (id: string) => request<ChannelSnapshot>(`/api/channels/${id}`),
  getRecordings: () => request<RecordingFile[]>("/api/recordings"),

  createChannel: (payload: { name: string; description: string; preset?: string }) =>
    request<ChannelSnapshot>("/api/channels", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateChannelMeta: (id: string, payload: { name?: string; description?: string }) =>
    request<ChannelSnapshot>(`/api/channels/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  updateChannelGraph: (id: string, nodes: ConnectorNodeData[], edges: ConnectorEdgeData[]) =>
    request<ChannelSnapshot>(`/api/channels/${id}/graph`, {
      method: "PUT",
      body: JSON.stringify({ nodes, edges }),
    }),

  updateNodeParams: (
    channelId: string,
    nodeId: string,
    payload: { label?: string; params: Record<string, string | number | boolean> }
  ) =>
    request<ChannelSnapshot>(`/api/channels/${channelId}/nodes/${nodeId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  startChannel: (id: string) =>
    request<ChannelSnapshot>(`/api/channels/${id}/start`, { method: "POST" }),

  stopChannel: (id: string) =>
    request<ChannelSnapshot>(`/api/channels/${id}/stop`, { method: "POST" }),

  restartChannel: (id: string) =>
    request<ChannelSnapshot>(`/api/channels/${id}/restart`, { method: "POST" }),

  deleteChannel: (id: string) =>
    request<void>(`/api/channels/${id}`, { method: "DELETE" }),

  previewStreamUrl: (channelId: string, cacheBust?: string | number) =>
    `/api/channels/${channelId}/preview.mjpeg${
      cacheBust ? `?v=${encodeURIComponent(String(cacheBust))}` : ""
    }`,
};

export function connectTelemetryWebSocket(
  onMessage: (msg: TelemetryMessage) => void,
  onConnectionChange?: (connected: boolean) => void
): () => void {
  let ws: WebSocket | null = null;
  let closed = false;
  let reconnectTimer: number | null = null;

  const connect = () => {
    if (closed) return;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${protocol}//${window.location.host}/ws/telemetry`;
    ws = new WebSocket(url);

    ws.onopen = () => {
      onConnectionChange?.(true);
    };

    ws.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data) as TelemetryMessage;
        if (parsed.type === "telemetry") {
          onMessage(parsed);
        }
      } catch {
        // ignore malformed frames
      }
    };

    ws.onclose = () => {
      onConnectionChange?.(false);
      if (!closed) {
        reconnectTimer = window.setTimeout(connect, 2000);
      }
    };

    ws.onerror = () => {
      ws?.close();
    };
  };

  connect();

  return () => {
    closed = true;
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer);
    }
    ws?.close();
  };
}
