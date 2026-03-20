import { useCallback, useEffect, useLayoutEffect } from "react";

export function shouldOpenDrawerFromSearch(search: string): boolean {
  const params = new URLSearchParams(search);
  const tab = params.get("tab");
  const plan = params.get("plan")?.trim();
  const tabImpliesPanel = tab != null && tab !== "" && tab !== "launch";
  return tabImpliesPanel || Boolean(plan);
}

export function useDeepLinkDrawer(isNarrowViewport: boolean,setDrawerOpen: (open: boolean) => void): void {
  const syncFromLocation = useCallback(() => {
    if (typeof window === "undefined" || !isNarrowViewport) return;
    setDrawerOpen(shouldOpenDrawerFromSearch(window.location.search));
  }, [isNarrowViewport, setDrawerOpen]);

  useLayoutEffect(() => {
    syncFromLocation();
  }, [syncFromLocation]);

  useEffect(() => {
    const onPopState = () => syncFromLocation();
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [syncFromLocation]);
}
