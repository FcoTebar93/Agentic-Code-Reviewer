import { useState } from "react";
import type { PrApproval } from "../types/events";

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
    <div className="border border-orange-600/50 bg-orange-950/30 rounded-xl p-4 space-y-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="space-y-0.5">
          <p className="text-orange-300 text-xs font-mono font-semibold uppercase tracking-widest">
            Awaiting Human Review
          </p>
          <p className="text-slate-200 text-sm font-mono">
            Plan{" "}
            <span className="text-orange-400">{approval.plan_id.slice(0, 8)}</span>
          </p>
        </div>
        <span className="bg-orange-500/20 text-orange-300 text-xs font-mono px-2 py-0.5 rounded-full border border-orange-600/40 whitespace-nowrap">
          {approval.files_count} file{approval.files_count !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Branch */}
      <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
        <span className="text-slate-600">branch</span>
        <span className="text-slate-300">{approval.branch_name}</span>
      </div>

      {/* Security reasoning collapsible */}
      {approval.security_reasoning && (
        <div className="text-xs font-mono">
          <button
            onClick={() => setReasoningOpen((v) => !v)}
            className="flex items-center gap-1.5 text-slate-400 hover:text-slate-200 transition-colors"
          >
            <span
              className="inline-block transition-transform duration-200"
              style={{ transform: reasoningOpen ? "rotate(90deg)" : "rotate(0deg)" }}
            >
              ▶
            </span>
            Security reasoning
          </button>
          {reasoningOpen && (
            <p className="mt-2 text-slate-400 leading-relaxed pl-4 border-l border-slate-700">
              {approval.security_reasoning}
            </p>
          )}
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-2 pt-1">
        <button
          onClick={() => handle("approve")}
          disabled={loading !== null}
          className="flex-1 bg-emerald-700 hover:bg-emerald-600 disabled:bg-slate-700 disabled:text-slate-500 text-white text-xs font-mono rounded-lg px-3 py-2 transition-colors"
        >
          {loading === "approve" ? "Approving…" : "✓ Approve & Merge"}
        </button>
        <button
          onClick={() => handle("reject")}
          disabled={loading !== null}
          className="flex-1 bg-red-900/60 hover:bg-red-800/80 disabled:bg-slate-700 disabled:text-slate-500 text-red-300 text-xs font-mono rounded-lg px-3 py-2 transition-colors border border-red-700/50"
        >
          {loading === "reject" ? "Rejecting…" : "✗ Reject"}
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
  return (
    <div className="bg-slate-900 rounded-xl border border-slate-700 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-slate-400 text-xs font-mono uppercase tracking-widest">
          Human Approval Queue
        </h2>
        {approvals.length > 0 && (
          <span className="bg-orange-500 text-white text-xs font-mono rounded-full px-2 py-0.5 leading-none">
            {approvals.length}
          </span>
        )}
      </div>

      {approvals.length === 0 ? (
        <p className="text-slate-600 text-xs font-mono text-center py-4">
          No pending approvals
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
    </div>
  );
}
