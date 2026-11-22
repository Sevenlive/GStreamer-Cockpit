import React from "react";
import type { ConnectorCategory, ConnectorDefinition } from "../types";

interface ConnectorPaletteProps {
  connectors: ConnectorDefinition[];
  onAddConnector: (def: ConnectorDefinition) => void;
}

const SECTIONS: { category: ConnectorCategory; title: string }[] = [
  { category: "input", title: "Input Connectors" },
  { category: "transform", title: "Transform Connectors" },
  { category: "output", title: "Output Connectors" },
];

export const ConnectorPalette: React.FC<ConnectorPaletteProps> = ({
  connectors,
  onAddConnector,
}) => {
  return (
    <aside className="palette-sidebar" aria-label="Connector Library">
      {SECTIONS.map((sec) => {
        const items = connectors.filter((c) => c.category === sec.category);
        return (
          <div key={sec.category}>
            <div className="sidebar-section-header">{sec.title}</div>
            <div className="palette-list">
              {items.map((def) => (
                <button
                  key={def.type}
                  type="button"
                  className="palette-item"
                  onClick={() => onAddConnector(def)}
                  title={`${def.description} (Click to add to canvas)`}
                >
                  <span className={`palette-accent ${def.category}`} />
                  <div>
                    <div className="palette-item-title">{def.label}</div>
                    <div className="palette-item-sub">
                      {def.gst_elements.slice(0, 2).join(" ! ")}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </aside>
  );
};
