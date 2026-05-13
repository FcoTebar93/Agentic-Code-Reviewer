import { APP_EMPTY_STATE } from "./theme";
import { useTranslation } from "react-i18next";

export function PanelTabFallback() {
  const { t } = useTranslation();

  return (
    <div className={`${APP_EMPTY_STATE} animate-pulse py-10`}>
      {t("fallback.loading")}
    </div>
  );
}
