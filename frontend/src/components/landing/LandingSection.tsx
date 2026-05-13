import type { ReactNode } from "react";

interface LandingSectionProps {
  id?: string;
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
}

export function LandingSection({
  id,
  eyebrow,
  title,
  description,
  children,
}: LandingSectionProps) {
  return (
    <section id={id} className="landing-section">
      <div className="mx-auto flex max-w-[1280px] flex-col gap-10 px-6 lg:px-8">
        <div className="max-w-3xl space-y-4">
          <span className="landing-badge">{eyebrow}</span>
          <div className="space-y-4">
            <h2 className="text-3xl font-extrabold leading-tight text-[var(--color-polar-white)] md:text-5xl">
              {title}
            </h2>
            <p className="max-w-2xl text-base leading-7 text-[var(--color-silver-text)]/78 md:text-lg">
              {description}
            </p>
          </div>
        </div>
        {children}
      </div>
    </section>
  );
}
