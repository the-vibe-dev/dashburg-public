export type ModuleInfo = {
  key: string;
  name: string;
  sidebar_label: string;
  routes: { path: string; label: string }[];
  cards: { title: string; description: string; href: string }[];
};

export type MetricsSummary = {
  runs_today: number;
  runs_wtd: number;
  runs_mtd: number;
  running_now: number;
  failures_today: number;
  success_rate: number;
  total_last_24h: number;
  recent_failures: {
    id: string;
    repo_name: string;
    stage: string;
    updated_at: string;
    status: string;
  }[];
  live_active_runs: {
    id: string;
    repo_name: string;
    stage: string;
    status: string;
    started_at: string | null;
    updated_at: string;
  }[];
};

export type Run = {
  id: string;
  repo_name: string;
  monitor_name: string;
  status: string;
  stage: string;
  topic: string;
  timer_unit: string;
  run_kind: string;
  started_at: string | null;
  ended_at: string | null;
  updated_at: string;
};

export type VideoOverview = {
  generated_at: string;
  summary: {
    repos: number;
    healthy: number;
    running: number;
    errors: number;
  };
  rollup: {
    status: string;
    total_views: number;
    followers: number;
    coverage_live: number;
    coverage_total: number;
    by_platform: { platform: string; views: number; followers: number }[];
    upload_states: { ok: number; fail: number; pending: number; off: number; unknown: number };
    token_health: { ok: number; bad: number; unknown: number };
    last_updated: string;
  };
  repos: Array<Record<string, unknown>>;
  running: Array<Record<string, unknown>>;
};

export type Project = {
  id: number;
  title: string;
  description: string;
  priority_rank: number | null;
  created_at: string;
  updated_at: string;
};

export type ProjectTaskPreview = {
  id: string;
  content: string;
  status: "todo" | "in_progress" | "done" | "blocked" | string;
  priority: "low" | "medium" | "high" | "critical" | string;
  created_at: string;
};

export type ProjectDashboardItem = Project & {
  notes_preview: string;
  top_tasks: ProjectTaskPreview[];
};

export type ProjectPage = {
  blocks: Array<Record<string, unknown>>;
};

export type TopicTrendingItem = {
  id: string;
  topic: string;
  pain_count: number;
  last_seen: string;
  [key: string]: unknown;
};

export type TopicRun = {
  id?: string;
  run_id?: string;
  status: string;
  started_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  mode?: string;
  trigger?: string;
  [key: string]: unknown;
};

export type TopicRunDetail = {
  id?: string;
  run_id?: string;
  summary?: Record<string, unknown>;
  clusters?: Array<Record<string, unknown>>;
  ideas?: Array<Record<string, unknown>>;
  pains?: Array<Record<string, unknown>>;
  provider_stats?: Record<string, unknown>;
  cache_stats?: Record<string, unknown>;
  [key: string]: unknown;
};

export type TopicLogsTailResponse = {
  lines: string[];
  offset: number;
  next_offset: number;
  has_more?: boolean;
  [key: string]: unknown;
};

export type TopicRunTargetedRequest = {
  query: string;
  topic: string;
  limit: number;
  enable_youtube: boolean;
  target_final_ideas?: number;
  ingest_overrides?: Record<string, unknown>;
  max_comment_posts?: number;
  max_comments_per_thread?: number;
  subreddits?: string[];
  search_terms?: string[];
  use_default_subreddits?: boolean;
  use_default_search_terms?: boolean;
  enable_reddit?: boolean;
  enable_web_search?: boolean;
  low_fanout_mode?: boolean;
  category_mode?: "broad" | "focused" | "strict";
  category_filters?: string[];
  exclude_categories?: string[];
  recency_window?: "7d" | "30d" | "90d" | "1y";
};

export type TopicRunAutoRequest = {
  ideas_per_run: number;
  target_topics: number;
  limit_per_topic: number;
  enable_youtube: boolean;
  target_final_ideas?: number;
  ingest_overrides?: Record<string, unknown>;
  max_posts_per_source?: number;
  max_comment_posts?: number;
  max_comments_per_thread?: number;
  subreddits?: string[];
  search_terms?: string[];
  use_default_subreddits?: boolean;
  use_default_search_terms?: boolean;
  enable_reddit?: boolean;
  enable_web_search?: boolean;
  low_fanout_mode?: boolean;
  category_mode?: "broad" | "focused" | "strict";
  category_filters?: string[];
  exclude_categories?: string[];
  recency_window?: "7d" | "30d" | "90d" | "1y";
  provider_order?: string[];
  safe_mode?: boolean;
  concurrency?: number;
};

export type TopicRunStartRequest = {
  query: string;
  topic: string;
  limit: number;
  enable_youtube?: boolean;
  target_final_ideas?: number;
  enable_pain_graph?: boolean;
  ingest_overrides?: Record<string, unknown>;
  subreddits?: string[];
  search_terms?: string[];
  use_default_subreddits?: boolean;
  use_default_search_terms?: boolean;
  enable_reddit?: boolean;
  enable_web_search?: boolean;
  low_fanout_mode?: boolean;
  category_mode?: "broad" | "focused" | "strict";
  category_filters?: string[];
  exclude_categories?: string[];
};

export type TopicSearchStrategy = {
  defaults?: Record<string, unknown>;
  overrides?: Record<string, unknown>;
  effective?: Record<string, unknown>;
  source?: string;
  [key: string]: unknown;
};

export type TopicSearchStrategyUpdateRequest = {
  default_subreddits?: string[];
  default_search_terms?: string[];
  pain_queries?: string[];
  custom_sites?: string[];
  web_provider_chain?: string[];
  methods?: string[];
};

export type TopicIdeaDetail = Record<string, unknown>;

export type TopicAppgenIdea = Record<string, unknown>;
export type TopicAppgenRun = Record<string, unknown>;
export type TopicAppgenAnalyzeRunRequest = {
  appgen_run_id: string;
};
export type TopicAppgenAnalyzeRunResponse = Record<string, unknown>;
export type TopicAppgenGenerateRequest = {
  pain_point_ids?: string[];
  seed_text?: string;
  count: number;
  constraints?: Record<string, unknown>;
};
export type TopicAppgenGenerateResponse = {
  run_id: string;
  idea_ids: string[];
};

export type TopicSignal = {
  id: string;
  run_id?: string;
  source?: string;
  title?: string;
  body?: string;
  score?: number;
  [key: string]: unknown;
};

export type TopicMicroProblem = {
  id?: string;
  text: string;
  evidence_snippet: string;
  intensity_score: number;
  repeatability_score: number;
  automation_possible: number;
  workaround_detected: boolean;
  workaround_type?: string;
  cluster_id?: string;
  community_id?: string;
  [key: string]: unknown;
};

export type TopicPainGraphEdge = {
  source_problem_id: string;
  target_problem_id: string;
  similarity: number;
  community_id: string;
  [key: string]: unknown;
};

export type PromotedIdea = {
  id: number;
  source_run_id: string;
  source_idea_id: string;
  title: string;
  summary: string;
  idea_type?: "video" | "app" | "saas" | string;
  problem_summary?: string;
  target_user?: string;
  why_now?: string;
  first_build_step?: string;
  raw_json: Record<string, unknown>;
  created_at: string;
};

export type PromotedIdeaCreateRequest = {
  run_id: string;
  idea_id: string;
  raw_json: Record<string, unknown>;
};

export type TopicOpportunity = {
  id?: string;
  title: string;
  summary: string;
  idea_type: "video" | "app" | "saas" | string;
  problem_summary: string;
  target_user: string;
  why_now: string;
  first_build_step: string;
  source_run_id?: string;
  cluster_id?: string;
  evidence?: string[];
  score_components?: Record<string, number>;
  score: number;
  raw?: Record<string, unknown>;
  [key: string]: unknown;
};

export type WeeklyReview = {
  id: string;
  week_start: string;
  week_end: string;
  status: string;
  generated_by: string;
  dataset: Record<string, unknown>;
  analysis: Record<string, unknown>;
  analysis_model?: string | null;
  analysis_error?: string | null;
  created_at: string;
  updated_at: string;
};

export type RemoteOpsSettings = {
  main_llm_provider: "openai" | "ollama" | "custom_http";
  main_llm_model: string;
  main_llm_base_url: string;
  main_llm_api_key_ref: string;
  chat_enabled: boolean;
  execution_mode: "propose_only" | "require_confirm" | "auto_execute_allowlisted";
  default_target_node_id: string;
  job_timeouts: Record<string, number>;
  log_retention_days: number;
  allow_codex_jobs: boolean;
  allow_system_actions: boolean;
  allow_apt_upgrade: boolean;
  max_concurrent_jobs_per_node: number;
  max_concurrent_jobs_global: number;
  terminal_enabled: boolean;
  terminal_idle_timeout_minutes: number;
  terminal_max_sessions: number;
  terminal_recording_enabled: boolean;
  chat_client_token: string;
};

export type RemoteOpsNode = {
  id: string;
  enabled: boolean;
  label: string;
  base_url: string;
  supports_codex: boolean;
  supports_terminal: boolean;
  max_concurrent_jobs: number;
  capabilities: Record<string, unknown>;
  allowed_job_types: string[];
  allowed_repos: string[];
  allowed_services: string[];
  notes: string;
  key_id: string;
  last_seen_at: string | null;
  created_at: string;
  updated_at: string;
  keys: Array<{ key_id: string; created_at: string; disabled_at: string | null }>;
  install?: {
    node_id: string;
    key_id: string;
    secret: string;
    config_yaml: string;
    install_commands: string;
    main_terminal_commands?: string;
  };
};

export type RemoteServer = {
  id: string;
  name: string;
  base_url: string;
  codex_enabled: boolean;
  supports_terminal?: boolean;
  tags: string[];
  repos: string[];
  status: string;
  health: Record<string, unknown>;
  enabled?: boolean;
  last_seen_at?: string | null;
};

export type RemoteNodeHealthStatus = "healthy" | "slow" | "down" | "unknown";

export type RemoteNodeHealth = {
  node_id: string;
  ok: boolean;
  latency_ms: number | null;
  status: RemoteNodeHealthStatus;
  checked_at: string;
  error: string | null;
};

export type HostTopProcess = {
  pid: number;
  cpu_percent: number;
  mem_percent: number;
  command: string;
};

export type HostGpuInfo = {
  index: number;
  name: string;
  util_gpu: number;
  util_mem: number;
  memory_used_mib: number;
  memory_total_mib: number;
  temperature_c: number;
  power_w: number;
};

export type HostMonitorStatusPayload = {
  ok?: boolean;
  timestamp?: string;
  health?: {
    status?: string;
    issues?: string[];
  };
  cpu?: {
    usage_percent?: number;
    load1?: number;
    load5?: number;
    load15?: number;
  };
  memory?: {
    used_gib?: number;
    total_gib?: number;
    used_percent?: number;
  };
  swap?: {
    used_gib?: number;
    total_gib?: number;
    used_percent?: number;
  };
  disk?: {
    mount?: string;
    used_gib?: number;
    total_gib?: number;
    used_percent?: number;
  };
  ollama?: {
    status?: string;
    reachable?: boolean;
    service_present?: boolean;
    service_running?: boolean;
    process_count?: number;
    listening_11434?: boolean;
    models_count?: number;
    model_count?: number;
    models?: Array<{
      name?: string;
      model?: string;
      size?: number | null;
      size_vram?: number | null;
      context_length?: number | null;
      expires_at?: string | null;
      endpoint_url?: string | null;
    }>;
    endpoints?: Array<{
      url?: string;
      reachable?: boolean;
      model_count?: number;
      status?: string;
      error?: string | null;
    }>;
    error?: string;
    source_url?: string | null;
  };
  comfyui?: {
    status?: string;
    reachable?: boolean;
    queue_running?: number;
    queue_pending?: number;
    running_items?: string[];
    pending_items?: string[];
    error?: string | null;
    source_url?: string | null;
  };
  comfyui_wrapper?: {
    status?: string;
    reachable?: boolean;
    enabled?: boolean;
    queue_waiting?: number;
    queue_active?: number;
    queued_seconds?: number;
    max_queue_depth?: number | null;
    endpoints?: Array<Record<string, unknown>>;
    source_url?: string | null;
    error?: string | null;
    details?: Record<string, unknown>;
  };
  gpu_audio_wrapper?: {
    status?: string;
    reachable?: boolean;
    enabled?: boolean;
    queue_waiting?: number;
    queue_active?: number;
    queued_seconds?: number;
    max_queue_depth?: number | null;
    endpoints?: Array<Record<string, unknown>>;
    source_url?: string | null;
    error?: string | null;
    details?: Record<string, unknown>;
  };
  capabilities?: {
    has_gpu?: boolean;
    has_ollama?: boolean;
    has_comfyui?: boolean;
    has_comfyui_wrapper?: boolean;
    has_gpu_audio_wrapper?: boolean;
  };
  gpus?: HostGpuInfo[];
  top_processes?: HostTopProcess[];
  gpu_processes?: HostTopProcess[];
};

export type RemoteNodeHostMonitor = {
  node_id: string;
  label: string;
  monitor_base_url: string;
  ok: boolean;
  latency_ms: number | null;
  status: RemoteNodeHealthStatus;
  checked_at: string;
  error: string | null;
  payload: HostMonitorStatusPayload;
};

export type RemoteTerminalSession = {
  id: string;
  node_id: string;
  status: string;
  created_by: string;
  record_io: boolean;
  last_activity_at: string;
  created_at: string;
  closed_at: string | null;
};

export type OrchestrationSettings = {
  preferred_terminal_node_id: string;
  preferred_execution_mode: "delegated_runner" | "direct_ssh";
  default_codex_mode: "read-only" | "workspace-write" | "danger-full-access";
  default_timeout_seconds: number;
  global_max_active_jobs: number;
  default_max_retries: number;
  scheduler_poll_seconds: number;
};

export type OrchestrationJob = {
  id: string;
  title: string;
  task_type: string;
  target_node: string;
  repo_path: string;
  workspace_path: string;
  prompt: string;
  instructions: string;
  execution_mode: "delegated_runner" | "direct_ssh" | string;
  codex_mode: "read-only" | "workspace-write" | "danger-full-access" | string;
  priority: number;
  timeout_seconds: number;
  dependencies: string[];
  status: string;
  runner_job_id: string;
  retry_count: number;
  max_retries: number;
  assigned_runner: string;
  logs_url: string;
  result_summary: string;
  changed_files: string[];
  artifacts: Array<Record<string, unknown>>;
  metadata: Record<string, unknown>;
  dependency_state: Array<Record<string, unknown>>;
  last_error: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
};

export type OrchestrationNodeSummary = {
  id: string;
  label: string;
  base_url: string;
  enabled: boolean;
  supports_codex: boolean;
  supports_terminal: boolean;
  max_concurrent_jobs: number;
  running_jobs: number;
  queued_jobs: number;
  health_status: string;
  capabilities: Record<string, unknown>;
  repos: string[];
  mailbox_counts: Record<string, number>;
};

export type OrchestrationMailboxItem = {
  id: string;
  node_id: string;
  direction: string;
  type: string;
  subject: string;
  body: string;
  job_id: string;
  run_id: string;
  severity: string;
  status: string;
  created_at: string;
  updated_at: string | null;
  from: string;
  to: string;
  attachments: Array<Record<string, unknown>>;
  tags: string[];
  acknowledged: boolean;
  acknowledged_at: string | null;
  archived: boolean;
  archived_at: string | null;
  metadata: Record<string, unknown>;
};

export type OrchestrationOverview = {
  localops_mode: string;
  orchestration_mode: string;
  settings: OrchestrationSettings;
  nodes: OrchestrationNodeSummary[];
  running_jobs: OrchestrationJob[];
  queued_jobs: OrchestrationJob[];
  recent_jobs: OrchestrationJob[];
  dependency_edges: Array<Record<string, unknown>>;
  mailbox: OrchestrationMailboxItem[];
};

export type OrchestrationTerminalLaunch = {
  node_id: string;
  cwd: string;
  command: string;
  injected_label: string;
};

export type ScheduleOpsNode = {
  id: string;
  label: string;
  enabled: boolean;
  base_url: string;
  supports_codex: boolean;
  max_concurrent_jobs: number;
  health_status: string;
  health_ok: boolean;
  last_seen_at: string | null;
};

export type ScheduleOpsEntry = {
  id: string;
  label: string;
  kind: "mailbox_dispatch" | "shell_command" | string;
  enabled: boolean;
  cron: string;
  recipient_kind: "any" | "runner" | "agent" | string;
  recipient: string;
  limit: number;
  command: string;
};

export type ScheduleOpsConfig = {
  version: number;
  node_id: string;
  timezone: string;
  notes: string;
  entries: ScheduleOpsEntry[];
  updated_at: string;
};

export type ScheduleOpsNodePayload = {
  config: ScheduleOpsConfig;
  rendered: {
    lines: string[];
    warnings: string[];
    path: string;
  };
  apply?: {
    ok: boolean;
    dest_path: string;
    install_rc: number;
    install_stdout: string;
    install_stderr: string;
    reload_rc: number;
    reload_stdout: string;
    reload_stderr: string;
  };
};

export type ScheduleOpsEntryRuntimeStatus = {
  id: string;
  label: string;
  kind: "mailbox_dispatch" | "shell_command" | string;
  enabled: boolean;
  cron: string;
  recipient_kind: "any" | "runner" | "agent" | string;
  recipient: string;
  limit: number;
  command: string;
  log_path: string;
  last_seen_at: string | null;
  running_now: boolean;
  matching_pids: number[];
  installed_line_present: boolean;
  status: "running" | "idle" | "scheduled" | "missing" | "disabled" | string;
};

export type ScheduleOpsInstallStatus = {
  path: string;
  installed: boolean;
  managed_header?: boolean;
  line_count?: number;
  error?: string | null;
};

export type ScheduleOpsNodeStatus = {
  node_id: string;
  generated_at: string | null;
  config_updated_at: string | null;
  install: ScheduleOpsInstallStatus;
  entries: ScheduleOpsEntryRuntimeStatus[];
  error?: string;
  node: ScheduleOpsNode;
};

export type ScheduleOpsClusterStatus = {
  items: ScheduleOpsNodeStatus[];
};

export type RedisBrokerAlert = {
  severity: "info" | "warn" | "error" | string;
  code: string;
  message: string;
};

export type RedisBrokerProvider = {
  provider: string;
  base_url: string;
  capability: "llm" | "vision" | "image" | "tts" | "stt" | string;
  healthy: boolean;
  circuit_open: boolean;
  inflight: number;
  max_concurrency: number;
  priority?: number;
  dispatch_delay_ms?: number;
  latency_ms: number;
  priority_class: "primary" | "secondary" | "tertiary" | string;
  routing_reason?: "explicit_flag" | "heuristic" | "default" | string;
  operation_type?: string | null;
};

export type RedisBrokerServiceFamily = {
  healthy: boolean;
  up?: number;
  total?: number;
  inflight?: number;
  detail?: string;
};

export type RedisBrokerOverview = {
  ok: boolean;
  generated_at: string;
  broker: {
    status: string;
    redis: string;
  };
  services: {
    redis: RedisBrokerServiceFamily;
    comfy: RedisBrokerServiceFamily;
    ollama: RedisBrokerServiceFamily;
    tts: RedisBrokerServiceFamily;
    stt: RedisBrokerServiceFamily;
  };
  queues: {
    queues: Record<string, number>;
    retries: Record<string, number>;
    dlq: Record<string, number>;
    states: Record<string, number>;
    attempt_states: Record<string, number>;
  };
  providers: RedisBrokerProvider[];
  durations: { avg_seconds: number; p95_seconds: number };
  failures_24h: Record<string, number>;
  alerts: RedisBrokerAlert[];
  source?: { base_url?: string };
  errors?: string[];
  ai_route_discovery?: {
    enabled: boolean;
    repos: Array<{ repo: string; path: string; has_wan2b_i2v_workflow: boolean }>;
    error?: string;
  };
};

export type RedisBrokerProviderConfig = {
  path: string;
  providers: Array<Record<string, unknown>>;
};

export type MailCenterFolder = {
  key: string;
  label: string;
  count: number;
};

export type MailCenterMessage = {
  id: string;
  thread_id: string;
  subject: string;
  snippet: string;
  body: string;
  from: string;
  to: string;
  cc: string[];
  bcc: string[];
  direction: "inbound" | "outbound" | string;
  status: string;
  folder: string;
  created_at: string;
  sent_at: string | null;
  received_at: string | null;
  updated_at: string | null;
  tags: string[];
  unread: boolean;
  has_attachments: boolean;
  attachments: Array<Record<string, unknown>>;
  processing_state: string;
  classification: string;
  automation_rule: string;
  reply_draft_state: string;
  failure_reason: string;
  retry_info: Record<string, unknown>;
  linked_entity: Record<string, unknown>;
  account: string;
  mailbox: string;
  source: string;
  metadata: Record<string, unknown>;
  recipient_node_id?: string;
  recipient_kind?: string;
  recipient_agent_slug?: string;
};

export type MailCenterThread = {
  thread_id: string;
  subject: string;
  snippet: string;
  latest_message_id: string;
  latest_at: string;
  message_count: number;
  unread_count: number;
  has_failed: boolean;
  participants: string[];
  status_counts: Record<string, number>;
  direction_mix: Record<string, number>;
  account: string;
  tags: string[];
  folder: string;
};

export type MailCenterOverview = {
  counts: Record<string, number>;
  statuses: Record<string, number>;
  processing: Record<string, number>;
  directions: Record<string, number>;
  accounts: Array<{ account: string; count: number }>;
  subsystem: {
    status: string;
    last_activity_at: string | null;
    sources: string[];
    threads: number;
  };
  folders: MailCenterFolder[];
};

export type MailCenterMessageDetail = {
  message: MailCenterMessage;
  thread: {
    thread_id: string;
    subject: string;
    message_count: number;
    messages: MailCenterMessage[];
    activity: Array<{
      at: string;
      event: string;
      summary: string;
      direction: string;
      id: string;
    }>;
  };
};

export type MailCenterRecipientNode = {
  node_id: string;
  label: string;
  address: string;
  kind: "runner" | string;
};

export type MailCenterRecipientAgent = {
  node_id: string;
  slug: string;
  name: string;
  address: string;
  kind: "agent" | string;
  status?: string;
};

export type MailCenterRecipients = {
  nodes: MailCenterRecipientNode[];
  agents: MailCenterRecipientAgent[];
};

export type RemoteServerDetail = {
  server: {
    id: string;
    name: string;
    base_url: string;
    codex_enabled: boolean;
    supports_terminal?: boolean;
    tags: string[];
    repos: string[];
  };
  health: Record<string, unknown>;
  metrics: Record<string, unknown>;
  services: Record<string, unknown>;
};

export type RemoteJob = {
  id: string;
  node_id: string;
  runner_job_id: string;
  job_type: string;
  status: string;
  params: Record<string, unknown>;
  result: Record<string, unknown>;
  created_by: string;
  log_offset: number;
  merged_label: boolean;
  archived: boolean;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
  runner_detail?: Record<string, unknown>;
};

export type TrendsRunStatus = "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | string;

export type TrendsRun = {
  id: string;
  status: TrendsRunStatus;
  started_at: string | null;
  finished_at: string | null;
  params_json: Record<string, unknown>;
  totals_json: Record<string, unknown>;
  error: string | null;
};

export type TrendsRunLogs = {
  run_id: string;
  offset: number;
  next_offset: number;
  total_lines: number;
  has_more: boolean;
  lines: string[];
};

export type TrendsRunStartRequest = {
  sources: {
    youtube: { enabled: boolean; limit?: number };
    trends: { enabled: boolean; limit?: number };
    reddit: { enabled: boolean; limit?: number };
    x_trends?: { enabled: boolean; limit?: number };
  };
  limits: {
    size: "small" | "medium" | "large";
    youtube?: number;
    reddit?: number;
    trends?: number;
    x_trends?: number;
  };
  sources_config?: {
    x_trends?: {
      enabled?: boolean;
      max_items?: number;
      use_auth?: boolean;
    };
    [key: string]: unknown;
  };
  categories: string[];
  subreddits: string[];
  region: string;
  query?: string;
  objective?: string;
  use_openai_strategy?: boolean;
  llm_rerank_top_n?: number;
  min_focus_relevance?: number;
};

export type TrendsTopicResult = {
  topic_id: string;
  title: string;
  score: number;
  sources: string[];
  source_details?: Record<string, unknown>;
  source_confidence?: "low" | "medium" | "high" | string;
  emerging_on_x?: boolean;
  summary?: string;
  hooks?: string[];
  channels?: Record<string, number>;
  channel_rankings?: Array<{
    channel_id?: string;
    channel_name?: string;
    relevance_pct?: number;
    relevance?: number;
    relevancePercent?: number;
    match_pct?: number;
    percent?: number;
    score?: number;
    why?: string;
    reason?: string;
    reason_code?: string;
    debug_reason?: string;
    match_reason?: string;
    overlap_terms?: string[];
    [key: string]: unknown;
  }>;
  [key: string]: unknown;
};

export type TrendsRunResults = {
  run_id: string;
  status: TrendsRunStatus;
  top_overall: TrendsTopicResult[];
  top_per_channel: Record<string, TrendsTopicResult[]>;
  top_by_source?: Record<string, TrendsTopicResult[]>;
  idea_candidates?: Array<Record<string, unknown>>;
  idea_candidates_by_type?: Record<string, Array<Record<string, unknown>>>;
  idea_groups?: Array<Record<string, unknown>>;
  big_calls?: Array<Record<string, unknown>>;
  score_breakdowns?: Record<string, Record<string, unknown>>;
  evidence_links?: Record<string, Array<Record<string, unknown>>>;
  recommended_next_actions?: string[];
  review_notes?: string[];
  strategy_status?: Record<string, unknown>;
  [key: string]: unknown;
};

export type TrendsOpenAiKeyStatus = {
  configured: boolean;
  source: string;
  masked: string;
};

export type TrendsTopicDetail = {
  topic_id?: string;
  id?: string;
  title?: string;
  summary?: string;
  llm_summary?: string;
  hooks?: string[];
  source_breakdown?: Record<string, unknown> | Array<Record<string, unknown>>;
  channels?: Record<string, number>;
  [key: string]: unknown;
};

export type TrendsTopicAction = "like" | "maybe" | "skip" | "used" | "blacklist";

export type TrendsTopicActionRequest = {
  action: TrendsTopicAction;
  note?: string;
};

export type TrendsExportRequest = {
  format: "topic_factory_v1" | "idea_factory_v2" | "topic_factory_v2";
  topic_ids: string[];
  run_id?: string;
  include_actions?: boolean;
};

export type LocalOpsExecutionMode = "propose_only" | "require_confirm" | "auto_execute_allowlisted";

export type LocalOpsSettings = {
  default_provider_id: "openai" | "ollama";
  default_model: string;
  execution_mode: LocalOpsExecutionMode;
  max_tool_steps_per_run: number;
  max_run_seconds: number;
  max_concurrent_runs: number;
  terminal_idle_timeout_minutes: number;
  allow_shell_exec: boolean;
  shell_allowlist: string[];
};

export type LocalOpsProvider = {
  id: number;
  provider_id: "openai" | "ollama";
  name: string;
  base_url: string;
  enabled: boolean;
  default_for_agents: boolean;
  extra: Record<string, unknown>;
};

export type LocalOpsThread = {
  id: string;
  title: string;
  provider_id: "openai" | "ollama";
  provider_endpoint_id?: number | null;
  model: string;
  execution_mode: LocalOpsExecutionMode;
  created_at: string;
  updated_at: string;
};

export type LocalOpsMessage = {
  id: string;
  thread_id: string;
  run_id: string | null;
  role: string;
  content: string;
  meta: Record<string, unknown>;
  created_at: string;
};

export type LocalOpsRun = {
  id: string;
  thread_id: string;
  status: string;
  llm_status?: string;
  provider_id: "openai" | "ollama";
  provider_endpoint_id?: number | null;
  endpoint_label?: string;
  endpoint_url?: string;
  model: string;
  request_type?: string;
  telemetry?: Record<string, unknown>;
  execution_mode: LocalOpsExecutionMode;
  error: string;
  started_at: string;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
};

export type LocalOpsToolCall = {
  id: string;
  run_id: string;
  tool_name: string;
  args: Record<string, unknown>;
  result: Record<string, unknown>;
  status: string;
  created_at: string;
  updated_at: string;
};

export type LocalOpsOpenAiStatus = {
  configured: boolean;
  source: string;
  masked: string;
};

export type LocalOpsTerminalSession = {
  session_id: string;
  cwd: string;
  command: string;
  open: boolean;
  last_activity: number;
  started_at: number;
};

export type LocalOpsAgentPack = {
  slug: string;
  title: string;
  has_instructions: boolean;
  has_skill?: boolean;
  instructions?: string;
  tooling?: string;
  skill_md?: string;
};

export type LocalOpsAgentSession = {
  id: string;
  agent_slug: string;
  name?: string;
  title: string;
  codex_model?: string;
  workspace_root?: string;
  workspace_path: string;
  input_file: string;
  output_file: string;
  state_file?: string;
  memory_file?: string;
  notes_file?: string;
  investigations_file?: string;
  host_profile_file?: string;
  repo_profile_file?: string;
  log_file?: string;
  status: string;
  last_result: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type LocalOpsAgentSessionFile = {
  session_id: string;
  file_key: string;
  path: string;
  content: string;
};

export type FactoryRunStatus = "queued" | "running" | "failed" | "succeeded" | "cancelled" | string;
export type FactoryPriority = "low" | "medium" | "high" | "critical" | string;
export type FactoryValidationToggle = "lint" | "test" | "typecheck";

export type FactoryOverviewSummary = {
  total_runs: number;
  active_runs: number;
  failed_runs: number;
  open_issues: number;
  unread_messages: number;
  success_rate: number;
};

export type FactoryIssueCounts = {
  p0: number;
  p1: number;
  p2: number;
  p3: number;
};

export type FactoryRunRow = {
  id: string;
  app_name: string;
  name?: string;
  run_name?: string;
  workspace_id?: string;
  template_id?: string;
  template_key?: string;
  preset_key?: string;
  mode?: string;
  app_type?: string;
  agents?: string[];
  preview_url?: string;
  status: FactoryRunStatus;
  current_stage: string;
  progress_pct: number;
  task_count: number;
  issue_count: number;
  artifact_count: number;
  message_count: number;
  created_at: string;
  updated_at: string;
};

export type FactoryRun = FactoryRunRow;

export type PromptPreset = {
  id: string;
  key?: string;
  name: string;
  description: string;
  goal: string;
  constraints: string[];
  examples: string[];
  app_type?: string;
  default_agents?: string[];
  example_prompt?: string;
  recommended_fields?: string[];
  tags?: string[];
};

export type RunTemplate = {
  id: string;
  key?: string;
  name: string;
  description: string;
  app_type?: string;
  recommended_mode?: string;
  execution_order?: string[];
  flow_summary?: string;
  default_agents: string[];
  default_constraints: string[];
  default_validation: FactoryValidationToggle[];
};

export type Workspace = {
  id: string;
  key?: string;
  name: string;
  path?: string;
  repo_path?: string;
  description?: string;
  branch?: string;
  app_type?: string;
  is_active?: boolean;
  repo_exists?: boolean;
  last_used_at?: string | null;
  available_templates?: string[];
  default_branch?: string;
  preview_url?: string;
};

export type FactoryWorkspaceCreateRequest = {
  key: string;
  name: string;
  repo_path: string;
  app_type?: string;
  is_active?: boolean;
  default_branch?: string;
  app_template_slug?: string;
  metadata?: Record<string, unknown>;
};

export type FactoryWorkspaceBootstrapRequest = {
  workspace_id?: string;
  workspace_path?: string;
  create_path?: boolean;
  install_dependencies?: boolean;
};

export type FactoryWorkspaceBootstrapResponse = {
  ok: boolean;
  status: "created_path" | "path_exists" | "deps_installed" | "deps_failed" | "no_dependency_manifest" | "install_skipped" | string;
  workspace_path: string;
  host: string;
  log_tail?: string;
};

export type FactoryAgent = {
  id: string;
  key?: string;
  name: string;
  role?: string;
  description?: string;
  enabled?: boolean;
  queue_name?: string;
  model_name?: string;
};

export type FactoryMode = {
  id: string;
  key?: string;
  name: string;
  description?: string;
  app_types?: string[];
};

export type FactoryComposeRunRequest = {
  name?: string;
  run_name?: string;
  workspace_id?: string;
  template_id?: string;
  template_key?: string;
  preset_key?: string;
  prompt_preset_id?: string;
  goal?: string;
  constraints?: string[];
  agents?: string[];
  mode?: string;
  app_type?: string;
  auto_start?: boolean;
  metadata?: Record<string, unknown>;
  source_channel?: string;
  create_initial_tasks?: boolean;
  checks?: {
    lint: boolean;
    test: boolean;
    typecheck: boolean;
  };
};

export type FactoryComposeRunResponse = {
  run_id: string;
  run: FactoryRun;
  resolved?: Record<string, unknown>;
  composed_payload: Record<string, unknown>;
};

export type FactoryPreviewStartRequest = {
  run_id?: string;
  workspace_id?: string;
  workspace_path?: string;
  port?: number;
  ensure_backend?: boolean;
};

export type FactoryPreviewStartResponse = {
  ok: boolean;
  status: "starting" | "started" | "already_running" | string;
  preview_url: string;
  workspace_path: string;
  port: number;
  host: string;
  backend_status?: string;
  backend_url?: string;
  log_tail?: string;
};

export type FactoryPreviewStopRequest = {
  run_id?: string;
  workspace_id?: string;
  workspace_path?: string;
  port?: number;
  stop_backend?: boolean;
};

export type FactoryPreviewStopResponse = {
  ok: boolean;
  status: "stopped" | "not_running" | "still_running" | string;
  workspace_path: string;
  port: number;
  host: string;
  backend_status?: string;
  backend_url?: string;
  log_tail?: string;
};

export type FactoryInboxMessage = {
  id: string;
  run_id?: string;
  sender: string;
  recipient: string;
  subject: string;
  body: string;
  priority: FactoryPriority;
  status?: string;
  created_at?: string;
};

export type FactoryArtifact = {
  id: string;
  run_id?: string;
  kind: string;
  name: string;
  score?: number;
  notes?: string;
  preview_url?: string;
  created_at?: string;
};

export type FactoryIssue = {
  id: string;
  run_id?: string;
  severity: string;
  status: string;
  source_agent: string;
  file_path: string;
  summary: string;
  created_at: string;
  updated_at: string;
};

export type FactoryTask = {
  id: string;
  title: string;
  stage: string;
  status: string;
  assignee?: string;
  started_at?: string;
  completed_at?: string;
};

export type FactoryTimelineEvent = {
  id: string;
  stage: string;
  status: string;
  message?: string;
  created_at: string;
};

export type FactoryMetricsSummary = {
  build_success_rate: number;
  mean_cycle_time_ms: number;
  average_issues_per_run: number;
  runs_last_24h: number;
  tasks_completed_last_24h: number;
};

export type FactoryRunDetail = {
  run: FactoryRunRow;
  preview_url?: string;
  preview_candidates?: string[];
  timeline: FactoryTimelineEvent[];
  tasks: FactoryTask[];
  issues: FactoryIssue[];
  artifacts: FactoryArtifact[];
  messages: FactoryInboxMessage[];
  metrics: FactoryMetricsSummary;
  logs?: string[];
  output?: Record<string, unknown>;
  raw_run?: Record<string, unknown>;
};

export type FactoryOverviewPayload = {
  summary: FactoryOverviewSummary;
  issue_counts: FactoryIssueCounts;
  recent_runs: FactoryRunRow[];
  recent_messages: FactoryInboxMessage[];
  recent_artifacts: FactoryArtifact[];
};

export type FactoryHealthStatus = {
  label: string;
  ok: boolean;
  endpoint: string;
  error?: string;
  checked_at: string;
};

export type SkilledAgentsHealth = {
  ok: boolean;
  service: string;
  time: string;
  db_path?: string;
  agents_count?: number;
  starter_templates_count?: number;
};

export type SkilledSkillSummary = {
  id: string;
  slug: string;
  name: string;
  version: string;
  description: string;
  category: string;
  tags: string[];
  path: string;
  checksum?: string | null;
};

export type SkilledSkillDetail = SkilledSkillSummary & {
  runtime?: Record<string, unknown>;
  dependencies?: Array<Record<string, unknown>>;
  env_vars?: Record<string, string>;
  permissions?: Record<string, unknown>;
  tools?: Array<Record<string, unknown>>;
  hooks?: Record<string, unknown>;
  templates?: Array<Record<string, unknown>>;
  prompt_entry?: string;
  config_schema?: Record<string, unknown>;
  test_commands?: string[];
  compatible_agent_types?: string[];
  readme?: string | null;
};

export type SkilledSkillCreateRequest = {
  id: string;
  name?: string;
  description?: string;
  category?: string;
  tags?: string[];
  version?: string;
  readme?: string;
};

export type SkilledAgentTemplateSummary = {
  id: string;
  name: string;
  description: string;
  category: string;
  strict_by_default: boolean;
};

export type SkilledAgentTemplateDetail = SkilledAgentTemplateSummary & {
  version: string;
  agent_type: string;
  domain_focus: string;
  execution_mode: string;
  runtime: string;
  model_provider?: string | null;
  model_name?: string | null;
  recommended_skills: string[];
  allowed_skills: string[];
  allowed_tools: string[];
  disallowed_capabilities: string[];
  default_prompts: Record<string, string>;
  runtime_policies: Record<string, unknown>;
  execution_expectations: string[];
  ui_hints: Record<string, unknown>;
};

export type SkilledStarterTemplate = {
  slug: string;
  name: string;
  description: string;
  template_version: string;
  pack_version: string;
  source_zip: string;
  source_pack: string;
  uses_webagent: boolean;
  compatibility_badges: Record<string, boolean>;
  recommended_deploy_mode: "safe" | "sandboxed" | "networked" | "yolo" | string;
  imported_at: string;
  readme_snippet?: string;
  is_top_agent?: boolean;
  top_rank?: number | null;
  category?: string;
  source_file?: string | null;
};

export type SkilledTemplatePreview = {
  files_to_create: string[];
  skills_to_attach: string[];
  dependencies_to_install: string[];
  recommended_deploy_mode: string;
  selected_deploy_mode: string;
  final_execution_mode: string;
  entrypoint: string;
  compatibility_badges: Record<string, boolean>;
  external_dependencies: string[];
  uses_webagent: boolean;
  delegates_playwright?: boolean;
  warnings: string[];
};

export type SkilledAgentSnapshot = {
  id: string;
  agent_id: string;
  reason: string;
  snapshot: Record<string, unknown>;
  created_at: string;
};

export type SkilledAgent = {
  id: string;
  name: string;
  slug: string;
  description: string;
  agent_type: string;
  runtime: string;
  model_provider?: string | null;
  model_name?: string | null;
  model_settings: Record<string, unknown>;
  workspace_path: string;
  selected_skills: string[];
  env_config: Record<string, string>;
  flags: Record<string, unknown>;
  network_access: boolean;
  sandbox_mode: string;
  yolo_mode: boolean;
  template_id?: string | null;
  specialization_mode: "strict" | "custom" | string;
  role_identity?: string | null;
  domain_focus?: string | null;
  execution_mode?: string | null;
  allowed_tools: string[];
  runtime_policies: Record<string, unknown>;
  saved_prompts: Record<string, string>;
  specialization_metadata: Record<string, unknown>;
  status: string;
  last_run_at?: string | null;
  last_error?: string | null;
  created_at: string;
  updated_at: string;
};

export type SkilledAgentCreateRequest = {
  name: string;
  slug: string;
  description: string;
  agent_type: string;
  runtime: string;
  model_provider?: string | null;
  model_name?: string | null;
  model_settings?: Record<string, unknown>;
  workspace_path?: string | null;
  selected_skills?: string[];
  env_config?: Record<string, string>;
  flags?: Record<string, unknown>;
  network_access?: boolean;
  sandbox_mode?: string;
  yolo_mode?: boolean;
  template_id?: string | null;
  specialization_mode?: "strict" | "custom" | string;
  role_identity?: string | null;
  domain_focus?: string | null;
  execution_mode?: string | null;
  allowed_tools?: string[];
  runtime_policies?: Record<string, unknown>;
  saved_prompts?: Record<string, string>;
  specialization_metadata?: Record<string, unknown>;
};

export type SkilledAgentUpdateRequest = Partial<Omit<SkilledAgentCreateRequest, "workspace_path" | "selected_skills">>;

export type SkilledAgentActionResponse = {
  agent_id: string;
  action: string;
  status: string;
  message: string;
  run_id?: string | null;
};

export type SkilledAgentStatus = {
  agent_id: string;
  status: string;
  pid?: number | null;
  active_run_id?: string | null;
  last_run_at?: string | null;
  last_error?: string | null;
  updated_at: string;
};

export type SkilledAgentRunRequest = {
  command?: string | null;
  args?: string[];
};

export type SkilledAgentLogEntry = {
  id: string;
  agent_id: string;
  run_id?: string | null;
  level: string;
  message: string;
  created_at: string;
};

export type SkilledAgentLogsResponse = {
  agent_id: string;
  count: number;
  logs: SkilledAgentLogEntry[];
};

export type SkilledAgentWorkspaceResponse = {
  agent_id: string;
  workspace_path: string;
  exists: boolean;
  files: string[];
};

export type SkilledAgentManifestResponse = {
  agent_id: string;
  manifest: Record<string, unknown>;
};

export type SkilledAgentSnapshotsResponse = {
  agent_id: string;
  count: number;
  snapshots: SkilledAgentSnapshot[];
};

export type SkilledAgentLatestSnapshotResponse = {
  agent_id: string;
  snapshot: SkilledAgentSnapshot | null;
};

export type MemoryHealth = {
  ok: boolean;
  shared_root: string;
  shared_available: boolean;
  replay_queue_length: number;
  fallback_root: string;
  lock_timeout_seconds: number;
};

export type MemorySettings = {
  shared_root: string;
  fallback_root: string;
  brief_max_chars: number;
  rerank_default: boolean;
  lock_timeout_seconds: number;
  using_env_root: boolean;
};

export type MemorySearchResult = {
  stage: string;
  score: number;
  item: Record<string, unknown>;
};

export type MemorySearchResponse = {
  items: MemorySearchResult[];
  stages: string[];
  rerank_applied: boolean;
};

export type MemoryBriefResponse = {
  brief: string;
  chars: number;
};

export type MemoryCompactResponse = {
  states: string[];
  candidate?: Record<string, unknown> | null;
  compacted_count: number;
  replayed_count: number;
};

export type ChatMessageRole = "user" | "assistant" | "system" | "tool";
export type ChatMessageSource = "web" | "discord" | "system" | "agent" | "tool";

export type ChatMessage = {
  id: string;
  session_id: string;
  role: ChatMessageRole;
  source: ChatMessageSource;
  content: string;
  created_at: string;
  model: string;
  provider: string;
  status: string;
  metadata?: Record<string, unknown>;
  tool_payload?: Record<string, unknown> | null;
  audit_id?: string | null;
};

export type ChatSession = {
  id: string;
  title: string;
  status: string;
  model: string;
  provider: string;
  source_types: ChatMessageSource[];
  discord_link: {
    guild_id?: string;
    channel_id?: string;
    user_id?: string;
  };
  message_count: number;
  created_at: string;
  updated_at: string;
  last_message_at?: string | null;
  metadata?: Record<string, unknown>;
};

export type ChatSessionListResponse = { items: ChatSession[] };
export type ChatMessageListResponse = { items: ChatMessage[] };
