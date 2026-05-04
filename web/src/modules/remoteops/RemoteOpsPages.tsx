import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { Loader2, Play, Plus, RefreshCw, Server, Settings, Terminal, Trash2 } from "lucide-react";

import {
  useCreateRemoteJob,
  useCreateRemoteNode,
  useCreateTerminalSession,
  useActiveTerminalSession,
  useDeleteRemoteNode,
  useDisableNodeKey,
  useKillTerminalSession,
  usePatchRemoteJob,
  useRemoteJob,
  useRemoteJobs,
  useRemoteNodes,
  useRemoteNodesHostMonitor,
  useRemoteNodesHealth,
  useRemoteServerDetail,
  useRemoteServers,
  useRemoteSettings,
  useRotateNodeKey,
  useTestNode,
  useUpdateRemoteNode,
  useUpdateRemoteSettings,
  useRebootRemoteNodeHostMonitor,
} from "../../shared/api/hooks";
import type { HostMonitorStatusPayload, RemoteJob, RemoteOpsNode, RemoteOpsSettings, RemoteServer } from "../../shared/api/types";
import { eventsUrl, websocketUrl } from "../../shared/api/client";
import { Button } from "../../shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../shared/components/ui/card";
import { TerminalSurface, type TerminalSurfaceApi } from "../../shared/components/terminal/TerminalSurface";
import { Input, Textarea } from "../../shared/components/ui/input";
import { StatusDot } from "../../shared/components/ui/status-dot";
import { PageHeader } from "../../shared/components/ui/page-header";
import { AdvancedRawJson, ObjectReadout, RecordTableReadout } from "../../shared/components/ui/readouts";
import { useStreamingMode } from "../../app/useStreamingMode";
import { withStreamingObfuscation } from "../../app/streamingObfuscation";

function fmt(value: unknown): string {
  if (value == null) return "-";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

function relTime(iso: string | null | undefined): string {
  if (!iso) return "never";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "unknown";
  const sec = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  return `${Math.floor(hr / 24)}d ago`;
}

const TERMINAL_DA_RESPONSE_RE = /^(?:\x1b\[\?[0-9;]*c|\x1b\[>[0-9;]*c|[0-9]+(?:;[0-9]+)*c)$/;
const SHARED_MEM_CODEX_CMD =
  'codex "Please load cluster memory from /mnt/nas_ai/shared/MEM.md first when available; if unavailable, fallback to ~/MEM.md, and use that as host topology memory for this session. For remote investigations, open ONE persistent SSH session per target host and run multiple commands inside that session; avoid one-off ssh command invocations unless necessary. Before finishing any remote investigation, write two markdown files on that remote machine under ~/runner/investigations/: (1) a timestamped conclusion file with findings and next actions, and (2) a host/repo profile file with durable observations, discovered settings, and known issues so future agents can understand the device/repo quickly. Summarize key nodes and SSH/RemoteOps commands first."';

function shouldForwardTerminalInput(data: string): boolean {
  const normalized = data.replace(/[\r\n]+/g, "");
  if (!normalized) return true;
  return !TERMINAL_DA_RESPONSE_RE.test(normalized);
}

function RemoteOpsTabs() {
  const location = useLocation();
  const { streamingMode } = useStreamingMode();
  const [adminToken, setAdminToken] = useState(() => localStorage.getItem("dashburg.remoteops.adminToken") ?? "");
  const [clientToken, setClientToken] = useState(() => localStorage.getItem("dashburg.remoteops.clientToken") ?? "");
  const [showAuth, setShowAuth] = useState(false);

  useEffect(() => {
    localStorage.setItem("dashburg.remoteops.adminToken", adminToken.trim());
  }, [adminToken]);
  useEffect(() => {
    localStorage.setItem("dashburg.remoteops.clientToken", clientToken.trim());
  }, [clientToken]);

  const tabs = [
    { href: "/modules/remote-ops/nodes", label: "Nodes", icon: <Server size={12} /> },
    { href: "/modules/remote-ops/jobs", label: "Jobs", icon: <Play size={12} /> },
    { href: "/modules/remote-ops/codex", label: "Codex Jobs", icon: <Terminal size={12} /> },
    { href: "/modules/remote-ops/terminal", label: "Terminal", icon: <Terminal size={12} /> },
    { href: "/modules/remote-ops/settings", label: "Settings", icon: <Settings size={12} /> },
  ];

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {tabs.map((tab) => (
          <Link key={tab.href} to={tab.href}>
            <Button variant={location.pathname.startsWith(tab.href) ? "default" : "outline"} size="sm">
              {tab.icon}
              {tab.label}
            </Button>
          </Link>
        ))}
        <Button variant="outline" size="sm" onClick={() => setShowAuth((v) => !v)}>
          Auth Tokens
        </Button>
      </div>
      {showAuth ? (
        <div className="grid gap-2 rounded-lg border border-border p-2 md:grid-cols-3">
          {streamingMode ? (
            <div className="md:col-span-2 rounded border border-warning/40 bg-warning/10 px-2 py-1.5 text-xs text-warning">
              Streaming mode is enabled. Admin/client tokens are hidden.
            </div>
          ) : (
            <>
              <label className="text-xs text-muted-foreground">
                Admin token
                <Input value={adminToken} onChange={(e) => setAdminToken(e.target.value)} placeholder="REMOTEOPS_ADMIN_TOKEN" />
              </label>
              <label className="text-xs text-muted-foreground">
                Client token
                <Input value={clientToken} onChange={(e) => setClientToken(e.target.value)} placeholder="chat_client_token" />
              </label>
            </>
          )}
          <div className="flex items-end gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setAdminToken("");
                setClientToken("");
              }}
            >
              Clear
            </Button>
            <p className="text-xs text-muted-foreground">Saved in browser localStorage.</p>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function clampPercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, value));
}

function NodeUtilBar({ label, value, tone = "primary" }: { label: string; value: number; tone?: "primary" | "warning" | "danger" | "success" }) {
  const pct = clampPercent(value);
  const toneClass =
    tone === "danger"
      ? "bg-danger"
      : tone === "warning"
        ? "bg-warning"
        : tone === "success"
          ? "bg-success"
          : "bg-primary";
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-[11px] text-muted-foreground">
        <span>{label}</span>
        <span className="font-mono">{pct.toFixed(1)}%</span>
      </div>
      <div className="h-2 w-full rounded bg-background/40">
        <div className={`h-2 rounded ${toneClass}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function formatBytes(value?: number | null): string {
  if (!value || !Number.isFinite(value)) return "-";
  const gib = 1024 ** 3;
  if (value >= gib) return `${(value / gib).toFixed(1)} GiB`;
  return `${(value / (1024 ** 2)).toFixed(1)} MiB`;
}

function NodeHostOpsPanel({
  nodeId,
  label,
  monitorBaseUrl,
  latencyMs,
  status,
  error,
  payload,
  rebootPending,
  onReboot,
}: {
  nodeId: string;
  label: string;
  monitorBaseUrl: string;
  latencyMs: number | null;
  status: string;
  error: string | null;
  payload: HostMonitorStatusPayload;
  rebootPending: boolean;
  onReboot: () => void;
}) {
  const health = String(payload?.health?.status ?? status ?? "unknown").toLowerCase();
  const cpu = payload?.cpu?.usage_percent ?? 0;
  const mem = payload?.memory?.used_percent ?? 0;
  const swap = payload?.swap?.used_percent ?? 0;
  const issues = payload?.health?.issues ?? [];
  const gpus = payload?.gpus ?? [];
  const top = payload?.top_processes ?? [];
  const gpuProcs = payload?.gpu_processes ?? [];
  const capabilities = payload?.capabilities ?? {};
  const hasGpu = capabilities.has_gpu ?? gpus.length > 0;
  const hasOllama = capabilities.has_ollama ?? !!payload?.ollama;
  const hasComfyui = capabilities.has_comfyui ?? !!payload?.comfyui;
  const hasComfyuiWrapper = capabilities.has_comfyui_wrapper ?? !!payload?.comfyui_wrapper;
  const hasGpuAudioWrapper = capabilities.has_gpu_audio_wrapper ?? !!payload?.gpu_audio_wrapper;
  const ollama = payload?.ollama;
  const comfyui = payload?.comfyui;
  const comfyuiWrapper = payload?.comfyui_wrapper;
  const gpuAudioWrapper = payload?.gpu_audio_wrapper;
  const ollamaStatus = String(ollama?.status ?? "unknown").toLowerCase();
  const ollamaDup = (ollama?.process_count ?? 0) > 1;
  const ollamaModels = ollama?.models ?? [];
  const ollamaEndpoints = ollama?.endpoints ?? [];
  const reachableOllamaEndpoints = ollamaEndpoints.filter((endpoint) => endpoint.reachable).length;
  const comfyStatus = String(comfyui?.status ?? "unknown").toLowerCase();
  const comfyRunning = comfyui?.queue_running ?? 0;
  const comfyPending = comfyui?.queue_pending ?? 0;
  const comfyWrapperStatus = String(comfyuiWrapper?.status ?? "unknown").toLowerCase();
  const comfyWrapperWaiting = comfyuiWrapper?.queue_waiting ?? 0;
  const comfyWrapperActive = comfyuiWrapper?.queue_active ?? 0;
  const gpuAudioStatus = String(gpuAudioWrapper?.status ?? "unknown").toLowerCase();
  const gpuAudioWaiting = gpuAudioWrapper?.queue_waiting ?? 0;
  const gpuAudioActive = gpuAudioWrapper?.queue_active ?? 0;

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">{label}</p>
          <p className="text-xs text-muted-foreground">
            {nodeId} · {monitorBaseUrl} · {latencyMs != null ? `${latencyMs}ms` : "n/a"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`rounded px-2 py-1 text-xs font-medium ${health === "healthy" ? "bg-success/15 text-success" : "bg-danger/15 text-danger"}`}>
            {health}
          </span>
          <Button type="button" variant="outline" size="sm" onClick={onReboot} disabled={rebootPending}>
            {rebootPending ? "Rebooting..." : "Reboot Host"}
          </Button>
        </div>
      </div>

      <div className={`grid gap-4 ${hasGpu ? "lg:grid-cols-3" : "lg:grid-cols-1"}`}>
        <div className="space-y-3 rounded-lg border border-border/60 bg-background/20 p-3">
          <NodeUtilBar label="CPU" value={cpu} tone={cpu > 90 ? "danger" : cpu > 70 ? "warning" : "success"} />
          <NodeUtilBar label="Memory" value={mem} tone={mem > 90 ? "danger" : mem > 75 ? "warning" : "success"} />
          <NodeUtilBar label="Swap" value={swap} tone={swap > 50 ? "warning" : "success"} />
          <div className="text-xs text-muted-foreground">
            Load: <span className="font-mono">{(payload?.cpu?.load1 ?? 0).toFixed(2)} / {(payload?.cpu?.load5 ?? 0).toFixed(2)} / {(payload?.cpu?.load15 ?? 0).toFixed(2)}</span>
          </div>
          <div className="text-xs text-muted-foreground">
            Disk /: <span className="font-mono">{(payload?.disk?.used_percent ?? 0).toFixed(1)}%</span>
          </div>
          {hasOllama ? (
            <div className={`rounded border px-2 py-1 text-xs ${ollamaStatus === "healthy" || ollamaStatus === "empty" ? "border-success/30 text-success" : "border-danger/30 text-danger"}`}>
              Ollama: {ollamaStatus} · procs={ollama?.process_count ?? 0} · models={ollama?.model_count ?? ollama?.models_count ?? 0}
              {ollamaDup ? " · duplicate serve detected" : ""}
            </div>
          ) : null}
        </div>

        {hasGpu ? (
          <div className="rounded-lg border border-border/60 bg-background/20 p-3 lg:col-span-2">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">GPU Board</p>
            {gpus.length === 0 ? (
              <p className="text-sm text-muted-foreground">No GPU telemetry available.</p>
            ) : (
              <div className="space-y-3">
                {gpus.map((gpu) => (
                  <div key={`${gpu.index}-${gpu.name}`} className="rounded border border-border/60 bg-background/30 p-2">
                    <div className="mb-1 flex items-center justify-between text-xs">
                      <span className="font-medium text-foreground">GPU {gpu.index}: {gpu.name}</span>
                      <span className="font-mono text-muted-foreground">{gpu.temperature_c}C · {gpu.power_w}W</span>
                    </div>
                    <div className="grid gap-2 md:grid-cols-2">
                      <NodeUtilBar label="GPU Util" value={gpu.util_gpu} tone={gpu.util_gpu > 95 ? "danger" : gpu.util_gpu > 70 ? "warning" : "success"} />
                      <NodeUtilBar label={`VRAM ${gpu.memory_used_mib}/${gpu.memory_total_mib} MiB`} value={(gpu.memory_total_mib ? (gpu.memory_used_mib / gpu.memory_total_mib) * 100 : 0)} tone="primary" />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : null}
      </div>

      {hasOllama || hasComfyui ? (
        <div className={`mt-4 grid gap-4 ${hasOllama && hasComfyui ? "lg:grid-cols-2" : "lg:grid-cols-1"}`}>
          {hasOllama ? (
            <div className="rounded-lg border border-border/60 bg-background/20 p-3">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">Loaded Models</p>
                <span className={`rounded px-2 py-0.5 text-[11px] ${ollamaStatus === "healthy" || ollamaStatus === "empty" ? "bg-success/15 text-success" : "bg-danger/15 text-danger"}`}>
                  {ollamaStatus === "empty" ? "Empty" : ollamaStatus === "unreachable" ? "Unreachable" : "Healthy"}
                </span>
              </div>
              {!ollama?.reachable ? (
                <p className="text-xs text-danger">{ollama?.error || "Ollama installed but unreachable."}</p>
              ) : ollamaModels.length === 0 ? (
                <p className="text-xs text-muted-foreground">Ollama running, no models currently loaded.</p>
              ) : (
                <div className="space-y-2">
                  {ollamaEndpoints.length > 1 ? (
                    <p className="text-xs text-muted-foreground">
                      Endpoints reachable: {reachableOllamaEndpoints}/{ollamaEndpoints.length}
                    </p>
                  ) : null}
                  {ollamaModels.map((model, idx) => (
                    <div key={`${model.name ?? model.model ?? "model"}-${idx}`} className="rounded border border-border/40 bg-background/30 px-2 py-1.5 text-xs">
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-medium text-foreground">{model.name ?? model.model}</span>
                        <span className="text-muted-foreground">{formatBytes(model.size_vram ?? model.size)}</span>
                      </div>
                      <div className="mt-1 grid gap-1 text-muted-foreground sm:grid-cols-2">
                        <span>Context: {model.context_length ?? "-"}</span>
                        <span className="truncate">Expires: {model.expires_at ?? "-"}</span>
                        <span className="truncate sm:col-span-2">Endpoint: {model.endpoint_url ?? "-"}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : null}
          {hasComfyui ? (
            <div className="rounded-lg border border-border/60 bg-background/20 p-3">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">ComfyUI Queue</p>
                <span className={`rounded px-2 py-0.5 text-[11px] ${comfyStatus === "ok" || comfyStatus === "empty" ? "bg-success/15 text-success" : "bg-danger/15 text-danger"}`}>
                  {comfyStatus === "empty" ? "Empty" : comfyStatus === "unreachable" ? "Unreachable" : "Healthy"}
                </span>
              </div>
              {!comfyui?.reachable ? (
                <p className="text-xs text-danger">{comfyui?.error || "ComfyUI installed but unreachable."}</p>
              ) : (
                <div className="grid gap-2 sm:grid-cols-2">
                  <div className="rounded border border-border/40 bg-background/30 px-2 py-2 text-xs">
                    <p className="text-muted-foreground">Queue Running</p>
                    <p className="font-mono text-foreground">{comfyRunning}</p>
                  </div>
                  <div className="rounded border border-border/40 bg-background/30 px-2 py-2 text-xs">
                    <p className="text-muted-foreground">Queue Pending</p>
                    <p className="font-mono text-foreground">{comfyPending}</p>
                  </div>
                  <div className="sm:col-span-2 text-xs text-muted-foreground">
                    {comfyRunning + comfyPending === 0
                      ? "No running or pending ComfyUI jobs."
                      : `Running IDs: ${(comfyui?.running_items ?? []).join(", ") || "-"} · Pending IDs: ${(comfyui?.pending_items ?? []).join(", ") || "-"}`}
                  </div>
                </div>
              )}
            </div>
          ) : null}
        </div>
      ) : null}

      {hasComfyuiWrapper || hasGpuAudioWrapper ? (
        <div className={`mt-4 grid gap-4 ${hasComfyuiWrapper && hasGpuAudioWrapper ? "lg:grid-cols-2" : "lg:grid-cols-1"}`}>
          {hasComfyuiWrapper ? (
            <div className="rounded-lg border border-border/60 bg-background/20 p-3">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">Comfy Wrapper</p>
                <span className={`rounded px-2 py-0.5 text-[11px] ${comfyWrapperStatus === "ok" || comfyWrapperStatus === "busy" ? "bg-success/15 text-success" : "bg-danger/15 text-danger"}`}>
                  {comfyWrapperStatus === "busy" ? "Busy" : comfyWrapperStatus === "ok" ? "Healthy" : comfyWrapperStatus === "unreachable" ? "Unreachable" : comfyWrapperStatus}
                </span>
              </div>
              {!comfyuiWrapper?.reachable ? (
                <p className="text-xs text-danger">{comfyuiWrapper?.error || "Comfy wrapper is unreachable."}</p>
              ) : (
                <div className="grid gap-2 sm:grid-cols-2">
                  <div className="rounded border border-border/40 bg-background/30 px-2 py-2 text-xs">
                    <p className="text-muted-foreground">Queue Waiting</p>
                    <p className="font-mono text-foreground">{comfyWrapperWaiting}</p>
                  </div>
                  <div className="rounded border border-border/40 bg-background/30 px-2 py-2 text-xs">
                    <p className="text-muted-foreground">Active Jobs</p>
                    <p className="font-mono text-foreground">{comfyWrapperActive}</p>
                  </div>
                  <div className="sm:col-span-2 text-xs text-muted-foreground">Source: {comfyuiWrapper?.source_url ?? "-"}</div>
                </div>
              )}
            </div>
          ) : null}
          {hasGpuAudioWrapper ? (
            <div className="rounded-lg border border-border/60 bg-background/20 p-3">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">GPU Audio Wrapper</p>
                <span className={`rounded px-2 py-0.5 text-[11px] ${gpuAudioStatus === "ok" || gpuAudioStatus === "busy" ? "bg-success/15 text-success" : "bg-danger/15 text-danger"}`}>
                  {gpuAudioStatus === "busy" ? "Busy" : gpuAudioStatus === "ok" ? "Healthy" : gpuAudioStatus === "unreachable" ? "Unreachable" : gpuAudioStatus}
                </span>
              </div>
              {!gpuAudioWrapper?.reachable ? (
                <p className="text-xs text-danger">{gpuAudioWrapper?.error || "GPU audio wrapper is unreachable."}</p>
              ) : (
                <div className="grid gap-2 sm:grid-cols-2">
                  <div className="rounded border border-border/40 bg-background/30 px-2 py-2 text-xs">
                    <p className="text-muted-foreground">Queue Waiting</p>
                    <p className="font-mono text-foreground">{gpuAudioWaiting}</p>
                  </div>
                  <div className="rounded border border-border/40 bg-background/30 px-2 py-2 text-xs">
                    <p className="text-muted-foreground">Active Jobs</p>
                    <p className="font-mono text-foreground">{gpuAudioActive}</p>
                  </div>
                  <div className="sm:col-span-2 text-xs text-muted-foreground">Source: {gpuAudioWrapper?.source_url ?? "-"}</div>
                </div>
              )}
            </div>
          ) : null}
        </div>
      ) : null}

      <div className={`mt-4 grid gap-4 ${hasGpu ? "lg:grid-cols-2" : "lg:grid-cols-1"}`}>
        <div className="rounded-lg border border-border/60 bg-background/20 p-3">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">HTOP Top CPU</p>
          <div className="max-h-56 overflow-auto rounded border border-border/40 bg-black/30 p-2 font-mono text-[11px]">
            {top.length === 0 ? (
              <p className="text-muted-foreground">No process data.</p>
            ) : (
              top.map((p) => (
                <div key={`${p.pid}-${p.command}`} className="grid grid-cols-[64px_54px_54px_1fr] gap-2 text-foreground">
                  <span>{p.pid}</span>
                  <span>{p.cpu_percent.toFixed(1)}</span>
                  <span>{p.mem_percent.toFixed(1)}</span>
                  <span className="truncate">{p.command}</span>
                </div>
              ))
            )}
          </div>
        </div>
        {hasGpu ? (
          <div className="rounded-lg border border-border/60 bg-background/20 p-3">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">NVTOP GPU Procs</p>
            <div className="max-h-56 overflow-auto rounded border border-border/40 bg-black/30 p-2 font-mono text-[11px]">
              {gpuProcs.length === 0 ? (
                <p className="text-muted-foreground">No GPU process data.</p>
              ) : (
                gpuProcs.map((p) => (
                  <div key={`${p.pid}-${p.command}`} className="grid grid-cols-[64px_54px_54px_1fr] gap-2 text-foreground">
                    <span>{p.pid}</span>
                    <span>{p.cpu_percent.toFixed(1)}</span>
                    <span>{p.mem_percent.toFixed(1)}</span>
                    <span className="truncate">{p.command}</span>
                  </div>
                ))
              )}
            </div>
          </div>
        ) : null}
      </div>

      {error ? (
        <div className="mt-4 rounded border border-danger/30 bg-danger/10 p-3 text-xs text-danger">
          {error}
        </div>
      ) : null}
      {!error && issues.length > 0 ? (
        <div className="mt-4 rounded border border-danger/30 bg-danger/10 p-3 text-xs text-danger">{issues.join(" | ")}</div>
      ) : null}
    </div>
  );
}

export function RemoteNodeHealthPage() {
  const { data, isLoading, error, refetch, isFetching } = useRemoteNodesHostMonitor({
    includeProcesses: false,
    includeGpuProcesses: false,
  });
  const reboot = useRebootRemoteNodeHostMonitor();
  const rows = data?.nodes ?? [];

  return (
    <div className="space-y-4">
      <PageHeader compact title="NodeHealth" />

      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
          {isFetching ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
          Refresh
        </Button>
        <p className="text-xs text-muted-foreground">
          TTL {data?.ttl_seconds ?? 15}s · {rows.length} nodes
        </p>
      </div>

      {isLoading ? <p className="text-sm text-muted-foreground">Loading node health...</p> : null}
      {error ? <p className="text-sm text-danger">{String(error)}</p> : null}

      {rows.length === 0 ? (
        <Card>
          <CardContent className="pt-6 text-sm text-muted-foreground">No node host-monitor data available.</CardContent>
        </Card>
      ) : (
        rows.map((row) => (
          <NodeHostOpsPanel
            key={row.node_id}
            nodeId={row.node_id}
            label={row.label}
            monitorBaseUrl={row.monitor_base_url}
            latencyMs={row.latency_ms}
            status={row.status}
            error={row.error}
            payload={row.payload ?? {}}
            rebootPending={reboot.isPending}
            onReboot={() => reboot.mutate({ nodeId: row.node_id })}
          />
        ))
      )}
    </div>
  );
}

export function RemoteSettingsPage() {
  const { data, isLoading, error } = useRemoteSettings();
  const save = useUpdateRemoteSettings();
  const [form, setForm] = useState<RemoteOpsSettings | null>(null);

  useEffect(() => {
    if (!data) return;
    setForm(data);
    if (data.chat_client_token) {
      localStorage.setItem("dashburg.remoteops.clientToken", data.chat_client_token);
    }
  }, [data]);

  return (
    <div className="space-y-4">
      <PageHeader compact title="Remote Ops Settings">
        <RemoteOpsTabs />
      </PageHeader>

      {isLoading ? <p className="text-sm text-muted-foreground">Loading settings...</p> : null}
      {error ? <p className="text-sm text-danger">{String(error)}</p> : null}

      {form ? (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle>Global Settings</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-3">
            <label className="text-xs text-muted-foreground">
              LLM Provider
              <select
                value={form.main_llm_provider}
                onChange={(e) => setForm({ ...form, main_llm_provider: e.target.value as RemoteOpsSettings["main_llm_provider"] })}
                className="mt-1 w-full rounded border border-border bg-input px-2 py-2 text-sm text-foreground"
              >
                <option value="openai">openai</option>
                <option value="ollama">ollama</option>
                <option value="custom_http">custom_http</option>
              </select>
            </label>
            <label className="text-xs text-muted-foreground">
              LLM Model
              <Input value={form.main_llm_model} onChange={(e) => setForm({ ...form, main_llm_model: e.target.value })} />
            </label>
            <label className="text-xs text-muted-foreground">
              LLM Base URL
              <Input value={form.main_llm_base_url} onChange={(e) => setForm({ ...form, main_llm_base_url: e.target.value })} />
            </label>
            <label className="text-xs text-muted-foreground">
              API Key Ref (env var name)
              <Input value={form.main_llm_api_key_ref} onChange={(e) => setForm({ ...form, main_llm_api_key_ref: e.target.value })} />
            </label>
            <label className="text-xs text-muted-foreground">
              Execution Mode
              <select
                value={form.execution_mode}
                onChange={(e) => setForm({ ...form, execution_mode: e.target.value as RemoteOpsSettings["execution_mode"] })}
                className="mt-1 w-full rounded border border-border bg-input px-2 py-2 text-sm text-foreground"
              >
                <option value="propose_only">propose_only</option>
                <option value="require_confirm">require_confirm</option>
                <option value="auto_execute_allowlisted">auto_execute_allowlisted</option>
              </select>
            </label>
            <label className="text-xs text-muted-foreground">
              Default Target Node
              <Input value={form.default_target_node_id} onChange={(e) => setForm({ ...form, default_target_node_id: e.target.value })} />
            </label>
            <label className="text-xs text-muted-foreground">
              Max Jobs / Node
              <Input
                type="number"
                value={form.max_concurrent_jobs_per_node}
                onChange={(e) => setForm({ ...form, max_concurrent_jobs_per_node: Number(e.target.value || 1) })}
              />
            </label>
            <label className="text-xs text-muted-foreground">
              Max Jobs Global
              <Input type="number" value={form.max_concurrent_jobs_global} onChange={(e) => setForm({ ...form, max_concurrent_jobs_global: Number(e.target.value || 1) })} />
            </label>
            <label className="text-xs text-muted-foreground">
              Log Retention Days
              <Input type="number" value={form.log_retention_days} onChange={(e) => setForm({ ...form, log_retention_days: Number(e.target.value || 14) })} />
            </label>
            <label className="text-xs text-muted-foreground">
              Terminal Idle Timeout (minutes)
              <Input
                type="number"
                value={form.terminal_idle_timeout_minutes}
                onChange={(e) => setForm({ ...form, terminal_idle_timeout_minutes: Number(e.target.value || 30) })}
              />
            </label>
            <label className="text-xs text-muted-foreground">
              Terminal Max Sessions
              <Input type="number" value={form.terminal_max_sessions} onChange={(e) => setForm({ ...form, terminal_max_sessions: Number(e.target.value || 2) })} />
            </label>
            <label className="text-xs text-muted-foreground md:col-span-3">
              Hub client token (for `remoteops` CLI)
              <Input value={form.chat_client_token} onChange={(e) => setForm({ ...form, chat_client_token: e.target.value })} />
            </label>

            <div className="md:col-span-3 flex flex-wrap gap-4 text-xs">
              <label className="inline-flex items-center gap-2">
                <input type="checkbox" checked={form.chat_enabled} onChange={(e) => setForm({ ...form, chat_enabled: e.target.checked })} />
                chat_enabled
              </label>
              <label className="inline-flex items-center gap-2">
                <input type="checkbox" checked={form.allow_codex_jobs} onChange={(e) => setForm({ ...form, allow_codex_jobs: e.target.checked })} />
                allow_codex_jobs
              </label>
              <label className="inline-flex items-center gap-2">
                <input type="checkbox" checked={form.allow_system_actions} onChange={(e) => setForm({ ...form, allow_system_actions: e.target.checked })} />
                allow_system_actions
              </label>
              <label className="inline-flex items-center gap-2">
                <input type="checkbox" checked={form.allow_apt_upgrade} onChange={(e) => setForm({ ...form, allow_apt_upgrade: e.target.checked })} />
                allow_apt_upgrade
              </label>
              <label className="inline-flex items-center gap-2">
                <input type="checkbox" checked={form.terminal_enabled} onChange={(e) => setForm({ ...form, terminal_enabled: e.target.checked })} />
                terminal_enabled
              </label>
              <label className="inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={form.terminal_recording_enabled}
                  onChange={(e) => setForm({ ...form, terminal_recording_enabled: e.target.checked })}
                />
                terminal_recording_enabled
              </label>
            </div>

            <div className="md:col-span-3">
              <Button
                onClick={() =>
                  save.mutate(form, {
                    onSuccess: (next) => {
                      if (next.chat_client_token) {
                        localStorage.setItem("dashburg.remoteops.clientToken", next.chat_client_token);
                      }
                    },
                  })
                }
                disabled={save.isPending}
              >
                {save.isPending ? <Loader2 size={13} className="animate-spin" /> : null}
                Save Settings
              </Button>
              {save.error ? <p className="mt-2 text-xs text-danger">{String(save.error)}</p> : null}
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

const STANDARD_JOB_TYPES = ["monitor.snapshot", "git.update", "systemd.restart", "docker.compose.up", "apt.upgrade", "codex.exec"];

function parseLines(value: string): string[] {
  return value
    .split("\n")
    .map((v) => v.trim())
    .filter(Boolean);
}

function NodeEditor({ node, onSave }: { node?: RemoteOpsNode; onSave: (payload: Record<string, unknown>) => void }) {
  const [id, setId] = useState(node?.id ?? "");
  const [label, setLabel] = useState(node?.label ?? "");
  const [baseUrl, setBaseUrl] = useState(node?.base_url ?? "http://runner.example.local:8444");
  const [supportsCodex, setSupportsCodex] = useState(node?.supports_codex ?? false);
  const [supportsTerminal, setSupportsTerminal] = useState(node?.supports_terminal ?? false);
  const [enabled, setEnabled] = useState(node?.enabled ?? true);
  const [allowedRepos, setAllowedRepos] = useState((node?.allowed_repos ?? []).join("\n"));
  const [allowedServices, setAllowedServices] = useState((node?.allowed_services ?? []).join("\n"));
  const [allowAllManagedActions, setAllowAllManagedActions] = useState((node?.allowed_job_types ?? []).length === 0);
  const [selectedJobTypes, setSelectedJobTypes] = useState<string[]>(node?.allowed_job_types ?? ["monitor.snapshot", "systemd.restart"]);
  const [customJobTypes, setCustomJobTypes] = useState("");
  const [notes, setNotes] = useState(node?.notes ?? "");

  function toggleJobType(jobType: string, checked: boolean) {
    setSelectedJobTypes((prev) => {
      if (checked) return Array.from(new Set([...prev, jobType]));
      return prev.filter((v) => v !== jobType);
    });
  }

  const effectiveJobTypes = allowAllManagedActions
    ? []
    : Array.from(new Set([...selectedJobTypes, ...parseLines(customJobTypes)]));

  return (
    <div className="grid gap-2 md:grid-cols-2">
      <label className="text-xs text-muted-foreground">
        Node ID
        <Input disabled={Boolean(node)} value={id} onChange={(e) => setId(e.target.value)} placeholder="main" />
      </label>
      <label className="text-xs text-muted-foreground">
        Label
        <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Main Server" />
      </label>
      <label className="text-xs text-muted-foreground md:col-span-2">
        Base URL
        <Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="http://runner.example.local:8444" />
      </label>
      <label className="text-xs text-muted-foreground">
        Allowed Repos (one per line)
        <Textarea rows={4} value={allowedRepos} onChange={(e) => setAllowedRepos(e.target.value)} />
      </label>
      <label className="text-xs text-muted-foreground">
        Allowed Services (one per line)
        <Textarea rows={4} value={allowedServices} onChange={(e) => setAllowedServices(e.target.value)} />
      </label>
      <div className="rounded border border-border p-2 text-xs md:col-span-2">
        <label className="inline-flex items-center gap-2">
          <input type="checkbox" checked={allowAllManagedActions} onChange={(e) => setAllowAllManagedActions(e.target.checked)} />
          Trusted Mode: allow all managed RemoteOps actions
        </label>
        <p className="mt-1 text-muted-foreground">Allows all supported runner job actions. Arbitrary shell execution is still blocked for safety.</p>
        {!allowAllManagedActions ? (
          <div className="mt-2 grid gap-2 md:grid-cols-3">
            {STANDARD_JOB_TYPES.map((jobType) => (
              <label key={jobType} className="inline-flex items-center gap-2">
                <input type="checkbox" checked={selectedJobTypes.includes(jobType)} onChange={(e) => toggleJobType(jobType, e.target.checked)} />
                {jobType}
              </label>
            ))}
            <label className="text-xs text-muted-foreground md:col-span-3">
              Custom job types (optional, one per line)
              <Textarea rows={2} value={customJobTypes} onChange={(e) => setCustomJobTypes(e.target.value)} />
            </label>
          </div>
        ) : null}
      </div>
      <label className="text-xs text-muted-foreground md:col-span-2">
        Notes
        <Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      <div className="md:col-span-2 flex flex-wrap gap-4 text-xs">
        <label className="inline-flex items-center gap-2">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} /> enabled
        </label>
        <label className="inline-flex items-center gap-2">
          <input type="checkbox" checked={supportsCodex} onChange={(e) => setSupportsCodex(e.target.checked)} /> supports_codex
        </label>
        <label className="inline-flex items-center gap-2">
          <input type="checkbox" checked={supportsTerminal} onChange={(e) => setSupportsTerminal(e.target.checked)} /> supports_terminal
        </label>
      </div>
      <div className="md:col-span-2">
        <Button
          onClick={() =>
            onSave({
              id,
              label,
              base_url: baseUrl,
              enabled,
              supports_codex: supportsCodex,
              supports_terminal: supportsTerminal,
              allowed_repos: parseLines(allowedRepos),
              allowed_services: parseLines(allowedServices),
              allowed_job_types: effectiveJobTypes,
              notes,
            })
          }
        >
          Save Node
        </Button>
      </div>
    </div>
  );
}

export function RemoteNodesPage() {
  const { data = [], isLoading, error, refetch } = useRemoteNodes();
  const { data: healthData } = useRemoteNodesHealth();
  const createNode = useCreateRemoteNode();
  const updateNode = useUpdateRemoteNode();
  const deleteNode = useDeleteRemoteNode();
  const rotateKey = useRotateNodeKey();
  const disableKey = useDisableNodeKey();

  const [editing, setEditing] = useState<RemoteOpsNode | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [snippet, setSnippet] = useState<RemoteOpsNode["install"] | null>(null);
  const editCardRef = useRef<HTMLDivElement | null>(null);
  const healthByNode = useMemo(
    () => new Map((healthData?.nodes ?? []).map((row) => [row.node_id, row])),
    [healthData?.nodes],
  );
  useEffect(() => {
    if (!editing || !editCardRef.current) return;
    editCardRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [editing]);

  return (
    <div className="space-y-4">
      <PageHeader
        compact
        title="Remote Ops Nodes"
        actions={(
          <>
            <Button variant="outline" onClick={() => refetch()}>
              <RefreshCw size={13} /> Refresh
            </Button>
            <Button onClick={() => setShowCreate((v) => !v)}>
              <Plus size={13} /> Add Node
            </Button>
          </>
        )}
      >
        <RemoteOpsTabs />
      </PageHeader>
      <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1"><StatusDot status="healthy" /> Healthy</span>
        <span className="inline-flex items-center gap-1"><StatusDot status="slow" pulse /> Slow</span>
        <span className="inline-flex items-center gap-1"><StatusDot status="down" pulse /> Down</span>
      </div>

      {showCreate ? (
        <Card>
          <CardHeader className="pb-2"><CardTitle>Add Node</CardTitle></CardHeader>
          <CardContent>
            <NodeEditor
              onSave={(payload) => {
                createNode.mutate(payload as never, {
                  onSuccess: (created) => {
                    setSnippet(created.install ?? null);
                    setShowCreate(false);
                  },
                });
              }}
            />
          </CardContent>
        </Card>
      ) : null}

      {snippet ? (
        <Card>
          <CardHeader className="pb-2"><CardTitle>Runner Onboarding Snippet</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-xs">
            <p className="text-muted-foreground">Generated secret and config for node `{snippet.node_id}`.</p>
            <pre className="max-h-72 overflow-auto rounded border border-border bg-background/40 p-2">{snippet.config_yaml}</pre>
            <pre className="max-h-72 overflow-auto rounded border border-border bg-background/40 p-2">{snippet.install_commands}</pre>
            {snippet.main_terminal_commands ? <pre className="max-h-72 overflow-auto rounded border border-border bg-background/40 p-2">{snippet.main_terminal_commands}</pre> : null}
          </CardContent>
        </Card>
      ) : null}

      {isLoading ? <p className="text-sm text-muted-foreground">Loading nodes...</p> : null}
      {error ? <p className="text-sm text-danger">{String(error)}</p> : null}

      {editing ? (
        <div ref={editCardRef}>
          <Card>
            <CardHeader className="pb-2"><CardTitle>Edit Node · {editing.id}</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <NodeEditor
                node={editing}
                onSave={(payload) => {
                  updateNode.mutate(
                    { nodeId: editing.id, payload },
                    {
                      onSuccess: () => {
                        setEditing(null);
                        refetch();
                      },
                    },
                  );
                }}
              />
              <div className="flex justify-end">
                <Button variant="outline" size="sm" onClick={() => setEditing(null)}>Cancel Edit</Button>
              </div>
            </CardContent>
          </Card>
        </div>
      ) : null}

      <div className="grid gap-3 md:grid-cols-2">
        {data.map((node) => (
          <Card key={node.id}>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-2">
                  <StatusDot
                    status={healthByNode.get(node.id)?.status ?? "unknown"}
                    size="md"
                    pulse={(healthByNode.get(node.id)?.status ?? "unknown") !== "healthy"}
                  />
                  {node.label} ({node.id})
                </span>
                <div className="flex items-center gap-2">
                  <Link to={`/modules/remote-ops/nodes/${node.id}`}><Button size="sm" variant="outline">Detail</Button></Link>
                  {node.supports_terminal ? <Link to={`/modules/remote-ops/terminal?node=${node.id}`}><Button size="sm">Connect</Button></Link> : null}
                </div>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs">
              {(() => {
                const health = healthByNode.get(node.id);
                if (!health) return <p className="text-muted-foreground">Last check: pending…</p>;
                if (health.status === "down") return <p className="text-danger">Down • {health.error || "unreachable"} • {relTime(health.checked_at)}</p>;
                return <p className="text-muted-foreground">Last check: {relTime(health.checked_at)} • {health.latency_ms ?? "-"}ms</p>;
              })()}
              <p><span className="text-muted-foreground">URL:</span> {node.base_url}</p>
              <p><span className="text-muted-foreground">key:</span> {node.key_id}</p>
              <p><span className="text-muted-foreground">supports_codex:</span> {String(node.supports_codex)} · <span className="text-muted-foreground">supports_terminal:</span> {String(node.supports_terminal)}</p>
              <div className="flex flex-wrap gap-2 pt-1">
                <Button size="sm" variant="outline" onClick={() => setEditing(node)}>Edit</Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    updateNode.mutate({ nodeId: node.id, payload: { ...node, enabled: !node.enabled } }, { onSuccess: () => refetch() })
                  }
                >
                  {node.enabled ? "Disable" : "Enable"}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    rotateKey.mutate(
                      { nodeId: node.id, disable_previous: false },
                      {
                        onSuccess: (res) => {
                          setSnippet({
                            node_id: node.id,
                            key_id: res.key_id,
                            secret: res.secret,
                            config_yaml: `key_id: ${res.key_id}\nshared_secret: ${res.secret}\n`,
                            install_commands: "Update /etc/dashburg-runner/config.yaml with new key and secret, then restart runner.",
                          });
                        },
                      },
                    )
                  }
                >
                  Rotate Key
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    if (!window.confirm(`Delete node ${node.id}?`)) return;
                    deleteNode.mutate(node.id);
                  }}
                >
                  <Trash2 size={12} /> Remove
                </Button>
              </div>

              {node.keys.length > 0 ? (
                <div className="rounded border border-border p-2">
                  <p className="mb-1 text-muted-foreground">Keys</p>
                  {node.keys.map((key) => (
                    <div key={key.key_id} className="flex items-center justify-between gap-2 py-1">
                      <span className="font-mono text-[11px]">{key.key_id} {key.disabled_at ? "(disabled)" : "(active?)"}</span>
                      {!key.disabled_at && key.key_id !== node.key_id ? (
                        <Button size="sm" variant="outline" onClick={() => disableKey.mutate({ nodeId: node.id, keyId: key.key_id })}>
                          Disable
                        </Button>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : null}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

export function RemoteNodeDetailPage() {
  const { id = "" } = useParams();
  const { data, isLoading, error, refetch } = useRemoteServerDetail(id || null);
  const testConn = useTestNode(id || null);
  const createJob = useCreateRemoteJob();
  const [serviceName, setServiceName] = useState("");

  return (
    <div className="space-y-4">
      <PageHeader
        compact
        title={`Node Detail · ${id}`}
        actions={(
          <>
            <Link to="/modules/remote-ops/nodes"><Button variant="outline" size="sm">Back</Button></Link>
            <Button variant="outline" size="sm" onClick={() => refetch()}><RefreshCw size={13} /> Refresh</Button>
          </>
        )}
      >
        <RemoteOpsTabs />
      </PageHeader>

      {isLoading ? <p className="text-sm text-muted-foreground">Loading...</p> : null}
      {error ? <p className="text-sm text-danger">{String(error)}</p> : null}

      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => testConn.refetch()}>Test Connection</Button>
        {testConn.data ? <p className="text-xs text-muted-foreground">{fmt(testConn.data.status)} {testConn.data.error ? `(${fmt(testConn.data.error)})` : ""}</p> : null}
        {data?.server.supports_terminal ? <Link to={`/modules/remote-ops/terminal?node=${id}`}><Button size="sm">Connect to Main Terminal</Button></Link> : null}
      </div>

      {data ? (
        <>
          <div className="grid gap-3 md:grid-cols-3">
            <Card>
              <CardHeader><CardTitle>Health</CardTitle></CardHeader>
              <CardContent className="space-y-2">
                <ObjectReadout data={(data.health as Record<string, unknown> | undefined) ?? {}} />
                <AdvancedRawJson data={data.health} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Metrics</CardTitle></CardHeader>
              <CardContent className="space-y-2">
                <ObjectReadout data={(data.metrics as Record<string, unknown> | undefined) ?? {}} />
                <AdvancedRawJson data={data.metrics} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Services</CardTitle></CardHeader>
              <CardContent className="space-y-2">
                {Array.isArray(data.services) ? (
                  <RecordTableReadout rows={data.services as Array<Record<string, unknown>>} />
                ) : (
                  <ObjectReadout data={(data.services as Record<string, unknown> | undefined) ?? {}} />
                )}
                <AdvancedRawJson data={data.services} />
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader><CardTitle>Quick Actions</CardTitle></CardHeader>
            <CardContent className="flex flex-wrap gap-2 items-end">
              <Button size="sm" onClick={() => createJob.mutate({ nodeId: id, type: "monitor.snapshot", params: {} })} disabled={createJob.isPending}>
                <Play size={12} /> monitor.snapshot
              </Button>

              <div className="space-y-1">
                <p className="text-xs text-muted-foreground">systemd.restart</p>
                <Input value={serviceName} onChange={(e) => setServiceName(e.target.value)} placeholder="service name" />
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => createJob.mutate({ nodeId: id, type: "systemd.restart", params: { service_name: serviceName } })}
                disabled={createJob.isPending || !serviceName.trim()}
              >
                Restart service
              </Button>
              {createJob.error ? <p className="text-xs text-danger">{String(createJob.error)}</p> : null}
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}

export function RemoteJobsPage() {
  const { data = [], isLoading, error, refetch } = useRemoteJobs();

  return (
    <div className="space-y-4">
      <PageHeader
        compact
        title="Remote Ops Jobs"
        actions={<Button variant="outline" onClick={() => refetch()}><RefreshCw size={13} /> Refresh</Button>}
      >
        <RemoteOpsTabs />
      </PageHeader>

      {isLoading ? <p className="text-sm text-muted-foreground">Loading jobs...</p> : null}
      {error ? <p className="text-sm text-danger">{String(error)}</p> : null}

      <Card>
        <CardContent className="pt-4">
          <div className="max-h-[620px] overflow-auto rounded-lg border border-border">
            <table className="w-full text-left text-xs">
              <thead className="bg-background/40 text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">Job ID</th>
                  <th className="px-3 py-2">Node</th>
                  <th className="px-3 py-2">Type</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Created By</th>
                  <th className="px-3 py-2">Action</th>
                </tr>
              </thead>
              <tbody>
                {data.map((job) => (
                  <tr key={job.id} className="border-t border-border/60">
                    <td className="px-3 py-2 font-mono">{job.id.slice(0, 10)}</td>
                    <td className="px-3 py-2">{job.node_id}</td>
                    <td className="px-3 py-2">{job.job_type}</td>
                    <td className="px-3 py-2">{job.status}</td>
                    <td className="px-3 py-2">{job.created_by}</td>
                    <td className="px-3 py-2">
                      <Link to={`/modules/remote-ops/jobs/${job.id}`}><Button size="sm" variant="outline">View</Button></Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export function RemoteJobDetailPage() {
  const { id = "" } = useParams();
  const { data, isLoading, error, refetch } = useRemoteJob(id || null);
  const patchJob = usePatchRemoteJob();

  const [lines, setLines] = useState<string[]>([]);

  useEffect(() => {
    if (!id) return;
    setLines([]);
    const adminToken = window.localStorage.getItem("dashburg.remoteops.adminToken") ?? "";
    const clientToken = window.localStorage.getItem("dashburg.remoteops.clientToken") ?? "";
    const qs = new URLSearchParams();
    if (adminToken) qs.set("admin_token", adminToken);
    if (clientToken) qs.set("client_token", clientToken);
    const streamUrl = `${eventsUrl(`/api/remote/jobs/${id}/stream`)}${qs.toString() ? `?${qs.toString()}` : ""}`;
    const source = new EventSource(streamUrl);

    source.addEventListener("log", (evt) => {
      try {
        const payload = JSON.parse((evt as MessageEvent).data) as { line?: string };
        if (!payload.line) return;
        setLines((prev) => [...prev, payload.line!].slice(-4000));
      } catch {
        // ignore
      }
    });

    source.addEventListener("status", () => {
      refetch();
    });

    return () => source.close();
  }, [id, refetch]);

  return (
    <div className="space-y-4">
      <PageHeader
        compact
        title={`Job Detail · ${id}`}
        actions={<Link to="/modules/remote-ops/jobs"><Button variant="outline" size="sm">Back</Button></Link>}
      >
        <RemoteOpsTabs />
      </PageHeader>

      {isLoading ? <p className="text-sm text-muted-foreground">Loading...</p> : null}
      {error ? <p className="text-sm text-danger">{String(error)}</p> : null}

      {data ? (
        <>
          <Card>
            <CardHeader className="pb-2"><CardTitle>Status</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p><span className="text-muted-foreground">Type:</span> {data.job_type}</p>
              <p><span className="text-muted-foreground">Node:</span> {data.node_id}</p>
              <p><span className="text-muted-foreground">Runner Job:</span> {data.runner_job_id}</p>
              <p><span className="text-muted-foreground">Status:</span> {data.status}</p>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => patchJob.mutate({ jobId: data.id, merged_label: !data.merged_label })}>
                  {data.merged_label ? "Unmark merged" : "Mark merged"}
                </Button>
                <Button size="sm" variant="outline" onClick={() => patchJob.mutate({ jobId: data.id, archived: !data.archived })}>
                  {data.archived ? "Unarchive" : "Archive"}
                </Button>
                <Link to={`/modules/remote-ops/terminal?inject=remoteops%20job%20tail%20${encodeURIComponent(data.id)}`}>
                  <Button size="sm" variant="outline">Send to Terminal</Button>
                </Link>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2"><Terminal size={12} /> Live Logs</CardTitle></CardHeader>
            <CardContent>
              <pre className="max-h-[420px] overflow-auto rounded-lg border border-border bg-background/40 p-3 text-xs leading-relaxed whitespace-pre-wrap">
                {lines.length > 0 ? lines.join("\n") : "Waiting for logs..."}
              </pre>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2"><CardTitle>Artifacts</CardTitle></CardHeader>
            <CardContent>
              <div className="space-y-2">
                {Array.isArray(data.result) ? (
                  <RecordTableReadout rows={data.result as Array<Record<string, unknown>>} />
                ) : (
                  <ObjectReadout data={(data.result as Record<string, unknown> | undefined) ?? {}} />
                )}
                <AdvancedRawJson data={data.result} />
              </div>
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}

export function RemoteCodexJobsPage() {
  const { streamingMode } = useStreamingMode();
  const displayRepoRef = (value: string) => withStreamingObfuscation(value, streamingMode, "repo");
  const { data: servers = [] } = useRemoteServers();
  const createJob = useCreateRemoteJob();

  const codexServers = useMemo(() => servers.filter((s) => s.codex_enabled), [servers]);
  const [nodeId, setNodeId] = useState("");
  const [repoPath, setRepoPath] = useState("");
  const [prompt, setPrompt] = useState("");
  const [branchName, setBranchName] = useState("");

  useEffect(() => {
    if (!nodeId && codexServers.length > 0) {
      setNodeId(codexServers[0].id);
    }
  }, [codexServers, nodeId]);

  const active: RemoteServer | undefined = codexServers.find((s) => s.id === nodeId);

  return (
    <div className="space-y-4">
      <PageHeader compact title="Remote Ops Codex Jobs">
        <RemoteOpsTabs />
      </PageHeader>
      <Card>
        <CardHeader className="pb-2"><CardTitle>Create Codex Job</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-2 md:grid-cols-2">
            <label className="text-xs text-muted-foreground">
              Target node
              <select
                value={nodeId}
                onChange={(e) => {
                  setNodeId(e.target.value);
                  setRepoPath("");
                }}
                className="mt-1 w-full rounded border border-border bg-input px-2 py-2 text-sm text-foreground"
              >
                {codexServers.map((s) => (
                  <option key={s.id} value={s.id}>{s.name} ({s.id})</option>
                ))}
              </select>
            </label>
            <label className="text-xs text-muted-foreground">
              Repo path
              <select
                value={repoPath}
                onChange={(e) => setRepoPath(e.target.value)}
                className="mt-1 w-full rounded border border-border bg-input px-2 py-2 text-sm text-foreground"
              >
                <option value="">Select repo</option>
                {(active?.repos ?? []).map((repo) => (
                  <option key={repo} value={repo}>
                    {displayRepoRef(repo)}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <Input placeholder="Optional branch name" value={branchName} onChange={(e) => setBranchName(e.target.value)} />
          <Textarea rows={7} placeholder="Codex prompt" value={prompt} onChange={(e) => setPrompt(e.target.value)} />

          <Button
            onClick={() =>
              createJob.mutate({
                nodeId,
                type: "codex.exec",
                params: { repo_path: repoPath, prompt, branch_name: branchName || undefined },
              })
            }
            disabled={!nodeId || !repoPath || !prompt.trim() || createJob.isPending}
          >
            {createJob.isPending ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} Submit Codex Job
          </Button>

          {createJob.data ? <Link to={`/modules/remote-ops/jobs/${createJob.data.id}`} className="text-sm text-primary underline">Open job detail</Link> : null}
          {createJob.error ? <p className="text-sm text-danger">{String(createJob.error)}</p> : null}
        </CardContent>
      </Card>
    </div>
  );
}

export function RemoteTerminalPage() {
  const { streamingMode } = useStreamingMode();
  const { data: servers = [] } = useRemoteServers();
  const createSession = useCreateTerminalSession();
  const killSession = useKillTerminalSession();

  const location = useLocation();
  const params = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const injectedCommand = params.get("inject") ?? "";

  const terminalNodes = useMemo(() => servers.filter((s) => s.supports_terminal), [servers]);
  const [nodeId, setNodeId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [availableSessionId, setAvailableSessionId] = useState("");
  const [connected, setConnected] = useState(false);
  const [lines, setLines] = useState<string[]>([]);
  const [socketEpoch, setSocketEpoch] = useState(0);
  const [adminToken, setAdminToken] = useState(() => localStorage.getItem("dashburg.remoteops.adminToken") ?? "");
  const [clientToken, setClientToken] = useState(() => localStorage.getItem("dashburg.remoteops.clientToken") ?? "");
  const [terminalLoadError, setTerminalLoadError] = useState("");
  const terminalApiRef = useRef<TerminalSurfaceApi | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const terminalResizeRef = useRef<{ cols: number; rows: number } | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const reconnectAttemptRef = useRef(0);
  const autoReconnectRef = useRef(true);
  const terminalExitCodeRef = useRef<number | null>(null);
  const suppressAutoAttachRef = useRef(false);
  const sessionStorageKey = useMemo(
    () => (nodeId ? `dashburg.remoteops.lastSession.${nodeId}` : ""),
    [nodeId],
  );

  const sendTerminalResize = () => {
    const ws = wsRef.current;
    const api = terminalApiRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN || !api) return;
    const term = api.getTerminalSize();
    const cols = Math.max(20, term.cols || 0);
    const rows = Math.max(10, term.rows || 0);
    if (terminalResizeRef.current && terminalResizeRef.current.cols === cols && terminalResizeRef.current.rows === rows) {
      return;
    }
    terminalResizeRef.current = { cols, rows };
    ws.send(JSON.stringify({ type: "resize", cols, rows }));
  };

  const { data: activeSession, isLoading: activeSessionLoading } = useActiveTerminalSession(nodeId || null);

  useEffect(() => {
    if (!nodeId && terminalNodes.length > 0) setNodeId(terminalNodes[0].id);
  }, [nodeId, terminalNodes]);

  useEffect(() => {
    const activeId = activeSession?.session_id ?? "";
    setAvailableSessionId(activeId);
    if (activeId && !sessionId && !suppressAutoAttachRef.current) {
      setSessionId(activeId);
      return;
    }
  }, [activeSession?.session_id, activeSessionLoading, connected]);

  useEffect(() => {
    if (!sessionStorageKey) return;
    const saved = localStorage.getItem(sessionStorageKey) ?? "";
    if (saved && !sessionId && !suppressAutoAttachRef.current) setSessionId(saved);
  }, [sessionStorageKey, sessionId]);

  useEffect(() => {
    if (!sessionStorageKey) return;
    if (sessionId) localStorage.setItem(sessionStorageKey, sessionId);
    else localStorage.removeItem(sessionStorageKey);
  }, [sessionStorageKey, sessionId]);

  useEffect(() => {
    localStorage.setItem("dashburg.remoteops.adminToken", adminToken);
  }, [adminToken]);

  useEffect(() => {
    localStorage.setItem("dashburg.remoteops.clientToken", clientToken);
  }, [clientToken]);

  const sendInput = (text: string) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "input", data: text }));
  };

  const haltAutoReconnect = (message: string) => {
    autoReconnectRef.current = false;
    reconnectAttemptRef.current = 0;
    suppressAutoAttachRef.current = true;
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (sessionStorageKey) {
      localStorage.removeItem(sessionStorageKey);
    }
    setLines((prev) => [...prev, message].slice(-5000));
    terminalApiRef.current?.write(`${message}\r\n`);
  };

  useEffect(() => {
    return () => {
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!sessionId) return;

    const qs = new URLSearchParams();
    if (adminToken) qs.set("admin_token", adminToken);
    if (clientToken) qs.set("client_token", clientToken);
    const url = websocketUrl(`/api/remote/terminal/sessions/${sessionId}/ws`, qs);
    const ws = new WebSocket(url);
    wsRef.current = ws;
    let closedByCleanup = false;
    let didOpen = false;

    ws.onopen = () => {
      didOpen = true;
      autoReconnectRef.current = true;
      reconnectAttemptRef.current = 0;
      terminalExitCodeRef.current = null;
      terminalResizeRef.current = null;
      setConnected(true);
      setLines((prev) => [...prev, "[connected]"]);
      terminalApiRef.current?.write("[connected]\r\n");
      terminalApiRef.current?.fit();
      terminalApiRef.current?.focus();
      sendTerminalResize();
      if (injectedCommand) ws.send(JSON.stringify({ type: "input", data: `${injectedCommand}\n` }));
    };
    ws.onclose = (event) => {
      setConnected(false);
      setLines((prev) => [...prev, "[disconnected]"]);
      terminalApiRef.current?.write("[disconnected]\r\n");
      if (!closedByCleanup && sessionId && autoReconnectRef.current) {
        const knownExitCode = terminalExitCodeRef.current ?? 0;
        if (knownExitCode === 401 || knownExitCode === 403 || knownExitCode === 410) {
          if (knownExitCode === 410) {
            haltAutoReconnect("[session unavailable; attach/open a new session]");
            setSessionId("");
            setAvailableSessionId("");
          } else {
            haltAutoReconnect("[auth denied; update token then click Reconnect]");
          }
          return;
        }
        const attempt = reconnectAttemptRef.current + 1;
        reconnectAttemptRef.current = attempt;
        if (event.code === 1008 || event.code === 4001 || event.code === 4401 || event.code === 4403) {
          const reason = (event.reason || "").toLowerCase();
          const authDenied = reason.includes("401") || reason.includes("403") || reason.includes("unauthorized") || reason.includes("forbidden");
          if (authDenied || event.code === 4001 || event.code === 4401 || event.code === 4403) {
            haltAutoReconnect("[auth denied; update token then click Reconnect]");
          } else {
            haltAutoReconnect("[session unavailable; attach/open a new session]");
          }
          setSessionId("");
        } else {
          if (!didOpen && attempt >= 3) {
            haltAutoReconnect("[connection failed repeatedly; click Reconnect]");
            return;
          }
          const delay = Math.min(12_000, 700 * attempt);
          if (reconnectTimerRef.current !== null) window.clearTimeout(reconnectTimerRef.current);
          reconnectTimerRef.current = window.setTimeout(() => {
            setSocketEpoch((v) => v + 1);
          }, delay);
        }
      }
    };
    ws.onerror = () => {
      setConnected(false);
      setLines((prev) => [...prev, "[terminal websocket error]"]);
      terminalApiRef.current?.write("[terminal websocket error]\r\n");
    };
    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as { type: string; data?: string; code?: number };
        const output = typeof payload.data === "string" ? payload.data : "";
        if (payload.type === "output" && output) {
          terminalApiRef.current?.write(output);
          setLines((prev) => [...prev, output].slice(-5000));
        }
        if (payload.type === "exit") {
          const exitCode = payload.code ?? 0;
          terminalExitCodeRef.current = exitCode;
          const line = `[exit code ${exitCode}]`;
          terminalApiRef.current?.write(`${line}\r\n`);
          setLines((prev) => [...prev, line].slice(-5000));
          if (exitCode === 401 || exitCode === 403) {
            haltAutoReconnect("[auth denied; update token then click Reconnect]");
          } else if (exitCode === 410) {
            haltAutoReconnect("[session unavailable; attach/open a new session]");
            setSessionId("");
            setAvailableSessionId("");
          }
          setConnected(false);
        }
      } catch {
        // ignore
      }
    };

    return () => {
      closedByCleanup = true;
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      ws.close();
      if (wsRef.current === ws) wsRef.current = null;
    };
  }, [sessionId, adminToken, clientToken, injectedCommand, socketEpoch]);

  return (
    <div className="space-y-4">
      <PageHeader compact title="Remote Ops Terminal">
        <RemoteOpsTabs />
      </PageHeader>

      <Card className="colFlexMin0 min-h-[78vh]">
        <CardHeader className="pb-2"><CardTitle>Connect to Main</CardTitle></CardHeader>
        <CardContent className="flex1Min0 space-y-2 min-h-0">
          <div className="grid gap-2 md:grid-cols-5">
            <label className="text-xs text-muted-foreground md:col-span-2">
              Terminal node
              <select
                value={nodeId}
                onChange={(e) => setNodeId(e.target.value)}
                className="mt-1 w-full rounded border border-border bg-input px-2 py-2 text-sm text-foreground"
              >
                <option value="">Select node</option>
                {terminalNodes.map((n) => <option key={n.id} value={n.id}>{n.name} ({n.id})</option>)}
              </select>
            </label>
            <label className="text-xs text-muted-foreground">
              Admin token (optional)
              <Input
                type="text"
                value={streamingMode ? "" : adminToken}
                onChange={(e) => {
                  if (streamingMode) return;
                  setAdminToken(e.target.value);
                }}
                placeholder={streamingMode ? "[hidden in streaming mode]" : "REMOTEOPS_ADMIN_TOKEN"}
                disabled={streamingMode}
              />
            </label>
            <label className="text-xs text-muted-foreground">
              Client token (recommended)
              <Input
                type="text"
                value={streamingMode ? "" : clientToken}
                onChange={(e) => {
                  if (streamingMode) return;
                  setClientToken(e.target.value);
                }}
                placeholder={streamingMode ? "[hidden in streaming mode]" : "chat_client_token"}
                disabled={streamingMode}
              />
            </label>
            <div className="flex flex-wrap items-end gap-2 md:justify-end">
              <Button
                size="sm"
                onClick={() => {
                  suppressAutoAttachRef.current = false;
                  createSession.mutate({ node_id: nodeId }, { onSuccess: (res) => setSessionId(res.session_id) });
                }}
                disabled={!nodeId || createSession.isPending}
              >
                {createSession.isPending ? <Loader2 size={13} className="animate-spin" /> : null}
                Connect
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  if (!availableSessionId) return;
                  suppressAutoAttachRef.current = false;
                  autoReconnectRef.current = true;
                  reconnectAttemptRef.current = 0;
                  setSessionId(availableSessionId);
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
                  suppressAutoAttachRef.current = false;
                  autoReconnectRef.current = true;
                  reconnectAttemptRef.current = 0;
                  setSocketEpoch((v) => v + 1);
                }}
                disabled={!sessionId || connected}
              >
                Reconnect
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  if (!sessionId) return;
                  autoReconnectRef.current = false;
                  killSession.mutate(sessionId, {
                    onSuccess: () => {
                      reconnectAttemptRef.current = 0;
                      setConnected(false);
                      setSessionId("");
                      setAvailableSessionId("");
                      setLines((prev) => [...prev, "[connection closed]"]);
                      terminalApiRef.current?.write("\r\n[connection closed]\r\n");
                    },
                  });
                }}
                disabled={!sessionId}
              >
                Close connection
              </Button>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs min-w-0">
            <span className={`inline-flex rounded-full px-2 py-1 ${connected ? "bg-success/20 text-success" : "bg-muted text-muted-foreground"}`}>
              {connected ? "connected" : "disconnected"}
            </span>
            <span className="text-muted-foreground max-w-full break-all">session: {sessionId || "-"}</span>
            <span className="text-muted-foreground">ui: terminal-r5</span>
            {!sessionId && availableSessionId ? <span className="text-muted-foreground max-w-full break-all">active available: {availableSessionId}</span> : null}
          </div>

          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => sendInput(`${SHARED_MEM_CODEX_CMD}\n`)}>Start Codex</Button>
            <Button size="sm" variant="outline" onClick={() => sendInput("remoteops nodes list\n")}>Nodes list</Button>
            <Button size="sm" variant="outline" onClick={() => sendInput("remoteops node info main\n")}>Main status</Button>
            <Button size="sm" variant="outline" onClick={() => sendInput("remoteops job tail ")}>Tail latest job</Button>
            <Button size="sm" variant="outline" onClick={() => sendInput("\u0003")}>Send SIGINT (^C)</Button>
            <Button size="sm" variant="outline" onClick={() => terminalApiRef.current?.clear()}>Clear</Button>
          </div>

          <div
            className="terminalHost terminalCard flex1Min0 h-[74vh] min-h-[540px]"
            onClick={() => terminalApiRef.current?.focus()}
          >
            <TerminalSurface
              isActive
              className="h-full w-full"
              inputEnabled={connected}
              onReady={(api) => {
                terminalApiRef.current = api;
                if (api) setTerminalLoadError("");
              }}
              onError={(message) => setTerminalLoadError(message)}
              onData={(data) => {
                if (!shouldForwardTerminalInput(data)) return;
                const ws = wsRef.current;
                if (!ws || ws.readyState !== WebSocket.OPEN) return;
                ws.send(JSON.stringify({ type: "input", data }));
              }}
              onResize={() => sendTerminalResize()}
            />
          </div>
          {terminalLoadError ? <p className="text-danger">{terminalLoadError}</p> : null}
        </CardContent>
      </Card>
    </div>
  );
}
