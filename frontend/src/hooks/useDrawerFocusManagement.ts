import { type RefObject, useEffect, useRef } from "react";

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function listFocusables(container: HTMLElement): HTMLElement[] {
  const nodes = Array.from(
    container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
  );
  return nodes.filter((el) => {
    if (el.closest("[hidden]")) return false;
    if (el.getAttribute("aria-hidden") === "true") return false;
    const style = window.getComputedStyle(el);
    if (style.visibility === "hidden" || style.display === "none") return false;
    return true;
  });
}

type DrawerFocusOptions = {
  open: boolean;
  isNarrowViewport: boolean;
  containerRef: RefObject<HTMLElement | null>;
  returnFocusRef: RefObject<HTMLElement | null>;
  onRequestClose: () => void;
};

export function useDrawerFocusManagement({ open, isNarrowViewport, containerRef, returnFocusRef, onRequestClose }: DrawerFocusOptions) {
  const hadOpenDrawerRef = useRef(false);

  useEffect(() => {
    const active = open && isNarrowViewport;

    if (active) {
      hadOpenDrawerRef.current = true;
      const container = containerRef.current;
      if (!container) return;

      const focusFirst = () => {
        const list = listFocusables(container);
        (list[0] ?? container).focus();
      };
      const raf = requestAnimationFrame(focusFirst);

      const onDocKeyDown = (e: KeyboardEvent) => {
        if (e.key === "Escape") {
          e.preventDefault();
          onRequestClose();
          return;
        }
        if (e.key !== "Tab" || !container) return;

        const list = listFocusables(container);
        if (list.length === 0) return;

        const first = list[0];
        const last = list[list.length - 1];
        const ae = document.activeElement as HTMLElement | null;

        if (e.shiftKey) {
          if (ae === first || !container.contains(ae)) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (ae === last || !container.contains(ae)) {
            e.preventDefault();
            first.focus();
          }
        }
      };

      document.addEventListener("keydown", onDocKeyDown, true);
      return () => {
        cancelAnimationFrame(raf);
        document.removeEventListener("keydown", onDocKeyDown, true);
      };
    }

    if (hadOpenDrawerRef.current) {
      hadOpenDrawerRef.current = false;
      requestAnimationFrame(() => {
        returnFocusRef.current?.focus?.();
      });
    }

    return undefined;
  }, [
    open,
    isNarrowViewport,
    containerRef,
    returnFocusRef,
    onRequestClose,
  ]);
}
