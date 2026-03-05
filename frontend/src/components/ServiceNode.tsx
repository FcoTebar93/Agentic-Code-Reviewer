interface ServiceNodeProps {
  label: string;
  serviceId: string;
  x: number;
  y: number;
  active: boolean;
  activeColor?: string;
  width?: number;
  height?: number;
}

const NODE_W = 110;
const NODE_H = 44;

export function ServiceNode({
  label,
  serviceId: _serviceId,
  x,
  y,
  active,
  activeColor = "#6366f1",
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
        fill={active ? activeColor : "#020617"}
        stroke={active ? _lighten(activeColor, 1.35) : "#27272a"}
        strokeWidth={active ? 2 : 1}
        style={{
          transition: "fill 0.4s ease, stroke 0.4s ease",
          filter: active ? `drop-shadow(0 0 8px ${activeColor})` : "none",
        }}
      />
      <text
        x={x}
        y={y + 1}
        textAnchor="middle"
        dominantBaseline="middle"
        fill={active ? "#f8fafc" : "#94a3b8"}
        fontSize={11}
        fontFamily="monospace"
        style={{ transition: "fill 0.4s ease" }}
      >
        {label}
      </text>
    </g>
  );
}

function _lighten(hex: string, factor: number): string {
  const n = parseInt(hex.slice(1), 16);
  const r = Math.min(255, Math.round(((n >> 16) & 0xff) * factor));
  const g = Math.min(255, Math.round(((n >> 8) & 0xff) * factor));
  const b = Math.min(255, Math.round((n & 0xff) * factor));
  return `#${(r << 16 | g << 8 | b).toString(16).padStart(6, "0")}`;
}