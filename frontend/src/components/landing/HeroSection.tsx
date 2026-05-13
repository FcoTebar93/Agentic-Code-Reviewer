import { Link } from "react-router-dom";

const heroStats = [
  { label: "Servicios coordinados", value: "8" },
  { label: "Canales de entrada", value: "HTTP + WS" },
  { label: "Control humano", value: "HITL activo" },
];

export function HeroSection() {
  return (
    <section className="mx-auto grid max-w-[1280px] gap-10 px-6 pb-16 pt-12 lg:grid-cols-[minmax(0,1.2fr)_minmax(420px,0.8fr)] lg:px-8 lg:pb-24 lg:pt-20">
      <div className="flex flex-col gap-8">
        <div className="space-y-6">
          <span className="landing-badge">
            Synthwave dark lab · plataforma agéntica de Dev & QA
          </span>
          <div className="space-y-5">
            <h1 className="max-w-4xl text-5xl font-extrabold leading-[0.95] tracking-tight text-[var(--color-polar-white)] md:text-[72px]">
              Orquesta planes, código, QA y aprobaciones{" "}
              <span className="text-[var(--color-cyber-pink)]">desde un único</span>{" "}
              sistema agéntico.
            </h1>
            <p className="max-w-2xl text-lg leading-8 text-[var(--color-silver-text)]/80 md:text-xl">
              ADMADC convierte un prompt de alto nivel en un pipeline observable:
              crea planes, descompone tareas, ejecuta agentes, valida calidad y
              seguridad, y deja la decisión final en manos humanas antes de abrir
              el PR.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <Link to="/app" className="landing-button-primary">
            Entrar al sistema
          </Link>
          <a href="#capacidades" className="landing-button-ghost">
            Explorar capacidades
          </a>
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          {heroStats.map((stat) => (
            <div key={stat.label} className="landing-card">
              <p className="text-xs uppercase tracking-[0.22em] text-[var(--color-ash-text)]">
                {stat.label}
              </p>
              <p className="mt-3 text-2xl font-bold text-[var(--color-polar-white)]">
                {stat.value}
              </p>
            </div>
          ))}
        </div>
      </div>

      <div className="relative">
        <div className="relative overflow-hidden rounded-[var(--radius-default)] border border-[var(--color-slate-border)] bg-[linear-gradient(180deg,rgba(244,114,182,0.03),rgba(20,21,26,0.92))] shadow-[var(--shadow-xl)]">
          <div
            className="absolute inset-x-0 top-0 h-px"
            style={{ backgroundImage: "var(--gradient-gradient-pink-pulse)" }}
          />
          <div className="border-b border-[var(--color-slate-border)] px-5 py-4">
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-danger-red)]" />
              <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-warning-yellow)]" />
              <span className="h-2.5 w-2.5 rounded-full bg-[var(--color-system-green)]" />
              <span className="ml-3 font-[var(--font-jetbrains-mono)] text-xs text-[var(--color-silver-text)]/70">
                gateway / pipeline / approvals
              </span>
            </div>
          </div>
          <div className="space-y-5 p-5">
            <div className="landing-code-block">
              <p>
                <span className="text-[var(--color-electric-cyan)]">$</span>{" "}
                admadc plan --prompt &quot;Implementa la nueva experiencia
                pública&quot;
              </p>
              <p className="mt-3 text-[var(--color-faded-rose)]">
                plan.created
                <span className="text-[var(--color-silver-text)]">
                  {" "}
                  · task.assigned · spec.generated
                </span>
              </p>
              <p className="text-[var(--color-silver-text)]">
                code.generated · qa.passed · security.approved
              </p>
              <p className="text-[var(--color-cyber-pink)]">
                pr.pending_approval
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="rounded-[var(--radius-default)] border border-[var(--color-slate-border)] bg-[var(--color-midnight-core)] p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-[var(--color-ash-text)]">
                  Modo de operación
                </p>
                <p className="mt-3 text-xl font-semibold text-[var(--color-polar-white)]">
                  Event-driven orchestration
                </p>
                <p className="mt-2 text-sm leading-6 text-[var(--color-silver-text)]/72">
                  Gateway, planner, dev, QA y security coordinados por eventos
                  con trazabilidad de extremo a extremo.
                </p>
              </div>

              <div className="rounded-[var(--radius-default)] border border-[var(--color-slate-border)] bg-[linear-gradient(180deg,rgba(168,85,247,0.14),rgba(20,21,26,0.92))] p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-[var(--color-virtual-violet)]">
                  Intervención humana
                </p>
                <p className="mt-3 text-xl font-semibold text-[var(--color-polar-white)]">
                  Aprobación final integrada
                </p>
                <p className="mt-2 text-sm leading-6 text-[var(--color-silver-text)]/72">
                  El pipeline no ejecuta el paso final a GitHub sin revisión y
                  validación humana desde la UI.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
