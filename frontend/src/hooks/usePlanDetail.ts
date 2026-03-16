import { useEffect, useState } from "react";
import type { PlanDetail } from "../types/planDetail";

interface UsePlanDetailResult {
  data: PlanDetail | null;
  loading: boolean;
  error: string | null;
}

const HTTP_BASE =
  import.meta.env.VITE_GATEWAY_HTTP_URL ?? "http://localhost:8080";

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

    fetch(`${HTTP_BASE}/api/plan_detail/${encodeURIComponent(planId)}`)
      .then((resp) => {
        if (!resp.ok) {
          return resp
            .json()
            .catch(() => ({}))
            .then((body) => {
              const msg =
                (body && typeof body.error === "string" && body.error) ||
                `HTTP ${resp.status}`;
              throw new Error(msg);
            });
        }
        return resp.json() as Promise<PlanDetail>;
      })
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

