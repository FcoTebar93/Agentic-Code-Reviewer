import type { TFunction } from "i18next";

export const UI_LANGUAGE_STORAGE_KEY = "admadc.ui-language";
export const UI_LANGUAGES = ["es", "en"] as const;
export type UiLanguage = (typeof UI_LANGUAGES)[number];

export const AGENT_LOCALE_VALUES = [
  "auto",
  "en",
  "es",
  "fr",
  "de",
  "pt",
  "it",
] as const;

export type AgentLocaleChoice = (typeof AGENT_LOCALE_VALUES)[number];

const AGENT_PRIMARY = new Set([
  "en",
  "es",
  "fr",
  "de",
  "pt",
  "it",
  "ja",
  "zh",
  "ko",
]);

export function normalizeUiLanguage(raw: string | null | undefined): UiLanguage {
  const value = String(raw ?? "").trim().toLowerCase().split("-", 1)[0];
  return value === "en" ? "en" : "es";
}

export function getStoredUiLanguage(): UiLanguage | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(UI_LANGUAGE_STORAGE_KEY);
  return raw ? normalizeUiLanguage(raw) : null;
}

export function persistUiLanguage(language: UiLanguage): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, language);
}

export function getInitialUiLanguage(): UiLanguage {
  const stored = getStoredUiLanguage();
  if (stored) return stored;
  if (typeof navigator === "undefined") return "es";
  return normalizeUiLanguage(navigator.language);
}

export function normalizeAgentLocale(raw: string | null | undefined): string {
  const value = String(raw ?? "").trim().toLowerCase().replace("_", "-");
  const primary = value.split("-", 1)[0];
  if (AGENT_PRIMARY.has(primary)) return primary;
  return "en";
}

export function resolveAgentLocale(
  choice: string,
  currentUiLanguage: string,
): string {
  if (choice === "auto") {
    return normalizeAgentLocale(currentUiLanguage);
  }
  return normalizeAgentLocale(choice);
}

export function getAgentLocaleOptions(
  t: TFunction<"common">,
): Array<{ value: AgentLocaleChoice; label: string }> {
  return [
    {
      value: "auto",
      label: t("planForm.autoResponseLanguage"),
    },
    {
      value: "en",
      label: t("languages.english"),
    },
    {
      value: "es",
      label: t("languages.spanish"),
    },
    {
      value: "fr",
      label: t("languages.french"),
    },
    {
      value: "de",
      label: t("languages.german"),
    },
    {
      value: "pt",
      label: t("languages.portuguese"),
    },
    {
      value: "it",
      label: t("languages.italian"),
    },
  ];
}
