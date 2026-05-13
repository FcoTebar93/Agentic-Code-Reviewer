import React from "react";
import { useTranslation } from "react-i18next";
import { getDashboardHref } from "../hooks/useDashboardUrlSync";
import type { MainWorkspaceSectionId } from "./ui/MainWorkspaceNav";
import type { RightPanelTabId } from "./ui/RightPanelTabs";
import { translateGenericStatus } from "../i18n/formatters";
import {
  APP_BUTTON_SECONDARY,
  APP_BUTTON_SUBTLE,
  APP_EMPTY_STATE,
  cx,
} from "./ui/theme";

type Props = {
  planId: string | null;
  mode: string | null;
  rightTab: RightPanelTabId;
  mainSection: MainWorkspaceSectionId;
  onClear?: () => void;
};

export function ActivePlanBar({
  planId,
  mode,
  rightTab,
  mainSection,
  onClear,
}: Props) {
  const { t } = useTranslation();
  const [copied, setCopied] = React.useState<"id" | "link" | null>(null);

  if (!planId) {
    return (
      <div className={`${APP_EMPTY_STATE} px-3 py-2 text-[11px] text-left`}>
        {t("activePlan.empty")}
      </div>
    );
  }

  const id = planId;
  const short = `${id.slice(0, 8)}…`;
  const displayMode =
    mode === "ahorro" ? "save" : mode ?? "—";

  async function copyId() {
    try {
      await navigator.clipboard.writeText(id);
      setCopied("id");
      setTimeout(() => setCopied(null), 2000);
    } catch {
      setCopied(null);
    }
  }

  async function copyLink() {
    try {
      const path = getDashboardHref(id, rightTab, mainSection);
      const absolute = new URL(path, window.location.origin).href;
      await navigator.clipboard.writeText(absolute);
      setCopied("link");
      setTimeout(() => setCopied(null), 2000);
    } catch {
      setCopied(null);
    }
  }

  return (
    <div className="app-surface-soft flex flex-wrap items-center gap-2 px-3 py-2 text-[11px]">
      <span className="app-section-title text-[10px]">
        {t("activePlan.active")}
      </span>
      <span
        className="max-w-[200px] truncate font-mono text-[var(--color-polar-white)]"
        title={id}
      >
        {short}
      </span>
      <span className="app-muted-text">·</span>
      <span className="app-meta-text">
        {t("activePlan.mode", {
          mode: translateGenericStatus(t, displayMode),
        })}
      </span>
      <div className="flex flex-wrap gap-1.5 ml-auto">
        <button
          type="button"
          onClick={copyId}
          className={cx(APP_BUTTON_SECONDARY, "min-h-0 px-2.5 py-1 text-[10px]")}
        >
          {copied === "id" ? t("activePlan.copied") : t("activePlan.copyId")}
        </button>
        <button
          type="button"
          onClick={copyLink}
          className={cx(APP_BUTTON_SECONDARY, "min-h-0 px-2.5 py-1 text-[10px]")}
        >
          {copied === "link"
            ? t("activePlan.linkCopied")
            : t("activePlan.copyLink")}
        </button>
        {onClear && (
          <button
            type="button"
            onClick={onClear}
            className={cx(APP_BUTTON_SUBTLE, "min-h-0 px-2.5 py-1 text-[10px]")}
          >
            {t("activePlan.clearFilter")}
          </button>
        )}
      </div>
    </div>
  );
}
