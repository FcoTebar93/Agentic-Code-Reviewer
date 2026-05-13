import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { PrApproval } from "../types/events";
import { Card, SectionHeader } from "./ui/Card";
import {
  APP_BUTTON_DANGER,
  APP_BUTTON_PRIMARY,
  APP_EMPTY_STATE,
  cx,
} from "./ui/theme";

interface ApprovalQueueProps {
  approvals: PrApproval[];
  onApprove: (approvalId: string) => Promise<void>;
  onReject: (approvalId: string) => Promise<void>;
}

function ApprovalCard({
  approval,
  onApprove,
  onReject,
}: {
  approval: PrApproval;
  onApprove: (id: string) => Promise<void>;
  onReject: (id: string) => Promise<void>;
}) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState<"approve" | "reject" | null>(null);
  const [reasoningOpen, setReasoningOpen] = useState(false);

  async function handle(action: "approve" | "reject") {
    setLoading(action);
    try {
      if (action === "approve") await onApprove(approval.approval_id);
      else await onReject(approval.approval_id);
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="app-surface-soft space-y-3 border-amber-500/30 bg-[linear-gradient(180deg,rgba(252,211,77,0.08),rgba(20,21,26,0.72))] p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="space-y-0.5">
          <p className="app-section-title text-[10px] text-amber-300">
            {t("approvalQueue.awaitingReview")}
          </p>
          <p className="text-sm font-mono text-[var(--color-polar-white)]">
            {t("approvalQueue.plan")}{" "}
            <span className="text-amber-300">{approval.plan_id.slice(0, 8)}</span>
          </p>
        </div>
        <span className="app-badge whitespace-nowrap border-amber-500/40 bg-amber-500/16 text-amber-300">
          {t("approvalQueue.files", { count: approval.files_count })}
        </span>
      </div>

      <div className="flex items-center gap-2 text-xs font-mono">
        <span className="app-meta-text">{t("approvalQueue.branch")}</span>
        <span className="text-[var(--color-silver-text)]">{approval.branch_name}</span>
      </div>

      {approval.security_reasoning && (
        <div className="text-xs font-mono">
          <button
            type="button"
            onClick={() => setReasoningOpen((v) => !v)}
            className="flex items-center gap-1.5 text-[var(--color-silver-text)]/78 transition-colors hover:text-[var(--color-polar-white)]"
          >
            <span
              className="inline-block transition-transform duration-200"
              style={{ transform: reasoningOpen ? "rotate(90deg)" : "rotate(0deg)" }}
            >
              ▶
            </span>
            {t("approvalQueue.securityReasoning")}
          </button>
          {reasoningOpen && (
            <p className="mt-2 border-l border-[var(--color-warning-yellow)]/24 pl-4 leading-relaxed text-[var(--color-silver-text)]">
              {approval.security_reasoning}
            </p>
          )}
        </div>
      )}

      <div className="flex gap-2 pt-1">
        <button
          type="button"
          onClick={() => handle("approve")}
          disabled={loading !== null}
          className={cx(APP_BUTTON_PRIMARY, "flex-1 text-xs")}
        >
          {loading === "approve"
            ? t("approvalQueue.approving")
            : t("approvalQueue.approveMerge")}
        </button>
        <button
          type="button"
          onClick={() => handle("reject")}
          disabled={loading !== null}
          className={cx(APP_BUTTON_DANGER, "flex-1 text-xs")}
        >
          {loading === "reject"
            ? t("approvalQueue.rejecting")
            : t("approvalQueue.reject")}
        </button>
      </div>
    </div>
  );
}

export function ApprovalQueue({
  approvals,
  onApprove,
  onReject,
}: ApprovalQueueProps) {
  const { t } = useTranslation();
  return (
    <Card className="space-y-3">
      <SectionHeader
        right={
          approvals.length > 0 && (
            <span className="app-badge border-amber-500/40 bg-amber-500/16 text-amber-300">
              {approvals.length}
            </span>
          )
        }
      >
        {t("approvalQueue.title")}
      </SectionHeader>

      {approvals.length === 0 ? (
        <p className={`${APP_EMPTY_STATE} py-4`}>
          {t("approvalQueue.empty")}
        </p>
      ) : (
        <div className="space-y-3">
          {approvals.map((a) => (
            <ApprovalCard
              key={a.approval_id}
              approval={a}
              onApprove={onApprove}
              onReject={onReject}
            />
          ))}
        </div>
      )}
    </Card>
  );
}
