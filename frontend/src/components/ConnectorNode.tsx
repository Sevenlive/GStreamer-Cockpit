import React from "react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import type { ConnectorDefinition } from "../types";

export interface GstNodeData extends Record<string, unknown> {
  connectorType: string;
  label: string;
  params: Record<string, string | number | boolean>;
  definition?: ConnectorDefinition;
}

export type GstFlowNode = Node<GstNodeData, "connector">;

export const ConnectorNode: React.FC<NodeProps<GstFlowNode>> = ({
  data,
  selected,
}) => {
  const def = data.definition;
  const category = def?.category ?? "transform";
  const inputs = def?.inputs ?? [];
  const outputs = def?.outputs ?? [];

  const summaryEntries = Object.entries(data.params || {}).slice(0, 3);

  return (
    <div className={`gst-node ${selected ? "selected" : ""}`}>
      {/* Input Handles */}
      {inputs.map((port, idx) => {
        const topPct =
          inputs.length === 1
            ? 50
            : Math.round(((idx + 1) / (inputs.length + 1)) * 100);
        return (
          <Handle
            key={port.id}
            id={port.id}
            type="target"
            position={Position.Left}
            className={`gst-handle ${
              category === "transform" ? "transform-handle" : ""
            }`}
            style={{ top: `${topPct}%` }}
            title={`${port.label} (${port.id})`}
          />
        );
      })}

      <div className="gst-node-header">
        <span className={`gst-node-cat ${category}`}>{category}</span>
        <span className="gst-node-type">{data.connectorType}</span>
      </div>

      <div className="gst-node-body">
        <div className="gst-node-label">{data.label}</div>
        {summaryEntries.length > 0 && (
          <div className="gst-node-meta">
            {summaryEntries.map(([k, v]) => (
              <div key={k} className="gst-node-meta-row">
                <span>{k}</span>
                <span className="gst-node-meta-val" title={String(v)}>
                  {String(v)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Output Handles */}
      {outputs.map((port, idx) => {
        const topPct =
          outputs.length === 1
            ? 50
            : Math.round(((idx + 1) / (outputs.length + 1)) * 100);
        return (
          <Handle
            key={port.id}
            id={port.id}
            type="source"
            position={Position.Right}
            className="gst-handle output-handle"
            style={{ top: `${topPct}%` }}
            title={`${port.label} (${port.id})`}
          />
        );
      })}
    </div>
  );
};
