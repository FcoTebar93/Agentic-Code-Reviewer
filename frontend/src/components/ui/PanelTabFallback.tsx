import { useTranslation } from "react-i18next";

export function PanelTabFallback() {
  const { t } = useTranslation();

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900/50 px-4 py-10 text-center text-[11px] font-mono text-neutral-500 animate-pulse">
      {t("fallback.loading")}
    </div>
  );
}
