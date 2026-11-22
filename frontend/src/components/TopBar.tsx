import React from "react";
import { LayoutGrid, Network, Plus, Radio } from "lucide-react";
import type { EngineStatus } from "../types";

export type CockpitView = "dashboard" | "editor";

interface TopBarProps {
  activeView: CockpitView;
  onSelectView: (view: CockpitView) => void;
  engineStatus: EngineStatus | null;
  wsConnected: boolean;
  onNewChannel: () => void;
}

export const TopBar: React.FC<TopBarProps> = ({
  activeView,
  onSelectView,
  engineStatus,
  wsConnected,
  onNewChannel,
}) => {
  const isGst = engineStatus?.backend_mode === "gstreamer";

  return (
    <header className="topbar">
      <div className="topbar-brand">
        <div className="brand-mark" aria-hidden="true">
          <Radio size={17} />
        </div>
        <div>
          <h1 className="brand-title">GStreamer Cockpit</h1>
          <div className="brand-subtitle">VIRTUAL CHANNEL ENGINE</div>
        </div>
      </div>

      <nav className="topbar-nav" aria-label="Primary views">
        <button
          id="nav-dashboard"
          type="button"
          className={`nav-tab ${activeView === "dashboard" ? "active" : ""}`}
          onClick={() => onSelectView("dashboard")}
        >
          <LayoutGrid size={15} />
          Channel Dashboard
        </button>
        <button
          id="nav-editor"
          type="button"
          className={`nav-tab ${activeView === "editor" ? "active" : ""}`}
          onClick={() => onSelectView("editor")}
        >
          <Network size={15} />
          Node Graph Editor
        </button>
      </nav>

      <div className="topbar-right">
        <div
          className="engine-chip"
          title={
            engineStatus?.gstreamer_version ||
            "Running in software simulation mode (install GStreamer or use Docker for native pipelines)"
          }
        >
          <span
            className={`status-dot ${
              !wsConnected ? "error" : isGst ? "live" : "sim"
            }`}
          />
          <span>
            {!wsConnected
              ? "RECONNECTING"
              : isGst
              ? "GSTREAMER NATIVE"
              : "SIMULATION ENGINE"}
          </span>
        </div>

        <button
          id="btn-new-channel"
          type="button"
          className="btn btn-primary"
          onClick={onNewChannel}
        >
          <Plus size={15} />
          New Channel
        </button>
      </div>
    </header>
  );
};
