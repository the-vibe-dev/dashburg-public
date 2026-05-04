import { useQuery } from "@tanstack/react-query";

import { apiGet } from "../../shared/api/client";
import { PageHeader } from "../../shared/components/ui/page-header";

export function SystemPage() {
  const { data } = useQuery({ queryKey: ["config"], queryFn: () => apiGet<{ runs_directory: string; poll_interval_seconds: number }>("/api/config") });

  return (
    <div className="space-y-4">
      <PageHeader compact title="System" description="Runtime configuration and service defaults." />
      <div className="rounded-xl border border-border bg-card p-4">
        <h2 className="mb-2 text-lg font-semibold">System Settings</h2>
        <p className="text-sm">Runs directory: {data?.runs_directory ?? "-"}</p>
        <p className="text-sm">Poll interval: {data?.poll_interval_seconds ?? "-"}s</p>
      </div>
    </div>
  );
}
