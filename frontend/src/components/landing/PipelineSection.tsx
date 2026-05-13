import { LandingSection } from "./LandingSection";

const stages = [
  {
    title: "1. Entrada unificada",
    description:
      "El gateway recibe prompts, expone el WebSocket y concentra la interacción entre frontend y microservicios.",
  },
  {
    title: "2. Descomposición del trabajo",
    description:
      "El planner publica planes y tareas para que cada servicio especializado ejecute su parte con contexto compartido.",
  },
  {
    title: "3. Producción de cambios",
    description:
      "Spec y Dev generan especificación, código y metadatos, actualizando el estado del plan en memoria.",
  },
  {
    title: "4. Validación y replanning",
    description:
      "QA y Security aceptan, rechazan o fuerzan nuevas iteraciones cuando aparecen fallos o riesgos de seguridad.",
  },
  {
    title: "5. Aprobación y PR",
    description:
      "Cuando el cambio supera todas las puertas, el humano aprueba desde la UI y GitHub Service materializa el resultado.",
  },
];

const events = [
  "plan.created",
  "task.assigned",
  "spec.generated",
  "code.generated",
  "qa.passed",
  "security.approved",
  "pr.pending_approval",
  "pr.created",
];

export function PipelineSection() {
  return (
    <LandingSection
      id="pipeline"
      eyebrow="Arquitectura"
      title="Pipeline observable, modular y listo para intervención humana."
      description="ADMADC no es una sola UI bonita: por debajo hay una línea de ensamblaje basada en eventos, con servicios desacoplados y un gateway que unifica estado, aprobaciones y telemetría."
    >
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(360px,0.9fr)]">
        <div className="grid gap-4 md:grid-cols-2">
          {stages.map((stage) => (
            <article key={stage.title} className="landing-card">
              <h3 className="text-lg font-semibold text-[var(--color-polar-white)]">
                {stage.title}
              </h3>
              <p className="mt-3 text-sm leading-7 text-[var(--color-silver-text)]/76">
                {stage.description}
              </p>
            </article>
          ))}
        </div>

        <div className="landing-card flex flex-col gap-5">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-[var(--color-ash-text)]">
              Flujo de eventos
            </p>
            <h3 className="mt-3 text-2xl font-bold text-[var(--color-polar-white)]">
              Cada transición deja rastro.
            </h3>
          </div>

          <div className="landing-code-block">
            {events.map((eventName, index) => (
              <div
                key={eventName}
                className="flex items-center justify-between gap-4 border-b border-white/5 py-2 last:border-b-0"
              >
                <span className="text-[var(--color-faded-rose)]">
                  {eventName}
                </span>
                <span className="text-[var(--color-electric-cyan)]">
                  0{index + 1}
                </span>
              </div>
            ))}
          </div>

          <div className="rounded-[var(--radius-default)] border border-[var(--color-slate-border)] bg-[var(--color-midnight-core)] p-4">
            <p className="text-xs uppercase tracking-[0.2em] text-[var(--color-cyber-pink)]">
              Deep links intactos
            </p>
            <p className="mt-3 font-[var(--font-jetbrains-mono)] text-sm leading-7 text-[var(--color-silver-text)]/78">
              /app?plan=plan-42&amp;tab=metrics&amp;main=pipeline
            </p>
          </div>
        </div>
      </div>
    </LandingSection>
  );
}
