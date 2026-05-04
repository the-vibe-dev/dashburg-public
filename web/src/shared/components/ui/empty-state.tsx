import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Inbox } from "lucide-react";

import { cn } from "../../lib/utils";

type EmptyStateProps = {
  icon?: ReactNode;
  message: string;
  actionLabel?: string;
  actionHref?: string;
  className?: string;
};

export function EmptyState({
  icon,
  message,
  actionLabel,
  actionHref,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-lg border border-border/60 bg-background/20 px-4 py-8 text-center",
        className,
      )}
    >
      <div className="mb-3 text-muted-foreground/40">
        {icon ?? <Inbox size={28} strokeWidth={1.5} />}
      </div>
      <p className="text-sm text-muted-foreground">{message}</p>
      {actionLabel && actionHref && (
        <Link
          to={actionHref}
          className="mt-2 text-xs font-medium text-primary hover:underline"
        >
          {actionLabel}
        </Link>
      )}
    </div>
  );
}
