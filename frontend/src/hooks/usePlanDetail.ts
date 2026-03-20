import { useEffect, useState } from "react";
import { getJson } from "../api/gatewayClient";
import type { PlanDetail } from "../types/planDetail";

interface UsePlanDetailResult {
  data: PlanDetail | null;
  loading: boolean;
  error: string | null;
}

export function usePlanDetail(planId: string | null): UsePlanDetailResult {
  const [data, setData] = useState<PlanDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!planId) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    getJson<PlanDetail>(
      `/api/plan_detail/${encodeURIComponent(planId)}`,
    )
      .then((json) => {
        if (!cancelled) {
          setData(json);
          setError(null);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
          setData(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [planId]);

  return { data, loading, error };
}

