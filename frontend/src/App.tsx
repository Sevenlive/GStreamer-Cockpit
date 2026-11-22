import React, { useCallback, useEffect, useState } from "react";
import { api, connectTelemetryWebSocket } from "./api/client";
import { ChannelDashboard } from "./components/ChannelDashboard";
import { ChannelEditor } from "./components/ChannelEditor";
import { NewChannelModal } from "./components/NewChannelModal";
import { TopBar, type CockpitView } from "./components/TopBar";
import type {
  ChannelSnapshot,
  ConnectorDefinition,
  ConnectorEdgeData,
  ConnectorNodeData,
  EngineStatus,
} from "./types";

export const App: React.FC = () => {
  const [view, setView] = useState<CockpitView>("dashboard");
  const [engineStatus, setEngineStatus] = useState<EngineStatus | null>(null);
  const [connectors, setConnectors] = useState<ConnectorDefinition[]>([]);
  const [channels, setChannels] = useState<ChannelSnapshot[]>([]);
  const [selectedChannelId, setSelectedChannelId] = useState<string>("");
  const [wsConnected, setWsConnected] = useState(false);
  const [busyChannelId, setBusyChannelId] = useState<string | null>(null);
  const [showNewModal, setShowNewModal] = useState(false);
  const [toastError, setToastError] = useState<string | null>(null);

  const upsertSnapshot = useCallback((snap: ChannelSnapshot) => {
    setChannels((prev) => {
      const exists = prev.some((c) => c.channel.id === snap.channel.id);
      if (!exists) return [...prev, snap];
      return prev.map((c) => (c.channel.id === snap.channel.id ? snap : c));
    });
  }, []);

  useEffect(() => {
    let active = true;
    Promise.all([api.getStatus(), api.getConnectors(), api.getChannels()])
      .then(([status, defs, chans]) => {
        if (!active) return;
        setEngineStatus(status);
        setConnectors(defs);
        setChannels(chans);
        if (chans.length > 0) {
          setSelectedChannelId((prev) => prev || chans[0].channel.id);
        }
      })
      .catch((err) => {
        if (active) {
          setToastError(
            err instanceof Error ? err.message : "Failed to connect to engine"
          );
        }
      });

    const disconnect = connectTelemetryWebSocket(
      (msg) => {
        if (!active) return;
        setEngineStatus(msg.status);
        setChannels(msg.channels);
        if (msg.channels.length > 0) {
          setSelectedChannelId((prev) => prev || msg.channels[0].channel.id);
        }
      },
      (connected) => {
        if (active) setWsConnected(connected);
      }
    );

    return () => {
      active = false;
      disconnect();
    };
  }, []);

  const runChannelAction = async (
    channelId: string,
    action: () => Promise<ChannelSnapshot>
  ) => {
    setBusyChannelId(channelId);
    setToastError(null);
    try {
      const updated = await action();
      upsertSnapshot(updated);
    } catch (err) {
      setToastError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusyChannelId(null);
    }
  };

  const handleStart = (channelId: string) =>
    runChannelAction(channelId, () => api.startChannel(channelId));

  const handleStop = (channelId: string) =>
    runChannelAction(channelId, () => api.stopChannel(channelId));

  const handleRestart = (channelId: string) =>
    runChannelAction(channelId, () => api.restartChannel(channelId));

  const handleDelete = async (channelId: string) => {
    setBusyChannelId(channelId);
    try {
      await api.deleteChannel(channelId);
      setChannels((prev) => prev.filter((c) => c.channel.id !== channelId));
    } catch (err) {
      setToastError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setBusyChannelId(null);
    }
  };

  const handleCreateChannel = async (payload: {
    name: string;
    description: string;
    preset: string;
  }) => {
    const created = await api.createChannel(payload);
    upsertSnapshot(created);
    setSelectedChannelId(created.channel.id);
    setView("editor");
  };

  const handleSaveGraph = async (
    channelId: string,
    nodes: ConnectorNodeData[],
    edges: ConnectorEdgeData[]
  ) => {
    setToastError(null);
    const updated = await api.updateChannelGraph(channelId, nodes, edges);
    upsertSnapshot(updated);
  };

  const handleLiveUpdateNode = async (
    channelId: string,
    nodeId: string,
    params: Record<string, string | number | boolean>
  ) => {
    const updated = await api.updateNodeParams(channelId, nodeId, { params });
    upsertSnapshot(updated);
  };

  const handleOpenEditor = (channelId: string) => {
    setSelectedChannelId(channelId);
    setView("editor");
  };

  return (
    <div className="cockpit-shell">
      <TopBar
        activeView={view}
        onSelectView={setView}
        engineStatus={engineStatus}
        wsConnected={wsConnected}
        onNewChannel={() => setShowNewModal(true)}
      />

      {toastError && (
        <div
          className="validation-banner"
          style={{
            borderRadius: 0,
            display: "flex",
            justifyContent: "space-between",
            padding: "8px 20px",
          }}
        >
          <span>{toastError}</span>
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => setToastError(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      {view === "dashboard" ? (
        <ChannelDashboard
          channels={channels}
          connectors={connectors}
          engineStatus={engineStatus}
          busyChannelId={busyChannelId}
          onStart={handleStart}
          onStop={handleStop}
          onRestart={handleRestart}
          onDelete={handleDelete}
          onOpenEditor={handleOpenEditor}
        />
      ) : (
        <ChannelEditor
          channels={channels}
          selectedChannelId={selectedChannelId}
          connectors={connectors}
          busyChannelId={busyChannelId}
          onSelectChannel={setSelectedChannelId}
          onSaveGraph={handleSaveGraph}
          onLiveUpdateNode={handleLiveUpdateNode}
          onStart={handleStart}
          onStop={handleStop}
          onRestart={handleRestart}
        />
      )}

      {showNewModal && (
        <NewChannelModal
          onClose={() => setShowNewModal(false)}
          onCreate={handleCreateChannel}
        />
      )}
    </div>
  );
};

export default App;
