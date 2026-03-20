import { useSyncExternalStore } from "react";

function subscribeMaxWidth1023(onChange: () => void) {
  const mq = window.matchMedia("(max-width: 1023px)");
  mq.addEventListener("change", onChange);
  return () => mq.removeEventListener("change", onChange);
}

function getSnapshotMaxWidth1023() {
  return window.matchMedia("(max-width: 1023px)").matches;
}

function getServerSnapshotMaxWidth1023() {
  return false;
}

export function useIsNarrowDrawerViewport(): boolean {
  return useSyncExternalStore(
    subscribeMaxWidth1023,
    getSnapshotMaxWidth1023,
    getServerSnapshotMaxWidth1023,
  );
}
