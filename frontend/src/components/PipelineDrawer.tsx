import React, { useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  Terminal,
  Tv,
  ScrollText,
} from "lucide-react";
import { api } from "../api/client";
import type { ChannelSnapshot } from "../types";

interface PipelineDrawerProps {
  snapshot: ChannelSnapshot;
}

type DrawerTab = "pipeline" | "preview" | "logs";

export const PipelineDrawer: React.FC<PipelineDrawerProps> = ({ snapshot }) => {
  const [tab, setTab] = useState<DrawerTab>("pipeline");
  const [collapsed, setCollapsed] = useState(false);
  const [copied, setCopied] = useState(false);

  const isRunning = snapshot.telemetry.state === "running";
  const launchCmd = snapshot.pipeline_description
    ? `gst-launch-1.0 -e \\\n  ${snapshot.pipeline_description}`
    : "# Connect at least one Input to an Output to compile a pipeline.";

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(launchCmd);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      // clipboard unavailable
    }
  };

  return (
    <section
      className={`bottom-drawer ${collapsed ? "collapsed" : ""}`}
      aria-label="Pipeline Inspector and Logs"
    >
      <div className="drawer-tabs">
        <div className="drawer-tab-group">
          <button
            type="button"
            className={`drawer-tab ${tab === "pipeline" ? "active" : ""}`}
            onClick={() => {
              setTab("pipeline");
              setCollapsed(false);
            }}
          >
            <Terminal size={13} />
            Compiled Pipeline
          </button>
          <button
            type="button"
            className={`drawer-tab ${tab === "preview" ? "active" : ""}`}
            onClick={() => {
              setTab("preview");
              setCollapsed(false);
            }}
          >
            <Tv size={13} />
            Live Monitor
          </button>
          <button
            type="button"
            className={`drawer-tab ${tab === "logs" ? "active" : ""}`}
            onClick={() => {
              setTab("logs");
              setCollapsed(false);
            }}
          >
            <ScrollText size={13} />
            Bus Logs ({snapshot.recent_logs.length})
          </button>
        </div>

        <div className="drawer-tab-group">
          {tab === "pipeline" && !collapsed && (
            <button type="button" className="btn btn-sm" onClick={handleCopy}>
              {copied ? <Check size={13} /> : <Copy size={13} />}
              {copied ? "Copied" : "Copy gst-launch"}
            </button>
          )}
          <button
            type="button"
            className="btn btn-sm btn-icon"
            onClick={() => setCollapsed((c) => !c)}
            aria-label={collapsed ? "Expand drawer" : "Collapse drawer"}
          >
            {collapsed ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>
      </div>

      {!collapsed && (
        <div className="drawer-content">
          {tab === "pipeline" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {snapshot.validation_errors.length > 0 && (
                <div className="validation-banner">
                  {snapshot.validation_errors.join(" • ")}
                </div>
              )}
              <pre className="pipeline-code">{launchCmd}</pre>
            </div>
          )}

          {tab === "preview" && (
            <div className="drawer-preview-wrap">
              <div
                className="drawer-preview-box"
                style={
                  isRunning &&
                  snapshot.telemetry.preview_width &&
                  snapshot.telemetry.preview_height
                    ? {
                        aspectRatio: `${snapshot.telemetry.preview_width} / ${snapshot.telemetry.preview_height}`,
                      }
                    : undefined
                }
              >
                {isRunning && snapshot.telemetry.has_preview ? (
                  <img
                    key={`${snapshot.channel.id}-${snapshot.channel.updated_at}`}
                    src={api.previewStreamUrl(
                      snapshot.channel.id,
                      snapshot.channel.updated_at
                    )}
                    alt={`${snapshot.channel.name} monitor`}
                  />
                ) : (
                  <div className="monitor-standby">
                    <Tv size={22} />
                    <span>{isRunning ? "NO PREVIEW NODE" : "STOPPED"}</span>
                  </div>
                )}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <div className="metric-label">CHANNEL TELEMETRY</div>
                <div className="metric-val">
                  State: {snapshot.telemetry.state.toUpperCase()}
                </div>
                <div className="metric-val">
                  FPS: {isRunning ? snapshot.telemetry.fps.toFixed(1) : "0.0"} |{" "}
                  Bitrate: {Math.round(snapshot.telemetry.bitrate_kbps)} kbps
                </div>
                <div className="metric-val">
                  Frames: {snapshot.telemetry.frames_processed.toLocaleString()}
                </div>
              </div>
            </div>
          )}

          {tab === "logs" && (
            <div className="logs-list">
              {snapshot.recent_logs.length === 0 ? (
                <div className="form-help">
                  No bus logs yet. Start this channel to observe GStreamer bus
                  events.
                </div>
              ) : (
                snapshot.recent_logs.map((entry, idx) => (
                  <div key={`${entry.timestamp}-${idx}`} className="log-row">
                    <span className="log-ts">
                      {entry.timestamp.slice(11, 19)}
                    </span>
                    <span className={`log-lvl ${entry.level}`}>
                      {entry.level}
                    </span>
                    <span className="log-src">[{entry.source}]</span>
                    <span>{entry.message}</span>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
};
