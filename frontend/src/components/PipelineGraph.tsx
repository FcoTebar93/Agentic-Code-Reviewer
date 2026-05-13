import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ServiceNode } from "./ServiceNode";
import type { BaseEvent } from "../types/events";
import { PRODUCER_FOR_EVENT } from "../types/events";
import { Card, SectionHeader } from "./ui/Card";
import { APP_META_TEXT } from "./ui/theme";

interface Props {
  latestEvent: BaseEvent | null;
}

const SERVICES = [
  { id: "meta_planner", label: "Planner" },
  { id: "spec_service", label: "Spec" },
  { id: "dev_service", label: "Dev" },
  { id: "qa_service", label: "QA" },
  { id: "security_service", label: "Security" },
  { id: "github_service", label: "GitHub" },
];

const SERVICE_COLORS: Record<string, string> = {
  meta_planner: "#c084fc",
  spec_service: "#34d399",
  dev_service: "#f472b6",
  qa_service: "#22d3ee",
  security_service: "#a855f7",
  github_service: "#fcd34d",
};

function getServiceColor(serviceId: string): string {
  return SERVICE_COLORS[serviceId] ?? "#6366f1";
}

const SVG_H = 140;
const NODE_Y = SVG_H / 2;
const PADDING = 80;
const NODE_SPACING = 170;
const SVG_W = PADDING * 2 + NODE_SPACING * (SERVICES.length - 1);

const NODE_POSITIONS = SERVICES.map((s, i) => ({
  ...s,
  x: PADDING + i * NODE_SPACING,
  y: NODE_Y,
}));

const ACTIVE_MS = 1200;

export function PipelineGraph({ latestEvent }: Props) {
  const { t } = useTranslation();
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
    <Card className="shadow-lg shadow-black/30">
      <SectionHeader
        right={<span className={APP_META_TEXT}>{t("workspace.pipeline.hint")}</span>}
      >
        {t("dashboard.pipelineGraph")}
      </SectionHeader>
      <svg
        viewBox={`0 0 ${SVG_W} ${SVG_H}`}
        width="100%"
        height={SVG_H}
        className="overflow-visible"
      >
        {NODE_POSITIONS.slice(0, -1).map((node, i) => {
          const next = NODE_POSITIONS[i + 1];
          const isActive =
            activeService === node.id || activeService === next.id;
          const edgeColor = activeService
            ? getServiceColor(activeService)
            : "#6366f1";
          return (
            <line
              key={`edge-${i}`}
              x1={node.x + 70}
              y1={NODE_Y}
              x2={next.x - 70}
              y2={NODE_Y}
              stroke={isActive ? edgeColor : "#334155"}
              strokeWidth={isActive ? 2 : 1}
              strokeDasharray={isActive ? "0" : "4 3"}
              style={{ transition: "stroke 0.4s ease, stroke-width 0.4s ease" }}
            />
          );
        })}

        {NODE_POSITIONS.slice(0, -1).map((node, i) => {
          const next = NODE_POSITIONS[i + 1];
          const isActive =
            activeService === node.id || activeService === next.id;
          const edgeColor = activeService
            ? getServiceColor(activeService)
            : "#6366f1";
          const arrowX = next.x - 70;
          return (
            <polygon
              key={`arrow-${i}`}
              points={`${arrowX},${NODE_Y - 5} ${arrowX + 8},${NODE_Y} ${arrowX},${NODE_Y + 5}`}
              fill={isActive ? edgeColor : "#334155"}
              style={{ transition: "fill 0.4s ease" }}
            />
          );
        })}

        {NODE_POSITIONS.map((node) => (
          <ServiceNode
            key={node.id}
            serviceId={node.id}
            label={node.label}
            x={node.x}
            y={node.y}
            active={activeService === node.id}
            activeColor={getServiceColor(node.id)}
          />
        ))}
      </svg>
    </Card>
  );
}
