import { LandingSection } from "./LandingSection";
import { useTranslation } from "react-i18next";

export function ObservabilitySection() {
  const { t } = useTranslation();
  const tools = t("landing.observability.tools", {
    returnObjects: true,
  }) as string[];
  const metrics = t("landing.observability.metrics", {
    returnObjects: true,
  }) as Array<{ label: string; value: string; width: string }>;

  return (
    <LandingSection
      id="observabilidad"
      eyebrow={t("landing.observability.eyebrow")}
      title={t("landing.observability.title")}
      description={t("landing.observability.description")}
    >
      <div className="grid gap-6 lg:grid-cols-[minmax(0,0.95fr)_minmax(420px,1.05fr)]">
        <div className="landing-card">
          <p className="text-xs uppercase tracking-[0.2em] text-[var(--color-ash-text)]">
            {t("landing.observability.connectedTools")}
          </p>
          <div className="mt-6 space-y-4">
            {tools.map((item) => (
              <div
                key={item}
                className="flex items-start gap-3 rounded-[var(--radius-default)] border border-[var(--color-slate-border)] bg-[var(--color-midnight-core)] px-4 py-4"
              >
                <span className="mt-1 h-2.5 w-2.5 rounded-full bg-[var(--color-system-green)] shadow-[var(--shadow-md)]" />
                <p className="text-sm leading-7 text-[var(--color-silver-text)]/76">
                  {item}
                </p>
              </div>
            ))}
          </div>
        </div>

        <div className="landing-card">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-[var(--color-ash-text)]">
                {t("landing.observability.summary")}
              </p>
              <h3 className="mt-3 text-2xl font-bold text-[var(--color-polar-white)]">
                {t("landing.observability.summaryTitle")}
              </h3>
            </div>
            <span className="landing-badge-secondary">
              {t("landing.observability.telemetry")}
            </span>
          </div>

          <div className="mt-8 space-y-5">
            {metrics.map((metric) => (
              <div key={metric.label} className="space-y-2">
                <div className="flex items-center justify-between gap-4 text-sm text-[var(--color-silver-text)]">
                  <span>{metric.label}</span>
                  <span className="font-[var(--font-jetbrains-mono)] text-[var(--color-polar-white)]">
                    {metric.value}
                  </span>
                </div>
                <div className="h-3 rounded-[var(--radius-md)] bg-[var(--color-midnight-core)]">
                  <div
                    className="h-3 rounded-[var(--radius-md)] bg-[linear-gradient(90deg,var(--color-cyber-pink),var(--color-neon-violet))] shadow-[var(--shadow-xl)]"
                    style={{ width: metric.width }}
                  />
                </div>
              </div>
            ))}
          </div>

          <div className="mt-8 grid gap-4 md:grid-cols-2">
            <div className="rounded-[var(--radius-default)] border border-[var(--color-slate-border)] bg-[var(--color-midnight-core)] p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-[var(--color-electric-cyan)]">
                {t("landing.observability.websocket")}
              </p>
              <p className="mt-2 font-[var(--font-jetbrains-mono)] text-sm text-[var(--color-silver-text)]/80">
                ws://localhost:8080/ws
              </p>
            </div>
            <div className="rounded-[var(--radius-default)] border border-[var(--color-slate-border)] bg-[var(--color-midnight-core)] p-4">
              <p className="text-xs uppercase tracking-[0.2em] text-[var(--color-cyber-pink)]">
                {t("landing.observability.gatewayApi")}
              </p>
              <p className="mt-2 font-[var(--font-jetbrains-mono)] text-sm text-[var(--color-silver-text)]/80">
                http://localhost:8080/api/status
              </p>
            </div>
          </div>
        </div>
      </div>
    </LandingSection>
  );
}
