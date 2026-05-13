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
  serviceId,
  x,
  y,
  active,
  activeColor = "#6366f1",
  width = NODE_W,
  height = NODE_H,
}: ServiceNodeProps) {
  return (
    <g data-service-id={serviceId}>
      <rect
        x={x - width / 2}
        y={y - height / 2}
        width={width}
        height={height}
        rx={8}
        ry={8}
        fill={active ? _mix(activeColor, "#14151a", 0.78) : "#14151a"}
        stroke={active ? _lighten(activeColor, 1.2) : "#3a3a3f"}
        strokeWidth={active ? 2 : 1}
        style={{
          transition: "fill 0.4s ease, stroke 0.4s ease",
          filter: active ? `drop-shadow(0 0 10px ${_mix(activeColor, "#ffffff", 0.2)})` : "none",
        }}
      />
      <text
        x={x}
        y={y + 1}
        textAnchor="middle"
        dominantBaseline="middle"
        fill={active ? "#ffffff" : "#e5e7eb"}
        fontSize={11}
        fontFamily="JetBrains Mono, ui-monospace, monospace"
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

function _mix(primaryHex: string, secondaryHex: string, alpha: number): string {
  const n1 = parseInt(primaryHex.slice(1), 16);
  const n2 = parseInt(secondaryHex.slice(1), 16);
  const r = Math.round((((n1 >> 16) & 0xff) * alpha) + (((n2 >> 16) & 0xff) * (1 - alpha)));
  const g = Math.round((((n1 >> 8) & 0xff) * alpha) + (((n2 >> 8) & 0xff) * (1 - alpha)));
  const b = Math.round(((n1 & 0xff) * alpha) + ((n2 & 0xff) * (1 - alpha)));
  return `#${(r << 16 | g << 8 | b).toString(16).padStart(6, "0")}`;
}