import { useState, type ReactNode } from "react";
import {
  APP_BUTTON_SUBTLE,
  cx,
} from "./theme";

interface CodePanelProps {
  code: string;
  language?: string;
  className?: string;
  headerExtra?: ReactNode;
}

export function CodePanel({
  code,
  language = "text",
  className,
  headerExtra,
}: CodePanelProps) {
  const [copied, setCopied] = useState(false);

  function copy() {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  return (
    <div className={cx("app-code-panel", className)}>
      <div className="app-code-panel-header">
        <span className="app-code-panel-title">
          {language}
        </span>
        <div className="flex items-center gap-2">
          {headerExtra}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              copy();
            }}
            className={cx(APP_BUTTON_SUBTLE, "min-h-0 px-0 py-0 text-[10px]")}
          >
            {copied ? "copied ✓" : "copy"}
          </button>
        </div>
      </div>
      <pre className="app-code-panel-body">
        {code}
      </pre>
    </div>
  );
}

