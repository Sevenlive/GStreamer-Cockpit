import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  MarkerType,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Play, RotateCw, Save, Square } from "lucide-react";

import type {
  ChannelSnapshot,
  ConnectorDefinition,
  ConnectorEdgeData,
  ConnectorNodeData,
} from "../types";
import { ConnectorNode, type GstFlowNode } from "./ConnectorNode";
import { ConnectorPalette } from "./ConnectorPalette";
import { InspectorPanel } from "./InspectorPanel";
import { PipelineDrawer } from "./PipelineDrawer";

const NODE_TYPES: NodeTypes = {
  connector: ConnectorNode,
};

interface ChannelEditorProps {
  channels: ChannelSnapshot[];
  selectedChannelId: string;
  connectors: ConnectorDefinition[];
  busyChannelId: string | null;
  onSelectChannel: (channelId: string) => void;
  onSaveGraph: (
    channelId: string,
    nodes: ConnectorNodeData[],
    edges: ConnectorEdgeData[]
  ) => Promise<void>;
  onLiveUpdateNode: (
    channelId: string,
    nodeId: string,
    params: Record<string, string | number | boolean>
  ) => Promise<void>;
  onStart: (channelId: string) => void;
  onStop: (channelId: string) => void;
  onRestart: (channelId: string) => void;
}

export const ChannelEditor: React.FC<ChannelEditorProps> = ({
  channels,
  selectedChannelId,
  connectors,
  busyChannelId,
  onSelectChannel,
  onSaveGraph,
  onLiveUpdateNode,
  onStart,
  onStop,
  onRestart,
}) => {
  const snapshot = useMemo(
    () => channels.find((c) => c.channel.id === selectedChannelId) ?? channels[0],
    [channels, selectedChannelId]
  );

  const defMap = useMemo(
    () => new Map(connectors.map((c) => [c.type, c])),
    [connectors]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState<GstFlowNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  // Hydrate React Flow graph whenever switching channels
  useEffect(() => {
    if (!snapshot) return;
    const flowNodes: GstFlowNode[] = snapshot.channel.nodes.map((n) => ({
      id: n.id,
      type: "connector",
      position: { x: n.position.x, y: n.position.y },
      data: {
        connectorType: n.type,
        label: n.label,
        params: { ...n.params },
        definition: defMap.get(n.type),
      },
    }));

    const flowEdges: Edge[] = snapshot.channel.edges.map((e) => ({
      id: e.id,
      source: e.source,
      sourceHandle: e.source_handle || "out",
      target: e.target,
      targetHandle: e.target_handle || "in",
      animated: snapshot.telemetry.state === "running",
      style: { stroke: "#5c7089", strokeWidth: 2 },
      markerEnd: { type: MarkerType.ArrowClosed, color: "#5c7089" },
    }));

    setNodes(flowNodes);
    setEdges(flowEdges);
    setSelectedNodeId(null);
    setDirty(false);
  }, [snapshot?.channel.id, defMap, setNodes, setEdges]);

  // Animate edges when running state changes without clobbering unsaved edits
  useEffect(() => {
    if (!snapshot) return;
    const running = snapshot.telemetry.state === "running";
    setEdges((prev) =>
      prev.map((edge) => ({
        ...edge,
        animated: running,
        style: {
          stroke: running ? "#22b8cf" : "#5c7089",
          strokeWidth: 2,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: running ? "#22b8cf" : "#5c7089",
        },
      }))
    );
  }, [snapshot?.telemetry.state, setEdges]);

  const handleNodesChange = useCallback(
    (changes: Parameters<typeof onNodesChange>[0]) => {
      onNodesChange(changes);
      if (
        changes.some(
          (ch) => ch.type === "position" || ch.type === "remove"
        )
      ) {
        setDirty(true);
      }
    },
    [onNodesChange]
  );

  const handleEdgesChange = useCallback(
    (changes: Parameters<typeof onEdgesChange>[0]) => {
      onEdgesChange(changes);
      if (changes.some((ch) => ch.type === "remove")) {
        setDirty(true);
      }
    },
    [onEdgesChange]
  );

  const handleConnect = useCallback(
    (connection: Connection) => {
      const running = snapshot?.telemetry.state === "running";
      setEdges((eds) =>
        addEdge(
          {
            ...connection,
            id: `e_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
            animated: running,
            style: { stroke: running ? "#22b8cf" : "#5c7089", strokeWidth: 2 },
            markerEnd: {
              type: MarkerType.ArrowClosed,
              color: running ? "#22b8cf" : "#5c7089",
            },
          },
          eds
        )
      );
      setDirty(true);
    },
    [setEdges, snapshot?.telemetry.state]
  );

  const handleAddConnector = useCallback(
    (def: ConnectorDefinition) => {
      const id = `${def.category.slice(0, 2)}_${Date.now().toString(36)}`;
      const defaults: Record<string, string | number | boolean> = {};
      def.params.forEach((p) => {
        defaults[p.name] = p.default;
      });

      const baseX =
        def.category === "input"
          ? 70
          : def.category === "transform"
          ? 380
          : 700;
      const offsetY = 70 + (nodes.length % 5) * 95;

      const newNode: GstFlowNode = {
        id,
        type: "connector",
        position: { x: baseX, y: offsetY },
        data: {
          connectorType: def.type,
          label: def.label,
          params: defaults,
          definition: def,
        },
      };
      setNodes((prev) => [...prev, newNode]);
      setSelectedNodeId(id);
      setDirty(true);
    },
    [nodes.length, setNodes]
  );

  const handleChangeLabel = useCallback(
    (nodeId: string, label: string) => {
      setNodes((prev) =>
        prev.map((n) =>
          n.id === nodeId ? { ...n, data: { ...n.data, label } } : n
        )
      );
      setDirty(true);
    },
    [setNodes]
  );

  const handleChangeParam = useCallback(
    (
      nodeId: string,
      paramName: string,
      value: string | number | boolean,
      isLiveUpdatable: boolean
    ) => {
      setNodes((prev) =>
        prev.map((n) =>
          n.id === nodeId
            ? {
                ...n,
                data: {
                  ...n.data,
                  params: { ...n.data.params, [paramName]: value },
                },
              }
            : n
        )
      );
      setDirty(true);

      if (
        isLiveUpdatable &&
        snapshot &&
        snapshot.telemetry.state === "running"
      ) {
        onLiveUpdateNode(snapshot.channel.id, nodeId, { [paramName]: value }).catch(
          () => {}
        );
      }
    },
    [setNodes, snapshot, onLiveUpdateNode]
  );

  const handleDeleteNode = useCallback(
    (nodeId: string) => {
      setNodes((prev) => prev.filter((n) => n.id !== nodeId));
      setEdges((prev) =>
        prev.filter((e) => e.source !== nodeId && e.target !== nodeId)
      );
      setSelectedNodeId(null);
      setDirty(true);
    },
    [setNodes, setEdges]
  );

  const handleSave = async () => {
    if (!snapshot) return;
    setSaving(true);
    try {
      const apiNodes: ConnectorNodeData[] = nodes.map((n) => ({
        id: n.id,
        type: n.data.connectorType,
        label: n.data.label,
        params: n.data.params,
        position: { x: Math.round(n.position.x), y: Math.round(n.position.y) },
      }));
      const apiEdges: ConnectorEdgeData[] = edges.map((e) => ({
        id: e.id,
        source: e.source,
        source_handle: e.sourceHandle || "out",
        target: e.target,
        target_handle: e.targetHandle || "in",
      }));
      await onSaveGraph(snapshot.channel.id, apiNodes, apiEdges);
      setDirty(false);
    } finally {
      setSaving(false);
    }
  };

  const selectedNodeData: ConnectorNodeData | null = useMemo(() => {
    if (!selectedNodeId) return null;
    const found = nodes.find((n) => n.id === selectedNodeId);
    if (!found) return null;
    return {
      id: found.id,
      type: found.data.connectorType,
      label: found.data.label,
      params: found.data.params,
      position: found.position,
    };
  }, [nodes, selectedNodeId]);

  if (!snapshot) {
    return (
      <div className="dashboard-scroll">
        <p>No virtual channels available. Create one to begin.</p>
      </div>
    );
  }

  const isRunning = snapshot.telemetry.state === "running";
  const isBusy = busyChannelId === snapshot.channel.id;

  return (
    <div className="editor-layout">
      <div className="editor-toolbar">
        <div className="editor-toolbar-left">
          <select
            aria-label="Select virtual channel"
            className="channel-select"
            value={snapshot.channel.id}
            onChange={(e) => onSelectChannel(e.target.value)}
          >
            {channels.map((c) => (
              <option key={c.channel.id} value={c.channel.id}>
                {c.channel.name} ({c.telemetry.state.toUpperCase()})
              </option>
            ))}
          </select>

          {dirty && <span className="dirty-badge">UNSAVED CHANGES</span>}
        </div>

        <div className="editor-toolbar-right">
          <button
            id="btn-save-graph"
            type="button"
            className="btn btn-primary btn-sm"
            disabled={!dirty || saving}
            onClick={handleSave}
          >
            <Save size={14} />
            {saving ? "Saving..." : "Save & Compile"}
          </button>

          {!isRunning ? (
            <button
              type="button"
              className="btn btn-start btn-sm"
              disabled={isBusy || saving || (!dirty && snapshot.validation_errors.length > 0)}
              onClick={async () => {
                if (dirty) {
                  await handleSave();
                }
                onStart(snapshot.channel.id);
              }}
            >
              <Play size={14} />
              Start Channel
            </button>
          ) : (
            <>
              <button
                type="button"
                className="btn btn-stop btn-sm"
                disabled={isBusy}
                onClick={() => onStop(snapshot.channel.id)}
              >
                <Square size={14} />
                Stop
              </button>
              <button
                type="button"
                className="btn btn-sm"
                disabled={isBusy}
                onClick={() => onRestart(snapshot.channel.id)}
              >
                <RotateCw size={14} />
                Restart
              </button>
            </>
          )}
        </div>
      </div>

      <div className="editor-main">
        <ConnectorPalette
          connectors={connectors}
          onAddConnector={handleAddConnector}
        />

        <div className="canvas-wrapper">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={NODE_TYPES}
            onNodesChange={handleNodesChange}
            onEdgesChange={handleEdgesChange}
            onConnect={handleConnect}
            onNodeClick={(_e, node) => setSelectedNodeId(node.id)}
            onPaneClick={() => setSelectedNodeId(null)}
            fitView
            colorMode="dark"
            deleteKeyCode={["Backspace", "Delete"]}
          >
            <Background
              variant={BackgroundVariant.Dots}
              gap={22}
              size={1.2}
              color="#222c3a"
            />
            <Controls />
            <MiniMap
              nodeColor={(n) => {
                const cat = (n.data as GstNodeData)?.definition?.category;
                if (cat === "input") return "#22b8cf";
                if (cat === "output") return "#22c55e";
                return "#e5a00d";
              }}
              maskColor="rgba(11, 14, 19, 0.72)"
            />
          </ReactFlow>
        </div>

        <InspectorPanel
          selectedNode={selectedNodeData}
          definition={
            selectedNodeData
              ? defMap.get(selectedNodeData.type) ?? null
              : null
          }
          isChannelRunning={isRunning}
          onChangeLabel={handleChangeLabel}
          onChangeParam={handleChangeParam}
          onDeleteNode={handleDeleteNode}
        />
      </div>

      <PipelineDrawer snapshot={snapshot} />
    </div>
  );
};
