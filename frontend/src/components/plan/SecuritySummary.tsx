import type { PlanDetail, SecurityOutcome } from "../../types/planDetail";

function isSecurityOutcome(
  security: PlanDetail["security_outcome"],
): security is SecurityOutcome {
  return Object.keys(security).length > 0;
}

export function SecuritySummary({
  security,
}: {
  security: PlanDetail["security_outcome"];
}) {
  if (!isSecurityOutcome(security)) return null;
  return (
    <div className="mt-3 border-t border-neutral-800 pt-2">
      <p className="text-neutral-500 text-[10px] font-mono mb-1">
        Seguridad
      </p>
      <div className="text-xs space-y-0.5">
        <div>
          Aprobado:{" "}
          <span className="font-medium">
            {security.approved ? "sí" : "no"}
          </span>{" "}
          · severidad:{" "}
          <span className="font-medium">
            {security.severity_hint || "medium"}
          </span>
        </div>
        <div>
          Files escaneados: <span>{security.files_scanned}</span>
        </div>
        {security.violations && security.violations.length > 0 && (
          <ul className="list-disc ml-4 text-[10px] space-y-0.5">
            {security.violations.slice(0, 4).map((v, idx) => (
              <li key={idx}>{v}</li>
            ))}
            {security.violations.length > 4 && (
              <li>… {security.violations.length - 4} violaciones más.</li>
            )}
          </ul>
        )}
      </div>
    </div>
  );
}
