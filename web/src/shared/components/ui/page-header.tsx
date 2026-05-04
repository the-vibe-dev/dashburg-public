import type { ReactNode } from "react";

import { cn } from "../../lib/utils";
import { Card, CardContent } from "./card";

type PageHeaderProps = {
  title: ReactNode;
  description?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  contentClassName?: string;
  compact?: boolean;
  /** Show the logo image (default: true) */
  showLogo?: boolean;
};

export function PageHeader({
  title,
  description,
  meta,
  actions,
  children,
  className,
  contentClassName,
  compact = false,
  showLogo = true,
}: PageHeaderProps) {
  const logoSize = compact ? "h-12 w-12" : "h-14 w-14";
  const titleSize = compact ? "text-2xl" : "text-3xl";

  return (
    <Card className={className}>
      <CardContent className={cn("px-4 py-4", contentClassName)}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            {showLogo && (
              <img
                src="/logo.png"
                alt="Dashburg"
                className={cn(logoSize, "shrink-0 rounded-lg border border-border/60 bg-background/40 object-cover")}
              />
            )}
            <div className="min-w-0">
              <h1 className={cn("font-display font-bold tracking-tight text-foreground", titleSize)}>{title}</h1>
              {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
              {meta ? <div className="mt-2 text-xs text-muted-foreground">{meta}</div> : null}
            </div>
          </div>
          {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
        </div>
        {children ? <div className="mt-3">{children}</div> : null}
      </CardContent>
    </Card>
  );
}
