import type {
  FactoryAgent,
  FactoryArtifact,
  FactoryComposeRunRequest,
  FactoryComposeRunResponse,
  FactoryHealthStatus,
  FactoryInboxMessage,
  FactoryIssue,
  FactoryMetricsSummary,
  FactoryMode,
  FactoryOverviewPayload,
  FactoryPreviewStartRequest,
  FactoryPreviewStartResponse,
  FactoryPreviewStopRequest,
  FactoryPreviewStopResponse,
  FactoryRun,
  FactoryRunDetail,
  FactoryRunRow,
  FactoryWorkspaceBootstrapRequest,
  FactoryWorkspaceBootstrapResponse,
  FactoryWorkspaceCreateRequest,
  FactoryTask,
  FactoryTimelineEvent,
  PromptPreset,
  RunTemplate,
  Workspace,
} from "./types";

type FactoryListParams = {
  limit?: number;
  offset?: number;
  status?: string;
  search?: string;
  run_id?: string;
  kind?: string;
  severity?: string;
  sender?: string;
  recipient?: string;
};

class FactoryApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "FactoryApiError";
    this.status = status;
  }
}

function resolveFactoryApiBase(): string {
  const env = import.meta.env as Record<string, string | undefined>;
  const explicit = String(env.VITE_DASHBURG_FACTORY_API_BASE ?? env.DASHBURG_FACTORY_API_BASE ?? "").trim();
  if (explicit) {
    const normalized = explicit.replace(/\/+$/, "");
    if (normalized.includes("/api/factory-proxy") || normalized.startsWith("/")) return normalized;
    // Direct upstream base URLs trigger browser CORS; prefer backend proxy unless
    // explicit proxy path is provided.
  }
  if (typeof window !== "undefined") {
    const { protocol, hostname } = window.location;
    return `${protocol}//${hostname}:8321/api/factory-proxy`;
  }
  return "http://127.0.0.1:8321/api/factory-proxy";
}

function isFactoryMockEnabled(): boolean {
  const env = import.meta.env as Record<string, string | undefined>;
  const raw = String(env.VITE_DASHBURG_FACTORY_MOCK ?? env.DASHBURG_FACTORY_MOCK ?? "").trim().toLowerCase();
  return raw === "1" || raw === "true" || raw === "yes";
}

const FACTORY_API_BASE = resolveFactoryApiBase();
const FACTORY_MOCK_MODE = isFactoryMockEnabled();

function toNumber(value: unknown, fallback = 0): number {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function toString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function toSafePreviewUrl(value: unknown): string {
  const raw = toString(value).trim();
  if (!raw) return "";
  try {
    const parsed = new URL(raw);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return "";
    return parsed.toString();
  } catch {
    return "";
  }
}

function toRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function asArray(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  if (value && typeof value === "object") {
    const obj = value as Record<string, unknown>;
    const candidates = [obj.items, obj.results, obj.data, obj.rows, obj.runs, obj.messages, obj.issues, obj.artifacts, obj.metrics, obj.tasks, obj.events];
    for (const candidate of candidates) {
      if (Array.isArray(candidate)) return candidate;
    }
  }
  return [];
}

function statusFromRun(input: Record<string, unknown>): string {
  return toString(input.status ?? input.state ?? input.run_status, "unknown");
}

function stageFromRun(input: Record<string, unknown>): string {
  return toString(input.current_stage ?? input.stage ?? input.stage_name, "unknown");
}

function normalizeRun(input: unknown): FactoryRunRow {
  const row = toRecord(input);
  const nestedRun = toRecord(row.run);
  const source = Object.keys(nestedRun).length > 0 ? { ...nestedRun, ...row } : row;
  const metadataFactory = toRecord(toRecord(source.metadata_json).factory);
  const inputs = toRecord(source.inputs_json);
  const agents = asArray(source.agents ?? metadataFactory.agents ?? inputs.agents).map((item) => toString(item)).filter(Boolean);
  const tasksTotal = toNumber(source.task_count ?? source.tasks_count);
  const queued = toNumber(source.queued_task_count);
  const running = toNumber(source.running_task_count);
  const completed = toNumber(source.completed_task_count);
  const failed = toNumber(source.failed_task_count);
  const safeTaskCount = tasksTotal || queued + running + completed + failed;
  const progress =
    toNumber(source.progress_pct ?? source.progress ?? source.progress_percent) ||
    (safeTaskCount > 0 ? ((completed + failed) / safeTaskCount) * 100 : 0);
  const fallbackId = [
    toString(source.id),
    toString(source.run_id),
    toString(source.uuid),
    toString(source.created_at),
    toString(source.app_name ?? source.app ?? source.title ?? source.name),
  ]
    .filter(Boolean)
    .join(":");

  return {
    id: toString(source.id ?? source.run_id ?? source.uuid, fallbackId || "unknown_run"),
    app_name: toString(source.app_name ?? source.app ?? source.app_title ?? source.title ?? source.name, "Unknown App"),
    name: toString(source.name),
    run_name: toString(source.run_name ?? source.name),
    workspace_id: toString(source.workspace_id ?? source.workspace_key ?? metadataFactory.workspace_id ?? inputs.workspace_id),
    template_id: toString(source.template_id ?? source.template_key ?? metadataFactory.template_key ?? inputs.template_key),
    template_key: toString(source.template_key ?? metadataFactory.template_key ?? inputs.template_key),
    preset_key: toString(source.preset_key ?? metadataFactory.preset_key ?? inputs.preset_key),
    mode: toString(source.mode ?? metadataFactory.mode ?? inputs.mode),
    app_type: toString(source.app_type ?? metadataFactory.app_type ?? inputs.app_type),
    agents,
    preview_url: toSafePreviewUrl(
      source.preview_url ??
      source.previewUrl ??
      toRecord(source.metadata_json).preview_url ??
      toRecord(source.metadata_json).previewUrl ??
      metadataFactory.preview_url ??
      metadataFactory.previewUrl ??
      toRecord(inputs).preview_url ??
      toRecord(inputs).previewUrl,
    ),
    status: statusFromRun(source),
    current_stage: stageFromRun(source),
    progress_pct: progress,
    task_count: safeTaskCount,
    issue_count: toNumber(source.issue_count ?? source.issues_count),
    artifact_count: toNumber(source.artifact_count ?? source.artifacts_count),
    message_count: toNumber(source.message_count ?? source.messages_count),
    created_at: toString(source.created_at ?? source.started_at),
    updated_at: toString(source.updated_at ?? source.finished_at ?? source.created_at),
  };
}

function normalizeMessage(input: unknown): FactoryInboxMessage {
  const row = toRecord(input);
  return {
    id: toString(row.id, "unknown_message"),
    run_id: toString(row.run_id ?? row.runId),
    sender: toString(row.sender ?? row.from_role ?? row.sender_role, "unknown"),
    recipient: toString(row.recipient ?? row.to_role ?? row.recipient_role, "unknown"),
    subject: toString(row.subject, "No subject"),
    body: toString(row.body ?? row.content),
    priority: toString(row.priority ?? row.severity, "medium"),
    status: toString(row.status, "unknown"),
    created_at: toString(row.created_at),
  };
}

function normalizeArtifact(input: unknown): FactoryArtifact {
  const row = toRecord(input);
  return {
    id: toString(row.id, "unknown_artifact"),
    run_id: toString(row.run_id ?? row.runId),
    kind: toString(row.kind ?? row.type, "unknown"),
    name: toString(row.name ?? row.filename, "unnamed"),
    score: row.score == null ? undefined : toNumber(row.score),
    notes: toString(row.notes ?? row.summary),
    preview_url: toString(row.preview_url ?? row.previewUrl ?? row.url),
    created_at: toString(row.created_at),
  };
}

function normalizeIssue(input: unknown): FactoryIssue {
  const row = toRecord(input);
  return {
    id: toString(row.id, "unknown_issue"),
    run_id: toString(row.run_id ?? row.runId),
    severity: toString(row.severity ?? row.priority, "unknown"),
    status: toString(row.status ?? "open"),
    source_agent: toString(row.source_agent ?? row.agent ?? row.source, "unknown"),
    file_path: toString(row.file_path ?? row.path),
    summary: toString(row.summary ?? row.message, "Issue"),
    created_at: toString(row.created_at),
    updated_at: toString(row.updated_at ?? row.created_at),
  };
}

function normalizeTask(input: unknown): FactoryTask {
  const row = toRecord(input);
  return {
    id: toString(row.id, "unknown_task"),
    title: toString(row.title ?? row.name, "Untitled task"),
    stage: toString(row.stage ?? row.phase, "unknown"),
    status: toString(row.status, "unknown"),
    assignee: toString(row.assignee ?? row.agent),
    started_at: toString(row.started_at ?? row.created_at),
    completed_at: toString(row.completed_at ?? row.finished_at),
  };
}

function normalizeTimelineEvent(input: unknown): FactoryTimelineEvent {
  const row = toRecord(input);
  return {
    id: toString(row.id, `evt_${Math.random().toString(36).slice(2)}`),
    stage: toString(row.stage ?? row.stage_name, "unknown"),
    status: toString(row.status, "unknown"),
    message: toString(row.message ?? row.summary),
    created_at: toString(row.created_at ?? row.updated_at),
  };
}

function normalizeMetricsSummary(input: unknown): FactoryMetricsSummary {
  const row = toRecord(input);
  return {
    build_success_rate: toNumber(row.build_success_rate ?? row.success_rate),
    mean_cycle_time_ms: toNumber(row.mean_cycle_time_ms ?? row.cycle_time_ms),
    average_issues_per_run: toNumber(row.average_issues_per_run ?? row.issues_per_run),
    runs_last_24h: toNumber(row.runs_last_24h),
    tasks_completed_last_24h: toNumber(row.tasks_completed_last_24h),
  };
}

function queryString(params?: FactoryListParams): string {
  const qp = new URLSearchParams();
  if (!params) return "";
  for (const [key, value] of Object.entries(params)) {
    if (value == null || value === "") continue;
    qp.set(key, String(value));
  }
  const raw = qp.toString();
  return raw ? `?${raw}` : "";
}

async function fetchFactory(path: string): Promise<unknown> {
  const url = `${FACTORY_API_BASE}${path}`;
  const resp = await fetch(url, { headers: { "Content-Type": "application/json" } });
  if (!resp.ok) {
    let detail = "";
    try {
      const body = (await resp.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail != null) detail = JSON.stringify(body.detail);
    } catch {
      detail = "";
    }
    throw new FactoryApiError(`${detail || `Factory API request failed (${resp.status}) for ${path}`}`, resp.status);
  }
  return (await resp.json()) as unknown;
}

async function postFactory(path: string, body: unknown): Promise<unknown> {
  const url = `${FACTORY_API_BASE}${path}`;
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    let detail = "";
    try {
      const bodyJson = (await resp.json()) as { detail?: unknown };
      if (typeof bodyJson.detail === "string") detail = bodyJson.detail;
      else if (bodyJson.detail != null) detail = JSON.stringify(bodyJson.detail);
    } catch {
      detail = "";
    }
    throw new FactoryApiError(`${detail || `Factory API request failed (${resp.status}) for ${path}`}`, resp.status);
  }
  return (await resp.json()) as unknown;
}

async function tryFetchFactory(path: string): Promise<unknown | null> {
  try {
    return await fetchFactory(path);
  } catch (error) {
    if (error instanceof FactoryApiError && error.status === 404) return null;
    throw error;
  }
}

const mockRuns: FactoryRunRow[] = [
  {
    id: "run_20260306_001",
    app_name: "Connection Compass",
    status: "running",
    current_stage: "test",
    progress_pct: 72,
    task_count: 14,
    issue_count: 3,
    artifact_count: 8,
    message_count: 5,
    created_at: "2026-03-06T13:10:00Z",
    updated_at: "2026-03-06T14:04:00Z",
  },
  {
    id: "run_20260306_002",
    app_name: "Daily Habit Beacon",
    status: "failed",
    current_stage: "visual_review",
    progress_pct: 83,
    task_count: 18,
    issue_count: 6,
    artifact_count: 12,
    message_count: 7,
    created_at: "2026-03-06T12:15:00Z",
    updated_at: "2026-03-06T13:44:00Z",
  },
  {
    id: "run_20260305_019",
    app_name: "ScriptSprint Mobile",
    status: "succeeded",
    current_stage: "release_candidate",
    progress_pct: 100,
    task_count: 21,
    issue_count: 0,
    artifact_count: 17,
    message_count: 11,
    created_at: "2026-03-05T18:05:00Z",
    updated_at: "2026-03-05T20:48:00Z",
  },
];

const mockMessages: FactoryInboxMessage[] = [
  {
    id: "msg_1",
    run_id: "run_20260306_001",
    sender: "review_agent",
    recipient: "patch_agent",
    subject: "Primary CTA below fold on 390px viewport",
    body: "The onboarding continue button is not visible without scroll on smaller devices.",
    priority: "high",
    status: "unread",
    created_at: "2026-03-06T14:00:00Z",
  },
  {
    id: "msg_2",
    run_id: "run_20260306_002",
    sender: "test_agent",
    recipient: "builder_agent",
    subject: "Regression in auth route guard",
    body: "Guest users can land on premium settings after logout via deep link.",
    priority: "critical",
    status: "unread",
    created_at: "2026-03-06T13:42:00Z",
  },
];

const mockArtifacts: FactoryArtifact[] = [
  {
    id: "art_1",
    run_id: "run_20260306_001",
    kind: "screenshot",
    name: "onboarding_step_2_small.png",
    score: 0.72,
    notes: "CTA below fold on smaller phones",
    preview_url: "",
    created_at: "2026-03-06T14:01:00Z",
  },
  {
    id: "art_2",
    run_id: "run_20260305_019",
    kind: "android_build",
    name: "scriptsprint-rc1.aab",
    score: 0.98,
    notes: "Release candidate build passed smoke tests",
    preview_url: "",
    created_at: "2026-03-05T20:44:00Z",
  },
];

const mockIssues: FactoryIssue[] = [
  {
    id: "iss_1",
    run_id: "run_20260306_001",
    severity: "p1",
    status: "open",
    source_agent: "review_agent",
    file_path: "src/screens/onboarding.tsx",
    summary: "Continue button is below fold on 390px viewports",
    created_at: "2026-03-06T14:00:00Z",
    updated_at: "2026-03-06T14:03:00Z",
  },
  {
    id: "iss_2",
    run_id: "run_20260306_002",
    severity: "p0",
    status: "open",
    source_agent: "test_agent",
    file_path: "src/routes/auth-guard.ts",
    summary: "Premium settings route remains accessible after logout",
    created_at: "2026-03-06T13:40:00Z",
    updated_at: "2026-03-06T13:44:00Z",
  },
];

const mockWorkspaces: Workspace[] = [
  {
    id: "ws_dashburg",
    name: "Dashburg",
    path: "/srv/repos/dashgithub",
    description: "Dashburg frontend/backend workspace",
    branch: "main",
  },
  {
    id: "ws_topicsite",
    name: "Topicsite",
    path: "/srv/repos/topic-service",
    description: "Topicsite API workspace",
    branch: "main",
  },
];

const mockTemplates: RunTemplate[] = [
  {
    id: "template_fullstack",
    name: "Fullstack Feature",
    description: "Build UI + API + tests for a new feature.",
    app_type: "fullstack",
    default_agents: ["planner", "builder", "tester"],
    default_constraints: ["keep existing routes stable", "include error states"],
    default_validation: ["lint", "typecheck", "test"],
  },
  {
    id: "template_frontend",
    name: "Frontend Addition",
    description: "Implement a frontend feature against existing APIs.",
    app_type: "frontend",
    default_agents: ["planner", "ui_builder", "qa"],
    default_constraints: ["theme-consistent", "compact UI"],
    default_validation: ["lint", "typecheck"],
  },
];

const mockPresets: PromptPreset[] = [
  {
    id: "preset_factory_control_plane",
    name: "Factory Control Plane",
    description: "Operator-facing dashboard + run control for AI app factory.",
    goal: "Add a compact control plane UI that supports run creation, launch, and monitoring.",
    constraints: ["do not break existing pages", "keep cards compact", "add loading/error/empty states"],
    examples: [
      "Create a run for a new AI App Factory UI with /factory routes and live run detail polling.",
      "Build a run composer with templates, presets, agent selection, and payload preview.",
    ],
    app_type: "frontend",
    tags: ["factory", "dashboard", "react"],
  },
  {
    id: "preset_bugfix_sweep",
    name: "Bugfix Sweep",
    description: "Targeted bugfix run with strong regression protection.",
    goal: "Fix production regressions and add tests for affected flows.",
    constraints: ["preserve external API behavior", "add regression coverage"],
    examples: [
      "Fix stale run status tracking while preserving existing run API shapes.",
      "Correct run counters and ensure deleted/failed runs are removed from running count.",
    ],
    app_type: "fullstack",
    tags: ["bugfix", "regression"],
  },
];

const mockAgents: FactoryAgent[] = [
  { id: "planner", name: "Planner", role: "planning", description: "Scoping and task decomposition", enabled: true },
  { id: "builder", name: "Builder", role: "implementation", description: "Core implementation agent", enabled: true },
  { id: "ui_builder", name: "UI Builder", role: "frontend", description: "UI and interaction implementation", enabled: true },
  { id: "tester", name: "Tester", role: "verification", description: "Validation and test coverage", enabled: true },
  { id: "qa", name: "QA", role: "review", description: "Final QA and quality checks", enabled: true },
];

const mockModes: FactoryMode[] = [
  { id: "web_app", name: "Web App", description: "General web application flow", app_types: ["frontend", "fullstack"] },
  { id: "api_service", name: "API Service", description: "Backend/API implementation flow", app_types: ["backend", "fullstack"] },
];

function mockOverview(): FactoryOverviewPayload {
  return {
    summary: {
      total_runs: 42,
      active_runs: 6,
      failed_runs: 3,
      open_issues: 14,
      unread_messages: 9,
      success_rate: 0.88,
    },
    issue_counts: { p0: 1, p1: 3, p2: 6, p3: 4 },
    recent_runs: mockRuns,
    recent_messages: mockMessages,
    recent_artifacts: mockArtifacts,
  };
}

function mockMetrics(): FactoryMetricsSummary {
  return {
    build_success_rate: 0.88,
    mean_cycle_time_ms: 3_240_000,
    average_issues_per_run: 1.9,
    runs_last_24h: 12,
    tasks_completed_last_24h: 94,
  };
}

function mockRunDetail(runId: string): FactoryRunDetail {
  const run = mockRuns.find((item) => item.id === runId) ?? mockRuns[0];
  return {
    run,
    timeline: [
      {
        id: `${run.id}_evt_1`,
        stage: "plan",
        status: "done",
        message: "Planning completed",
        created_at: run.created_at,
      },
      {
        id: `${run.id}_evt_2`,
        stage: "build",
        status: run.status === "running" ? "running" : "done",
        message: "Build pipeline executing",
        created_at: run.updated_at,
      },
    ],
    tasks: [
      {
        id: `${run.id}_task_1`,
        title: "Scaffold app shell",
        stage: "build",
        status: "done",
        assignee: "builder_agent",
        started_at: run.created_at,
        completed_at: run.updated_at,
      },
      {
        id: `${run.id}_task_2`,
        title: "Validate responsive layout",
        stage: "test",
        status: run.status === "running" ? "running" : "done",
        assignee: "test_agent",
        started_at: run.updated_at,
        completed_at: run.status === "running" ? "" : run.updated_at,
      },
    ],
    issues: mockIssues.filter((issue) => issue.run_id === run.id),
    artifacts: mockArtifacts.filter((artifact) => artifact.run_id === run.id),
    messages: mockMessages.filter((message) => message.run_id === run.id),
    metrics: mockMetrics(),
    logs: [
      `[${run.created_at}] run created`,
      `[${run.updated_at}] stage ${run.current_stage} status ${run.status}`,
    ],
    output: { run_id: run.id, stage: run.current_stage, status: run.status },
  };
}

function normalizeWorkspace(input: unknown): Workspace {
  const row = toRecord(input);
  const repoPath = toString(row.repo_path ?? row.path ?? row.root_path);
  const metadata = toRecord(row.metadata_json);
  const previewUrl = toSafePreviewUrl(row.preview_url ?? row.previewUrl ?? metadata.preview_url ?? metadata.previewUrl);
  return {
    id: toString(row.id ?? row.workspace_id, "workspace"),
    key: toString(row.key),
    name: toString(row.name ?? row.label ?? row.workspace_name, "Workspace"),
    path: repoPath,
    repo_path: repoPath,
    description: toString(row.description),
    branch: toString(row.branch ?? row.default_branch),
    app_type: toString(row.app_type),
    is_active: row.is_active == null ? true : Boolean(row.is_active),
    repo_exists: row.repo_exists == null ? undefined : Boolean(row.repo_exists),
    last_used_at: toString(row.last_used_at) || null,
    available_templates: asArray(row.available_templates).map((item) => toString(item)).filter(Boolean),
    default_branch: toString(row.default_branch ?? row.branch),
    preview_url: previewUrl,
  };
}

function normalizeTemplate(input: unknown): RunTemplate {
  const row = toRecord(input);
  const title = toString(row.title ?? row.name ?? row.label, "Template");
  const key = toString(row.key ?? row.id ?? row.template_id, "template");
  const taskBlueprint = asArray(row.task_blueprint).map((item) => toRecord(item));
  const executionOrder = taskBlueprint
    .map((item) => toString(item.agent_role || item.stage))
    .filter(Boolean);
  return {
    id: key,
    key,
    name: title,
    description: toString(row.description),
    app_type: toString(row.app_type),
    recommended_mode: toString(row.recommended_mode),
    execution_order: executionOrder,
    flow_summary: executionOrder.length > 0 ? executionOrder.join(" -> ") : "",
    default_agents: asArray(row.default_agents ?? row.agents).map((item) => toString(item)).filter(Boolean),
    default_constraints: asArray(row.default_constraints ?? row.constraints).map((item) => toString(item)).filter(Boolean),
    default_validation: asArray(row.default_validation ?? row.validation)
      .map((item) => toString(item))
      .filter((item): item is "lint" | "test" | "typecheck" => item === "lint" || item === "test" || item === "typecheck"),
  };
}

function normalizePromptPreset(input: unknown): PromptPreset {
  const row = toRecord(input);
  const key = toString(row.key ?? row.id ?? row.preset_id, "preset");
  const title = toString(row.title ?? row.name ?? row.label, "Preset");
  const defaultGoal = toString(row.default_goal ?? row.goal ?? row.prompt ?? row.objective);
  const examplePrompt = toString(row.example_prompt);
  const examples = asArray(row.examples ?? row.example_prompts ?? row.sample_prompts).map((item) => toString(item)).filter(Boolean);
  return {
    id: key,
    key,
    name: title,
    description: toString(row.description),
    goal: defaultGoal,
    constraints: asArray(row.default_constraints ?? row.constraints).map((item) => toString(item)).filter(Boolean),
    examples: [examplePrompt, ...examples].filter(Boolean),
    app_type: toString(row.app_type),
    default_agents: asArray(row.default_agents).map((item) => toString(item)).filter(Boolean),
    example_prompt: examplePrompt,
    recommended_fields: asArray(row.recommended_fields).map((item) => toString(item)).filter(Boolean),
    tags: asArray(row.tags).map((item) => toString(item)).filter(Boolean),
  };
}

function normalizeAgent(input: unknown): FactoryAgent {
  const row = toRecord(input);
  return {
    id: toString(row.id ?? row.agent_id ?? row.role, "agent"),
    key: toString(row.role ?? row.id ?? row.agent_id),
    name: toString(row.name ?? row.label ?? row.agent_name ?? row.role, "Agent"),
    role: toString(row.role ?? row.id ?? row.agent_id),
    description: toString(row.description),
    enabled: row.enabled == null ? true : Boolean(row.enabled),
    queue_name: toString(row.queue_name),
    model_name: toString(row.model_name),
  };
}

function normalizeMode(input: unknown): FactoryMode {
  const row = toRecord(input);
  return {
    id: toString(row.id ?? row.mode_id ?? row.key, "mode"),
    key: toString(row.key ?? row.id ?? row.mode_id),
    name: toString(row.title ?? row.name ?? row.label, "Mode"),
    description: toString(row.description),
    app_types: asArray(row.app_types ?? row.app_type).map((item) => toString(item)).filter(Boolean),
  };
}

export function getFactoryApiBase(): string {
  return FACTORY_API_BASE;
}

export async function getFactoryOverview(): Promise<FactoryOverviewPayload> {
  if (FACTORY_MOCK_MODE) return mockOverview();
  const raw = await fetchFactory("/api/v1/dashboard/overview");
  const payload = toRecord(raw);
  const counts = toRecord(payload.counts);
  const summary = toRecord(payload.summary);
  const totalRuns = toNumber(counts.total_runs ?? summary.total_runs);
  const failedRuns = toNumber(summary.failed_runs);
  const computedSuccessRate = totalRuns > 0 ? (totalRuns - failedRuns) / totalRuns : 0;
  return {
    summary: {
      total_runs: totalRuns,
      active_runs: toNumber(counts.active_runs ?? summary.active_runs),
      failed_runs: failedRuns,
      open_issues: toNumber(counts.open_issues ?? summary.open_issues),
      unread_messages: toNumber(counts.messages ?? summary.unread_messages),
      success_rate: toNumber(summary.success_rate, computedSuccessRate),
    },
    issue_counts: {
      p0: toNumber(toRecord(payload.issue_counts).p0),
      p1: toNumber(toRecord(payload.issue_counts).p1),
      p2: toNumber(toRecord(payload.issue_counts).p2),
      p3: toNumber(toRecord(payload.issue_counts).p3),
    },
    recent_runs: asArray(payload.recent_runs).map(normalizeRun),
    recent_messages: asArray(payload.recent_messages).map(normalizeMessage),
    recent_artifacts: asArray(payload.recent_artifacts).map(normalizeArtifact),
  };
}

export async function getFactoryRuns(params?: FactoryListParams): Promise<FactoryRunRow[]> {
  if (FACTORY_MOCK_MODE) return mockRuns;
  const raw = await fetchFactory(`/api/v1/runs${queryString(params)}`);
  const payload = toRecord(raw);
  return asArray(payload.runs ?? payload.items ?? payload).map(normalizeRun);
}

export async function getFactoryTemplates(): Promise<RunTemplate[]> {
  if (FACTORY_MOCK_MODE) return mockTemplates;
  const raw = await fetchFactory("/api/v1/factory/templates");
  const payload = toRecord(raw);
  return asArray(payload.templates ?? payload.items ?? payload).map(normalizeTemplate);
}

export async function getFactoryPromptPresets(): Promise<PromptPreset[]> {
  if (FACTORY_MOCK_MODE) return mockPresets;
  const raw = await fetchFactory("/api/v1/factory/prompt-presets");
  const payload = toRecord(raw);
  return asArray(payload.presets ?? payload.prompt_presets ?? payload.items ?? payload).map(normalizePromptPreset);
}

export async function getFactoryWorkspaces(): Promise<Workspace[]> {
  if (FACTORY_MOCK_MODE) return mockWorkspaces;
  const raw = await fetchFactory("/api/v1/factory/workspaces");
  const payload = toRecord(raw);
  return asArray(payload.workspaces ?? payload.items ?? payload).map(normalizeWorkspace);
}

export async function createFactoryWorkspace(payload: FactoryWorkspaceCreateRequest): Promise<Workspace> {
  if (FACTORY_MOCK_MODE) {
    return normalizeWorkspace({
      id: payload.key,
      key: payload.key,
      name: payload.name,
      repo_path: payload.repo_path,
      app_type: payload.app_type,
      is_active: payload.is_active ?? true,
      repo_exists: false,
      default_branch: payload.default_branch ?? "main",
      metadata_json: payload.metadata ?? {},
    });
  }
  const raw = await postFactory("/api/v1/factory/workspaces", payload);
  const root = toRecord(raw);
  return normalizeWorkspace(root.workspace ?? root);
}

export async function bootstrapFactoryWorkspace(
  payload: FactoryWorkspaceBootstrapRequest,
): Promise<FactoryWorkspaceBootstrapResponse> {
  if (FACTORY_MOCK_MODE) {
    return {
      ok: true,
      status: "deps_installed",
      workspace_path: String(payload.workspace_path ?? "/workspace"),
      host: "localhost",
      log_tail: "Mock workspace bootstrap completed",
    };
  }
  const raw = await postFactory("/workspaces/bootstrap", payload);
  const row = toRecord(raw);
  return {
    ok: Boolean(row.ok ?? false),
    status: toString(row.status, "unknown"),
    workspace_path: toString(row.workspace_path),
    host: toString(row.host),
    log_tail: toString(row.log_tail),
  };
}

export async function getFactoryAgents(): Promise<FactoryAgent[]> {
  if (FACTORY_MOCK_MODE) return mockAgents;
  const raw = await fetchFactory("/api/v1/factory/agents");
  const payload = toRecord(raw);
  return asArray(payload.agents ?? payload.items ?? payload).map(normalizeAgent);
}

export async function getFactoryModes(): Promise<FactoryMode[]> {
  if (FACTORY_MOCK_MODE) return mockModes;
  const raw = await fetchFactory("/api/v1/factory/modes");
  const payload = toRecord(raw);
  return asArray(payload.modes ?? payload.items ?? payload).map(normalizeMode);
}

function buildComposePayload(payload: FactoryComposeRunRequest): Record<string, unknown> {
  const checks = payload.checks ?? { lint: true, test: true, typecheck: true };
  return {
    name: payload.name ?? payload.run_name ?? "",
    goal: payload.goal ?? "",
    template_key: payload.template_key ?? payload.template_id ?? "",
    preset_key: payload.preset_key ?? payload.prompt_preset_id ?? "",
    workspace_id: payload.workspace_id ?? "",
    mode: payload.mode ?? "",
    app_type: payload.app_type ?? "",
    agents: payload.agents ?? [],
    constraints: payload.constraints ?? [],
    auto_start: Boolean(payload.auto_start),
    source_channel: payload.source_channel ?? "dashburg",
    create_initial_tasks: payload.create_initial_tasks ?? true,
    metadata: {
      ...(payload.metadata ?? {}),
      dashburg: { checks },
    },
  };
}

export async function composeFactoryRun(payload: FactoryComposeRunRequest): Promise<FactoryComposeRunResponse> {
  if (FACTORY_MOCK_MODE) {
    const mockRun: FactoryRun = {
      ...mockRuns[0],
      id: `run_${Date.now()}`,
      app_name: payload.run_name || payload.name || "New Factory Run",
      run_name: payload.run_name ?? payload.name,
      workspace_id: payload.workspace_id,
      template_id: payload.template_id ?? payload.template_key,
      mode: payload.mode,
      app_type: payload.app_type,
      agents: payload.agents,
      status: payload.auto_start ? "running" : "queued",
      current_stage: payload.auto_start ? "plan" : "composed",
      progress_pct: payload.auto_start ? 4 : 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    return { run_id: mockRun.id, run: mockRun, composed_payload: payload as Record<string, unknown> };
  }
  const request = buildComposePayload(payload);
  const raw = await postFactory("/api/v1/factory/runs/compose", request);
  const root = toRecord(raw);
  const run = normalizeRun(root.run ?? root);
  const runId = toString(run.id || toRecord(root.run).id, "");
  if (!runId) throw new FactoryApiError("Compose response missing run id", 500);
  return {
    run_id: runId,
    run,
    resolved: toRecord(root.resolved),
    composed_payload: toRecord(root.resolved ?? root.composed_payload ?? request),
  };
}

export async function startFactoryRun(runId: string): Promise<FactoryRun> {
  if (FACTORY_MOCK_MODE) return { ...mockRuns[0], id: runId, status: "running", current_stage: "plan", updated_at: new Date().toISOString() };
  const raw = await postFactory(`/api/v1/factory/runs/${encodeURIComponent(runId)}/start`, {});
  const root = toRecord(raw);
  return normalizeRun(root.run ?? root);
}

export async function startFactoryPreview(payload: FactoryPreviewStartRequest): Promise<FactoryPreviewStartResponse> {
  const body: Record<string, unknown> = {
    run_id: payload.run_id,
    workspace_id: payload.workspace_id,
    workspace_path: payload.workspace_path,
    port: payload.port,
    ensure_backend: payload.ensure_backend ?? true,
  };
  if (FACTORY_MOCK_MODE) {
    return {
      ok: true,
      status: "started",
      preview_url: "http://127.0.0.1:8081",
      workspace_path: String(payload.workspace_path ?? "/workspace"),
      port: Number(payload.port ?? 8081),
      host: "localhost",
      backend_status: "started",
      backend_url: "http://127.0.0.1:8000",
      log_tail: "Mock preview launched",
    };
  }
  const raw = await postFactory("/preview/start", body);
  const row = toRecord(raw);
  return {
    ok: Boolean(row.ok ?? true),
    status: toString(row.status, "starting"),
    preview_url: toSafePreviewUrl(row.preview_url),
    workspace_path: toString(row.workspace_path),
    port: toNumber(row.port, 8081),
    host: toString(row.host),
    backend_status: toString(row.backend_status),
    backend_url: toString(row.backend_url),
    log_tail: toString(row.log_tail),
  };
}

export async function stopFactoryPreview(payload: FactoryPreviewStopRequest): Promise<FactoryPreviewStopResponse> {
  const body: Record<string, unknown> = {
    run_id: payload.run_id,
    workspace_id: payload.workspace_id,
    workspace_path: payload.workspace_path,
    port: payload.port,
    stop_backend: payload.stop_backend ?? false,
  };
  if (FACTORY_MOCK_MODE) {
    return {
      ok: true,
      status: "stopped",
      workspace_path: String(payload.workspace_path ?? "/workspace"),
      port: Number(payload.port ?? 8081),
      host: "localhost",
      backend_status: payload.stop_backend ? "stopped" : "skipped",
      backend_url: "http://127.0.0.1:8000",
      log_tail: "Mock preview stopped",
    };
  }
  const raw = await postFactory("/preview/stop", body);
  const row = toRecord(raw);
  return {
    ok: Boolean(row.ok ?? true),
    status: toString(row.status, "stopped"),
    workspace_path: toString(row.workspace_path),
    port: toNumber(row.port, 8081),
    host: toString(row.host),
    backend_status: toString(row.backend_status),
    backend_url: toString(row.backend_url),
    log_tail: toString(row.log_tail),
  };
}

export async function getFactoryRunDetail(runId: string): Promise<FactoryRunDetail> {
  if (FACTORY_MOCK_MODE) return mockRunDetail(runId);

  const encoded = encodeURIComponent(runId);
  const [runRaw, tasksRaw, timelineRaw, issuesRaw, artifactsRaw, inboxRaw, messagesRaw, metricsRaw] = await Promise.all([
    fetchFactory(`/api/v1/runs/${encoded}`),
    tryFetchFactory(`/api/v1/runs/${encoded}/tasks`),
    tryFetchFactory(`/api/v1/runs/${encoded}/timeline`),
    tryFetchFactory(`/api/v1/runs/${encoded}/issues`),
    tryFetchFactory(`/api/v1/runs/${encoded}/artifacts`),
    tryFetchFactory(`/api/v1/runs/${encoded}/inbox`),
    tryFetchFactory(`/api/v1/factory/runs/${encoded}/messages`),
    tryFetchFactory(`/api/v1/runs/${encoded}/metrics`),
  ]);

  const runPayload = toRecord(runRaw);
  const runNormalized = normalizeRun(runPayload);
  const metadataFactory = toRecord(toRecord(runPayload.metadata_json).factory);
  const workspaceId = runNormalized.workspace_id || toString(metadataFactory.workspace_id);
  const workspaceRaw = workspaceId ? await tryFetchFactory(`/api/v1/factory/workspaces/${encodeURIComponent(workspaceId)}`) : null;
  const workspacePreview = workspaceRaw ? normalizeWorkspace(workspaceRaw).preview_url : "";
  const tasks = asArray(toRecord(tasksRaw ?? {}).items ?? tasksRaw).map(normalizeTask);
  const timelineRows = asArray(toRecord(timelineRaw ?? {}).timeline ?? toRecord(timelineRaw ?? {}).items ?? timelineRaw).map((row) => {
    const item = toRecord(row);
    return normalizeTimelineEvent({
      id: item.task_id ?? item.id,
      stage: item.name ?? item.stage ?? item.agent_role,
      status: item.status,
      message: item.agent_role,
      created_at: item.started_at ?? item.finished_at,
    });
  });
  const issues = asArray(toRecord(issuesRaw ?? {}).items ?? issuesRaw).map(normalizeIssue);
  const artifacts = asArray(toRecord(artifactsRaw ?? {}).items ?? artifactsRaw).map(normalizeArtifact);
  const inboxMessages = asArray(toRecord(inboxRaw ?? {}).items ?? inboxRaw).map(normalizeMessage);
  const runMessages = asArray(toRecord(messagesRaw ?? {}).items ?? messagesRaw).map(normalizeMessage);
  const metricsItems = asArray(toRecord(metricsRaw ?? {}).items ?? metricsRaw);

  const previewCandidates = Array.from(
    new Set(
      [
        runNormalized.preview_url,
        workspacePreview,
        ...artifacts.map((artifact) => toSafePreviewUrl(artifact.preview_url)),
      ].filter((value): value is string => Boolean(value)),
    ),
  );

  return {
    run: runNormalized,
    preview_url: previewCandidates[0] || "",
    preview_candidates: previewCandidates,
    timeline: timelineRows,
    tasks,
    issues,
    artifacts,
    messages: runMessages.length > 0 ? runMessages : inboxMessages,
    metrics: normalizeMetricsSummary({
      tasks_completed_last_24h: metricsItems.length,
      average_issues_per_run: issues.length,
      runs_last_24h: 0,
      build_success_rate: 0,
      mean_cycle_time_ms: 0,
    }),
    logs: [],
    output: {
      inputs_json: toRecord(runPayload.inputs_json),
      metadata_json: toRecord(runPayload.metadata_json),
      metrics_items: metricsItems,
    },
    raw_run: runPayload,
  };
}

export async function getFactoryInbox(params?: FactoryListParams): Promise<FactoryInboxMessage[]> {
  if (FACTORY_MOCK_MODE) return mockMessages;
  if (params?.run_id) {
    const raw = await fetchFactory(`/api/v1/runs/${encodeURIComponent(params.run_id)}/inbox${queryString({ recipient: params.recipient })}`);
    return asArray(toRecord(raw).items ?? raw).map(normalizeMessage);
  }
  const raw = await tryFetchFactory(`/api/v1/inbox/messages${queryString(params)}`);
  if (!raw) return [];
  return asArray(toRecord(raw).messages ?? toRecord(raw).items ?? raw).map(normalizeMessage);
}

export async function getFactoryIssues(params?: FactoryListParams): Promise<FactoryIssue[]> {
  if (FACTORY_MOCK_MODE) return mockIssues;
  if (params?.run_id) {
    const raw = await fetchFactory(`/api/v1/runs/${encodeURIComponent(params.run_id)}/issues${queryString({ severity: params.severity, status: params.status })}`);
    return asArray(toRecord(raw).items ?? raw).map(normalizeIssue);
  }
  const raw = await tryFetchFactory(`/api/v1/issues${queryString(params)}`);
  if (!raw) return [];
  return asArray(toRecord(raw).issues ?? toRecord(raw).items ?? raw).map(normalizeIssue);
}

export async function getFactoryArtifacts(params?: FactoryListParams): Promise<FactoryArtifact[]> {
  if (FACTORY_MOCK_MODE) return mockArtifacts;
  if (params?.run_id) {
    const raw = await fetchFactory(`/api/v1/runs/${encodeURIComponent(params.run_id)}/artifacts${queryString({ kind: params.kind })}`);
    return asArray(toRecord(raw).items ?? raw).map(normalizeArtifact);
  }
  const raw = await tryFetchFactory(`/api/v1/artifacts${queryString(params)}`);
  if (!raw) return [];
  return asArray(toRecord(raw).artifacts ?? toRecord(raw).items ?? raw).map(normalizeArtifact);
}

export async function getFactoryMetricsSummary(): Promise<FactoryMetricsSummary> {
  if (FACTORY_MOCK_MODE) return mockMetrics();
  const raw = await fetchFactory("/api/v1/metrics/summary");
  const payload = toRecord(raw);
  const totalRuns = toNumber(payload.total_runs);
  const completedRuns = toNumber(payload.completed_runs);
  return normalizeMetricsSummary({
    build_success_rate: totalRuns > 0 ? completedRuns / totalRuns : 0,
    mean_cycle_time_ms: 0,
    average_issues_per_run: 0,
    runs_last_24h: totalRuns,
    tasks_completed_last_24h: asArray(payload.latest_metrics).length,
  });
}

export async function getFactoryHealthChecks(): Promise<FactoryHealthStatus[]> {
  const now = new Date().toISOString();
  if (FACTORY_MOCK_MODE) {
    return [
      { label: "API reachable", ok: true, endpoint: "/api/v1/dashboard/overview", checked_at: now },
      { label: "Worker reachable", ok: true, endpoint: "/api/v1/factory/agents", checked_at: now },
    ];
  }
  const checks: Array<{ label: string; endpoint: string }> = [
    { label: "API reachable", endpoint: "/api/v1/dashboard/overview" },
    { label: "Worker reachable", endpoint: "/api/v1/factory/agents" },
  ];
  return Promise.all(
    checks.map(async (check) => {
      try {
        await fetchFactory(check.endpoint);
        return { ...check, ok: true, checked_at: now };
      } catch (error) {
        return { ...check, ok: false, checked_at: now, error: String((error as { message?: unknown })?.message ?? error) };
      }
    }),
  );
}
