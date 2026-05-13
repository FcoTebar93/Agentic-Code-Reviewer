import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

export function CtaSection() {
  const { t } = useTranslation();

  return (
    <section className="pb-24 pt-6">
      <div className="mx-auto max-w-[1280px] px-6 lg:px-8">
        <div className="overflow-hidden rounded-[var(--radius-default)] border border-[var(--color-slate-border)] bg-[linear-gradient(180deg,rgba(236,72,153,0.12),rgba(20,21,26,0.96))] p-8 shadow-[var(--shadow-xl)] md:p-10">
          <div className="flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl space-y-4">
              <span className="landing-badge-secondary">
                {t("landing.cta.badge")}
              </span>
              <h2 className="text-3xl font-extrabold leading-tight text-[var(--color-polar-white)] md:text-5xl">
                {t("landing.cta.title")}
              </h2>
              <p className="text-base leading-7 text-[var(--color-silver-text)]/78 md:text-lg">
                {t("landing.cta.description")}
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-4">
              <Link to="/app" className="landing-button-primary">
                {t("landing.nav.enterSystem")}
              </Link>
              <a href="#top" className="landing-button-ghost">
                {t("landing.cta.backToTop")}
              </a>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
