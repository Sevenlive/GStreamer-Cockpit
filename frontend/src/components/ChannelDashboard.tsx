import React from "react";
import {
  Network,
  Play,
  RotateCw,
  Square,
  Trash2,
  Tv,
  AlertTriangle,
} from "lucide-react";
import { api } from "../api/client";
import type {
  ChannelSnapshot,
  ConnectorDefinition,
  EngineStatus,
} from "../types";

interface ChannelDashboardProps {
  channels: ChannelSnapshot[];
  connectors: ConnectorDefinition[];
  engineStatus: EngineStatus | null;
  busyChannelId: string | null;
  onStart: (channelId: string) => void;
  onStop: (channelId: string) => void;
  onRestart: (channelId: string) => void;
  onDelete: (channelId: string) => void;
  onOpenEditor: (channelId: string) => void;
}

function formatUptime(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const rem = s % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(
    rem
  ).padStart(2, "0")}`;
}

export const ChannelDashboard: React.FC<ChannelDashboardProps> = ({
  channels,
  connectors,
  engineStatus,
  busyChannelId,
  onStart,
  onStop,
  onRestart,
  onDelete,
  onOpenEditor,
}) => {
  const defMap = React.useMemo(
    () => new Map(connectors.map((c) => [c.type, c])),
    [connectors]
  );

  const runningCount = channels.filter(
    (c) => c.telemetry.state === "running"
  ).length;
  const totalBitrate = channels.reduce(
    (acc, c) => acc + (c.telemetry.state === "running" ? c.telemetry.bitrate_kbps : 0),
    0
  );
  const totalOutputs = channels.reduce(
    (acc, c) => acc + c.telemetry.active_outputs,
    0
  );

  return (
    <main className="dashboard-scroll">
      <section className="dashboard-header">
        <div>
          <h2>Virtual Channel Multiview</h2>
          <p>
            Monitor live video pipelines, toggle streaming &amp; recording
            channels, or inspect connector routing.
          </p>
        </div>

        <div className="kpi-strip">
          <div className="kpi-box">
            <div className="kpi-label">Active Channels</div>
            <div className="kpi-value">
              {runningCount} / {engineStatus?.total_channels ?? channels.length}
            </div>
          </div>
          <div className="kpi-box">
            <div className="kpi-label">Aggregate Bitrate</div>
            <div className="kpi-value">
              {(totalBitrate / 1000).toFixed(2)} Mbps
            </div>
          </div>
          <div className="kpi-box">
            <div className="kpi-label">Active Outputs</div>
            <div className="kpi-value">{totalOutputs}</div>
          </div>
        </div>
      </section>

      <section className="channel-grid" aria-label="Virtual Channels">
        {channels.map((snap) => {
          const { channel, telemetry, validation_errors } = snap;
          const isRunning = telemetry.state === "running";
          const isBusy = busyChannelId === channel.id;
          const hasErrors = validation_errors.length > 0;

          return (
            <article key={channel.id} className="channel-card">
              <div className="channel-monitor">
                {isRunning && telemetry.has_preview ? (
                  <img
                    key={`${channel.id}-${channel.updated_at}`}
                    src={api.previewStreamUrl(channel.id, channel.updated_at)}
                    alt={`${channel.name} live preview`}
                  />
                ) : (
                  <div className="monitor-standby">
                    <Tv size={28} strokeWidth={1.5} />
                    <span>
                      {isRunning
                        ? "RUNNING (NO PREVIEW CONNECTOR)"
                        : "STANDBY • NO SIGNAL"}
                    </span>
                  </div>
                )}

                <div className={`monitor-badge ${telemetry.state}`}>
                  <span
                    className={`status-dot ${
                      isRunning
                        ? "error"
                        : telemetry.state === "error"
                        ? "sim"
                        : ""
                    }`}
                  />
                  {isRunning
                    ? "ON AIR"
                    : telemetry.state === "error"
                    ? "FAULT"
                    : "STANDBY"}
                </div>
              </div>

              <div className="channel-body">
                <div className="channel-title-row">
                  <div>
                    <h3 className="channel-name">{channel.name}</h3>
                    {channel.description && (
                      <p className="channel-desc">{channel.description}</p>
                    )}
                  </div>
                </div>

                <div className="telemetry-row">
                  <div className="metric-cell">
                    <span className="metric-label">FPS</span>
                    <span className="metric-val">
                      {isRunning ? telemetry.fps.toFixed(1) : "—"}
                    </span>
                  </div>
                  <div className="metric-cell">
                    <span className="metric-label">Bitrate</span>
                    <span className="metric-val">
                      {isRunning ? `${Math.round(telemetry.bitrate_kbps)}k` : "—"}
                    </span>
                  </div>
                  <div className="metric-cell">
                    <span className="metric-label">Uptime</span>
                    <span className="metric-val">
                      {isRunning ? formatUptime(telemetry.uptime_sec) : "00:00:00"}
                    </span>
                  </div>
                  <div className="metric-cell">
                    <span className="metric-label">Outputs</span>
                    <span className="metric-val">
                      {telemetry.active_outputs}
                    </span>
                  </div>
                </div>

                <div className="chain-strip">
                  {channel.nodes.map((node) => {
                    const cat = defMap.get(node.type)?.category ?? "transform";
                    return (
                      <span
                        key={node.id}
                        className={`connector-pill ${cat}`}
                        title={`${node.type}: ${node.label}`}
                      >
                        {node.label}
                      </span>
                    );
                  })}
                </div>

                {hasErrors && (
                  <div className="validation-banner">
                    <AlertTriangle
                      size={13}
                      style={{ verticalAlign: "middle", marginRight: 6 }}
                    />
                    {validation_errors[0]}
                  </div>
                )}

                {telemetry.error_message && (
                  <div className="validation-banner">
                    {telemetry.error_message}
                  </div>
                )}

                <div className="channel-actions">
                  <div className="channel-actions-left">
                    {!isRunning ? (
                      <button
                        type="button"
                        className="btn btn-start btn-sm"
                        disabled={isBusy || hasErrors}
                        onClick={() => onStart(channel.id)}
                      >
                        <Play size={13} />
                        Start
                      </button>
                    ) : (
                      <>
                        <button
                          type="button"
                          className="btn btn-stop btn-sm"
                          disabled={isBusy}
                          onClick={() => onStop(channel.id)}
                        >
                          <Square size={13} />
                          Stop
                        </button>
                        <button
                          type="button"
                          className="btn btn-sm btn-icon"
                          title="Restart channel"
                          disabled={isBusy}
                          onClick={() => onRestart(channel.id)}
                        >
                          <RotateCw size={13} />
                        </button>
                      </>
                    )}
                  </div>

                  <div className="channel-actions-right">
                    <button
                      type="button"
                      className="btn btn-sm"
                      onClick={() => onOpenEditor(channel.id)}
                    >
                      <Network size={13} />
                      Edit Graph
                    </button>
                    <button
                      type="button"
                      className="btn btn-sm btn-icon"
                      title="Delete channel"
                      disabled={isBusy}
                      onClick={() => onDelete(channel.id)}
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              </div>
            </article>
          );
        })}
      </section>
    </main>
  );
};
