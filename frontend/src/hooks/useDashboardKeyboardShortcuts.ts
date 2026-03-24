import { useEffect } from "react";
import type { MainWorkspaceSectionId } from "../components/ui/MainWorkspaceNav";
import { RIGHT_PANEL_TAB_IDS, type RightPanelTabId } from "../components/ui/RightPanelTabs";

function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  const tag = el.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  return el.isContentEditable;
}

export function useDashboardKeyboardShortcuts(setMainSection: (s: MainWorkspaceSectionId) => void, setRightTab: (t: RightPanelTabId) => void): void {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (!e.altKey || e.ctrlKey || e.metaKey) return;
      if (isTypingTarget(e.target)) return;

      if (e.code === "Digit1" || e.code === "Digit2") {
        e.preventDefault();
        setMainSection("pipeline");
        return;
      }

      const tabIndexByCode: Record<string, number> = {
        Digit3: 0,
        Digit4: 1,
        Digit5: 2,
        Digit6: 3,
      };
      const idx = tabIndexByCode[e.code];
      if (idx !== undefined) {
        const tab = RIGHT_PANEL_TAB_IDS[idx];
        if (tab) {
          e.preventDefault();
          setRightTab(tab);
        }
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [setMainSection, setRightTab]);
}
