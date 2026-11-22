import React from "react";
import { Trash2 } from "lucide-react";
import type { ConnectorDefinition, ConnectorNodeData } from "../types";

interface InspectorPanelProps {
  selectedNode: ConnectorNodeData | null;
  definition: ConnectorDefinition | null;
  isChannelRunning: boolean;
  onChangeLabel: (nodeId: string, label: string) => void;
  onChangeParam: (
    nodeId: string,
    paramName: string,
    value: string | number | boolean,
    isLiveUpdatable: boolean
  ) => void;
  onDeleteNode: (nodeId: string) => void;
}

export const InspectorPanel: React.FC<InspectorPanelProps> = ({
  selectedNode,
  definition,
  isChannelRunning,
  onChangeLabel,
  onChangeParam,
  onDeleteNode,
}) => {
  if (!selectedNode || !definition) {
    return (
      <aside className="inspector-sidebar" aria-label="Connector Inspector">
        <div className="inspector-header">
          <h3>Inspector</h3>
        </div>
        <div className="inspector-empty">
          Select any connector node on the canvas to configure its GStreamer
          properties, or click a connector in the left library to add it.
        </div>
      </aside>
    );
  }

  return (
    <aside className="inspector-sidebar" aria-label="Connector Inspector">
      <div className="inspector-header">
        <div>
          <h3>{definition.label}</h3>
          <div className="brand-subtitle">{definition.type}</div>
        </div>
        <button
          type="button"
          className="btn btn-stop btn-sm btn-icon"
          title="Remove connector from channel"
          onClick={() => onDeleteNode(selectedNode.id)}
        >
          <Trash2 size={14} />
        </button>
      </div>

      <div className="inspector-body">
        <p className="form-help" style={{ margin: 0 }}>
          {definition.description}
        </p>

        <div className="form-field">
          <label className="form-label" htmlFor="node-label-input">
            Connector Label
          </label>
          <input
            id="node-label-input"
            className="form-input"
            value={selectedNode.label}
            onChange={(e) => onChangeLabel(selectedNode.id, e.target.value)}
          />
        </div>

        {definition.params.map((spec) => {
          const val =
            selectedNode.params[spec.name] !== undefined
              ? selectedNode.params[spec.name]
              : spec.default;
          const fieldId = `param-${selectedNode.id}-${spec.name}`;

          if (spec.type === "boolean") {
            return (
              <div key={spec.name} className="form-field">
                <div className="form-checkbox-row">
                  <label className="form-label" htmlFor={fieldId}>
                    {spec.label}
                  </label>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    {spec.live_updatable && isChannelRunning && (
                      <span className="live-tag">LIVE</span>
                    )}
                    <input
                      id={fieldId}
                      type="checkbox"
                      checked={Boolean(val)}
                      onChange={(e) =>
                        onChangeParam(
                          selectedNode.id,
                          spec.name,
                          e.target.checked,
                          spec.live_updatable
                        )
                      }
                    />
                  </div>
                </div>
                {spec.description && (
                  <span className="form-help">{spec.description}</span>
                )}
              </div>
            );
          }

          if (spec.type === "select" && spec.options) {
            return (
              <div key={spec.name} className="form-field">
                <div className="form-label-row">
                  <label className="form-label" htmlFor={fieldId}>
                    {spec.label}
                  </label>
                  {spec.live_updatable && isChannelRunning && (
                    <span className="live-tag">LIVE</span>
                  )}
                </div>
                <select
                  id={fieldId}
                  className="form-select"
                  value={String(val)}
                  onChange={(e) =>
                    onChangeParam(
                      selectedNode.id,
                      spec.name,
                      e.target.value,
                      spec.live_updatable
                    )
                  }
                >
                  {spec.options.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            );
          }

          if (spec.type === "integer" || spec.type === "number") {
            return (
              <div key={spec.name} className="form-field">
                <div className="form-label-row">
                  <label className="form-label" htmlFor={fieldId}>
                    {spec.label}
                  </label>
                  {spec.live_updatable && isChannelRunning && (
                    <span className="live-tag">LIVE</span>
                  )}
                </div>
                <input
                  id={fieldId}
                  type="number"
                  className="form-input"
                  value={Number(val)}
                  min={spec.min ?? undefined}
                  max={spec.max ?? undefined}
                  step={spec.step ?? (spec.type === "integer" ? 1 : 0.05)}
                  onChange={(e) => {
                    const parsed =
                      spec.type === "integer"
                        ? parseInt(e.target.value, 10)
                        : parseFloat(e.target.value);
                    if (!Number.isNaN(parsed)) {
                      onChangeParam(
                        selectedNode.id,
                        spec.name,
                        parsed,
                        spec.live_updatable
                      );
                    }
                  }}
                />
                {spec.description && (
                  <span className="form-help">{spec.description}</span>
                )}
              </div>
            );
          }

          return (
            <div key={spec.name} className="form-field">
              <div className="form-label-row">
                <label className="form-label" htmlFor={fieldId}>
                  {spec.label}
                </label>
                {spec.live_updatable && isChannelRunning && (
                  <span className="live-tag">LIVE</span>
                )}
              </div>
              <input
                id={fieldId}
                type="text"
                className="form-input"
                value={String(val ?? "")}
                placeholder={spec.placeholder ?? ""}
                onChange={(e) =>
                  onChangeParam(
                    selectedNode.id,
                    spec.name,
                    e.target.value,
                    spec.live_updatable
                  )
                }
              />
              {spec.description && (
                <span className="form-help">{spec.description}</span>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
};
