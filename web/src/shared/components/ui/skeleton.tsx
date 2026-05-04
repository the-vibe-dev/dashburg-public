import { cn } from "../../lib/utils";

type SkeletonProps = {
  className?: string;
};

export function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      className={cn(
        "animate-skeleton rounded-lg bg-primary/[0.04]",
        className,
      )}
    />
  );
}

/** Skeleton for a metric card matching DashboardPage MetricCard dimensions */
export function MetricCardSkeleton() {
  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <Skeleton className="h-4 w-4 rounded-md mb-3" />
      <Skeleton className="h-7 w-20 mb-1.5" />
      <Skeleton className="h-4 w-16" />
    </div>
  );
}

/** Skeleton for a list row */
export function ListRowSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}

/** Skeleton for a dashboard panel with title + list */
export function PanelSkeleton() {
  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <Skeleton className="h-3 w-24 mb-4" />
      <ListRowSkeleton count={3} />
    </div>
  );
}
