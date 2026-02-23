interface ServiceNodeProps {
  label: string;
  serviceId: string;
  x: number;
  y: number;
  active: boolean;
  width?: number;
  height?: number;
}

const NODE_W = 130;
const NODE_H = 44;

export function ServiceNode({
  label,
  serviceId: _serviceId,
  x,
  y,
  active,
  width = NODE_W,
  height = NODE_H,
}: ServiceNodeProps) {
  return (
    <g>
      <rect
        x={x - width / 2}
        y={y - height / 2}
        width={width}
        height={height}
        rx={8}
        ry={8}
        fill={active ? "#6366f1" : "#1e293b"}
        stroke={active ? "#a5b4fc" : "#334155"}
        strokeWidth={active ? 2 : 1}
        style={{
          transition: "fill 0.4s ease, stroke 0.4s ease",
          filter: active ? "drop-shadow(0 0 8px #6366f1)" : "none",
        }}
      />
      <text
        x={x}
        y={y + 1}
        textAnchor="middle"
        dominantBaseline="middle"
        fill={active ? "#e0e7ff" : "#94a3b8"}
        fontSize={11}
        fontFamily="monospace"
        style={{ transition: "fill 0.4s ease" }}
      >
        {label}
      </text>
    </g>
  );
}
