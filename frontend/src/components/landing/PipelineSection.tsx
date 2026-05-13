import { LandingSection } from "./LandingSection";
import { useTranslation } from "react-i18next";

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
  const { t } = useTranslation();
  const stages = t("landing.pipeline.stages", {
    returnObjects: true,
  }) as Array<{ title: string; description: string }>;

  return (
    <LandingSection
      id="pipeline"
      eyebrow={t("landing.pipeline.eyebrow")}
      title={t("landing.pipeline.title")}
      description={t("landing.pipeline.description")}
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
              {t("landing.pipeline.eventsLabel")}
            </p>
            <h3 className="mt-3 text-2xl font-bold text-[var(--color-polar-white)]">
              {t("landing.pipeline.eventsTitle")}
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
              {t("landing.pipeline.deepLinks")}
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
