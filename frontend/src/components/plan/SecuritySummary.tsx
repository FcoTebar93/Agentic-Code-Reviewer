import type { PlanDetail, SecurityOutcome } from "../../types/planDetail";
import { useTranslation } from "react-i18next";
import { translateSeverity } from "../../i18n/formatters";
import { APP_META_TEXT } from "../ui/theme";

function isSecurityOutcome(
  security: PlanDetail["security_outcome"],
): security is SecurityOutcome {
  return Object.keys(security).length > 0;
}

export function SecuritySummary({
  security,
}: {
  security: PlanDetail["security_outcome"];
}) {
  const { t } = useTranslation();
  if (!isSecurityOutcome(security)) return null;
  return (
    <div className="app-divider mt-3 border-t pt-2">
      <p className="app-section-title mb-1 text-[10px]">
        {t("securitySummary.title")}
      </p>
      <div className="space-y-1 text-xs">
        <div className="text-[var(--color-silver-text)]">
          {t("securitySummary.approved")}:{" "}
          <span className="font-medium text-[var(--color-polar-white)]">
            {security.approved ? t("values.yes") : t("values.no")}
          </span>{" "}
          · {t("securitySummary.severity")}:{" "}
          <span className="font-medium text-[var(--color-warning-yellow)]">
            {translateSeverity(t, security.severity_hint || "medium")}
          </span>
        </div>
        <div className={APP_META_TEXT}>
          {t("securitySummary.filesScanned")}: <span>{security.files_scanned}</span>
        </div>
        {security.violations && security.violations.length > 0 && (
          <ul className="ml-4 list-disc space-y-0.5 text-[10px] text-[var(--color-silver-text)]/78">
            {security.violations.slice(0, 4).map((v, idx) => (
              <li key={idx}>{v}</li>
            ))}
            {security.violations.length > 4 && (
              <li>
                {t("securitySummary.moreViolations", {
                  count: security.violations.length - 4,
                })}
              </li>
            )}
          </ul>
        )}
      </div>
    </div>
  );
}
