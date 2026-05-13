import { Card, SectionHeader } from "./ui/Card";
import { StatRow } from "./ui/StatRow";
import type { BaseEvent } from "../types/events";
import { useTranslation } from "react-i18next";
import { translateEventType, translateGenericStatus } from "../i18n/formatters";

type Props = {
  visibleEventsCount: number;
  pendingApprovalsCount: number;
  activePlanMode: string | null;
  latestEvent: BaseEvent | null;
};

export function RightPanelMoreTab({ visibleEventsCount, pendingApprovalsCount, activePlanMode, latestEvent }: Props) {
  const { t } = useTranslation();

  return (
    <>
      <Card>
        <SectionHeader>{t("moreTab.shortcuts")}</SectionHeader>
        <ul className="text-[11px] font-mono text-neutral-400 space-y-1.5 leading-relaxed">
          <li>
            {t("moreTab.shortcutLine1")}
          </li>
          <li>
            {t("moreTab.shortcutLine2")}
          </li>
          <li className="text-neutral-600 text-[10px] pt-1">
            {t("moreTab.shortcutHint")}
          </li>
        </ul>
      </Card>

      <Card>
        <SectionHeader>{t("moreTab.stats")}</SectionHeader>
        <dl className="space-y-2">
          <StatRow label={t("moreTab.totalEvents")} value={visibleEventsCount} />
          <StatRow
            label={t("moreTab.pendingApprovals")}
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
              label={t("moreTab.activePlanMode")}
              value={
                <span
                  className={
                    activePlanMode === "save" || activePlanMode === "ahorro"
                      ? "text-emerald-400"
                      : "text-neutral-300"
                  }
                >
                  {translateGenericStatus(
                    t,
                    activePlanMode === "ahorro" ? "save" : activePlanMode,
                  )}
                </span>
              }
            />
          )}
          <StatRow
            label={t("moreTab.lastEvent")}
            value={
              <span className="text-neutral-200 truncate max-w-[180px] inline-block">
                {latestEvent
                  ? translateEventType(t, latestEvent.event_type)
                  : "—"}
              </span>
            }
          />
          <StatRow
            label={t("moreTab.producer")}
            value={latestEvent?.producer ?? "—"}
          />
        </dl>
      </Card>

      <Card>
        <SectionHeader>{t("moreTab.quickLinks")}</SectionHeader>
        <div className="space-y-1.5">
          {[
            { label: "Grafana", url: "http://localhost:3000" },
            { label: t("moreTab.grafanaSlis"), url: "http://localhost:3000/d/admadc-slis" },
            { label: "Prometheus", url: "http://localhost:9090" },
            { label: "Alertmanager", url: "http://localhost:9093" },
            { label: "Loki", url: "http://localhost:3100/ready" },
            { label: t("moreTab.rabbitMqUi"), url: "http://localhost:15672" },
            { label: t("moreTab.gatewayApi"), url: "http://localhost:8080/docs" },
            {
              label: t("moreTab.pendingApprovalsApi"),
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
