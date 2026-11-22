import React from "react";
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";

export interface DeletableEdgeData extends Record<string, unknown> {
  onDelete?: (edgeId: string) => void;
}

export type GstFlowEdge = Edge<DeletableEdgeData, "deletable">;

export const DeletableEdge: React.FC<EdgeProps<GstFlowEdge>> = ({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style,
  markerEnd,
  selected,
  data,
}) => {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const mergedStyle: React.CSSProperties = {
    ...style,
    stroke: selected ? "#ef4444" : style?.stroke,
    strokeWidth: selected ? 2.8 : style?.strokeWidth ?? 2,
  };

  return (
    <>
      <BaseEdge id={id} path={edgePath} markerEnd={markerEnd} style={mergedStyle} />
      <EdgeLabelRenderer>
        <div
          className={`edge-delete-wrap nodrag nopan ${selected ? "visible" : ""}`}
          style={{
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
          }}
        >
          <button
            type="button"
            className="edge-delete-btn"
            title="Remove connection"
            aria-label="Remove connection"
            onClick={(event) => {
              event.stopPropagation();
              data?.onDelete?.(id);
            }}
          >
            ×
          </button>
        </div>
      </EdgeLabelRenderer>
    </>
  );
};
