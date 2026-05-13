import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import { getInitialUiLanguage, normalizeUiLanguage, persistUiLanguage } from "./locale";
import { resources } from "./resources";

void i18n.use(initReactI18next).init({
  resources,
  lng: getInitialUiLanguage(),
  fallbackLng: "es",
  defaultNS: "common",
  ns: ["common"],
  interpolation: {
    escapeValue: false,
  },
  returnObjects: true,
});

if (typeof document !== "undefined") {
  document.documentElement.lang = normalizeUiLanguage(i18n.resolvedLanguage);
}

i18n.on("languageChanged", (language) => {
  const normalized = normalizeUiLanguage(language);
  persistUiLanguage(normalized);
  if (typeof document !== "undefined") {
    document.documentElement.lang = normalized;
  }
});

export default i18n;
