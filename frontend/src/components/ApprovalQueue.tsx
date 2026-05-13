import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { PrApproval } from "../types/events";
import { Card, SectionHeader } from "./ui/Card";

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
    <div className="border border-amber-600/50 bg-amber-950/30 rounded-xl p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div className="space-y-0.5">
          <p className="text-amber-300 text-xs font-mono font-semibold uppercase tracking-widest">
            {t("approvalQueue.awaitingReview")}
          </p>
          <p className="text-neutral-100 text-sm font-mono">
            {t("approvalQueue.plan")}{" "}
            <span className="text-amber-400">{approval.plan_id.slice(0, 8)}</span>
          </p>
        </div>
        <span className="bg-amber-500/20 text-amber-300 text-xs font-mono px-2 py-0.5 rounded-full border border-amber-600/40 whitespace-nowrap">
          {t("approvalQueue.files", { count: approval.files_count })}
        </span>
      </div>

      <div className="flex items-center gap-2 text-xs font-mono text-neutral-400">
        <span className="text-neutral-600">{t("approvalQueue.branch")}</span>
        <span className="text-neutral-200">{approval.branch_name}</span>
      </div>

      {approval.security_reasoning && (
        <div className="text-xs font-mono">
          <button
            onClick={() => setReasoningOpen((v) => !v)}
            className="flex items-center gap-1.5 text-neutral-400 hover:text-neutral-200 transition-colors"
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
            <p className="mt-2 text-neutral-300 leading-relaxed pl-4 border-l border-neutral-800">
              {approval.security_reasoning}
            </p>
          )}
        </div>
      )}

      <div className="flex gap-2 pt-1">
        <button
          onClick={() => handle("approve")}
          disabled={loading !== null}
          className="flex-1 bg-emerald-500 hover:bg-emerald-400 disabled:bg-neutral-800 disabled:text-neutral-500 text-black text-xs font-mono rounded-lg px-3 py-2 transition-colors"
        >
          {loading === "approve"
            ? t("approvalQueue.approving")
            : t("approvalQueue.approveMerge")}
        </button>
        <button
          onClick={() => handle("reject")}
          disabled={loading !== null}
          className="flex-1 bg-red-900/60 hover:bg-red-800/80 disabled:bg-neutral-800 disabled:text-neutral-500 text-red-300 text-xs font-mono rounded-lg px-3 py-2 transition-colors border border-red-700/50"
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
            <span className="bg-amber-500 text-black text-xs font-mono rounded-full px-2 py-0.5 leading-none">
              {approvals.length}
            </span>
          )
        }
      >
        {t("approvalQueue.title")}
      </SectionHeader>

      {approvals.length === 0 ? (
        <p className="text-neutral-600 text-xs font-mono text-center py-4">
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
