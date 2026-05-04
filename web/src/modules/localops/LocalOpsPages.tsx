import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Bot, Loader2, Play, Plus, Settings as SettingsIcon, Terminal, Trash2 } from "lucide-react";

import {
  useApproveLocalOpsToolCall,
  useCancelLocalOpsRun,
  useCreateLocalOpsAgentSession,
  useCreateLocalOpsProvider,
  useCreateLocalOpsTerminalSession,
  useCreateLocalOpsThread,
  useDeleteLocalOpsThread,
  useDeleteLocalOpsProvider,
  useDisconnectOpenAiOauth,
  useKillLocalOpsTerminalSession,
  useLocalOpsActiveTerminalSession,
  useLocalOpsAgentPacks,
  useLocalOpsAgentSessionFile,
  useLocalOpsAgentSessions,
  useLocalOpsProviders,
  useLocalOpsRun,
  useLocalOpsSettings,
  useLocalOpsThread,
  useLocalOpsThreads,
  useOpenAiOauthStatus,
  useOpenAiModels,
  useOllamaModels,
  usePostLocalOpsMessage,
  useRunLocalOpsAgentSession,
  useSetOpenAiApiKey,
  useSaveLocalOpsAgentSessionFile,
  useTestOllama,
  useUpdateLocalOpsAgentSession,
  useUpdateLocalOpsProvider,
  useUpdateLocalOpsSettings,
  useUpsertLocalOpsAgentPack,
} from "../../shared/api/hooks";
import type { LocalOpsExecutionMode, LocalOpsSettings } from "../../shared/api/types";
import { ApiError, eventsUrl, websocketUrl } from "../../shared/api/client";
import { Button } from "../../shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../shared/components/ui/card";
import { TerminalSurface, type TerminalSurfaceApi } from "../../shared/components/terminal/TerminalSurface";
import { Input, Textarea } from "../../shared/components/ui/input";
import { PageHeader } from "../../shared/components/ui/page-header";
import { AdvancedRawJson, ObjectReadout } from "../../shared/components/ui/readouts";

function localOpsToken(): string {
  return window.localStorage.getItem("dashburg.localops.token") ?? "";
}

function setLocalOpsToken(token: string) {
  window.localStorage.setItem("dashburg.localops.token", token.trim());
}

type LocalOpsDispatchDebugEntry = {
  ts: string;
  kind: "create_thread_request" | "create_thread_response" | "send_message_request" | "send_message_response" | "thread_state" | "run_state";
  thread_id?: string;
  run_id?: string;
  provider_id?: "openai" | "ollama";
  provider_endpoint_id?: number | null;
  model?: string;
  execution_mode?: LocalOpsExecutionMode;
  note?: string;
};

const TERMINAL_DA_RESPONSE_RE = /^(?:\x1b\[\?[0-9;]*c|\x1b\[>[0-9;]*c|[0-9]+(?:;[0-9]+)*c)$/;
const SHARED_MEM_CODEX_CMD =
  'codex "Please load cluster memory from /srv/dashburg/shared/MEM.md first when available; if unavailable, fallback to ~/MEM.md, and use that as host topology memory for this session. For remote investigations, open ONE persistent SSH session per target host and run multiple commands inside that session; avoid one-off ssh command invocations unless necessary. Before finishing any remote investigation, write two markdown files on that remote machine under ~/runner/investigations/: (1) a timestamped conclusion file with findings and next actions, and (2) a host/repo profile file with durable observations, discovered settings, and known issues so future agents can understand the device/repo quickly. Summarize key nodes and SSH/RemoteOps commands first."';

function shouldForwardTerminalInput(data: string): boolean {
  const normalized = data.replace(/[\r\n]+/g, "");
  if (!normalized) return true;
  return !TERMINAL_DA_RESPONSE_RE.test(normalized);
}

function LocalOpsTabs() {
  const location = useLocation();

  const tabs = [
    { href: "/modules/local-ops/chat", label: "Chat", icon: <Play size={12} /> },
    { href: "/modules/local-ops/settings", label: "Settings", icon: <SettingsIcon size={12} /> },
  ];

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {tabs.map((tab) => (
          <Link key={tab.href} to={tab.href}>
            <Button variant={location.pathname.startsWith(tab.href) ? "default" : "outline"} size="sm">
              {tab.icon}
              {tab.label}
            </Button>
          </Link>
        ))}
      </div>
    </div>
  );
}

export function LocalOpsSettingsPage() {
  const { data: settings, isLoading, error } = useLocalOpsSettings();
  const saveSettings = useUpdateLocalOpsSettings();
  const { data: providers = [] } = useLocalOpsProviders();
  const createProvider = useCreateLocalOpsProvider();
  const updateProvider = useUpdateLocalOpsProvider();
  const deleteProvider = useDeleteLocalOpsProvider();
  const openAiStatus = useOpenAiOauthStatus();
  const setOpenAiApiKey = useSetOpenAiApiKey();
  const disconnectOpenAi = useDisconnectOpenAiOauth();
  const testOllama = useTestOllama();

  const [form, setForm] = useState<LocalOpsSettings | null>(null);
  const [providerForm, setProviderForm] = useState({
    name: "homelab-ollama",
    base_url: "http://127.0.0.1:11434",
    enabled: true,
    default_for_agents: false,
  });
  const [adminTokenInput, setAdminTokenInput] = useState(() => localOpsToken());
  const [openAiKeyInput, setOpenAiKeyInput] = useState("");

  useEffect(() => {
    if (settings) setForm(settings);
  }, [settings]);

  return (
    <div className="space-y-4">
      <PageHeader compact title="LocalOps Settings">
        <LocalOpsTabs />
      </PageHeader>

      {isLoading ? <p className="text-sm text-muted-foreground">Loading settings...</p> : null}
      {error ? <p className="text-sm text-danger">{String(error)}</p> : null}

      <Card>
        <CardHeader className="pb-2"><CardTitle>LocalOps Access</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          <label className="text-xs text-muted-foreground">
            LocalOps admin token
            <Input value={adminTokenInput} onChange={(e) => setAdminTokenInput(e.target.value)} placeholder="LOCALOPS_ADMIN_TOKEN" />
          </label>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => setLocalOpsToken(adminTokenInput)}>
              Save Token
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setAdminTokenInput("");
                setLocalOpsToken("");
              }}
            >
              Clear Token
            </Button>
            <p className="text-xs text-muted-foreground">Stored in localStorage, used as `X-LocalOps-Token`.</p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2"><CardTitle>OpenAI API Key</CardTitle></CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p className="text-muted-foreground">
            Status: {openAiStatus.data?.configured ? "Configured" : "Not configured"}
            {openAiStatus.data?.source ? ` · source: ${openAiStatus.data.source}` : ""}
            {openAiStatus.data?.masked ? ` · ${openAiStatus.data.masked}` : ""}
          </p>
          <div className="flex gap-2">
            <Input
              placeholder="sk-..."
              value={openAiKeyInput}
              onChange={(e) => setOpenAiKeyInput(e.target.value)}
            />
            <Button
              onClick={() =>
                setOpenAiApiKey.mutate(openAiKeyInput, {
                  onSuccess: () => setOpenAiKeyInput(""),
                })
              }
              disabled={setOpenAiApiKey.isPending || !openAiKeyInput.trim()}
            >
              Save API Key
            </Button>
            <Button variant="outline" onClick={() => disconnectOpenAi.mutate()} disabled={disconnectOpenAi.isPending}>
              Clear
            </Button>
          </div>
          {openAiStatus.error ? <p className="text-xs text-danger">{String(openAiStatus.error)}</p> : null}
        </CardContent>
      </Card>

      {form ? (
        <Card>
          <CardHeader className="pb-2"><CardTitle>LocalOps Limits + Defaults</CardTitle></CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-3">
            <label className="text-xs text-muted-foreground">Default provider
              <select
                className="mt-1 w-full rounded border border-border bg-input px-2 py-2 text-sm text-foreground"
                value={form.default_provider_id}
                onChange={(e) => setForm({ ...form, default_provider_id: e.target.value as LocalOpsSettings["default_provider_id"] })}
              >
                <option value="openai">openai</option>
                <option value="ollama">ollama</option>
              </select>
            </label>
            <label className="text-xs text-muted-foreground">Default model
              <Input value={form.default_model} onChange={(e) => setForm({ ...form, default_model: e.target.value })} />
            </label>
            <label className="text-xs text-muted-foreground">Execution mode
              <select
                className="mt-1 w-full rounded border border-border bg-input px-2 py-2 text-sm text-foreground"
                value={form.execution_mode}
                onChange={(e) => setForm({ ...form, execution_mode: e.target.value as LocalOpsExecutionMode })}
              >
                <option value="propose_only">propose_only</option>
                <option value="require_confirm">require_confirm</option>
                <option value="auto_execute_allowlisted">auto_execute_allowlisted</option>
              </select>
            </label>
            <label className="text-xs text-muted-foreground">Max tool steps
              <Input type="number" value={form.max_tool_steps_per_run} onChange={(e) => setForm({ ...form, max_tool_steps_per_run: Number(e.target.value || 8) })} />
            </label>
            <label className="text-xs text-muted-foreground">Max run seconds
              <Input type="number" value={form.max_run_seconds} onChange={(e) => setForm({ ...form, max_run_seconds: Number(e.target.value || 600) })} />
            </label>
            <label className="text-xs text-muted-foreground">Max concurrent runs
              <Input type="number" value={form.max_concurrent_runs} onChange={(e) => setForm({ ...form, max_concurrent_runs: Number(e.target.value || 2) })} />
            </label>
            <label className="text-xs text-muted-foreground">Terminal idle timeout (minutes)
              <Input
                type="number"
                value={form.terminal_idle_timeout_minutes}
                onChange={(e) => setForm({ ...form, terminal_idle_timeout_minutes: Number(e.target.value || 30) })}
              />
            </label>
            <label className="text-xs text-muted-foreground md:col-span-3">
              Shell allowlist prefixes (one per line)
              <Textarea
                rows={3}
                value={form.shell_allowlist.join("\n")}
                onChange={(e) => setForm({ ...form, shell_allowlist: e.target.value.split("\n").map((v) => v.trim()).filter(Boolean) })}
              />
            </label>
            <label className="inline-flex items-center gap-2 text-xs md:col-span-3">
              <input type="checkbox" checked={form.allow_shell_exec} onChange={(e) => setForm({ ...form, allow_shell_exec: e.target.checked })} />
              allow_shell_exec
            </label>
            <div className="md:col-span-3">
              <Button onClick={() => saveSettings.mutate(form)} disabled={saveSettings.isPending}>
                {saveSettings.isPending ? <Loader2 size={13} className="animate-spin" /> : null}
                Save Settings
              </Button>
              {saveSettings.error ? <p className="mt-2 text-xs text-danger">{String(saveSettings.error)}</p> : null}
            </div>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader className="pb-2"><CardTitle>Ollama Providers</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs text-muted-foreground">Recommended for your setup: base URL `http://127.0.0.1:11434` and default model `qwen3:8b`.</p>
          <div className="grid gap-2 md:grid-cols-5">
            <Input placeholder="name" value={providerForm.name} onChange={(e) => setProviderForm((p) => ({ ...p, name: e.target.value }))} />
            <Input placeholder="base_url" value={providerForm.base_url} onChange={(e) => setProviderForm((p) => ({ ...p, base_url: e.target.value }))} className="md:col-span-2" />
            <label className="inline-flex items-center gap-2 text-xs"><input type="checkbox" checked={providerForm.enabled} onChange={(e) => setProviderForm((p) => ({ ...p, enabled: e.target.checked }))} />enabled</label>
            <label className="inline-flex items-center gap-2 text-xs"><input type="checkbox" checked={providerForm.default_for_agents} onChange={(e) => setProviderForm((p) => ({ ...p, default_for_agents: e.target.checked }))} />default_for_agents</label>
          </div>
          <div className="flex gap-2">
            <Button
              onClick={() => createProvider.mutate({ provider_id: "ollama", ...providerForm, extra: {} })}
              disabled={createProvider.isPending || !providerForm.name.trim() || !providerForm.base_url.trim()}
            >
              Add Ollama Provider
            </Button>
            <Button variant="outline" onClick={() => testOllama.mutate(providerForm.base_url)}>
              Test Connection
            </Button>
            {testOllama.data ? <p className="text-xs text-muted-foreground">OK · models: {testOllama.data.models_count ?? 0}</p> : null}
            {testOllama.error ? <p className="text-xs text-danger">{String(testOllama.error)}</p> : null}
          </div>

          <div className="space-y-2">
            {providers.filter((p) => p.provider_id === "ollama").map((provider) => (
              <div key={provider.id} className="grid gap-2 rounded border border-border p-2 md:grid-cols-5">
                <Input value={provider.name} onChange={(e) => updateProvider.mutate({ providerId: provider.id, payload: { ...provider, name: e.target.value, api_key: "" } })} />
                <Input value={provider.base_url} className="md:col-span-2" onChange={(e) => updateProvider.mutate({ providerId: provider.id, payload: { ...provider, base_url: e.target.value, api_key: "" } })} />
                <label className="inline-flex items-center gap-2 text-xs"><input type="checkbox" checked={provider.enabled} onChange={(e) => updateProvider.mutate({ providerId: provider.id, payload: { ...provider, enabled: e.target.checked, api_key: "" } })} />enabled</label>
                <div className="flex justify-end">
                  <Button variant="outline" size="sm" onClick={() => deleteProvider.mutate(provider.id)}>Delete</Button>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export function LocalOpsChatPage() {
  const { data: settings } = useLocalOpsSettings();
  const { data: providers = [] } = useLocalOpsProviders();
  const threadsQuery = useLocalOpsThreads();
  const threads = threadsQuery.data ?? [];
  const refetchThreads = threadsQuery.refetch;
  const createThread = useCreateLocalOpsThread();
  const deleteThread = useDeleteLocalOpsThread();
  const postMessage = usePostLocalOpsMessage();
  const approveTool = useApproveLocalOpsToolCall();
  const cancelRun = useCancelLocalOpsRun();
  const activeTerminalQuery = useLocalOpsActiveTerminalSession();
  const createTerminalSession = useCreateLocalOpsTerminalSession();
  const killTerminalSession = useKillLocalOpsTerminalSession();
  const agentPacks = useLocalOpsAgentPacks();
  const agentSessions = useLocalOpsAgentSessions();
  const createAgentSession = useCreateLocalOpsAgentSession();
  const updateAgentSession = useUpdateLocalOpsAgentSession();
  const upsertAgentPack = useUpsertLocalOpsAgentPack();
  const runAgentSession = useRunLocalOpsAgentSession();
  const saveAgentSessionFile = useSaveLocalOpsAgentSessionFile();

  const [threadId, setThreadId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [liveChunks, setLiveChunks] = useState<string[]>([]);
  const [centerMode, setCenterMode] = useState<"chat" | "terminal">("chat");
  const [sideTab, setSideTab] = useState<"run" | "agents">("run");
  const [terminalSessionId, setTerminalSessionId] = useState(() => window.localStorage.getItem("dashburg.localops.terminalSessionId") ?? "");
  const [terminalConnected, setTerminalConnected] = useState(false);
  const [terminalLoadError, setTerminalLoadError] = useState("");
  const [agentSlug, setAgentSlug] = useState("report-writer");
  const [agentName, setAgentName] = useState("");
  const [agentTitle, setAgentTitle] = useState("");
  const [agentWorkspaceRoot, setAgentWorkspaceRoot] = useState("");
  const [agentCodexModel, setAgentCodexModel] = useState("gpt-5.3-codex");
  const [agentSessionId, setAgentSessionId] = useState("");
  const [agentTask, setAgentTask] = useState("Read INPUT.md and write a polished result to OUTPUT.md.");
  const [agentInputFile, setAgentInputFile] = useState("INPUT.md");
  const [agentOutputFile, setAgentOutputFile] = useState("OUTPUT.md");
  const [agentStateFile, setAgentStateFile] = useState("STATE.md");
  const [agentMemoryFile, setAgentMemoryFile] = useState("MEM.md");
  const [agentNotesFile, setAgentNotesFile] = useState("NOTES.md");
  const [newAgentSlug, setNewAgentSlug] = useState("");
  const [newAgentTitle, setNewAgentTitle] = useState("");
  const [newAgentInstructions, setNewAgentInstructions] = useState("You are an autonomous helper. Read INPUT.md and write clear markdown to OUTPUT.md.");
  const [newAgentSkill, setNewAgentSkill] = useState("");
  const [agentEditFileKey, setAgentEditFileKey] = useState("investigations");
  const [agentFileDraft, setAgentFileDraft] = useState("");
  const [showNewThreadPrompt, setShowNewThreadPrompt] = useState(false);
  const [sendAfterThreadCreate, setSendAfterThreadCreate] = useState(false);
  const [newThreadTitle, setNewThreadTitle] = useState("New Thread");
  const [newThreadProviderId, setNewThreadProviderId] = useState<"openai" | "ollama">("openai");
  const [newThreadProviderEndpointId, setNewThreadProviderEndpointId] = useState<number | null>(null);
  const [newThreadModel, setNewThreadModel] = useState("gpt-4o-mini");
  const [newThreadExecutionMode, setNewThreadExecutionMode] = useState<LocalOpsExecutionMode>("require_confirm");
  const [dispatchDebug, setDispatchDebug] = useState<LocalOpsDispatchDebugEntry[]>([]);
  const conversationRef = useRef<HTMLDivElement | null>(null);
  const terminalApiRef = useRef<TerminalSurfaceApi | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const terminalResizeRef = useRef<{ cols: number; rows: number } | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const reconnectAttemptRef = useRef(0);
  const autoReconnectRef = useRef(true);
  const [socketEpoch, setSocketEpoch] = useState(0);
  const initializedThreadDefaultsRef = useRef(false);
  const threadLaunchOverridesRef = useRef<Record<string, { provider_id: "openai" | "ollama"; provider_endpoint_id?: number | null; model: string; execution_mode: LocalOpsExecutionMode }>>({});
  const lastThreadStateDebugRef = useRef("");
  const lastRunStateDebugRef = useRef("");
  const pushDispatchDebug = (entry: LocalOpsDispatchDebugEntry) => {
    setDispatchDebug((prev) => [entry, ...prev].slice(0, 25));
  };

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

  const sendTerminalInput = (text: string) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "input", data: text }));
  };

  useEffect(() => {
    if (!threadId && threads.length > 0) setThreadId(threads[0].id);
  }, [threadId, threads]);

  const threadDetail = useLocalOpsThread(threadId);
  const runDetail = useLocalOpsRun(activeRunId);
  const threadProviderId = threadDetail.data?.thread?.provider_id;
  const threadProviderEndpointId = threadDetail.data?.thread?.provider_endpoint_id ?? null;
  const threadModel = threadDetail.data?.thread?.model;
  const threadExecutionMode = threadDetail.data?.thread?.execution_mode;
  const providerId = (threadProviderId ?? settings?.default_provider_id ?? "openai") as "openai" | "ollama";
  const model = (threadModel ?? settings?.default_model ?? "gpt-4o-mini").trim() || "gpt-4o-mini";
  const executionMode: LocalOpsExecutionMode = (threadExecutionMode ?? settings?.execution_mode ?? "require_confirm") as LocalOpsExecutionMode;
  const ollamaProviders = providers.filter((p) => p.provider_id === "ollama");
  const preferredOllamaProvider =
    ollamaProviders.find((p) => p.enabled && threadProviderEndpointId != null && p.id === threadProviderEndpointId) ??
    ollamaProviders.find((p) => p.enabled) ??
    ollamaProviders[0];
  const ollamaModelsQuery = useOllamaModels(preferredOllamaProvider?.base_url ?? null);
  const openAiModelsQuery = useOpenAiModels();
  const newThreadModelOptions = newThreadProviderId === "openai" ? (openAiModelsQuery.data ?? []) : (ollamaModelsQuery.data ?? []);

  useEffect(() => {
    const err = threadDetail.error;
    if (!(err instanceof ApiError) || err.status !== 404 || !threadId) return;
    setThreadId(null);
    setActiveRunId(null);
    void refetchThreads();
  }, [threadDetail.error, threadId, refetchThreads]);

  useEffect(() => {
    if (!settings) return;
    if (showNewThreadPrompt) return;
    if (initializedThreadDefaultsRef.current) return;
    setNewThreadProviderId((settings.default_provider_id ?? "openai") as "openai" | "ollama");
    setNewThreadProviderEndpointId(preferredOllamaProvider?.id ?? null);
    setNewThreadModel((settings.default_model ?? "gpt-4o-mini").trim() || "gpt-4o-mini");
    setNewThreadExecutionMode((settings.execution_mode ?? "require_confirm") as LocalOpsExecutionMode);
    initializedThreadDefaultsRef.current = true;
  }, [settings, showNewThreadPrompt, preferredOllamaProvider?.id]);

  useEffect(() => {
    if (newThreadProviderId !== "ollama") {
      setNewThreadProviderEndpointId(null);
      return;
    }
    if (newThreadProviderEndpointId != null && ollamaProviders.some((p) => p.id === newThreadProviderEndpointId)) return;
    setNewThreadProviderEndpointId(preferredOllamaProvider?.id ?? null);
  }, [newThreadProviderId, newThreadProviderEndpointId, ollamaProviders, preferredOllamaProvider?.id]);

  useEffect(() => {
    if (newThreadModelOptions.length === 0) return;
    const existing = newThreadModel.trim();
    if (existing && newThreadModelOptions.includes(existing)) return;
    setNewThreadModel(newThreadModelOptions[0]);
  }, [newThreadProviderId, newThreadModelOptions]);

  useEffect(() => {
    const thread = threadDetail.data?.thread;
    if (!thread) return;
    const signature = `${thread.id}:${thread.provider_id}:${thread.provider_endpoint_id ?? ""}:${thread.model}:${thread.execution_mode}`;
    if (lastThreadStateDebugRef.current === signature) return;
    lastThreadStateDebugRef.current = signature;
    const expected = threadLaunchOverridesRef.current[thread.id];
    const mismatch = expected
      ? expected.model !== thread.model || expected.provider_id !== thread.provider_id || (expected.provider_endpoint_id ?? null) !== (thread.provider_endpoint_id ?? null) || expected.execution_mode !== thread.execution_mode
      : false;
    pushDispatchDebug({
      ts: new Date().toISOString(),
      kind: "thread_state",
      thread_id: thread.id,
      provider_id: thread.provider_id,
      provider_endpoint_id: thread.provider_endpoint_id ?? null,
      model: thread.model,
      execution_mode: thread.execution_mode,
      note: mismatch
        ? `Thread state differs from selected override (${expected?.provider_id}/${expected?.provider_endpoint_id ?? "-"}/${expected?.model}/${expected?.execution_mode})`
        : "Thread state from backend",
    });
  }, [threadDetail.data?.thread]);

  useEffect(() => {
    const run = runDetail.data?.run;
    if (!run) return;
    const signature = `${run.id}:${run.status}:${run.llm_status ?? ""}:${run.provider_id}:${run.provider_endpoint_id ?? ""}:${run.model}:${run.execution_mode}`;
    if (lastRunStateDebugRef.current === signature) return;
    lastRunStateDebugRef.current = signature;
    const expected = threadLaunchOverridesRef.current[run.thread_id];
    const mismatch = expected
      ? expected.model !== run.model || expected.provider_id !== run.provider_id || (expected.provider_endpoint_id ?? null) !== (run.provider_endpoint_id ?? null) || expected.execution_mode !== run.execution_mode
      : false;
    pushDispatchDebug({
      ts: new Date().toISOString(),
      kind: "run_state",
      thread_id: run.thread_id,
      run_id: run.id,
      provider_id: run.provider_id,
      provider_endpoint_id: run.provider_endpoint_id ?? null,
      model: run.model,
      execution_mode: run.execution_mode,
      note: mismatch
        ? `Run state differs from selected override (${expected?.provider_id}/${expected?.provider_endpoint_id ?? "-"}/${expected?.model}/${expected?.execution_mode})`
        : `Run state from backend (${run.status}${run.llm_status ? `/${run.llm_status}` : ""})`,
    });
  }, [runDetail.data?.run]);

  useEffect(() => {
    if (!agentSessionId && (agentSessions.data?.length ?? 0) > 0) {
      setAgentSessionId(agentSessions.data?.[0]?.id ?? "");
    }
  }, [agentSessionId, agentSessions.data]);

  useEffect(() => {
    if (!activeRunId) return;
    setLiveChunks([]);
    const token = localOpsToken();
    const qs = new URLSearchParams();
    if (token) qs.set("token", token);
    const source = new EventSource(`${eventsUrl(`/api/localops/runs/${activeRunId}/stream`)}${qs.toString() ? `?${qs.toString()}` : ""}`);
    source.addEventListener("token", (evt) => {
      try {
        const payload = JSON.parse((evt as MessageEvent).data) as { chunk?: string };
        const chunk = payload.chunk;
        if (typeof chunk === "string" && chunk.length > 0) {
          setLiveChunks((prev) => [...prev, chunk]);
        }
      } catch {
        // ignore
      }
    });
    source.addEventListener("run.status", () => {
      void runDetail.refetch();
      void threadDetail.refetch();
    });
    source.addEventListener("run.error", () => {
      void runDetail.refetch();
      void threadDetail.refetch();
    });
    source.addEventListener("tool.result", () => {
      void runDetail.refetch();
      void threadDetail.refetch();
    });
    source.addEventListener("tool.error", () => {
      void runDetail.refetch();
      void threadDetail.refetch();
    });
    source.addEventListener("ollama.event", () => {
      void runDetail.refetch();
    });
    return () => source.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeRunId]);

  useEffect(() => {
    const el = conversationRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [threadDetail.data?.messages, liveChunks]);

  useEffect(() => {
    const active = activeTerminalQuery.data?.session_id ?? "";
    if (active && !terminalSessionId) {
      setTerminalSessionId(active);
    }
  }, [activeTerminalQuery.data?.session_id, terminalSessionId]);

  useEffect(() => {
    if (terminalSessionId) {
      window.localStorage.setItem("dashburg.localops.terminalSessionId", terminalSessionId);
    } else {
      window.localStorage.removeItem("dashburg.localops.terminalSessionId");
    }
  }, [terminalSessionId]);

  useEffect(() => {
    return () => {
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (centerMode !== "terminal" || !terminalSessionId) return;
    const token = localOpsToken();
    const qs = new URLSearchParams();
    if (token) qs.set("token", token);
    const url = websocketUrl(`/api/localops/terminal/sessions/${terminalSessionId}/ws`, qs);
    const ws = new WebSocket(url);
    wsRef.current = ws;
    let closedByCleanup = false;
    ws.onopen = () => {
      autoReconnectRef.current = true;
      reconnectAttemptRef.current = 0;
      terminalResizeRef.current = null;
      setTerminalConnected(true);
      terminalApiRef.current?.write("[connected]\r\n");
      terminalApiRef.current?.fit();
      terminalApiRef.current?.focus();
      sendTerminalResize();
    };
    ws.onclose = (event) => {
      setTerminalConnected(false);
      terminalApiRef.current?.write("[disconnected]\r\n");
      if (!closedByCleanup && terminalSessionId && autoReconnectRef.current) {
        if (event.code === 1008) {
          autoReconnectRef.current = false;
          setTerminalSessionId("");
          void activeTerminalQuery.refetch();
          terminalApiRef.current?.write("[session unavailable; attach/open a new shell]\r\n");
          return;
        }
        const attempt = reconnectAttemptRef.current + 1;
        reconnectAttemptRef.current = attempt;
        const delay = Math.min(10_000, 700 * attempt);
        if (reconnectTimerRef.current !== null) window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = window.setTimeout(() => {
          setSocketEpoch((v) => v + 1);
        }, delay);
      }
    };
    ws.onerror = () => {
      setTerminalConnected(false);
      terminalApiRef.current?.write("[terminal websocket error]\r\n");
    };
    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as { type: string; data?: string; code?: number };
        if (payload.type === "output" && typeof payload.data === "string") terminalApiRef.current?.write(payload.data);
        if (payload.type === "exit") terminalApiRef.current?.write(`[exit code ${payload.code ?? 0}]\r\n`);
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
  }, [centerMode, terminalSessionId, socketEpoch]);

  function sendToThread(targetThreadId: string, overrides?: { provider_id?: "openai" | "ollama"; provider_endpoint_id?: number | null; model?: string; execution_mode?: LocalOpsExecutionMode }) {
    const launchOverride = threadLaunchOverridesRef.current[targetThreadId];
    const providerToSend = overrides?.provider_id ?? launchOverride?.provider_id ?? providerId;
    const providerEndpointIdToSend =
      providerToSend === "ollama"
        ? (overrides?.provider_endpoint_id ?? launchOverride?.provider_endpoint_id ?? threadProviderEndpointId ?? preferredOllamaProvider?.id ?? null)
        : null;
    const modelToSend = (overrides?.model ?? launchOverride?.model ?? model).trim();
    const modeToSend = overrides?.execution_mode ?? launchOverride?.execution_mode ?? executionMode;
    pushDispatchDebug({
      ts: new Date().toISOString(),
      kind: "send_message_request",
      thread_id: targetThreadId,
      provider_id: providerToSend,
      provider_endpoint_id: providerEndpointIdToSend,
      model: modelToSend,
      execution_mode: modeToSend,
      note: "Payload sent from LocalOps UI",
    });
    postMessage.mutate(
      {
        threadId: targetThreadId,
        payload: {
          content: draft,
          provider_id: providerToSend,
          provider_endpoint_id: providerEndpointIdToSend,
          model: modelToSend,
          execution_mode: modeToSend,
        },
      },
      {
        onSuccess: (data) => {
          pushDispatchDebug({
            ts: new Date().toISOString(),
            kind: "send_message_response",
            thread_id: targetThreadId,
            run_id: data.run_id,
            provider_id: providerToSend,
            provider_endpoint_id: providerEndpointIdToSend,
            model: modelToSend,
            execution_mode: modeToSend,
            note: "Run started",
          });
          setDraft("");
          setActiveRunId(data.run_id);
          void threadDetail.refetch();
          void refetchThreads();
        },
      },
    );
  }

  function handleSend() {
    if (!draft.trim()) return;
    if (threadId) {
      sendToThread(threadId);
      return;
    }
    setSendAfterThreadCreate(true);
    setShowNewThreadPrompt(true);
  }

  function openNewThreadPrompt() {
    setSendAfterThreadCreate(false);
    setShowNewThreadPrompt(true);
  }

  function createThreadWithSelection() {
    const selectedModel = newThreadModel.trim();
    if (!selectedModel) return;
    pushDispatchDebug({
      ts: new Date().toISOString(),
      kind: "create_thread_request",
      provider_id: newThreadProviderId,
      provider_endpoint_id: newThreadProviderId === "ollama" ? newThreadProviderEndpointId : null,
      model: selectedModel,
      execution_mode: newThreadExecutionMode,
      note: "Create thread request from modal",
    });
    createThread.mutate(
      {
        title: newThreadTitle.trim() || "New Thread",
        provider_id: newThreadProviderId,
        provider_endpoint_id: newThreadProviderId === "ollama" ? newThreadProviderEndpointId : null,
        model: selectedModel,
        execution_mode: newThreadExecutionMode,
      },
      {
        onSuccess: (row) => {
          threadLaunchOverridesRef.current[row.id] = {
            provider_id: newThreadProviderId,
            provider_endpoint_id: newThreadProviderId === "ollama" ? newThreadProviderEndpointId : null,
            model: selectedModel,
            execution_mode: newThreadExecutionMode,
          };
          pushDispatchDebug({
            ts: new Date().toISOString(),
            kind: "create_thread_response",
            thread_id: row.id,
            provider_id: row.provider_id,
            provider_endpoint_id: row.provider_endpoint_id ?? null,
            model: row.model,
            execution_mode: row.execution_mode,
            note: row.model !== selectedModel ? `Server returned "${row.model}" (expected "${selectedModel}")` : "Server thread model matched selection",
          });
          setThreadId(row.id);
          setActiveRunId(null);
          setShowNewThreadPrompt(false);
          const shouldSend = sendAfterThreadCreate && Boolean(draft.trim());
          setSendAfterThreadCreate(false);
          void refetchThreads();
          if (shouldSend) {
            sendToThread(row.id, {
              provider_id: newThreadProviderId,
              provider_endpoint_id: newThreadProviderId === "ollama" ? newThreadProviderEndpointId : null,
              model: selectedModel,
              execution_mode: newThreadExecutionMode,
            });
          }
        },
      },
    );
  }

  function connectHomeShell() {
    autoReconnectRef.current = true;
    reconnectAttemptRef.current = 0;
    createTerminalSession.mutate(
      { force_new: false, cwd: "~", command: "bash -l" },
      { onSuccess: (res) => setTerminalSessionId(res.session_id) },
    );
  }

  function connectCodexWithMem() {
    autoReconnectRef.current = true;
    reconnectAttemptRef.current = 0;
    createTerminalSession.mutate(
      {
        force_new: false,
        cwd: "~",
        command: SHARED_MEM_CODEX_CMD,
      },
      { onSuccess: (res) => setTerminalSessionId(res.session_id) },
    );
  }

  const currentAgentSession = (agentSessions.data ?? []).find((s) => s.id === agentSessionId) ?? null;
  const agentFileQuery = useLocalOpsAgentSessionFile(
    agentSessionId,
    agentEditFileKey,
    sideTab === "agents" && Boolean(agentSessionId),
  );

  useEffect(() => {
    if (!currentAgentSession) return;
    setAgentName(currentAgentSession.name ?? "");
    setAgentTitle(currentAgentSession.title ?? "");
    setAgentCodexModel(currentAgentSession.codex_model ?? "gpt-5.3-codex");
    setAgentInputFile(currentAgentSession.input_file ?? "INPUT.md");
    setAgentOutputFile(currentAgentSession.output_file ?? "OUTPUT.md");
    setAgentStateFile(currentAgentSession.state_file ?? "STATE.md");
    setAgentMemoryFile(currentAgentSession.memory_file ?? "MEM.md");
    setAgentNotesFile(currentAgentSession.notes_file ?? "NOTES.md");
  }, [currentAgentSession?.id]);

  useEffect(() => {
    if (typeof agentFileQuery.data?.content === "string") {
      setAgentFileDraft(agentFileQuery.data.content);
    }
  }, [agentFileQuery.data?.content, agentEditFileKey, agentSessionId]);

  return (
    <div className="space-y-4">
      <PageHeader
        compact
        title="LocalOps Chat"
        actions={(
          <Button
            variant="outline"
            onClick={openNewThreadPrompt}
          >
            <Plus size={12} /> New Thread
          </Button>
        )}
      >
        <LocalOpsTabs />
      </PageHeader>
      {threadsQuery.error ? (
        <p className="text-xs text-danger">
          LocalOps API unavailable: {String((threadsQuery.error as Error)?.message ?? threadsQuery.error)}
        </p>
      ) : null}

      <div className="localops-layout colFlexMin0">
        <Card className="colFlexMin0 min-h-0">
          <CardHeader className="pb-2"><CardTitle>Threads</CardTitle></CardHeader>
          <CardContent className="space-y-2 min-h-0 overflow-auto">
            {threads.map((thread) => (
              <div
                key={thread.id}
                className={`w-full rounded-xl border px-3 py-2 text-left text-xs transition ${thread.id === threadId ? "border-primary bg-primary/10" : "border-border bg-background/40 hover:bg-background/70"}`}
              >
                <button type="button" onClick={() => setThreadId(thread.id)} className="w-full text-left">
                  <p className="font-medium text-foreground">{thread.title}</p>
                  <p className="text-muted-foreground">{thread.provider_id} · {thread.model}</p>
                </button>
                <div className="mt-2 flex justify-end">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      deleteThread.mutate(thread.id, {
                        onSuccess: () => {
                          if (threadId === thread.id) {
                            setThreadId(null);
                            setActiveRunId(null);
                          }
                        },
                      })
                    }
                    disabled={deleteThread.isPending}
                  >
                    <Trash2 size={12} /> Delete
                  </Button>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className={`colFlexMin0 overflow-hidden ${centerMode === "terminal" ? "h-[78vh] min-h-[78vh]" : "h-[72vh] min-h-[72vh]"}`}>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between gap-2">
              <CardTitle>{centerMode === "chat" ? "Conversation" : "Local Terminal"}</CardTitle>
              <div className="flex gap-1">
                <Button size="sm" variant={centerMode === "chat" ? "default" : "outline"} onClick={() => setCenterMode("chat")}>
                  Chat
                </Button>
                <Button size="sm" variant={centerMode === "terminal" ? "default" : "outline"} onClick={() => setCenterMode("terminal")}>
                  <Terminal size={12} /> Terminal
                </Button>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              From Settings: provider <span className="font-mono">{providerId}</span>{providerId === "ollama" ? ` endpoint ${preferredOllamaProvider?.name || preferredOllamaProvider?.base_url || "-"}` : ""} · model <span className="font-mono">{model}</span> · mode <span className="font-mono">{executionMode}</span>
            </p>
          </CardHeader>
          <CardContent className="colFlexMin0 flex-1 min-h-0 gap-3 overflow-hidden">
            {centerMode === "chat" ? (
              <>
                <div ref={conversationRef} className="flex-1 space-y-3 overflow-auto rounded-xl border border-border bg-background/40 p-3">
                  {(threadDetail.data?.messages ?? []).map((message) => {
                    const isUser = message.role === "user";
                    const bubbleClass = isUser ? "ml-auto max-w-[85%] border-primary/30 bg-primary/12" : "mr-auto max-w-[92%] border-border bg-background/80";
                    return (
                      <div key={message.id} className={`rounded-2xl border p-3 ${bubbleClass}`}>
                        <p className="mb-1 flex items-center gap-1 text-[11px] uppercase tracking-wide text-muted-foreground">
                          {message.role === "assistant" ? <Bot size={12} /> : null}
                          {message.role}
                        </p>
                        <pre className="whitespace-pre-wrap text-sm leading-relaxed">{message.content}</pre>
                      </div>
                    );
                  })}
                  {liveChunks.length > 0 ? (
                    <div className="mr-auto max-w-[92%] rounded-2xl border border-primary/40 bg-primary/10 p-3">
                      <p className="mb-1 flex items-center gap-1 text-[11px] uppercase tracking-wide text-primary"><Bot size={12} /> streaming</p>
                      <pre className="whitespace-pre-wrap text-sm leading-relaxed">{liveChunks.join("")}<span className="animate-pulse">▋</span></pre>
                    </div>
                  ) : null}
                </div>

                <div className="sticky bottom-0 space-y-2 rounded-xl border border-border bg-card p-2">
                  <details className="rounded-lg border border-border/60 bg-background/25 p-2 text-[11px] text-muted-foreground">
                    <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-muted-foreground">Request Debug</summary>
                    <div className="mt-2 space-y-1.5 max-h-36 overflow-auto">
                      {dispatchDebug.length === 0 ? (
                        <p>No debug events yet.</p>
                      ) : (
                        dispatchDebug.map((entry, idx) => (
                          <div key={`${entry.ts}-${entry.kind}-${idx}`} className="rounded border border-border/60 bg-background/40 px-2 py-1">
                            <p className="font-mono text-[10px]">{new Date(entry.ts).toLocaleTimeString()} · {entry.kind}</p>
                            <p className="font-mono text-[10px]">
                              thread={entry.thread_id ?? "-"} run={entry.run_id ?? "-"} provider={entry.provider_id ?? "-"} endpoint={entry.provider_endpoint_id ?? "-"} model={entry.model ?? "-"} mode={entry.execution_mode ?? "-"}
                            </p>
                            {entry.note ? <p className="text-[10px]">{entry.note}</p> : null}
                          </div>
                        ))
                      )}
                    </div>
                  </details>
                  <Textarea
                    rows={3}
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    placeholder="Ask LocalOps..."
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        handleSend();
                      }
                    }}
                  />
                  <div className="flex items-center gap-2">
                    <Button onClick={handleSend} disabled={postMessage.isPending || createThread.isPending || !draft.trim() || !model.trim()}>
                      {(postMessage.isPending || createThread.isPending) ? <Loader2 size={13} className="animate-spin" /> : null}
                      Send
                    </Button>
                    {activeRunId ? <Button variant="outline" onClick={() => cancelRun.mutate(activeRunId)}>Cancel Run</Button> : null}
                    <Button variant="outline" size="sm" onClick={() => setDraft("Spawn report-writer agent, read INPUT.md, and write a final markdown report to ARTIFACTS/report.md.")}>
                      Prompt: report agent
                    </Button>
                  </div>
                </div>
              </>
            ) : (
              <>
                <div className="flex items-center gap-2">
                  <span className={`inline-flex rounded-full px-2 py-1 ${terminalConnected ? "bg-success/20 text-success" : "bg-muted text-muted-foreground"}`}>
                    {terminalConnected ? "connected" : "disconnected"}
                  </span>
                  <span className="text-muted-foreground">session: {terminalSessionId || activeTerminalQuery.data?.session_id || "-"}</span>
                  <span className="text-muted-foreground">ui: terminal-r5</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    onClick={connectHomeShell}
                    disabled={createTerminalSession.isPending}
                  >
                    {createTerminalSession.isPending ? <Loader2 size={12} className="animate-spin" /> : null}
                    Open Shell (~)
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={connectCodexWithMem}
                    disabled={createTerminalSession.isPending}
                  >
                    Open Codex + MEM
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      const active = activeTerminalQuery.data?.session_id ?? "";
                      if (!active) return;
                      autoReconnectRef.current = true;
                      reconnectAttemptRef.current = 0;
                      if (active === terminalSessionId) {
                        setSocketEpoch((v) => v + 1);
                      } else {
                        setTerminalSessionId(active);
                      }
                    }}
                    disabled={!activeTerminalQuery.data?.session_id || terminalConnected}
                  >
                    Attach Existing
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      if (!terminalSessionId) return;
                      autoReconnectRef.current = true;
                      reconnectAttemptRef.current = 0;
                      setSocketEpoch((v) => v + 1);
                    }}
                    disabled={!terminalSessionId || terminalConnected}
                  >
                    Reconnect
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => sendTerminalInput(`${SHARED_MEM_CODEX_CMD}\n`)}>Start Codex</Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      if (!terminalSessionId) return;
                      const currentSessionId = terminalSessionId;
                      autoReconnectRef.current = false;
                      reconnectAttemptRef.current = 0;
                      setTerminalConnected(false);
                      setTerminalSessionId("");
                      wsRef.current?.close();
                      killTerminalSession.mutate(currentSessionId);
                    }}
                    disabled={!terminalSessionId}
                  >
                    Close connection
                  </Button>
                </div>
                <div className="terminalHost terminalCard flex1Min0 min-h-[420px]" onClick={() => terminalApiRef.current?.focus()}>
                  <TerminalSurface
                    isActive={centerMode === "terminal"}
                    className="h-full w-full"
                    inputEnabled={terminalConnected}
                    onReady={(api) => {
                      terminalApiRef.current = api;
                      if (api) setTerminalLoadError("");
                    }}
                    onError={(message) => setTerminalLoadError(message)}
                    onData={(data) => {
                      if (!shouldForwardTerminalInput(data)) return;
                      sendTerminalInput(data);
                    }}
                    onResize={() => sendTerminalResize()}
                  />
                </div>
                {terminalLoadError ? <p className="text-danger">{terminalLoadError}</p> : null}
              </>
            )}
          </CardContent>
        </Card>

        <Card className="localops-workspace-panel colFlexMin0 min-h-0">
          <CardHeader className="pb-2">
            <CardTitle>Workspace</CardTitle>
            <div className="flex flex-wrap gap-1">
              <Button size="sm" variant={sideTab === "run" ? "default" : "outline"} onClick={() => setSideTab("run")}>Run</Button>
              <Button size="sm" variant={sideTab === "agents" ? "default" : "outline"} onClick={() => setSideTab("agents")}>Agents</Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-2 text-xs min-h-0 overflow-auto">
            {sideTab === "run" ? (
              <>
                {activeRunId ? <p className="text-muted-foreground">Run: {activeRunId}</p> : <p className="text-muted-foreground">No active run selected.</p>}
                {runDetail.data?.run ? (
                  <div className="rounded border border-border p-2 space-y-1">
                    <p><span className="text-muted-foreground">Status:</span> {runDetail.data.run.status}</p>
                    <p><span className="text-muted-foreground">LLM:</span> {runDetail.data.run.llm_status ?? "n/a"}</p>
                    <p><span className="text-muted-foreground">Provider:</span> {runDetail.data.run.provider_id}</p>
                    <p><span className="text-muted-foreground">Model:</span> {runDetail.data.run.model}</p>
                    <p><span className="text-muted-foreground">Endpoint:</span> {runDetail.data.run.endpoint_label || runDetail.data.run.endpoint_url || "-"}</p>
                    <p><span className="text-muted-foreground">Elapsed:</span> {Number((runDetail.data.run.telemetry as Record<string, unknown> | undefined)?.elapsed_ms ?? 0)} ms</p>
                    <p><span className="text-muted-foreground">Chunks:</span> {Number((runDetail.data.run.telemetry as Record<string, unknown> | undefined)?.chunk_count ?? 0)} · <span className="text-muted-foreground">Output chars:</span> {Number((runDetail.data.run.telemetry as Record<string, unknown> | undefined)?.output_char_count ?? 0)}</p>
                    <p><span className="text-muted-foreground">First token:</span> {Number((runDetail.data.run.telemetry as Record<string, unknown> | undefined)?.first_token_latency_ms ?? 0)} ms · <span className="text-muted-foreground">TPS:</span> {String((runDetail.data.run.telemetry as Record<string, unknown> | undefined)?.tokens_per_second ?? "-")}</p>
                    <p><span className="text-muted-foreground">Durations(ns):</span> total={String((runDetail.data.run.telemetry as Record<string, unknown> | undefined)?.total_duration_ns ?? "-")} load={String((runDetail.data.run.telemetry as Record<string, unknown> | undefined)?.load_duration_ns ?? "-")}</p>
                    <p><span className="text-muted-foreground">Eval:</span> prompt={String((runDetail.data.run.telemetry as Record<string, unknown> | undefined)?.prompt_eval_count ?? "-")} / {String((runDetail.data.run.telemetry as Record<string, unknown> | undefined)?.eval_count ?? "-")}</p>
                    <p className="whitespace-pre-wrap"><span className="text-muted-foreground">Preview:</span> {String((runDetail.data.run.telemetry as Record<string, unknown> | undefined)?.output_preview ?? "")}</p>
                    {runDetail.data.run.error ? <p className="text-danger">{runDetail.data.run.error}</p> : null}
                  </div>
                ) : null}
                <div className="max-h-[420px] space-y-2 overflow-auto">
                  {(runDetail.data?.tool_calls ?? []).map((call) => (
                    <div key={call.id} className="rounded border border-border p-2">
                      <p className="font-medium">{call.tool_name}</p>
                      <p className="text-muted-foreground">status: {call.status}</p>
                      {call.status === "pending" ? (
                        <Button
                          size="sm"
                          className="mt-2"
                          onClick={() => activeRunId && approveTool.mutate({ runId: activeRunId, toolCallId: call.id })}
                          disabled={!activeRunId || approveTool.isPending}
                        >
                          Approve
                        </Button>
                      ) : null}
                      {Object.keys(call.result ?? {}).length > 0 ? (
                        <div className="mt-2 space-y-2">
                          <ObjectReadout data={(call.result as Record<string, unknown> | undefined) ?? {}} />
                          <AdvancedRawJson data={call.result} />
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              </>
            ) : null}

            {sideTab === "agents" ? (
              <div className="space-y-2">
                <div className="rounded border border-border p-2">
                  <p className="mb-1 text-xs font-semibold text-muted-foreground">Add Agent Pack</p>
                  <div className="space-y-2">
                    <Input value={newAgentSlug} onChange={(e) => setNewAgentSlug(e.target.value)} placeholder="slug (ex: my-writer)" />
                    <Input value={newAgentTitle} onChange={(e) => setNewAgentTitle(e.target.value)} placeholder="display title" />
                    <Textarea rows={4} value={newAgentInstructions} onChange={(e) => setNewAgentInstructions(e.target.value)} placeholder="Instructions markdown" />
                    <Textarea rows={2} value={newAgentSkill} onChange={(e) => setNewAgentSkill(e.target.value)} placeholder="Optional SKILL.md content" />
                    <Button
                      size="sm"
                      onClick={() =>
                        upsertAgentPack.mutate(
                          {
                            slug: newAgentSlug,
                            title: newAgentTitle,
                            instructions: newAgentInstructions,
                            skill_md: newAgentSkill,
                          },
                          {
                            onSuccess: (pack) => {
                              setAgentSlug(pack.slug);
                              setNewAgentSlug("");
                            },
                          },
                        )
                      }
                      disabled={!newAgentSlug.trim() || !newAgentInstructions.trim() || upsertAgentPack.isPending}
                    >
                      {upsertAgentPack.isPending ? <Loader2 size={12} className="animate-spin" /> : null}
                      Save agent pack
                    </Button>
                  </div>
                </div>

                <label className="text-xs text-muted-foreground">Agent pack
                  <select className="mt-1 w-full rounded border border-border bg-input px-2 py-2 text-sm" value={agentSlug} onChange={(e) => setAgentSlug(e.target.value)}>
                    {(agentPacks.data ?? []).map((p) => <option key={p.slug} value={p.slug}>{p.slug}</option>)}
                  </select>
                </label>
                <Input value={agentName} onChange={(e) => setAgentName(e.target.value)} placeholder="Agent name (ex: Analyst-1)" />
                <Input value={agentTitle} onChange={(e) => setAgentTitle(e.target.value)} placeholder="Session title (optional)" />
                <Input value={agentWorkspaceRoot} onChange={(e) => setAgentWorkspaceRoot(e.target.value)} placeholder="Workspace root directory (optional)" />
                <Input value={agentCodexModel} onChange={(e) => setAgentCodexModel(e.target.value)} placeholder="Codex model (gpt-5.1-codex, gpt-5.2-codex, gpt-5.3-codex)" />
                <Button
                  size="sm"
                  onClick={() =>
                    createAgentSession.mutate(
                      {
                        agent_slug: agentSlug,
                        title: agentTitle,
                        agent_name: agentName,
                        workspace_root: agentWorkspaceRoot,
                        codex_model: agentCodexModel,
                        seed_markdown: "# Input\n\n",
                      },
                      { onSuccess: (row) => setAgentSessionId(row.id) },
                    )
                  }
                  disabled={!agentSlug || createAgentSession.isPending}
                >
                  {createAgentSession.isPending ? <Loader2 size={12} className="animate-spin" /> : null}
                  Create agent session
                </Button>
                <label className="text-xs text-muted-foreground">Session
                  <select className="mt-1 w-full rounded border border-border bg-input px-2 py-2 text-sm" value={agentSessionId} onChange={(e) => setAgentSessionId(e.target.value)}>
                    <option value="">Select session</option>
                    {(agentSessions.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.title} ({s.agent_slug})</option>)}
                  </select>
                </label>
                <div className="rounded border border-border p-2">
                  <p className="mb-1 text-xs font-semibold text-muted-foreground">Session files</p>
                  <div className="mb-2 flex gap-2">
                    <select
                      className="w-full rounded border border-border bg-input px-2 py-2 text-sm"
                      value={agentEditFileKey}
                      onChange={(e) => setAgentEditFileKey(e.target.value)}
                    >
                      <option value="investigations">INVESTIGATIONS.md</option>
                      <option value="host_profile">HOST_PROFILE.md</option>
                      <option value="repo_profile">REPO_PROFILE.md</option>
                      <option value="memory">MEM.md</option>
                      <option value="state">STATE.md</option>
                      <option value="notes">NOTES.md</option>
                      <option value="input">INPUT.md</option>
                      <option value="output">OUTPUT.md</option>
                      <option value="agent">AGENT.md</option>
                    </select>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => agentFileQuery.refetch()}
                      disabled={!agentSessionId || agentFileQuery.isFetching}
                    >
                      Reload
                    </Button>
                  </div>
                  <Textarea
                    rows={10}
                    value={agentFileDraft}
                    onChange={(e) => setAgentFileDraft(e.target.value)}
                    placeholder="Select a session and file to edit..."
                    disabled={!agentSessionId}
                  />
                  <div className="mt-2 flex justify-end">
                    <Button
                      size="sm"
                      onClick={() =>
                        agentSessionId &&
                        saveAgentSessionFile.mutate({
                          sessionId: agentSessionId,
                          fileKey: agentEditFileKey,
                          content: agentFileDraft,
                        })
                      }
                      disabled={!agentSessionId || saveAgentSessionFile.isPending}
                    >
                      {saveAgentSessionFile.isPending ? <Loader2 size={12} className="animate-spin" /> : null}
                      Save file
                    </Button>
                  </div>
                </div>
                <Textarea rows={4} value={agentTask} onChange={(e) => setAgentTask(e.target.value)} placeholder="Task for this agent session" />
                <div className="grid grid-cols-2 gap-2">
                  <Input value={agentInputFile} onChange={(e) => setAgentInputFile(e.target.value)} placeholder="input file" />
                  <Input value={agentOutputFile} onChange={(e) => setAgentOutputFile(e.target.value)} placeholder="output file" />
                  <Input value={agentStateFile} onChange={(e) => setAgentStateFile(e.target.value)} placeholder="state file" />
                  <Input value={agentMemoryFile} onChange={(e) => setAgentMemoryFile(e.target.value)} placeholder="memory file" />
                  <Input value={agentNotesFile} onChange={(e) => setAgentNotesFile(e.target.value)} placeholder="notes file" className="col-span-2" />
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      agentSessionId &&
                      updateAgentSession.mutate({
                        session_id: agentSessionId,
                        name: agentName,
                        title: agentTitle,
                        codex_model: agentCodexModel,
                        input_file: agentInputFile,
                        output_file: agentOutputFile,
                        state_file: agentStateFile,
                        memory_file: agentMemoryFile,
                        notes_file: agentNotesFile,
                      })
                    }
                    disabled={!agentSessionId || updateAgentSession.isPending}
                  >
                    Save session config
                  </Button>
                </div>
                <Button
                  size="sm"
                  onClick={() => agentSessionId && runAgentSession.mutate({ session_id: agentSessionId, task: agentTask })}
                  disabled={!agentSessionId || !agentTask.trim() || runAgentSession.isPending}
                >
                  {runAgentSession.isPending ? <Loader2 size={12} className="animate-spin" /> : null}
                  Run codex task
                </Button>
                {currentAgentSession ? (
                  <div className="rounded border border-border p-2">
                    <p><span className="text-muted-foreground">name:</span> {currentAgentSession.name || "-"}</p>
                    <p><span className="text-muted-foreground">codex model:</span> {currentAgentSession.codex_model || "-"}</p>
                    <p><span className="text-muted-foreground">workspace:</span> {currentAgentSession.workspace_path}</p>
                    <p><span className="text-muted-foreground">state:</span> {currentAgentSession.state_file || "STATE.md"} · <span className="text-muted-foreground">memory:</span> {currentAgentSession.memory_file || "MEM.md"}</p>
                    {Object.keys(currentAgentSession.last_result ?? {}).length > 0 ? (
                      <div className="mt-2 space-y-2">
                        <ObjectReadout data={(currentAgentSession.last_result as Record<string, unknown> | undefined) ?? {}} />
                        <AdvancedRawJson data={currentAgentSession.last_result} />
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>

      {showNewThreadPrompt ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4">
          <div className="w-full max-w-lg rounded-xl border border-border bg-card p-4 shadow-2xl">
            <p className="text-sm font-semibold text-foreground">Create LocalOps thread</p>
            <p className="mt-1 text-xs text-muted-foreground">Choose provider and model before starting.</p>
            <div className="mt-3 grid gap-2 md:grid-cols-2">
              <label className="text-xs text-muted-foreground md:col-span-2">Thread title
                <Input value={newThreadTitle} onChange={(e) => setNewThreadTitle(e.target.value)} />
              </label>
              <label className="text-xs text-muted-foreground">Provider
                <select
                  className="mt-1 w-full rounded border border-border bg-input px-2 py-2 text-sm text-foreground"
                  value={newThreadProviderId}
                  onChange={(e) => setNewThreadProviderId(e.target.value as "openai" | "ollama")}
                >
                  <option value="openai">openai</option>
                  <option value="ollama">ollama</option>
                </select>
              </label>
              <label className="text-xs text-muted-foreground">Execution mode
                <select
                  className="mt-1 w-full rounded border border-border bg-input px-2 py-2 text-sm text-foreground"
                  value={newThreadExecutionMode}
                  onChange={(e) => setNewThreadExecutionMode(e.target.value as LocalOpsExecutionMode)}
                >
                  <option value="propose_only">propose_only</option>
                  <option value="require_confirm">require_confirm</option>
                  <option value="auto_execute_allowlisted">auto_execute_allowlisted</option>
                </select>
              </label>
              {newThreadProviderId === "ollama" ? (
                <label className="text-xs text-muted-foreground md:col-span-2">Ollama endpoint
                  <select
                    className="mt-1 w-full rounded border border-border bg-input px-2 py-2 text-sm text-foreground"
                    value={newThreadProviderEndpointId ?? ""}
                    onChange={(e) => setNewThreadProviderEndpointId(e.target.value ? Number(e.target.value) : null)}
                  >
                    <option value="">Auto-select enabled endpoint</option>
                    {ollamaProviders.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name || `provider-${p.id}`} - {p.base_url}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <label className="text-xs text-muted-foreground md:col-span-2">Model
                {newThreadModelOptions.length > 0 ? (
                  <select
                    className="mt-1 w-full rounded border border-border bg-input px-2 py-2 text-sm text-foreground"
                    value={newThreadModel}
                    onChange={(e) => setNewThreadModel(e.target.value)}
                  >
                    {newThreadModelOptions.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                ) : (
                  <Input
                    value={newThreadModel}
                    onChange={(e) => setNewThreadModel(e.target.value)}
                    placeholder={newThreadProviderId === "openai" ? "gpt-5.3 or gpt-4o-mini" : "qwen3:8b, llama3.1:8b, ..."}
                  />
                )}
              </label>
            </div>
            <div className="mt-3 flex items-center justify-between gap-2 text-xs text-muted-foreground">
              <span>
                {newThreadProviderId === "openai"
                  ? `OpenAI models: ${openAiModelsQuery.isLoading ? "loading..." : newThreadModelOptions.length}`
                  : `Ollama models: ${ollamaModelsQuery.isLoading ? "loading..." : newThreadModelOptions.length}`}
              </span>
              <span>{newThreadProviderId === "ollama" ? (preferredOllamaProvider?.base_url || "No Ollama provider configured") : ""}</span>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <Button
                variant="outline"
                onClick={() => {
                  setShowNewThreadPrompt(false);
                  setSendAfterThreadCreate(false);
                }}
              >
                Cancel
              </Button>
              <Button
                onClick={createThreadWithSelection}
                disabled={createThread.isPending || !newThreadModel.trim()}
              >
                {createThread.isPending ? <Loader2 size={13} className="animate-spin" /> : null}
                {sendAfterThreadCreate ? "Create + Send" : "Create Thread"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
