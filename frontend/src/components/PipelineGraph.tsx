import { useEffect, useState } from "react";
import { ServiceNode } from "./ServiceNode";
import type { BaseEvent } from "../types/events";
import { PRODUCER_FOR_EVENT } from "../types/events";

interface Props {
  latestEvent: BaseEvent | null;
}

const SERVICES = [
  { id: "meta_planner", label: "meta_planner" },
  { id: "dev_service", label: "dev_service" },
  { id: "qa_service", label: "qa_service" },
  { id: "security_service", label: "security" },
  { id: "github_service", label: "github" },
];

const SVG_W = 760;
const SVG_H = 140;
const NODE_Y = SVG_H / 2;
const PADDING = 80;
const STEP = (SVG_W - PADDING * 2) / (SERVICES.length - 1);

const NODE_POSITIONS = SERVICES.map((s, i) => ({
  ...s,
  x: PADDING + i * STEP,
  y: NODE_Y,
}));

const ACTIVE_MS = 1200;

export function PipelineGraph({ latestEvent }: Props) {
  const [activeService, setActiveService] = useState<string | null>(null);

  useEffect(() => {
    if (!latestEvent) return;
    const producer =
      PRODUCER_FOR_EVENT[latestEvent.event_type] ?? latestEvent.producer;
    setActiveService(producer);
    const timer = setTimeout(() => setActiveService(null), ACTIVE_MS);
    return () => clearTimeout(timer);
  }, [latestEvent]);

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-700 p-4">
      <h2 className="text-slate-400 text-xs font-mono uppercase tracking-widest mb-3">
        Agent Pipeline
      </h2>
      <svg
        viewBox={`0 0 ${SVG_W} ${SVG_H}`}
        width="100%"
        height={SVG_H}
        className="overflow-visible"
      >
        {/* Edges */}
        {NODE_POSITIONS.slice(0, -1).map((node, i) => {
          const next = NODE_POSITIONS[i + 1];
          const isActive =
            activeService === node.id || activeService === next.id;
          return (
            <line
              key={`edge-${i}`}
              x1={node.x + 65}
              y1={NODE_Y}
              x2={next.x - 65}
              y2={NODE_Y}
              stroke={isActive ? "#6366f1" : "#334155"}
              strokeWidth={isActive ? 2 : 1}
              strokeDasharray={isActive ? "0" : "4 3"}
              style={{ transition: "stroke 0.4s ease, stroke-width 0.4s ease" }}
            />
          );
        })}

        {/* Arrow heads */}
        {NODE_POSITIONS.slice(0, -1).map((node, i) => {
          const next = NODE_POSITIONS[i + 1];
          const isActive =
            activeService === node.id || activeService === next.id;
          const arrowX = next.x - 65;
          return (
            <polygon
              key={`arrow-${i}`}
              points={`${arrowX},${NODE_Y - 5} ${arrowX + 8},${NODE_Y} ${arrowX},${NODE_Y + 5}`}
              fill={isActive ? "#6366f1" : "#334155"}
              style={{ transition: "fill 0.4s ease" }}
            />
          );
        })}

        {/* Nodes */}
        {NODE_POSITIONS.map((node) => (
          <ServiceNode
            key={node.id}
            serviceId={node.id}
            label={node.label}
            x={node.x}
            y={node.y}
            active={activeService === node.id}
          />
        ))}
      </svg>
    </div>
  );
}
