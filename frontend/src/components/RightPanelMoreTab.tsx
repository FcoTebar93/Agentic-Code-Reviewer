import { Card, SectionHeader } from "./ui/Card";
import { StatRow } from "./ui/StatRow";
import type { BaseEvent } from "../types/events";
import { useTranslation } from "react-i18next";
import { translateEventType, translateGenericStatus } from "../i18n/formatters";
import { APP_META_TEXT } from "./ui/theme";

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
        <ul className="space-y-1.5 text-[11px] font-mono leading-relaxed text-[var(--color-silver-text)]/78">
          <li>
            {t("moreTab.shortcutLine1")}
          </li>
          <li>
            {t("moreTab.shortcutLine2")}
          </li>
          <li className={`${APP_META_TEXT} pt-1 text-[10px]`}>
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
                    ? "text-[var(--color-warning-yellow)]"
                    : "text-[var(--color-polar-white)]"
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
                      ? "text-[var(--color-system-green)]"
                      : "text-[var(--color-polar-white)]"
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
              <span className="inline-block max-w-[180px] truncate text-[var(--color-polar-white)]">
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
              className="app-surface-soft flex items-center justify-between px-3 py-2 text-xs font-mono text-[var(--color-silver-text)]/78 transition-colors hover:text-[var(--color-polar-white)]"
            >
              <span>{label}</span>
              <span className="app-muted-text">↗</span>
            </a>
          ))}
        </div>
      </Card>
    </>
  );
}
