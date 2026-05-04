import { cn } from "../../lib/utils";

type BadgeVariant = "default" | "primary" | "success" | "warning" | "danger" | "accent" | "muted";

const variantClasses: Record<BadgeVariant, string> = {
  default: "border-border bg-border/30 text-foreground",
  primary: "border-primary/30 bg-primary/10 text-primary",
  success: "border-success/30 bg-success/10 text-success",
  warning: "border-warning/30 bg-warning/10 text-warning",
  danger: "border-danger/30 bg-danger/10 text-danger",
  accent: "border-accent/30 bg-accent/10 text-accent",
  muted: "border-border bg-border/20 text-muted-foreground",
};

type BadgeProps = {
  children: React.ReactNode;
  variant?: BadgeVariant;
  /** Show a filled dot before the label */
  dot?: boolean;
  className?: string;
};

export function Badge({ children, variant = "default", dot, className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium",
        variantClasses[variant],
        className,
      )}
    >
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current shrink-0" />}
      {children}
    </span>
  );
}

/** Map a status string to a badge variant */
export function statusVariant(status: string | undefined | null): BadgeVariant {
  if (!status) return "muted";
  const s = status.toLowerCase();
  if (["succeeded", "success", "done", "healthy", "ok", "deployed"].includes(s)) return "success";
  if (["failed", "error", "timed_out", "unreachable", "down"].includes(s)) return "danger";
  if (["running", "preparing", "deploying", "dispatched", "accepted", "busy"].includes(s)) return "accent";
  if (["slow", "pending", "queued", "blocked"].includes(s)) return "warning";
  if (["canceled", "disabled", "archived"].includes(s)) return "muted";
  return "default";
}

/** Convenience: renders a status badge from a status string */
export function StatusBadge({ status, className }: { status: string; className?: string }) {
  return (
    <Badge variant={statusVariant(status)} dot className={className}>
      {status}
    </Badge>
  );
}
