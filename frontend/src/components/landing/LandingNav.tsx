import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { LanguageSwitcher } from "../ui/LanguageSwitcher";

export function LandingNav() {
  const { t } = useTranslation();
  const navItems = [
    { href: "#capacidades", label: t("landing.nav.features") },
    { href: "#pipeline", label: t("landing.nav.pipeline") },
    { href: "#observabilidad", label: t("landing.nav.observability") },
  ];

  return (
    <header className="sticky top-0 z-30 border-b border-[var(--color-slate-border)]/80 bg-[rgba(13,14,17,0.82)] backdrop-blur-xl">
      <div className="mx-auto flex max-w-[1280px] items-center justify-between gap-4 px-6 py-4 lg:px-8">
        <Link
          to="/"
          className="font-[var(--font-jetbrains-mono)] text-lg font-semibold tracking-tight text-[var(--color-polar-white)]"
        >
          ADMADC
        </Link>

        <nav className="hidden items-center gap-2 md:flex">
          {navItems.map((item) => (
            <a key={item.href} href={item.href} className="landing-button-ghost">
              {item.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-3">
          <LanguageSwitcher />
          <a href="#pipeline" className="landing-button-ghost hidden sm:inline-flex">
            {t("landing.nav.architecture")}
          </a>
          <Link to="/app" className="landing-button-primary">
            {t("landing.nav.enterSystem")}
          </Link>
        </div>
      </div>
    </header>
  );
}
