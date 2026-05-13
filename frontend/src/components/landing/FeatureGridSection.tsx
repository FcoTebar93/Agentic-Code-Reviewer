import { LandingSection } from "./LandingSection";

const features = [
  {
    title: "Planificación desde prompts",
    description:
      "El Meta Planner traduce peticiones de alto nivel en planes ejecutables, tareas y contexto de archivos con memoria del sistema.",
    badge: "Meta Planner",
  },
  {
    title: "Especificación y desarrollo coordinados",
    description:
      "Spec Service y Dev Service colaboran para producir cambios concretos, reutilizando búsqueda en repo, lectura de archivos y herramientas de calidad.",
    badge: "Spec + Dev",
  },
  {
    title: "Quality gate determinista",
    description:
      "QA combina linters, revisiones estructuradas y reintentos controlados antes de que un cambio llegue al siguiente tramo del pipeline.",
    badge: "QA Gate",
  },
  {
    title: "Security gate previo al merge",
    description:
      "Security Service bloquea o aprueba PRs en función de reglas, patrones y escaneos configurables antes de solicitar aprobación humana.",
    badge: "Security",
  },
  {
    title: "HITL sin fricción",
    description:
      "Las aprobaciones pendientes llegan al gateway y al frontend para que la decisión humana ocurra dentro del flujo, sin pasos externos.",
    badge: "Human in the loop",
  },
  {
    title: "Materialización directa en GitHub",
    description:
      "Tras la aprobación final, el servicio de GitHub crea rama, commit y PR o deja los cambios listos en un workspace local para revisión.",
    badge: "GitHub Service",
  },
];

export function FeatureGridSection() {
  return (
    <LandingSection
      id="capacidades"
      eyebrow="Capacidades"
      title="Todo el ciclo de entrega, conectado en un solo tablero."
      description="La landing resume lo que ya existe en ADMADC: una plataforma donde la ejecución multiagente no es una demo aislada, sino un pipeline gobernado por memoria, eventos, validaciones y decisiones humanas."
    >
      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {features.map((feature) => (
          <article key={feature.title} className="landing-card h-full">
            <span className="landing-badge-secondary">{feature.badge}</span>
            <h3 className="mt-5 text-2xl font-bold leading-tight text-[var(--color-polar-white)]">
              {feature.title}
            </h3>
            <p className="mt-4 text-sm leading-7 text-[var(--color-silver-text)]/76">
              {feature.description}
            </p>
          </article>
        ))}
      </div>
    </LandingSection>
  );
}
