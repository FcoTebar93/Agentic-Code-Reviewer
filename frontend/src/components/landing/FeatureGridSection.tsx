import { LandingSection } from "./LandingSection";
import { useTranslation } from "react-i18next";

export function FeatureGridSection() {
  const { t } = useTranslation();
  const features = t("landing.featureGrid.items", {
    returnObjects: true,
  }) as Array<{ title: string; description: string; badge: string }>;

  return (
    <LandingSection
      id="capacidades"
      eyebrow={t("landing.featureGrid.eyebrow")}
      title={t("landing.featureGrid.title")}
      description={t("landing.featureGrid.description")}
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
