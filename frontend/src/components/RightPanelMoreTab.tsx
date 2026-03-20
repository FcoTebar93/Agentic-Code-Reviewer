import { Card, SectionHeader } from "./ui/Card";
import { StatRow } from "./ui/StatRow";
import type { BaseEvent } from "../types/events";

type Props = {
  visibleEventsCount: number;
  pendingApprovalsCount: number;
  activePlanMode: string | null;
  latestEvent: BaseEvent | null;
};

export function RightPanelMoreTab({ visibleEventsCount, pendingApprovalsCount, activePlanMode, latestEvent }: Props) {
  return (
    <>
      <Card>
        <SectionHeader>Atajos de teclado</SectionHeader>
        <ul className="text-[11px] font-mono text-neutral-400 space-y-1.5 leading-relaxed">
          <li>
            <span className="text-neutral-500">Alt+1 / Alt+2</span> — Pipeline /
            Eventos
          </li>
          <li>
            <span className="text-neutral-500">Alt+3 … Alt+7</span> — Lanzar,
            Métricas, Detalle, Aprobaciones, Más
          </li>
          <li className="text-neutral-600 text-[10px] pt-1">
            En móvil, Alt+3–7 abre el panel; Opción = Alt (macOS).
          </li>
        </ul>
      </Card>

      <Card>
        <SectionHeader>Stats</SectionHeader>
        <dl className="space-y-2">
          <StatRow label="Total events" value={visibleEventsCount} />
          <StatRow
            label="Pending approvals"
            value={
              <span
                className={
                  pendingApprovalsCount > 0
                    ? "text-amber-400"
                    : "text-neutral-200"
                }
              >
                {pendingApprovalsCount}
              </span>
            }
          />
          {activePlanMode && (
            <StatRow
              label="Active plan mode"
              value={
                <span
                  className={
                    activePlanMode === "save" || activePlanMode === "ahorro"
                      ? "text-emerald-400"
                      : "text-neutral-300"
                  }
                >
                  {activePlanMode === "ahorro" ? "save" : activePlanMode}
                </span>
              }
            />
          )}
          <StatRow
            label="Last event"
            value={
              <span className="text-neutral-200 truncate max-w-[180px] inline-block">
                {latestEvent?.event_type ?? "—"}
              </span>
            }
          />
          <StatRow label="Producer" value={latestEvent?.producer ?? "—"} />
        </dl>
      </Card>

      <Card>
        <SectionHeader>Quick Links</SectionHeader>
        <div className="space-y-1.5">
          {[
            { label: "Grafana", url: "http://localhost:3000" },
            { label: "Prometheus", url: "http://localhost:9090" },
            { label: "RabbitMQ UI", url: "http://localhost:15672" },
            { label: "Gateway API", url: "http://localhost:8080/docs" },
            {
              label: "Pending Approvals API",
              url: "http://localhost:8080/api/approvals",
            },
          ].map(({ label, url }) => (
            <a
              key={label}
              href={url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center justify-between text-xs font-mono text-neutral-400 hover:text-white transition-colors"
            >
              <span>{label}</span>
              <span className="text-neutral-600">↗</span>
            </a>
          ))}
        </div>
      </Card>
    </>
  );
}
