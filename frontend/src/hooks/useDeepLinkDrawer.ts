import { useEffect, useLayoutEffect, useRef } from "react";

export function useDeepLinkDrawer(isNarrowViewport: boolean, setDrawerOpen: (open: boolean) => void): void {
  const searchOnMount = useRef<string | null>(null);
  const handled = useRef(false);

  useLayoutEffect(() => {
    searchOnMount.current =
      typeof window !== "undefined" ? window.location.search : null;
  }, []);

  useEffect(() => {
    if (!isNarrowViewport || handled.current) return;
    const q = searchOnMount.current ?? "";
    const params = new URLSearchParams(q);
    const tab = params.get("tab");
    const plan = params.get("plan")?.trim();
    const tabImpliesPanel = tab != null && tab !== "" && tab !== "launch";
    if (tabImpliesPanel || Boolean(plan)) {
      setDrawerOpen(true);
      handled.current = true;
    }
  }, [isNarrowViewport, setDrawerOpen]);
}
