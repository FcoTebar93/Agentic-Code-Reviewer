import type { PlanDetail, SecurityOutcome } from "../../types/planDetail";
import { useTranslation } from "react-i18next";
import { translateSeverity } from "../../i18n/formatters";

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
    <div className="mt-3 border-t border-neutral-800 pt-2">
      <p className="text-neutral-500 text-[10px] font-mono mb-1">
        {t("securitySummary.title")}
      </p>
      <div className="text-xs space-y-0.5">
        <div>
          {t("securitySummary.approved")}:{" "}
          <span className="font-medium">
            {security.approved ? t("values.yes") : t("values.no")}
          </span>{" "}
          · {t("securitySummary.severity")}:{" "}
          <span className="font-medium">
            {translateSeverity(t, security.severity_hint || "medium")}
          </span>
        </div>
        <div>
          {t("securitySummary.filesScanned")}: <span>{security.files_scanned}</span>
        </div>
        {security.violations && security.violations.length > 0 && (
          <ul className="list-disc ml-4 text-[10px] space-y-0.5">
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
