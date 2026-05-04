import { type ReactNode, useEffect, useRef, useState } from "react";

import { cn } from "../../lib/utils";

export type TabItem = {
  id: string;
  label: ReactNode;
  icon?: ReactNode;
};

type TabsProps = {
  tabs: TabItem[];
  active: string;
  onChange: (id: string) => void;
  className?: string;
  /** Compact variant with smaller text */
  size?: "sm" | "md";
};

export function Tabs({ tabs, active, onChange, className, size = "md" }: TabsProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const tabRefs = useRef<Map<string, HTMLButtonElement>>(new Map());
  const [indicator, setIndicator] = useState({ left: 0, width: 0 });

  useEffect(() => {
    const el = tabRefs.current.get(active);
    const container = containerRef.current;
    if (el && container) {
      const containerRect = container.getBoundingClientRect();
      const elRect = el.getBoundingClientRect();
      setIndicator({
        left: elRect.left - containerRect.left,
        width: elRect.width,
      });
    }
  }, [active, tabs]);

  const textSize = size === "sm" ? "text-xs" : "text-sm";

  return (
    <div ref={containerRef} className={cn("relative flex gap-0.5 border-b border-border", className)}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          ref={(el) => {
            if (el) tabRefs.current.set(tab.id, el);
          }}
          type="button"
          role="tab"
          aria-selected={tab.id === active}
          onClick={() => onChange(tab.id)}
          onKeyDown={(e) => {
            const idx = tabs.findIndex((t) => t.id === tab.id);
            if (e.key === "ArrowRight" && idx < tabs.length - 1) {
              e.preventDefault();
              onChange(tabs[idx + 1].id);
            }
            if (e.key === "ArrowLeft" && idx > 0) {
              e.preventDefault();
              onChange(tabs[idx - 1].id);
            }
          }}
          className={cn(
            "relative flex items-center gap-1.5 px-3 py-2.5 font-medium transition-colors duration-150",
            textSize,
            tab.id === active
              ? "text-primary"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {tab.icon}
          {tab.label}
        </button>
      ))}
      {/* Animated underline indicator */}
      <span
        className="absolute bottom-0 h-[2px] bg-primary transition-all duration-200 ease-[cubic-bezier(0.4,0,0.2,1)]"
        style={{ left: indicator.left, width: indicator.width }}
      />
    </div>
  );
}
