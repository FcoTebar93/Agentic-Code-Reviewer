import { Link } from "react-router-dom";

export function CtaSection() {
  return (
    <section className="pb-24 pt-6">
      <div className="mx-auto max-w-[1280px] px-6 lg:px-8">
        <div className="overflow-hidden rounded-[var(--radius-default)] border border-[var(--color-slate-border)] bg-[linear-gradient(180deg,rgba(236,72,153,0.12),rgba(20,21,26,0.96))] p-8 shadow-[var(--shadow-xl)] md:p-10">
          <div className="flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl space-y-4">
              <span className="landing-badge-secondary">
                Acceso inmediato al sistema
              </span>
              <h2 className="text-3xl font-extrabold leading-tight text-[var(--color-polar-white)] md:text-5xl">
                Entra directo al sistema agéntico y empieza a operar el pipeline.
              </h2>
              <p className="text-base leading-7 text-[var(--color-silver-text)]/78 md:text-lg">
                Sin pantalla de login, sin pasos intermedios y sin romper la
                navegación profunda del dashboard. La landing vive en la raíz y
                la operación real empieza en <span className="font-[var(--font-jetbrains-mono)] text-[var(--color-faded-rose)]">/app</span>.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-4">
              <Link to="/app" className="landing-button-primary">
                Entrar al sistema
              </Link>
              <a href="#top" className="landing-button-ghost">
                Volver arriba
              </a>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
