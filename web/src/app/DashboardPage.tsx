import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, Brain, Boxes, FolderKanban, Mail, Network, TerminalSquare, Workflow } from "lucide-react";

import { apiGet } from "../shared/api/client";
import {
  useLocalOpsThreads,
  useMailCenterOverview,
  useMemoryHealth,
  useOrchestrationOverview,
  useRemoteJobs,
  useRemoteNodesHealth,
} from "../shared/api/hooks";
import type { ProjectDashboardItem } from "../shared/api/types";
import type { FrontendModule } from "../modules/types";
import { PageHeader } from "../shared/components/ui/page-header";
import { EmptyState } from "../shared/components/ui/empty-state";
import { relativeTime } from "../shared/lib/formatters";

function toneForStatus(status: string): string {
  const value = String(status || "").toLowerCase();
  if (["healthy", "ok", "succeeded", "done", "ready"].includes(value)) return "text-success";
  if (["slow", "queued", "running", "preparing"].includes(value)) return "text-warning";
  if (["down", "failed", "error", "canceled", "cancelled"].includes(value)) return "text-danger";
  return "text-muted-foreground";
}

export function DashboardPage({ modules }: { modules: FrontendModule[] }) {
  const nodesQuery = useRemoteNodesHealth();
  const jobsQuery = useRemoteJobs();
  const mailQuery = useMailCenterOverview();
  const orchestrationQuery = useOrchestrationOverview();
  const memoryQuery = useMemoryHealth();
  const threadsQuery = useLocalOpsThreads();
  const projectsQuery = useQuery({
    queryKey: ["dashboard", "projects"],
    queryFn: () => apiGet<ProjectDashboardItem[]>("/api/projects?limit=5&order=priority&include_top_tasks=true"),
    refetchInterval: 15_000,
  });

  const nodeRows = nodesQuery.data?.nodes ?? [];
  const remoteJobs = jobsQuery.data ?? [];
  const projects = projectsQuery.data ?? [];
  const localThreads = threadsQuery.data ?? [];
  const orchestration = orchestrationQuery.data;
  const mail = mailQuery.data;
  const memory = memoryQuery.data;

  const stats = useMemo(() => ({
    healthyNodes: nodeRows.filter((row) => row.status === "healthy").length,
    degradedNodes: nodeRows.filter((row) => row.status !== "healthy").length,
    activeJobs: remoteJobs.filter((row) => ["queued", "running", "accepted", "preparing"].includes(String(row.status || "").toLowerCase())).length,
    queuedMail: Number(mail?.counts?.queued ?? 0),
    projects: projects.length,
    localThreads: localThreads.length,
  }), [localThreads.length, mail?.counts?.queued, nodeRows, projects.length, remoteJobs]);

  const commandCards = [
    { label: "Healthy Nodes", value: stats.healthyNodes, icon: Network, href: "/modules/node-health" },
    { label: "Active Remote Jobs", value: stats.activeJobs, icon: Activity, href: "/modules/remote-ops/jobs" },
    { label: "Queued Mail", value: stats.queuedMail, icon: Mail, href: "/modules/mailcenter" },
    { label: "TaskVault Items", value: stats.projects, icon: FolderKanban, href: "/projects" },
    { label: "LocalOps Threads", value: stats.localThreads, icon: TerminalSquare, href: "/modules/local-ops/chat" },
    { label: "Shared Memory", value: memory?.shared_available ? "Online" : "Fallback", icon: Brain, href: "/modules/memory" },
  ];

  return (
    <div className="space-y-6 stagger-children">
      <PageHeader title="Command Center" description="Reduced Dashburg surface with installable add-on modules." />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {commandCards.map((card) => {
          const Icon = card.icon;
          return (
            <a key={card.label} href={card.href} className="card-hover-lift rounded-2xl border border-border bg-card/90 p-5 shadow-[var(--shadow)]">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{card.label}</p>
                  <p className="mt-2 text-3xl font-semibold text-foreground">{String(card.value)}</p>
                </div>
                <div className="rounded-xl border border-primary/20 bg-primary/10 p-3 text-primary"><Icon size={18} /></div>
              </div>
            </a>
          );
        })}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <section className="rounded-2xl border border-border bg-card/90 p-5 shadow-[var(--shadow)]">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <p className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">Control Plane</p>
              <h2 className="text-lg font-semibold text-foreground">Nodes and job traffic</h2>
            </div>
            <a href="/modules/remote-ops/nodes" className="text-sm text-primary hover:underline">Open RemoteOps</a>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="space-y-2">
              {nodeRows.length === 0 ? (
                <EmptyState message="No RemoteOps nodes configured yet." actionLabel="Open RemoteOps" actionHref="/modules/remote-ops/nodes" />
              ) : (
                nodeRows.slice(0, 8).map((row) => (
                  <div key={row.node_id} className="flex items-center justify-between rounded-xl border border-border/70 bg-background/20 px-3 py-2.5">
                    <div>
                      <p className="font-medium text-foreground">{row.node_id}</p>
                      <p className="text-xs text-muted-foreground">{row.node_id}</p>
                    </div>
                    <div className="text-right">
                      <p className={`text-sm font-medium ${toneForStatus(row.status)}`}>{row.status}</p>
                      <p className="text-xs text-muted-foreground">{row.latency_ms ?? "-"} ms</p>
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="space-y-2">
              {remoteJobs.length === 0 ? (
                <EmptyState message="No remote jobs yet." actionLabel="Open Jobs" actionHref="/modules/remote-ops/jobs" />
              ) : (
                remoteJobs.slice(0, 8).map((job) => (
                  <div key={job.id} className="rounded-xl border border-border/70 bg-background/20 px-3 py-2.5">
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-medium text-foreground">{job.job_type || job.id}</p>
                      <span className={`text-xs font-medium ${toneForStatus(String(job.status || ""))}`}>{job.status}</span>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">{job.node_id || "-"} • {job.updated_at ? relativeTime(job.updated_at) : "-"}</p>
                  </div>
                ))
              )}
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-border bg-card/90 p-5 shadow-[var(--shadow)]">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <p className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">Execution Surface</p>
              <h2 className="text-lg font-semibold text-foreground">Mailbox, orchestration, and local sessions</h2>
            </div>
            <a href="/modules/orchestration" className="text-sm text-primary hover:underline">Open Orchestration</a>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-xl border border-border/70 bg-background/20 p-4">
              <div className="flex items-center gap-2 text-foreground"><Workflow size={16} /><span className="font-medium">Orchestration</span></div>
              <dl className="mt-3 space-y-2 text-sm text-muted-foreground">
                <div className="flex justify-between gap-3"><dt>Running jobs</dt><dd>{orchestration?.running_jobs?.length ?? 0}</dd></div>
                <div className="flex justify-between gap-3"><dt>Queued jobs</dt><dd>{orchestration?.queued_jobs?.length ?? 0}</dd></div>
                <div className="flex justify-between gap-3"><dt>Mailbox entries</dt><dd>{orchestration?.mailbox?.length ?? 0}</dd></div>
              </dl>
            </div>

            <div className="rounded-xl border border-border/70 bg-background/20 p-4">
              <div className="flex items-center gap-2 text-foreground"><Boxes size={16} /><span className="font-medium">MailCenter</span></div>
              <dl className="mt-3 space-y-2 text-sm text-muted-foreground">
                <div className="flex justify-between gap-3"><dt>Inbox</dt><dd>{mail?.counts?.inbox ?? 0}</dd></div>
                <div className="flex justify-between gap-3"><dt>Queued</dt><dd>{mail?.counts?.queued ?? 0}</dd></div>
                <div className="flex justify-between gap-3"><dt>Replies needed</dt><dd>{mail?.counts?.replies_needed ?? 0}</dd></div>
              </dl>
            </div>
          </div>

          <div className="mt-4 rounded-xl border border-border/70 bg-background/20 p-4">
            <div className="flex items-center gap-2 text-foreground"><TerminalSquare size={16} /><span className="font-medium">LocalOps Sessions</span></div>
            {localThreads.length === 0 ? (
              <p className="mt-3 text-sm text-muted-foreground">No LocalOps threads yet.</p>
            ) : (
              <div className="mt-3 space-y-2">
                {localThreads.slice(0, 5).map((thread) => (
                  <div key={thread.id} className="flex items-center justify-between gap-3 rounded-lg border border-border/60 px-3 py-2 text-sm">
                    <div>
                      <p className="font-medium text-foreground">{thread.title}</p>
                      <p className="text-xs text-muted-foreground">{thread.provider_id} • {thread.model}</p>
                    </div>
                    <span className="text-xs text-muted-foreground">{relativeTime(thread.updated_at)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>

      <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
        <section className="rounded-2xl border border-border bg-card/90 p-5 shadow-[var(--shadow)]">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <p className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">Knowledge Surface</p>
              <h2 className="text-lg font-semibold text-foreground">TaskVault and memory</h2>
            </div>
            <a href="/projects" className="text-sm text-primary hover:underline">Open TaskVault</a>
          </div>
          {projects.length === 0 ? (
            <EmptyState message="No TaskVault projects yet." actionLabel="Open TaskVault" actionHref="/projects" />
          ) : (
            <div className="space-y-3">
              {projects.map((project) => (
                <a key={project.id} href={`/projects/${project.id}`} className="block rounded-xl border border-border/70 bg-background/20 p-4 hover:bg-background/30">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium text-foreground">{project.title}</p>
                      <p className="mt-1 text-sm text-muted-foreground">{project.notes_preview || project.description || "No notes yet."}</p>
                    </div>
                    <span className="text-xs text-muted-foreground">#{project.priority_rank ?? "-"}</span>
                  </div>
                  {project.top_tasks?.length ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {project.top_tasks.slice(0, 3).map((task) => (
                        <span key={task.id} className="rounded-full border border-border/70 px-2 py-1 text-xs text-muted-foreground">{task.content}</span>
                      ))}
                    </div>
                  ) : null}
                </a>
              ))}
            </div>
          )}
        </section>

        <section className="rounded-2xl border border-border bg-card/90 p-5 shadow-[var(--shadow)]">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <p className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">Surface Map</p>
              <h2 className="text-lg font-semibold text-foreground">Installed modules in this host</h2>
            </div>
            <a href="/settings/modules" className="text-sm text-primary hover:underline">Manage Modules</a>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {modules.map((mod) => {
              const href = mod.cards[0]?.href ?? mod.sidebar.href;
              return (
                <a key={mod.key} href={href} className="rounded-xl border border-border/70 bg-background/20 p-4 hover:bg-background/30">
                  <p className="font-medium text-foreground">{mod.name}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{mod.cards[0]?.description ?? mod.sidebar.label}</p>
                </a>
              );
            })}
          </div>
        </section>
      </div>
    </div>
  );
}
