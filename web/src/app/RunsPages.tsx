import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft } from "lucide-react";

import { apiGet } from "../shared/api/client";
import type { Run } from "../shared/api/types";
import { PageHeader } from "../shared/components/ui/page-header";
import { StatusBadge } from "../shared/components/ui/badge";
import { useStreamingMode } from "./useStreamingMode";
import { withStreamingObfuscation } from "./streamingObfuscation";

export function RunsListPage() {
  const { streamingMode } = useStreamingMode();
  const displayChannelRef = (value: string) => withStreamingObfuscation(value, streamingMode, "channel");
  const { data = [] } = useQuery({
    queryKey: ["runs"],
    queryFn: () => apiGet<Run[]>("/api/runs"),
  });

  return (
    <div className="space-y-6 stagger-children">
      <PageHeader title="Runs" description={`${data.length} pipeline runs`} />

      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[680px] text-left text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="px-5 py-4 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                  Run ID
                </th>
                <th className="px-5 py-4 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                  Repo
                </th>
                <th className="px-5 py-4 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                  Status
                </th>
                <th className="px-5 py-4 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                  Stage
                </th>
                <th className="px-5 py-4 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                  Updated
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {data.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-sm text-muted-foreground">
                    No runs yet
                  </td>
                </tr>
              ) : (
                data.map((run) => (
                  <tr key={run.id} className="row-hover transition-colors">
                    <td className="px-5 py-3.5">
                      <Link
                        to={`/runs/${run.id}`}
                        className="font-mono text-sm text-primary hover:text-primary/80 transition-colors"
                      >
                        {run.id.slice(0, 12)}…
                      </Link>
                    </td>
                    <td className="px-5 py-3.5 text-base text-foreground font-medium">
                      {displayChannelRef(run.repo_name)}
                    </td>
                    <td className="px-5 py-3.5">
                      <StatusBadge status={run.status} />
                    </td>
                    <td className="px-5 py-3.5 font-mono text-sm text-muted-foreground">
                      {run.stage}
                    </td>
                    <td className="px-5 py-3.5 text-sm text-muted-foreground">
                      {new Date(run.updated_at).toLocaleString()}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export function RunDetailPage() {
  const { streamingMode } = useStreamingMode();
  const displayChannelRef = (value: string) => withStreamingObfuscation(value, streamingMode, "channel");
  const { id } = useParams();
  const { data: run } = useQuery({
    queryKey: ["run", id],
    queryFn: () => apiGet<Run>(`/api/runs/${id}`),
    enabled: Boolean(id),
  });
  const { data: events = [] } = useQuery({
    queryKey: ["run-events", id],
    queryFn: () =>
      apiGet<Array<{ ts: string; event_type: string; message: string }>>(
        `/api/runs/${id}/events`,
      ),
    enabled: Boolean(id),
  });
  const { data: logs } = useQuery({
    queryKey: ["run-logs", id],
    queryFn: () => apiGet<{ run_id: string; logs: string }>(`/api/runs/${id}/logs`),
    enabled: Boolean(id),
  });

  return (
    <div className="space-y-3 stagger-children">
      <Link
        to="/runs"
        className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <ChevronLeft size={13} />
        Runs
      </Link>

      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-start gap-3 flex-wrap">
          <div className="flex-1">
            <h1 className="font-display text-xl font-bold text-foreground">
              Run detail
            </h1>
            <p className="mt-0.5 font-mono text-xs text-muted-foreground">{run?.id}</p>
          </div>
          {run && <StatusBadge status={run.status} />}
        </div>

        {run && (
          <div className="mt-4 grid gap-3 grid-cols-2 md:grid-cols-4">
            {[
              { label: "Repo", value: displayChannelRef(run.repo_name) },
              { label: "Stage", value: run.stage },
              { label: "Monitor", value: run.monitor_name },
              { label: "Kind", value: run.run_kind },
            ].map(({ label, value }) => (
              <div key={label}>
                <p className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground font-semibold">
                  {label}
                </p>
                <p className="mt-1 text-sm font-medium text-foreground font-mono">{value}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-xl border border-border bg-card p-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground mb-3">
          Events
        </p>
        {events.length === 0 ? (
          <p className="text-sm text-muted-foreground">No events</p>
        ) : (
          <ul className="space-y-1">
            {events.map((e, i) => (
              <li key={i} className="flex items-start gap-3 text-xs py-1 border-b border-border/30 last:border-0">
                <span className="font-mono text-muted-foreground/60 shrink-0">
                  {new Date(e.ts).toLocaleTimeString()}
                </span>
                <span className="text-accent font-medium shrink-0">{e.event_type}</span>
                <span className="text-foreground/80">{e.message}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="rounded-xl border border-border bg-card p-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground mb-3">
          Logs
        </p>
        <pre className="overflow-auto rounded-lg border border-border bg-background/60 p-3 text-xs font-mono text-foreground/80 leading-relaxed max-h-96">
          {logs?.logs ?? "No logs available."}
        </pre>
      </div>
    </div>
  );
}
