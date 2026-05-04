import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Archive, Loader2, Mail, Play, RefreshCcw, RotateCcw, Save, Send, Square, Terminal } from "lucide-react";

import {
  useAcknowledgeOrchestrationMailboxItem,
  useActiveTerminalSession,
  useArchiveOrchestrationMailboxItem,
  useCancelOrchestrationJob,
  useCreateOrchestrationJob,
  useCreateOrchestrationMailboxNote,
  useCreateTerminalSession,
  useKillTerminalSession,
  useOrchestrationJob,
  useOrchestrationMailbox,
  useOrchestrationOverview,
  useOrchestrationSettings,
  useOrchestrationTerminalLaunch,
  useRetryOrchestrationJob,
  useUpdateOrchestrationSettings,
} from "../../shared/api/hooks";
import { apiGet, websocketUrl } from "../../shared/api/client";
import { Button } from "../../shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../shared/components/ui/card";
import { Input, Textarea } from "../../shared/components/ui/input";
import { PageHeader } from "../../shared/components/ui/page-header";
import { TerminalSurface, type TerminalSurfaceApi } from "../../shared/components/terminal/TerminalSurface";
import { DashburgAssistantPanel } from "../../shared/components/chat/DashburgAssistantPanel";
import type { OrchestrationJob, OrchestrationMailboxItem, OrchestrationSettings } from "../../shared/api/types";

const TERMINAL_DA_RESPONSE_RE = /^(?:\x1b\[\?[0-9;]*c|\x1b\[>[0-9;]*c|[0-9]+(?:;[0-9]+)*c)$/;

function shouldForwardTerminalInput(data: string): boolean {
  const normalized = data.replace(/[\r\n]+/g, "");
  if (!normalized) return true;
  return !TERMINAL_DA_RESPONSE_RE.test(normalized);
}

function statusTone(status: string): string {
  if (["succeeded", "healthy", "ok"].includes(status)) return "bg-success/20 text-success";
  if (["failed", "timed_out", "error", "unreachable"].includes(status)) return "bg-danger/20 text-danger";
  if (["running", "preparing", "accepted", "dispatched", "busy"].includes(status)) return "bg-sky-500/20 text-sky-200";
  if (["canceled", "disabled", "archived"].includes(status)) return "bg-muted text-muted-foreground";
  return "bg-amber-500/20 text-amber-100";
}

function formatList(values: unknown): string {
  if (!Array.isArray(values) || !values.length) return "-";
  return values.map((value) => String(value)).join(", ");
}

export function OrchestrationPage() {
  const { id } = useParams();
  const { data: overview, isLoading, refetch } = useOrchestrationOverview();
  const { data: settings } = useOrchestrationSettings();
  const { data: launch } = useOrchestrationTerminalLaunch();
  const { data: selectedJob } = useOrchestrationJob(id ?? null);
  const mailboxQuery = useOrchestrationMailbox({ jobId: id ?? undefined, limit: 60 });
  const createJob = useCreateOrchestrationJob();
  const cancelJob = useCancelOrchestrationJob();
  const retryJob = useRetryOrchestrationJob();
  const createSession = useCreateTerminalSession();
  const killSession = useKillTerminalSession();
  const updateSettings = useUpdateOrchestrationSettings();
  const createMailboxNote = useCreateOrchestrationMailboxNote();
  const acknowledgeMailbox = useAcknowledgeOrchestrationMailboxItem();
  const archiveMailbox = useArchiveOrchestrationMailboxItem();

  const [form, setForm] = useState({
    title: "Parallel codex task",
    target_node: "",
    repo_path: "",
    workspace_path: "",
    prompt: "",
    instructions: "Dashburg Orchestration delegated runner task. Work locally on the node, summarize result, and leave LocalOps semantics unchanged.",
    timeout_seconds: 3600,
    priority: 100,
    dependencies: "",
  });
  const [settingsForm, setSettingsForm] = useState<OrchestrationSettings>({
    preferred_terminal_node_id: "devwork",
    preferred_execution_mode: "delegated_runner",
    default_codex_mode: "workspace-write",
    default_timeout_seconds: 3600,
    global_max_active_jobs: 8,
    default_max_retries: 1,
    scheduler_poll_seconds: 5,
  });
  const [noteForm, setNoteForm] = useState({
    node_id: "",
    recipient_kind: "runner",
    agent_slug: "",
    subject: "",
    body: "",
    severity: "info",
    type: "note",
  });
  const [sessionId, setSessionId] = useState("");
  const [selectedTerminalNode, setSelectedTerminalNode] = useState("");
  const [availableSessionId, setAvailableSessionId] = useState("");
  const [terminalConnectedWanted, setTerminalConnectedWanted] = useState(false);
  const [socketEpoch, setSocketEpoch] = useState(0);
  const [connected, setConnected] = useState(false);
  const [jobLogLines, setJobLogLines] = useState<string[]>([]);
  const terminalApiRef = useRef<TerminalSurfaceApi | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const nodeOptions = overview?.nodes ?? [];
  const terminalNodes = nodeOptions.filter((node) => node.supports_terminal);
  const activeSession = useActiveTerminalSession(selectedTerminalNode || null);
  const runningJobs = overview?.running_jobs ?? [];
  const queuedJobs = overview?.queued_jobs ?? [];
  const recentJobs = overview?.recent_jobs ?? [];
  const mailboxItems = mailboxQuery.data?.items ?? overview?.mailbox ?? [];
  const selected = selectedJob ?? overview?.recent_jobs.find((job) => job.id === id) ?? overview?.recent_jobs[0] ?? null;

  useEffect(() => {
    if (!form.target_node && nodeOptions.length) {
      const first = nodeOptions.find((node) => node.supports_codex) ?? nodeOptions[0];
      setForm((prev) => ({
        ...prev,
        target_node: first.id,
        repo_path: first.repos[0] ?? prev.repo_path,
      }));
      setNoteForm((prev) => ({ ...prev, node_id: first.id }));
    }
  }, [form.target_node, nodeOptions]);

  useEffect(() => {
    if (selectedTerminalNode || !nodeOptions.length) return;
    const preferred = "devwork";
    const chosen = terminalNodes.find((node) => node.id === preferred) ?? terminalNodes[0] ?? nodeOptions[0];
    if (chosen) setSelectedTerminalNode(chosen.id);
  }, [nodeOptions, selectedTerminalNode, terminalNodes]);

  useEffect(() => {
    if (!settings) return;
    setSettingsForm(settings);
  }, [settings]);

  useEffect(() => {
    if (!selected?.id) {
      setJobLogLines([]);
      return;
    }
    let cancelled = false;
    let offset = 0;
    const run = async () => {
      const payload = await apiGet<{ lines: string[]; offset: number }>(`/api/orchestration/jobs/${selected.id}/logs?offset=${offset}&max_lines=200`);
      if (cancelled) return;
      if (payload.lines?.length) {
        setJobLogLines((prev) => [...prev, ...payload.lines].slice(-500));
      }
      offset = payload.offset ?? offset;
    };
    setJobLogLines([]);
    void run();
    const timer = window.setInterval(() => void run(), 2500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [selected?.id]);

  useEffect(() => {
    setAvailableSessionId(activeSession.data?.session_id ?? "");
  }, [activeSession.data?.session_id]);

  useEffect(() => {
    const currentSessionId = sessionId || "";
    if (!terminalConnectedWanted) return;
    if (!currentSessionId) return;
    const clientToken = window.localStorage.getItem("dashburg.remoteops.clientToken") ?? "";
    const adminToken = window.localStorage.getItem("dashburg.remoteops.adminToken") ?? "";
    const qs = new URLSearchParams();
    if (clientToken) qs.set("client_token", clientToken);
    if (adminToken) qs.set("admin_token", adminToken);
    const ws = new WebSocket(websocketUrl(`/api/remote/terminal/sessions/${currentSessionId}/ws`, qs));
    wsRef.current = ws;
    ws.onopen = () => {
      setConnected(true);
      terminalApiRef.current?.fit();
      terminalApiRef.current?.focus();
    };
    ws.onclose = () => setConnected(false);
    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as { type: string; data?: string };
        if (payload.type === "output" && payload.data) terminalApiRef.current?.write(payload.data);
      } catch {
        // Keep terminal transport tolerant of malformed frames.
      }
    };
    return () => {
      ws.close();
      if (wsRef.current === ws) wsRef.current = null;
    };
  }, [sessionId, terminalConnectedWanted, socketEpoch]);

  const selectedDependencies = useMemo(() => {
    if (!selected?.dependency_state?.length) return "none";
    return selected.dependency_state.map((item) => `${String(item.title || item.job_id)} (${String(item.status || "unknown")})`).join(", ");
  }, [selected?.dependency_state]);

  const launchTerminal = () => {
    if (!selectedTerminalNode) return;
    createSession.mutate(
      { node_id: selectedTerminalNode, cwd: launch?.cwd ?? "/srv/repos/dashgithub", command: launch?.command ?? "bash -l", forceNew: false },
      {
        onSuccess: (res) => {
          setSessionId(res.session_id);
          setTerminalConnectedWanted(true);
        },
      },
    );
  };

  const submitJob = () =>
    createJob.mutate({
      title: form.title,
      target_node: form.target_node,
      repo_path: form.repo_path,
      workspace_path: form.workspace_path,
      prompt: form.prompt,
      instructions: form.instructions,
      timeout_seconds: form.timeout_seconds,
      priority: form.priority,
      execution_mode: "delegated_runner",
      codex_mode: settingsForm.default_codex_mode,
      dependencies: form.dependencies.split(",").map((value) => value.trim()).filter(Boolean),
      task_type: "codex_task",
      metadata: { requested_from: "orchestration-ui" },
    });

  const submitMailboxNote = () => {
    if (!noteForm.node_id || !noteForm.subject.trim() || !noteForm.body.trim()) return;
    const recipient =
      noteForm.recipient_kind === "agent" && noteForm.agent_slug.trim()
        ? `node:${noteForm.node_id}/agent:${noteForm.agent_slug.trim()}`
        : `node:${noteForm.node_id}/runner`;
    createMailboxNote.mutate({
      nodeId: noteForm.node_id,
      payload: {
        type: noteForm.type,
        subject: noteForm.subject,
        body: noteForm.body,
        severity: noteForm.severity,
        to: recipient,
        job_id: selected?.id ?? "",
        tags: ["operator-note", "orchestration-ui"],
        metadata: {
          selected_job_id: selected?.id ?? "",
          recipient_kind: noteForm.recipient_kind,
          recipient_agent_slug: noteForm.agent_slug.trim(),
        },
      },
    });
    setNoteForm((prev) => ({ ...prev, subject: "", body: "" }));
  };

  const persistSettings = () => updateSettings.mutate(settingsForm);

  const jobsByBucket: Array<{ label: string; jobs: OrchestrationJob[] }> = [
    { label: "Running", jobs: runningJobs },
    { label: "Queued", jobs: queuedJobs },
    { label: "Recent", jobs: recentJobs },
  ];

  return (
    <div className="space-y-4">
      <PageHeader compact title="Orchestration">
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={launchTerminal} disabled={!selectedTerminalNode || createSession.isPending}>
            {createSession.isPending ? <Loader2 size={13} className="animate-spin" /> : <Terminal size={13} />}
            Launch Orchestration Terminal
          </Button>
          <Button size="sm" variant="outline" onClick={() => refetch()}>
            <RefreshCcw size={13} />
            Refresh Status
          </Button>
          <Link to="/modules/local-ops/chat"><Button size="sm" variant="outline">Open LocalOps</Button></Link>
        </div>
      </PageHeader>

      <Card>
        <CardHeader className="pb-2"><CardTitle>Mode Boundary</CardTitle></CardHeader>
        <CardContent className="grid gap-3 text-sm md:grid-cols-2">
          <div className="rounded border border-border p-3">
            <p className="font-medium">LocalOps Direct Process</p>
            <p className="text-muted-foreground">{overview?.localops_mode ?? "LocalOps remains the current direct/manual process."}</p>
          </div>
          <div className="rounded border border-border p-3">
            <p className="font-medium">Delegated Orchestration</p>
            <p className="text-muted-foreground">{overview?.orchestration_mode ?? "Orchestration is the delegated multi-node runner path."}</p>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="space-y-4">
          <DashburgAssistantPanel
            sessionId="orchestration-operator-session"
            title="Orchestration Assistant"
            subtitle="Shared Redis session chat for orchestration-aware operator conversations."
            defaultModel="qwen3:14b"
            allowSessionSwitch
            showSessionControls
            showMetadata
            heightClass="h-[360px]"
          />

          <Card>
            <CardHeader className="pb-2"><CardTitle>Main Orchestration Terminal</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className={`inline-flex rounded-full px-2 py-1 ${connected ? "bg-success/20 text-success" : "bg-muted text-muted-foreground"}`}>{connected ? "connected" : "disconnected"}</span>
                <span className="text-muted-foreground">node: {selectedTerminalNode || "-"}</span>
                <span className="text-muted-foreground">cwd: {launch?.cwd ?? "-"}</span>
                <span className="text-muted-foreground">session: {sessionId || "-"}</span>
                {!sessionId && availableSessionId ? <span className="text-muted-foreground">available: {availableSessionId}</span> : null}
              </div>
              <div className="grid gap-2 md:grid-cols-[1fr_auto]">
                <label className="text-xs text-muted-foreground">
                  Terminal node
                  <select
                    className="mt-1 w-full rounded border border-border bg-input px-2 py-2 text-sm text-foreground"
                    value={selectedTerminalNode}
                    onChange={(e) => {
                      setSelectedTerminalNode(e.target.value);
                      setSessionId("");
                      setTerminalConnectedWanted(false);
                      setConnected(false);
                    }}
                  >
                    <option value="">Select node</option>
                    {terminalNodes.map((node) => <option key={node.id} value={node.id}>{node.label} ({node.id})</option>)}
                  </select>
                </label>
                <div className="flex flex-wrap items-end gap-2">
                  <Button size="sm" variant="outline" onClick={launchTerminal} disabled={!selectedTerminalNode || createSession.isPending}>
                    {createSession.isPending ? <Loader2 size={13} className="animate-spin" /> : <Terminal size={13} />}
                    Connect
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      if (!availableSessionId) return;
                      setSessionId(availableSessionId);
                      setTerminalConnectedWanted(true);
                    }}
                    disabled={!availableSessionId || connected}
                  >
                    Attach Existing
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      if (!sessionId) return;
                      setTerminalConnectedWanted(true);
                      setSocketEpoch((value) => value + 1);
                    }}
                    disabled={!sessionId || connected}
                  >
                    Reconnect
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setTerminalConnectedWanted(false);
                      setConnected(false);
                      wsRef.current?.close();
                    }}
                    disabled={!connected}
                  >
                    Disconnect
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      if (!sessionId) return;
                      setTerminalConnectedWanted(false);
                      killSession.mutate(sessionId, {
                        onSuccess: () => {
                          setSessionId("");
                          setAvailableSessionId("");
                          setConnected(false);
                        },
                      });
                    }}
                    disabled={!sessionId}
                  >
                    Close Session
                  </Button>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => wsRef.current?.send(JSON.stringify({ type: "input", data: "\u0003" }))} disabled={!connected}>Send SIGINT</Button>
                <Button size="sm" variant="outline" onClick={() => terminalApiRef.current?.clear()}>Clear</Button>
              </div>
              <div className="terminalHost terminalCard h-[40vh] min-h-[320px]" onClick={() => terminalApiRef.current?.focus()}>
                <TerminalSurface
                  isActive
                  className="h-full w-full"
                  inputEnabled={connected}
                  onReady={(api) => { terminalApiRef.current = api; }}
                  onData={(data) => {
                    if (!shouldForwardTerminalInput(data)) return;
                    wsRef.current?.send(JSON.stringify({ type: "input", data }));
                  }}
                  onResize={() => {
                    const api = terminalApiRef.current;
                    if (!api || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
                    const size = api.getTerminalSize();
                    wsRef.current.send(JSON.stringify({ type: "resize", cols: Math.max(20, size.cols || 0), rows: Math.max(10, size.rows || 0) }));
                  }}
                />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2"><CardTitle>Dispatch Job</CardTitle></CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-2">
              <label className="text-xs text-muted-foreground">Title<Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
              <label className="text-xs text-muted-foreground">Target node
                <select className="mt-1 w-full rounded border border-border bg-input px-2 py-2 text-sm text-foreground" value={form.target_node} onChange={(e) => setForm({ ...form, target_node: e.target.value })}>
                  <option value="">Select node</option>
                  {nodeOptions.map((node) => <option key={node.id} value={node.id}>{node.label} ({node.id})</option>)}
                </select>
              </label>
              <label className="text-xs text-muted-foreground md:col-span-2">Repo path<Input value={form.repo_path} onChange={(e) => setForm({ ...form, repo_path: e.target.value })} /></label>
              <label className="text-xs text-muted-foreground md:col-span-2">Workspace path (optional)<Input value={form.workspace_path} onChange={(e) => setForm({ ...form, workspace_path: e.target.value })} /></label>
              <label className="text-xs text-muted-foreground md:col-span-2">Instructions<Textarea rows={3} value={form.instructions} onChange={(e) => setForm({ ...form, instructions: e.target.value })} /></label>
              <label className="text-xs text-muted-foreground md:col-span-2">Prompt<Textarea rows={6} value={form.prompt} onChange={(e) => setForm({ ...form, prompt: e.target.value })} /></label>
              <label className="text-xs text-muted-foreground">Priority<Input type="number" value={form.priority} onChange={(e) => setForm({ ...form, priority: Number(e.target.value || 100) })} /></label>
              <label className="text-xs text-muted-foreground">Timeout seconds<Input type="number" value={form.timeout_seconds} onChange={(e) => setForm({ ...form, timeout_seconds: Number(e.target.value || 3600) })} /></label>
              <label className="text-xs text-muted-foreground md:col-span-2">Dependencies (comma-separated job ids)<Input value={form.dependencies} onChange={(e) => setForm({ ...form, dependencies: e.target.value })} /></label>
              <div className="flex gap-2 md:col-span-2">
                <Button onClick={submitJob} disabled={createJob.isPending || !form.target_node || !form.repo_path || !form.prompt.trim()}>
                  {createJob.isPending ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
                  Dispatch Job
                </Button>
                <Button size="sm" variant="outline" onClick={() => refetch()}>
                  <RefreshCcw size={13} />
                  Refresh
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2"><CardTitle>Settings</CardTitle></CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-2">
              <label className="text-xs text-muted-foreground">Preferred terminal node
                <select className="mt-1 w-full rounded border border-border bg-input px-2 py-2 text-sm text-foreground" value={settingsForm.preferred_terminal_node_id} onChange={(e) => setSettingsForm({ ...settingsForm, preferred_terminal_node_id: e.target.value })}>
                  {nodeOptions.map((node) => <option key={node.id} value={node.id}>{node.label} ({node.id})</option>)}
                </select>
              </label>
              <label className="text-xs text-muted-foreground">Execution mode
                <select className="mt-1 w-full rounded border border-border bg-input px-2 py-2 text-sm text-foreground" value={settingsForm.preferred_execution_mode} onChange={(e) => setSettingsForm({ ...settingsForm, preferred_execution_mode: e.target.value as OrchestrationSettings["preferred_execution_mode"] })}>
                  <option value="delegated_runner">delegated_runner</option>
                  <option value="direct_ssh">direct_ssh</option>
                </select>
              </label>
              <label className="text-xs text-muted-foreground">Codex mode
                <select className="mt-1 w-full rounded border border-border bg-input px-2 py-2 text-sm text-foreground" value={settingsForm.default_codex_mode} onChange={(e) => setSettingsForm({ ...settingsForm, default_codex_mode: e.target.value as OrchestrationSettings["default_codex_mode"] })}>
                  <option value="read-only">read-only</option>
                  <option value="workspace-write">workspace-write</option>
                  <option value="danger-full-access">danger-full-access</option>
                </select>
              </label>
              <label className="text-xs text-muted-foreground">Global max active jobs<Input type="number" value={settingsForm.global_max_active_jobs} onChange={(e) => setSettingsForm({ ...settingsForm, global_max_active_jobs: Number(e.target.value || 8) })} /></label>
              <label className="text-xs text-muted-foreground">Default timeout<Input type="number" value={settingsForm.default_timeout_seconds} onChange={(e) => setSettingsForm({ ...settingsForm, default_timeout_seconds: Number(e.target.value || 3600) })} /></label>
              <label className="text-xs text-muted-foreground">Default retries<Input type="number" value={settingsForm.default_max_retries} onChange={(e) => setSettingsForm({ ...settingsForm, default_max_retries: Number(e.target.value || 1) })} /></label>
              <label className="text-xs text-muted-foreground">Scheduler poll seconds<Input type="number" value={settingsForm.scheduler_poll_seconds} onChange={(e) => setSettingsForm({ ...settingsForm, scheduler_poll_seconds: Number(e.target.value || 5) })} /></label>
              <div className="md:col-span-2">
                <Button onClick={persistSettings} disabled={updateSettings.isPending}>
                  {updateSettings.isPending ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                  Save Orchestration Settings
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-2"><CardTitle>Nodes</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {isLoading ? <p className="text-sm text-muted-foreground">Loading orchestration overview...</p> : null}
              {nodeOptions.map((node) => (
                <div key={node.id} className="rounded border border-border p-3 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <p className="font-medium">{node.label}</p>
                      <p className="text-xs text-muted-foreground">{node.id} · {node.base_url}</p>
                    </div>
                    <span className={`inline-flex rounded-full px-2 py-1 text-xs ${statusTone(node.health_status)}`}>{node.health_status}</span>
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">running {node.running_jobs} / limit {node.max_concurrent_jobs} · queued {node.queued_jobs}</p>
                  <p className="text-xs text-muted-foreground">mailbox inbox {node.mailbox_counts?.inbox ?? 0} · outbox {node.mailbox_counts?.outbox ?? 0} · archive {node.mailbox_counts?.archive ?? 0}</p>
                  <p className="text-xs text-muted-foreground">repos: {node.repos.join(", ") || "-"}</p>
                  <p className="text-xs text-muted-foreground">capabilities: {formatList(Object.entries(node.capabilities ?? {}).map(([key, value]) => `${key}=${typeof value === "object" ? JSON.stringify(value) : String(value)}`))}</p>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2"><CardTitle>Jobs</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {jobsByBucket.map(({ label, jobs }) => (
                <div key={label}>
                  <p className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
                  <div className="space-y-2">
                    {jobs.slice(0, label === "Recent" ? 8 : 6).map((job) => (
                      <div key={job.id} className="rounded border border-border p-3 text-sm">
                        <div className="flex items-center justify-between gap-2">
                          <Link to={`/modules/orchestration/jobs/${job.id}`} className="font-medium hover:underline">{job.title}</Link>
                          <span className={`inline-flex rounded-full px-2 py-1 text-xs ${statusTone(job.status)}`}>{job.status}</span>
                        </div>
                        <p className="text-xs text-muted-foreground">{job.target_node} · {job.task_type}</p>
                        {job.dependencies.length ? <p className="text-xs text-muted-foreground">deps: {job.dependencies.join(", ")}</p> : null}
                        <div className="mt-2 flex gap-2">
                          <Button size="sm" variant="outline" onClick={() => cancelJob.mutate(job.id)} disabled={cancelJob.isPending || ["succeeded", "failed", "canceled", "timed_out"].includes(job.status)}><Square size={12} />Cancel</Button>
                          <Button size="sm" variant="outline" onClick={() => retryJob.mutate(job.id)} disabled={retryJob.isPending || job.retry_count >= job.max_retries}><RotateCcw size={12} />Retry</Button>
                        </div>
                      </div>
                    ))}
                    {!jobs.length ? <p className="text-xs text-muted-foreground">No jobs in this bucket.</p> : null}
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2"><CardTitle>Job Detail</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              {selected ? (
                <>
                  <p className="font-medium">{selected.title}</p>
                  <p className="text-xs text-muted-foreground">{selected.id} · {selected.target_node} · {selected.repo_path}</p>
                  <p className="text-xs text-muted-foreground">dependency state: {selectedDependencies}</p>
                  {selected.result_summary ? <pre className="max-h-32 overflow-auto rounded border border-border bg-background/40 p-2 text-xs whitespace-pre-wrap">{selected.result_summary}</pre> : null}
                  {selected.last_error ? <p className="text-xs text-danger">{selected.last_error}</p> : null}
                  <div className="rounded border border-border bg-background/40 p-2 text-xs max-h-48 overflow-auto">
                    <pre className="whitespace-pre-wrap">{jobLogLines.join("\n") || "No logs yet."}</pre>
                  </div>
                  {selected.changed_files?.length ? <p className="text-xs text-muted-foreground">changed: {selected.changed_files.join(", ")}</p> : null}
                  {selected.artifacts?.length ? <p className="text-xs text-muted-foreground">artifacts: {selected.artifacts.map((item) => String(item.path ?? item.name ?? "")).filter(Boolean).join(", ")}</p> : null}
                </>
              ) : (
                <p className="text-xs text-muted-foreground">Select a job to inspect status, dependency list, and logs.</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2"><CardTitle>Mailbox</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-3 md:grid-cols-2">
                <label className="text-xs text-muted-foreground">Node
                  <select className="mt-1 w-full rounded border border-border bg-input px-2 py-2 text-sm text-foreground" value={noteForm.node_id} onChange={(e) => setNoteForm({ ...noteForm, node_id: e.target.value })}>
                    <option value="">Select node</option>
                    {nodeOptions.map((node) => <option key={node.id} value={node.id}>{node.label} ({node.id})</option>)}
                  </select>
                </label>
                <label className="text-xs text-muted-foreground">Recipient kind
                  <select
                    className="mt-1 w-full rounded border border-border bg-input px-2 py-2 text-sm text-foreground"
                    value={noteForm.recipient_kind}
                    onChange={(e) => setNoteForm({ ...noteForm, recipient_kind: e.target.value, agent_slug: e.target.value === "agent" ? noteForm.agent_slug : "" })}
                  >
                    <option value="runner">runner</option>
                    <option value="agent">agent</option>
                  </select>
                </label>
                {noteForm.recipient_kind === "agent" ? (
                  <label className="text-xs text-muted-foreground md:col-span-2">Agent slug
                    <Input placeholder="mailbot" value={noteForm.agent_slug} onChange={(e) => setNoteForm({ ...noteForm, agent_slug: e.target.value })} />
                  </label>
                ) : null}
                <label className="text-xs text-muted-foreground">Severity
                  <select className="mt-1 w-full rounded border border-border bg-input px-2 py-2 text-sm text-foreground" value={noteForm.severity} onChange={(e) => setNoteForm({ ...noteForm, severity: e.target.value })}>
                    <option value="info">info</option>
                    <option value="warning">warning</option>
                    <option value="error">error</option>
                  </select>
                </label>
                <label className="text-xs text-muted-foreground md:col-span-2">Subject<Input value={noteForm.subject} onChange={(e) => setNoteForm({ ...noteForm, subject: e.target.value })} /></label>
                <label className="text-xs text-muted-foreground md:col-span-2">Body<Textarea rows={3} value={noteForm.body} onChange={(e) => setNoteForm({ ...noteForm, body: e.target.value })} /></label>
                <div className="md:col-span-2">
                  <Button
                    onClick={submitMailboxNote}
                    disabled={
                      createMailboxNote.isPending
                      || !noteForm.node_id
                      || !noteForm.subject.trim()
                      || !noteForm.body.trim()
                      || (noteForm.recipient_kind === "agent" && !noteForm.agent_slug.trim())
                    }
                  >
                    {createMailboxNote.isPending ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
                    Send Mail Message
                  </Button>
                </div>
              </div>
              <div className="space-y-2">
                {mailboxItems.map((item: OrchestrationMailboxItem) => (
                  <div key={item.id} className="rounded border border-border p-3 text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        {item.direction === "inbox" ? <Mail size={14} /> : <Terminal size={14} />}
                        <p className="font-medium">{item.subject}</p>
                      </div>
                      <span className={`inline-flex rounded-full px-2 py-1 text-xs ${statusTone(item.severity || item.status)}`}>{item.direction} · {item.type}</span>
                    </div>
                    <p className="text-xs text-muted-foreground">{item.node_id} · {item.created_at} {item.job_id ? `· job ${item.job_id}` : ""}</p>
                    <p className="mt-2 whitespace-pre-wrap text-xs text-muted-foreground">{item.body}</p>
                    {item.attachments?.length ? <p className="mt-2 text-xs text-muted-foreground">attachments: {item.attachments.map((attachment) => String(attachment.path ?? attachment.name ?? "")).filter(Boolean).join(", ")}</p> : null}
                    <div className="mt-2 flex gap-2">
                      <Button size="sm" variant="outline" onClick={() => acknowledgeMailbox.mutate({ nodeId: item.node_id, itemId: item.id })} disabled={acknowledgeMailbox.isPending || item.acknowledged}><Mail size={12} />Acknowledge</Button>
                      <Button size="sm" variant="outline" onClick={() => archiveMailbox.mutate({ nodeId: item.node_id, itemId: item.id })} disabled={archiveMailbox.isPending || item.archived}><Archive size={12} />Archive</Button>
                    </div>
                  </div>
                ))}
                {!mailboxItems.length ? <p className="text-xs text-muted-foreground">No mailbox traffic yet.</p> : null}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2"><CardTitle>Dependencies</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-xs">
              {(overview?.dependency_edges ?? []).slice(0, 16).map((edge, index) => (
                <div key={`${String(edge.job_id)}-${String(edge.depends_on)}-${index}`} className="rounded border border-border p-2">
                  <p>{String(edge.job_id)} depends on {String(edge.depends_on)}</p>
                  <p className="text-muted-foreground">status: {String(edge.status ?? "unknown")}</p>
                </div>
              ))}
              {!overview?.dependency_edges?.length ? <p className="text-muted-foreground">No dependency links in recent jobs.</p> : null}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
