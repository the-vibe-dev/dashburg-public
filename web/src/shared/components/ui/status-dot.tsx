export type HealthStatus = "healthy" | "slow" | "down" | "unknown";

const STATUS_CLASS: Record<HealthStatus, string> = {
  healthy: "bg-success",
  slow: "bg-warning",
  down: "bg-danger",
  unknown: "bg-muted-foreground/40",
};

export function StatusDot({
  status,
  size = "sm",
  pulse = false,
  className,
}: {
  status: HealthStatus;
  size?: "sm" | "md";
  pulse?: boolean;
  className?: string;
}) {
  const sizeClass = size === "md" ? "h-2.5 w-2.5" : "h-2 w-2";
  const pulseClass = pulse ? "animate-pulse" : "";
  return (
    <span
      aria-label={`status-${status}`}
      className={["inline-block rounded-full", STATUS_CLASS[status], sizeClass, pulseClass, className ?? ""].join(" ").trim()}
    />
  );
}
