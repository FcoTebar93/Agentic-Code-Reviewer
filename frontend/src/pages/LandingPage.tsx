import { CtaSection } from "../components/landing/CtaSection";
import { FeatureGridSection } from "../components/landing/FeatureGridSection";
import { HeroSection } from "../components/landing/HeroSection";
import { LandingNav } from "../components/landing/LandingNav";
import { ObservabilitySection } from "../components/landing/ObservabilitySection";
import { PipelineSection } from "../components/landing/PipelineSection";

export function LandingPage() {
  return (
    <div id="top" className="landing-page min-h-dvh">
      <div className="landing-background-glow" aria-hidden />
      <LandingNav />
      <main className="relative">
        <HeroSection />
        <FeatureGridSection />
        <PipelineSection />
        <ObservabilitySection />
        <CtaSection />
      </main>
    </div>
  );
}
