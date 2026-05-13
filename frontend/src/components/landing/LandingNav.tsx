import { Link } from "react-router-dom";

const navItems = [
  { href: "#capacidades", label: "Capacidades" },
  { href: "#pipeline", label: "Pipeline" },
  { href: "#observabilidad", label: "Observabilidad" },
];

export function LandingNav() {
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
          <a href="#pipeline" className="landing-button-ghost hidden sm:inline-flex">
            Ver arquitectura
          </a>
          <Link to="/app" className="landing-button-primary">
            Entrar al sistema
          </Link>
        </div>
      </div>
    </header>
  );
}
