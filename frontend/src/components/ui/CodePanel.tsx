import { useState, type ReactNode } from "react";

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
    <div className={`relative ${className ?? ""}`}>
      <div className="flex items-center justify-between bg-black rounded-t px-3 py-1 border border-neutral-800">
        <span className="text-neutral-500 text-[10px] uppercase tracking-widest">
          {language}
        </span>
        <div className="flex items-center gap-2">
          {headerExtra}
          <button
            onClick={(e) => {
              e.stopPropagation();
              copy();
            }}
            className="text-neutral-500 hover:text-neutral-300 text-[10px] transition-colors"
          >
            {copied ? "copied ✓" : "copy"}
          </button>
        </div>
      </div>
      <pre className="bg-black border border-t-0 border-neutral-800 rounded-b px-3 py-2 overflow-x-auto max-h-64 text-[11px] leading-relaxed text-neutral-200 whitespace-pre">
        {code}
      </pre>
    </div>
  );
}

