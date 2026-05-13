import { useTranslation } from "react-i18next";
import type { UiLanguage } from "../../i18n/locale";

const LANGUAGES: Array<{ value: UiLanguage; flag: string }> = [
  { value: "es", flag: "🇪🇸" },
  { value: "en", flag: "🇬🇧" },
];

export function LanguageSwitcher() {
  const { i18n, t } = useTranslation();
  const current = (i18n.resolvedLanguage === "en" ? "en" : "es") as UiLanguage;

  return (
    <div
      className="inline-flex items-center gap-1 rounded-full border border-[var(--color-slate-border)] bg-[rgba(20,21,26,0.72)] p-1"
      aria-label={t("languageSwitcher.ariaLabel")}
      role="group"
    >
      {LANGUAGES.map(({ value, flag }) => {
        const active = current === value;
        return (
          <button
            key={value}
            type="button"
            onClick={() => void i18n.changeLanguage(value)}
            aria-pressed={active}
            title={t(`languageSwitcher.${value}`)}
            className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-mono transition-colors ${
              active
                ? "bg-[var(--color-magenta-glow)] text-[var(--color-polar-white)]"
                : "text-[var(--color-silver-text)] hover:bg-[var(--color-charcoal-canvas)]"
            }`}
          >
            <span aria-hidden>{flag}</span>
            <span>{value.toUpperCase()}</span>
          </button>
        );
      })}
    </div>
  );
}
