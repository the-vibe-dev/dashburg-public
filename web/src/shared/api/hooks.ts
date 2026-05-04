import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, apiDelete, apiGet, apiPatch, apiPost, apiPut, eventsUrl } from "./client";
import {
  bootstrapFactoryWorkspace,
  composeFactoryRun,
  createFactoryWorkspace,
  getFactoryApiBase,
  getFactoryArtifacts,
  getFactoryAgents,
  getFactoryHealthChecks,
  getFactoryInbox,
  getFactoryIssues,
  getFactoryMetricsSummary,
  getFactoryModes,
  getFactoryOverview,
  getFactoryPromptPresets,
  getFactoryRunDetail,
  getFactoryRuns,
  getFactoryTemplates,
  getFactoryWorkspaces,
  stopFactoryPreview,
  startFactoryPreview,
  startFactoryRun,
} from "./factory";
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
  PromptPreset,
  RunTemplate,
  Workspace,
  LocalOpsAgentPack,
  LocalOpsAgentSession,
  LocalOpsAgentSessionFile,
  LocalOpsMessage,
  LocalOpsOpenAiStatus,
  LocalOpsProvider,
  LocalOpsRun,
  LocalOpsSettings,
  LocalOpsThread,
  LocalOpsTerminalSession,
  LocalOpsToolCall,
  IdeaVaultCreateRequest,
  IdeaVaultItem,
  IdeaVaultPatchRequest,
  OpportunityLineageTrace,
  PromotedIdea,
  PromotedIdeaCreateRequest,
  TopicOpportunity,
  RemoteJob,
  RemoteOpsNode,
  RemoteOpsSettings,
  RemoteNodeHealth,
  RemoteNodeHostMonitor,
  OrchestrationJob,
  OrchestrationMailboxItem,
  OrchestrationNodeSummary,
  OrchestrationOverview,
  OrchestrationSettings,
  OrchestrationTerminalLaunch,
  ScheduleOpsClusterStatus,
  ScheduleOpsConfig,
  ScheduleOpsNodeStatus,
  ScheduleOpsNode,
  ScheduleOpsNodePayload,
  RedisBrokerOverview,
  RedisBrokerProviderConfig,
  MailCenterMessage,
  MailCenterMessageDetail,
  MailCenterOverview,
  MailCenterRecipients,
  MailCenterThread,
  RemoteServer,
  RemoteServerDetail,
  RemoteTerminalSession,
  WebAgentOverview,
  WebAgentArtifactList,
  WebAgentDiscovery,
  WebAgentGeneratedTests,
  WebAgentLiveSession,
  WebAgentLogs,
  WebAgentReplayAssets,
  WebAgentReport,
  WebAgentRun,
  WebAgentRunSettings,
  WebAgentSessionAction,
  WebAgentSessionResult,
  WebAgentStatus,
  WebAgentToolResult,
  TrendsExportRequest,
  TrendsRun,
  TrendsRunLogs,
  TrendsRunResults,
  TrendsRunStartRequest,
  TrendsOpenAiKeyStatus,
  TrendsTopicActionRequest,
  TrendsTopicDetail,
  TrendsTopicFactoryImportResponse,
  AiVideoFactoryUploadOption,
  ViralVideoAutomationSettings,
  ViralVideoChannelProfile,
  ViralVideoInsightDay,
  ViralVideoInsightPost,
  ViralVideoInsightsSummary,
  ViralVideoOverview,
  ViralVideoRun,
  ViralVideoScript,
  ViralCreatorChannelOverview,
  ViralCreatorCreativeDraft,
  ViralCreatorAutonomousHistoryItem,
  ViralCreatorAutonomousProfile,
  ViralCreatorAutonomousState,
  ViralCreatorInboxItem,
  ViralCreatorOrchestrationRun,
  ViralCreatorResearchResult,
  ViralCreatorState,
  TopicFactoryQueueCreateRequest,
  TopicFactoryQueueItem,
  TopicAppgenAnalyzeRunRequest,
  TopicAppgenAnalyzeRunResponse,
  TopicAppgenGenerateRequest,
  TopicAppgenGenerateResponse,
  TopicAppgenIdea,
  TopicAppgenRun,
  TopicIdeaDetail,
  TopicLogsTailResponse,
  TopicMicroProblem,
  TopicPainGraphEdge,
  TopicRun,
  TopicRunAutoRequest,
  TopicRunDetail,
  TopicSearchStrategy,
  TopicSearchStrategyUpdateRequest,
  TopicRunStartRequest,
  TopicSignal,
  TopicRunTargetedRequest,
  TopicTrendingItem,
  WeeklyReview,
  SkilledAgent,
  SkilledAgentActionResponse,
  SkilledAgentCreateRequest,
  SkilledAgentLogsResponse,
  SkilledAgentManifestResponse,
  SkilledAgentRunRequest,
  SkilledAgentSnapshotsResponse,
  SkilledAgentStatus,
  SkilledAgentUpdateRequest,
  SkilledAgentWorkspaceResponse,
  SkilledAgentsHealth,
  SkilledAgentLatestSnapshotResponse,
  SkilledAgentTemplateDetail,
  SkilledAgentTemplateSummary,
  SkilledStarterTemplate,
  SkilledTemplatePreview,
  SkilledSkillDetail,
  SkilledSkillCreateRequest,
  SkilledSkillSummary,
  MemoryHealth,
  MemorySettings,
  MemorySearchResponse,
  MemoryBriefResponse,
  MemoryCompactResponse,
  DiscordDispatchTarget,
  DiscordDispatchRequest,
  DiscordApprovalRequest,
  DispatchWorkerStatus,
  DiscordSettings,
  DiscordStatusPayload,
  ChatMessage,
  ChatMessageListResponse,
  ChatSession,
  ChatSessionListResponse,
} from "./types";

function asArray<T>(value: unknown): T[] {
  if (Array.isArray(value)) return value as T[];
  if (value && typeof value === "object") {
    const obj = value as Record<string, unknown>;
    const candidates = [obj.items, obj.jobs, obj.events, obj.data, obj.results, obj.trending, obj.runs, obj.ideas, obj.video_ideas, obj.queue, obj.queue_items];
    let firstArray: T[] | null = null;
    for (const candidate of candidates) {
      if (!Array.isArray(candidate)) continue;
      const rows = candidate as T[];
      if (!firstArray) firstArray = rows;
      if (rows.length > 0) return rows;
    }
    if (firstArray) return firstArray;
  }
  return [];
}

function isNotFoundError(error: unknown): boolean {
  if (error instanceof ApiError) return error.status === 404;
  const maybe = error as { status?: unknown; message?: unknown };
  if (maybe && typeof maybe.status === "number") return maybe.status === 404;
  return typeof maybe?.message === "string" && maybe.message.includes("404");
}

function shouldTryTopicFactoryFallback(error: unknown): boolean {
  if (!isNotFoundError(error)) return false;
  const message = String((error as { message?: unknown })?.message ?? "");
  // Parse default route-missing message from ApiError: "<METHOD> <PATH> failed: 404"
  return message.includes("failed: 404");
}

function videoIdeasRetry(failureCount: number, error: unknown): boolean {
  return !isNotFoundError(error) && failureCount < 2;
}

function looksLikeUuid(value: string | null | undefined): boolean {
  if (!value) return false;
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(String(value).trim());
}

const topicFactoryQueueBases = ["/api/topic/queue", "/api/topicfactory/queue"] as const;
let topicFactoryQueueUnavailable = false;
let topicLogsTailUnavailable = false;

async function getTopicFactoryQueue(): Promise<TopicFactoryQueueItem[]> {
  if (topicFactoryQueueUnavailable) return [];
  for (const base of topicFactoryQueueBases) {
    try {
      const rows = asArray<TopicFactoryQueueItem>(await apiGet<unknown>(base));
      topicFactoryQueueUnavailable = false;
      return rows;
    } catch (error) {
      if (shouldTryTopicFactoryFallback(error)) continue;
      if (isNotFoundError(error)) return [];
      throw error;
    }
  }
  topicFactoryQueueUnavailable = true;
  return [];
}

async function postTopicFactoryQueue(payload: TopicFactoryQueueCreateRequest): Promise<TopicFactoryQueueItem> {
  topicFactoryQueueUnavailable = false;
  for (const base of topicFactoryQueueBases) {
    try {
      return await apiPost<TopicFactoryQueueItem>(base, payload);
    } catch (error) {
      if (shouldTryTopicFactoryFallback(error)) continue;
      throw error;
    }
  }
  throw new ApiError("TopicFactory queue endpoint not available on backend", 404, "POST", topicFactoryQueueBases[0]);
}

async function postTopicFactoryQueueAction(queueId: string, action: "start" | "cancel"): Promise<TopicFactoryQueueItem> {
  topicFactoryQueueUnavailable = false;
  for (const base of topicFactoryQueueBases) {
    try {
      return await apiPost<TopicFactoryQueueItem>(`${base}/${queueId}/${action}`);
    } catch (error) {
      if (shouldTryTopicFactoryFallback(error)) continue;
      throw error;
    }
  }
  throw new ApiError("TopicFactory queue endpoint not available on backend", 404, "POST", `${topicFactoryQueueBases[0]}/${queueId}/${action}`);
}

async function deleteTopicFactoryQueueItem(queueId: string): Promise<{ ok: boolean; id: string; deleted: boolean }> {
  topicFactoryQueueUnavailable = false;
  for (const base of topicFactoryQueueBases) {
    try {
      return await apiDelete<{ ok: boolean; id: string; deleted: boolean }>(`${base}/${queueId}`);
    } catch (error) {
      if (shouldTryTopicFactoryFallback(error)) continue;
      if (isNotFoundError(error) && String((error as { message?: unknown })?.message ?? "").toLowerCase().includes("queue item not found")) {
        return { ok: true, id: queueId, deleted: false };
      }
      throw error;
    }
  }
  throw new ApiError("TopicFactory queue endpoint not available on backend", 404, "DELETE", `${topicFactoryQueueBases[0]}/${queueId}`);
}

function isRunReadyStatus(status: unknown): boolean {
  const value = String(status ?? "").toLowerCase();
  return value !== "queued" && value !== "running";
}

function normalizeTopicRunRow(row: Record<string, unknown>): TopicRun {
  const nestedRun = row.run && typeof row.run === "object" ? (row.run as Record<string, unknown>) : null;
  const base = nestedRun ? { ...nestedRun, ...row } : row;
  const runId = String(base.run_id ?? base.id ?? "");
  const progressObj =
    base.progress && typeof base.progress === "object" ? (base.progress as Record<string, unknown>) : null;
  const stage =
    String(base.stage ?? base.current_stage ?? progressObj?.stage ?? "").trim() || undefined;
  const progressRaw = Number(base.progress_pct ?? base.progress_percent ?? progressObj?.percent ?? Number.NaN);
  const progress = Number.isFinite(progressRaw) ? Math.max(0, Math.min(100, progressRaw)) : undefined;
  const heartbeatAt = String(base.heartbeat_at ?? base.updated_at ?? "").trim() || undefined;
  return {
    ...base,
    id: runId,
    run_id: runId,
    status: String(base.status ?? "unknown"),
    ...(stage ? { stage } : {}),
    ...(progress !== undefined ? { progress_pct: progress } : {}),
    ...(heartbeatAt ? { heartbeat_at: heartbeatAt } : {}),
    updated_at: String(base.updated_at ?? base.finished_at ?? base.started_at ?? base.created_at ?? ""),
    created_at: String(base.created_at ?? ""),
  } as TopicRun;
}

function normalizeTopicRunsFromEvents(events: Array<Record<string, unknown>>): TopicRun[] {
  const byRun = new Map<string, TopicRun>();
  for (const event of events) {
    const runId = String(event.run_id ?? event.id ?? "").trim();
    if (!runId) continue;
    const stage = String(event.stage_name ?? "").trim().toLowerCase();
    const eventStatus = String(event.status ?? "").trim().toLowerCase();
    const createdAt = String(event.created_at ?? "");
    const existing = byRun.get(runId);
    const nextStatus =
      eventStatus === "running"
        ? "running"
        : eventStatus === "error"
          ? "failed"
          : stage === "harvest" && eventStatus === "ok"
            ? "running"
            : ((existing?.status ?? eventStatus) || "unknown");
    const nextStage = stage || String(existing?.stage ?? "");
    const next: TopicRun = {
      ...(existing ?? {}),
      id: runId,
      run_id: runId,
      status: nextStatus,
      stage: nextStage || undefined,
      updated_at: createdAt || existing?.updated_at || existing?.created_at || "",
      created_at: existing?.created_at || createdAt || "",
      started_at: existing?.started_at ?? (stage === "run_start" ? createdAt : null),
      error_message: event.error_message ?? existing?.error_message,
      output_count: event.output_count ?? existing?.output_count,
    };
    byRun.set(runId, next);
  }
  return Array.from(byRun.values()).sort((a, b) => {
    const at = Date.parse(String(a.updated_at ?? a.created_at ?? "")) || 0;
    const bt = Date.parse(String(b.updated_at ?? b.created_at ?? "")) || 0;
    return bt - at;
  });
}

function topicRunEventToLine(event: Record<string, unknown>): string {
  const createdAt = String(event.created_at ?? "").trim();
  const stage = String(event.stage_name ?? event.stage ?? "").trim();
  const status = String(event.status ?? "").trim();
  const outputCount = Number(event.output_count ?? Number.NaN);
  const inputCount = Number(event.input_count ?? Number.NaN);
  const errorMessage = String(event.error_message ?? "").trim();
  const pieces = [
    createdAt ? `[${createdAt}]` : "",
    stage || "event",
    status || "",
    Number.isFinite(inputCount) ? `in=${inputCount}` : "",
    Number.isFinite(outputCount) ? `out=${outputCount}` : "",
    errorMessage ? `error=${errorMessage}` : "",
  ].filter(Boolean);
  return pieces.join(" ");
}

function normalizeTopicRunDetailPayload(data: unknown): TopicRunDetail {
  const obj = data && typeof data === "object" ? ({ ...(data as Record<string, unknown>) } as Record<string, unknown>) : {};
  const progressObj =
    (obj.progress && typeof obj.progress === "object" ? (obj.progress as Record<string, unknown>) : null) ??
    (obj.job && typeof obj.job === "object" && (obj.job as Record<string, unknown>).progress && typeof (obj.job as Record<string, unknown>).progress === "object"
      ? ((obj.job as Record<string, unknown>).progress as Record<string, unknown>)
      : null);
  const stage =
    String(obj.stage ?? obj.current_stage ?? progressObj?.stage ?? "").trim() ||
    String((obj.summary as Record<string, unknown> | undefined)?.stage ?? "").trim() ||
    undefined;
  const progressRaw = Number(
    obj.progress_pct ??
      obj.progress_percent ??
      progressObj?.percent ??
      (obj.summary as Record<string, unknown> | undefined)?.progress_pct ??
      Number.NaN,
  );
  const counts =
    (obj.counts && typeof obj.counts === "object" ? (obj.counts as Record<string, unknown>) : null) ??
    (obj.job && typeof obj.job === "object" && (obj.job as Record<string, unknown>).counts && typeof (obj.job as Record<string, unknown>).counts === "object"
      ? ((obj.job as Record<string, unknown>).counts as Record<string, unknown>)
      : null) ??
    {};
  const heartbeatAt =
    String(obj.heartbeat_at ?? obj.updated_at ?? (obj.job as Record<string, unknown> | undefined)?.updated_at ?? "").trim() || undefined;
  return {
    ...(obj as TopicRunDetail),
    ...(stage ? { stage } : {}),
    ...(Number.isFinite(progressRaw) ? { progress_pct: Math.max(0, Math.min(100, progressRaw)) } : {}),
    heartbeat_at: heartbeatAt ?? null,
    counts,
  } as TopicRunDetail;
}

export function useDashburgSSE() {
  const client = useQueryClient();

  useEffect(() => {
    const source = new EventSource(eventsUrl("/api/events/stream"));
    const handler = (event: Event) => {
      const evt = event.type || "message";
      // Scope invalidation to run/dashboard surfaces touched by collector SSE events.
      if (evt === "run.new" || evt === "run.status" || evt === "run.event") {
        client.invalidateQueries({ queryKey: ["runs"] });
        client.invalidateQueries({ queryKey: ["metrics-summary"] });
        client.invalidateQueries({ queryKey: ["dashboard-monitor-live"] });
      }
    };

    source.addEventListener("run.new", handler);
    source.addEventListener("run.status", handler);
    source.addEventListener("run.event", handler);

    return () => {
      source.close();
    };
  }, [client]);
}

export function useTopicTrending(limit = 20, enabled = true) {
  return useQuery({
    queryKey: ["topic", "trending", limit],
    queryFn: async () => {
      const data = await apiGet<unknown>(`/api/topic/trending?limit=${limit}`);
      return asArray<TopicTrendingItem>(data);
    },
    enabled,
    refetchInterval: enabled ? 30_000 : false,
  });
}

export function useTopicHealth(enabled = true) {
  return useQuery({
    queryKey: ["topic", "health"],
    queryFn: () => apiGet<Record<string, unknown>>("/api/topic/health"),
    enabled,
    refetchInterval: enabled ? 15_000 : false,
  });
}

export function useTopicProviderStats(limit = 200, enabled = true) {
  return useQuery({
    queryKey: ["topic", "provider-stats", limit],
    queryFn: () => apiGet<Record<string, unknown>>(`/api/topic/providers/stats?limit=${limit}`),
    enabled,
    refetchInterval: enabled ? 10_000 : false,
  });
}

export function useTopicRuns(limit = 200, enabled = true) {
  return useQuery({
    queryKey: ["topic", "runs", limit],
    queryFn: async () => {
      const data = await apiGet<unknown>(`/api/topic/runs?limit=${limit}`);
      if (data && typeof data === "object") {
        const obj = data as Record<string, unknown>;
        const rows = Array.isArray(obj.jobs)
          ? (obj.jobs as Array<Record<string, unknown>>)
          : Array.isArray(obj.runs)
            ? (obj.runs as Array<Record<string, unknown>>)
            : Array.isArray(obj.items)
              ? (obj.items as Array<Record<string, unknown>>)
              : null;
        if (rows) {
          const normalized = rows
            .map((job) => normalizeTopicRunRow(job))
            .filter((run) => run.id || run.run_id) as TopicRun[];
          if (normalized.length > 0) return normalized;
        }
        if (Array.isArray(obj.events)) {
          return normalizeTopicRunsFromEvents(obj.events as Array<Record<string, unknown>>)
            .slice(0, limit) as TopicRun[];
        }
      }
      return asArray<Record<string, unknown>>(data)
        .map((job) => normalizeTopicRunRow(job))
        .filter((run) => run.id || run.run_id) as TopicRun[];
    },
    enabled,
    refetchInterval: (query) => {
      if (!enabled) return false;
      const rows = Array.isArray(query.state.data) ? (query.state.data as TopicRun[]) : [];
      const hasActive = rows.some((run) => {
        const status = String(run.status ?? "").toLowerCase();
        return status === "queued" || status === "running" || status === "cancel_requested";
      });
      return hasActive ? 5_000 : 15_000;
    },
    staleTime: 0,
    refetchOnWindowFocus: true,
  });
}

export function useTopicRunDetail(runId: string | null, enabled = true) {
  return useQuery({
    queryKey: ["topic", "run-detail", runId],
    queryFn: async () => {
      const data = await apiGet<unknown>(`/api/topic/runs/${runId}`);
      return normalizeTopicRunDetailPayload(data);
    },
    enabled: Boolean(runId) && enabled,
    refetchInterval: enabled ? 3_000 : false,
  });
}

export function useTopicIdeas(clusterId: string | null, limit = 100, enabled = true) {
  return useQuery({
    queryKey: ["topic", "ideas", clusterId, limit],
    queryFn: () => {
      const query = clusterId
        ? `/api/topic/ideas?cluster_id=${encodeURIComponent(clusterId)}&limit=${limit}`
        : `/api/topic/ideas?limit=${limit}`;
      return apiGet<Array<Record<string, unknown>>>(query).then((data) => asArray<Record<string, unknown>>(data));
    },
    enabled,
  });
}

export function useTopicIdeaDetail(ideaId: string | null) {
  return useQuery({
    queryKey: ["topic", "idea-detail", ideaId],
    queryFn: () => apiGet<TopicIdeaDetail>(`/api/topic/ideas/${ideaId}`),
    enabled: Boolean(ideaId),
  });
}

export function useTopicSignals(runId: string | null, limit = 200, enabled = true) {
  return useQuery({
    queryKey: ["topic", "signals", runId, limit],
    queryFn: async () => {
      const query = new URLSearchParams();
      if (runId) query.set("run_id", runId);
      query.set("limit", String(limit));
      const data = await apiGet<unknown>(`/api/topic/signals?${query.toString()}`);
      return asArray<TopicSignal>(data);
    },
    enabled: Boolean(runId) && enabled,
    refetchInterval: enabled ? 30_000 : false,
  });
}

export function useTopicMicroProblems(runId: string | null, limit = 200, enabled = true) {
  return useQuery({
    queryKey: ["topic", "micro-problems", runId, limit],
    queryFn: async () => {
      const query = new URLSearchParams();
      if (runId) query.set("run_id", runId);
      query.set("limit", String(limit));
      const data = await apiGet<unknown>(`/api/topic/micro_problems?${query.toString()}`);
      return asArray<TopicMicroProblem>(data);
    },
    enabled: Boolean(runId) && enabled,
    refetchInterval: enabled ? 30_000 : false,
  });
}

export function useTopicInsightsClusters(runId: string | null, limit = 200, enabled = true) {
  return useQuery({
    queryKey: ["topic", "insights-clusters", runId, limit],
    queryFn: async () => {
      const query = new URLSearchParams();
      if (runId) query.set("run_id", runId);
      query.set("limit", String(limit));
      const data = await apiGet<unknown>(`/api/topic/clusters?${query.toString()}`);
      return asArray<Record<string, unknown>>(data);
    },
    enabled: Boolean(runId) && enabled,
    refetchInterval: enabled ? 30_000 : false,
  });
}

export function useTopicWorkarounds(runId: string | null, limit = 200, enabled = true) {
  return useQuery({
    queryKey: ["topic", "workarounds", runId, limit],
    queryFn: async () => {
      const query = new URLSearchParams();
      if (runId) query.set("run_id", runId);
      query.set("limit", String(limit));
      const data = await apiGet<unknown>(`/api/topic/workarounds?${query.toString()}`);
      return asArray<TopicMicroProblem>(data);
    },
    enabled: Boolean(runId) && enabled,
    refetchInterval: enabled ? 30_000 : false,
  });
}

export function useTopicPainGraph(runId: string | null, limit = 500) {
  return useQuery({
    queryKey: ["topic", "pain-graph", runId, limit],
    queryFn: async () => {
      const query = new URLSearchParams();
      if (runId) query.set("run_id", runId);
      query.set("limit", String(limit));
      const data = await apiGet<unknown>(`/api/topic/pain_graph?${query.toString()}`);
      return asArray<TopicPainGraphEdge>(data);
    },
    refetchInterval: 30_000,
  });
}

export function useTopicIdeasTop(runId: string | null, limit = 20) {
  return useQuery({
    queryKey: ["topic", "ideas-top", runId, limit],
    queryFn: async () => {
      const query = new URLSearchParams();
      if (runId) query.set("run_id", runId);
      query.set("limit", String(limit));
      const data = await apiGet<unknown>(`/api/topic/ideas/top?${query.toString()}`);
      return asArray<Record<string, unknown>>(data);
    },
    refetchInterval: 30_000,
  });
}

export function useTopicOpportunities(runId: string | null, limit = 80, enabled = true) {
  return useQuery({
    queryKey: ["topic", "opportunities", runId, limit],
    queryFn: async () => {
      const query = new URLSearchParams();
      if (runId) query.set("run_id", runId);
      query.set("limit", String(limit));
      const data = await apiGet<unknown>(`/api/topic/opportunities?${query.toString()}`);
      if (data && typeof data === "object") {
        const rows = asArray<TopicOpportunity>((data as Record<string, unknown>).items ?? data);
        return rows;
      }
      return [] as TopicOpportunity[];
    },
    enabled,
    refetchInterval: enabled ? 20_000 : false,
  });
}

export function useTopicVideoIdeas(runId: string | null, limit = 50, runStatus: string | null = null) {
  const ready = isRunReadyStatus(runStatus);
  const supportsVideoIdeas = Boolean(runId) && !String(runId).startsWith("appgen-analysis:") && !looksLikeUuid(runId);
  return useQuery({
    queryKey: ["topic", "video-ideas", runId, limit, runStatus],
    queryFn: async () => {
      const query = new URLSearchParams();
      if (runId) query.set("run_id", runId);
      query.set("limit", String(limit));
      const data = await apiGet<unknown>(`/api/topic/video_ideas?${query.toString()}`);
      return asArray<Record<string, unknown>>(data);
    },
    enabled: supportsVideoIdeas && ready,
    refetchInterval: 30_000,
    retry: videoIdeasRetry,
    refetchOnWindowFocus: false,
  });
}

export function useTopicVideoIdeasTop(runId: string | null, limit = 20, runStatus: string | null = null) {
  const ready = isRunReadyStatus(runStatus);
  const supportsVideoIdeas = Boolean(runId) && !String(runId).startsWith("appgen-analysis:") && !looksLikeUuid(runId);
  return useQuery({
    queryKey: ["topic", "video-ideas-top", runId, limit, runStatus],
    queryFn: async () => {
      const query = new URLSearchParams();
      if (runId) query.set("run_id", runId);
      query.set("limit", String(limit));
      const data = await apiGet<unknown>(`/api/topic/video_ideas/top?${query.toString()}`);
      return asArray<Record<string, unknown>>(data);
    },
    enabled: supportsVideoIdeas && ready,
    refetchInterval: 30_000,
    retry: videoIdeasRetry,
    refetchOnWindowFocus: false,
  });
}

export function useTopicVideoIdeaDetail(videoIdeaId: string | null) {
  return useQuery({
    queryKey: ["topic", "video-idea-detail", videoIdeaId],
    queryFn: () => apiGet<Record<string, unknown>>(`/api/topic/video_ideas/${videoIdeaId}`),
    enabled: Boolean(videoIdeaId),
    retry: videoIdeasRetry,
    refetchOnWindowFocus: false,
  });
}

export function useTopicRunsLatest() {
  return useQuery({
    queryKey: ["topic", "runs-latest"],
    queryFn: () => apiGet<Record<string, unknown>>("/api/topic/runs/latest"),
    refetchInterval: 15_000,
  });
}

export function useTopicSearchStrategy(enabled = true) {
  return useQuery({
    queryKey: ["topic", "search-strategy"],
    queryFn: () => apiGet<TopicSearchStrategy>("/api/topic/search_strategy"),
    enabled,
    refetchInterval: enabled ? 30_000 : false,
  });
}

export function useUpdateTopicSearchStrategy() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: TopicSearchStrategyUpdateRequest) => apiPut<TopicSearchStrategy>("/api/topic/search_strategy", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["topic", "search-strategy"] });
    },
  });
}

export function useTopicLogsTail(offset: number, maxLines = 200, enabled = true) {
  return useQuery({
    queryKey: ["topic", "logs-tail", maxLines],
    queryFn: async () => {
      if (topicLogsTailUnavailable) {
        return { lines: [], offset, next_offset: offset, has_more: false };
      }
      try {
        const data = await apiGet<TopicLogsTailResponse>(`/api/topic/logs/tail?offset=${offset}&max_lines=${maxLines}`);
        topicLogsTailUnavailable = false;
        return data;
      } catch (error) {
        if (isNotFoundError(error)) {
          topicLogsTailUnavailable = true;
          return { lines: [], offset, next_offset: offset, has_more: false };
        }
        throw error;
      }
    },
    enabled,
    refetchInterval: enabled && !topicLogsTailUnavailable ? 2_500 : false,
    retry: (count, error) => !isNotFoundError(error) && count < 2,
    refetchOnWindowFocus: false,
  });
}

export function useTopicRunLogs(runId: string | null, offset: number, maxLines = 200, enabled = true) {
  return useQuery({
    queryKey: ["topic", "run-logs", runId, offset, maxLines],
    queryFn: async (): Promise<TopicLogsTailResponse> => {
      if (!runId) return { lines: [], offset, next_offset: offset, has_more: false };
      try {
        const data = await apiGet<unknown>(`/api/topic/runs/${runId}/logs?offset=${offset}&max_lines=${maxLines}`);
        const obj = (data && typeof data === "object" ? (data as Record<string, unknown>) : {}) as Record<string, unknown>;
        const lines = Array.isArray(obj.lines)
          ? obj.lines.map((line) => String(line))
          : Array.isArray(obj.items)
            ? obj.items.map((line) =>
                line && typeof line === "object"
                  ? topicRunEventToLine(line as Record<string, unknown>)
                  : String(line),
              )
          : Array.isArray(obj.events)
            ? obj.events.map((line) =>
                line && typeof line === "object"
                  ? topicRunEventToLine(line as Record<string, unknown>)
                  : String(line),
              )
            : [];
        const nextOffset = Number(obj.next_offset ?? obj.offset ?? offset);
        return {
          lines,
          offset: Number(obj.offset ?? offset),
          next_offset: Number.isFinite(nextOffset) ? nextOffset : offset,
          has_more: Boolean(obj.has_more ?? false),
        };
      } catch (error) {
        if (isNotFoundError(error)) {
          return { lines: [], offset, next_offset: offset, has_more: false };
        }
        throw error;
      }
    },
    enabled: Boolean(runId) && enabled,
    refetchInterval: enabled ? 2_500 : false,
    retry: (count, error) => !isNotFoundError(error) && count < 2,
    refetchOnWindowFocus: false,
  });
}

export function useStartTargetedRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: TopicRunTargetedRequest) => apiPost<Record<string, unknown>>("/api/topic/runs/targeted", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["topic", "runs"] });
      client.invalidateQueries({ queryKey: ["topic", "trending"] });
    },
  });
}

export function useStartTopicRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (payload: TopicRunStartRequest) => {
      try {
        return await apiPost<Record<string, unknown>>("/api/topic/runs/start", payload);
      } catch (err) {
        const msg = String((err as Error)?.message ?? "");
        if (!msg.includes("404") && !msg.includes("405")) throw err;
        // Backward compatible fallback for older topic services.
        return await apiPost<Record<string, unknown>>("/api/topic/runs/targeted", {
          query: payload.query,
          topic: payload.topic,
          limit: payload.limit,
          enable_youtube: false,
        });
      }
    },
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["topic", "runs"] });
      client.invalidateQueries({ queryKey: ["topic", "runs-latest"] });
      client.invalidateQueries({ queryKey: ["topic", "trending"] });
    },
  });
}

export function useStartAutoRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (payload: TopicRunAutoRequest) => apiPost<Record<string, unknown>>("/api/topic/runs/auto", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["topic", "runs"] });
      client.invalidateQueries({ queryKey: ["topic", "trending"] });
    },
  });
}

export function useCancelTopicRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => apiPost<Record<string, unknown>>(`/api/topic/runs/${runId}/cancel`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["topic", "runs"] });
      client.invalidateQueries({ queryKey: ["topic", "run-detail"] });
      client.invalidateQueries({ queryKey: ["topic", "runs-latest"] });
    },
  });
}

export function useDeleteTopicRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => apiDelete<Record<string, unknown>>(`/api/topic/runs/${runId}`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["topic", "runs"] });
      client.invalidateQueries({ queryKey: ["topic", "run-detail"] });
      client.invalidateQueries({ queryKey: ["topic", "runs-latest"] });
    },
  });
}

export function usePromotedIdeas() {
  return useQuery({
    queryKey: ["appgen", "promoted"],
    queryFn: () => apiGet<PromotedIdea[]>("/api/appgen/promoted"),
  });
}

export function usePromoteIdea() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: PromotedIdeaCreateRequest) => apiPost<PromotedIdea>("/api/appgen/promoted", payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ["appgen", "promoted"] }),
  });
}

export function useDeletePromotedIdea() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => apiDelete<{ ok: boolean }>(`/api/appgen/promoted/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["appgen", "promoted"] }),
  });
}

export function useWeeklyReviews(enabled = true) {
  return useQuery({
    queryKey: ["appgen", "weekly-reviews"],
    queryFn: () => apiGet<WeeklyReview[]>("/api/appgen/weekly_reviews"),
    enabled,
    refetchInterval: enabled ? 60_000 : false,
  });
}

export function useWeeklyReview(reviewId: string | null, enabled = true) {
  return useQuery({
    queryKey: ["appgen", "weekly-review", reviewId],
    queryFn: () => apiGet<WeeklyReview>(`/api/appgen/weekly_reviews/${reviewId}`),
    enabled: Boolean(reviewId) && enabled,
  });
}

export function useGenerateWeeklyReview() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<WeeklyReview>("/api/appgen/weekly_reviews/generate"),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["appgen", "weekly-reviews"] });
    },
  });
}

export function useTopicAppgenIdeas(limit = 100, enabled = true, runId: string | null = null) {
  return useQuery({
    queryKey: ["topic", "appgen", "ideas", limit, runId ?? ""],
    queryFn: async () => {
      const suffix = runId ? `&run_id=${encodeURIComponent(runId)}` : "";
      const data = await apiGet<unknown>(`/api/topic/appgen/ideas?sort=updated_desc${suffix}`);
      return asArray<TopicAppgenIdea>(data).slice(0, limit);
    },
    enabled,
    refetchInterval: enabled ? 30_000 : false,
  });
}

export function useTopicAppgenRuns(limit = 100, enabled = true) {
  return useQuery({
    queryKey: ["topic", "appgen", "runs", limit],
    queryFn: async () => {
      const data = await apiGet<unknown>(`/api/topic/appgen/runs?limit=${limit}`);
      return asArray<TopicAppgenRun>(data);
    },
    enabled,
    refetchInterval: enabled ? 30_000 : false,
  });
}

export function useTopicAppgenRunDetail(runId: string | null, enabled = true) {
  return useQuery({
    queryKey: ["topic", "appgen", "run-detail", runId],
    queryFn: async () => {
      try {
        return await apiGet<Record<string, unknown>>(`/api/topic/appgen/runs/${runId}`);
      } catch (error) {
        if (isNotFoundError(error)) return null as unknown as Record<string, unknown>;
        throw error;
      }
    },
    enabled: Boolean(runId) && enabled,
    refetchInterval: enabled ? 7_500 : false,
    retry: (count, error) => !isNotFoundError(error) && count < 2,
  });
}

export function useTopicAppgenAnalyzeRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: TopicAppgenAnalyzeRunRequest) => apiPost<TopicAppgenAnalyzeRunResponse>("/api/topic/appgen/analyze-run", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["topic", "runs"] });
      client.invalidateQueries({ queryKey: ["topic", "appgen", "runs"] });
    },
  });
}

export function useTopicAppgenGenerate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: TopicAppgenGenerateRequest) => apiPost<TopicAppgenGenerateResponse>("/api/topic/appgen/generate", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["topic", "appgen", "runs"] });
      client.invalidateQueries({ queryKey: ["topic", "appgen", "ideas"] });
    },
  });
}

export function useCancelTopicAppgenRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => apiPost<Record<string, unknown>>(`/api/topic/appgen/runs/${runId}/cancel`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["topic", "appgen", "runs"] });
      client.invalidateQueries({ queryKey: ["topic", "appgen", "run-detail"] });
    },
  });
}

export function useDeleteTopicAppgenRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (runId: string) => {
      try {
        return await apiDelete<Record<string, unknown>>(`/api/topic/appgen/runs/${runId}`);
      } catch (error) {
        if (isNotFoundError(error)) return { ok: true, deleted: false, reason: "not_found" } as Record<string, unknown>;
        throw error;
      }
    },
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["topic", "appgen", "runs"] });
      client.invalidateQueries({ queryKey: ["topic", "appgen", "run-detail"] });
      client.invalidateQueries({ queryKey: ["topic", "appgen", "ideas"] });
    },
  });
}

// Trends Researcher
export function useTrendsRuns() {
  return useQuery({
    queryKey: ["trends", "runs"],
    queryFn: async () => {
      const data = await apiGet<unknown>("/api/trends/runs");
      const rows = Array.isArray(data) ? (data as Array<Record<string, unknown>>) : [];
      const normalized = rows
        .map((row) => {
          const id = String(row.id ?? row.run_id ?? "").trim();
          if (!id) return null;
          return {
            id,
            status: String(row.status ?? "UNKNOWN"),
            started_at: (row.started_at as string | null | undefined) ?? null,
            finished_at: (row.finished_at as string | null | undefined) ?? null,
            params_json: (row.params_json as Record<string, unknown> | undefined) ?? {},
            totals_json: (row.totals_json as Record<string, unknown> | undefined) ?? {},
            error: (row.error as string | null | undefined) ?? null,
          } satisfies TrendsRun;
        })
        .filter((item): item is TrendsRun => Boolean(item));

      normalized.sort((a, b) => {
        const ta = new Date(a.started_at ?? a.finished_at ?? 0).getTime();
        const tb = new Date(b.started_at ?? b.finished_at ?? 0).getTime();
        return tb - ta;
      });
      return normalized;
    },
    refetchInterval: 15_000,
  });
}

export function useTrendsRun(runId: string | null, enabled = true) {
  return useQuery({
    queryKey: ["trends", "run", runId],
    queryFn: async () => {
      let row: Record<string, unknown>;
      try {
        row = await apiGet<Record<string, unknown>>(`/api/trends/runs/${runId}`);
      } catch (error) {
        if (isNotFoundError(error)) {
          return {
            id: String(runId ?? ""),
            status: "MISSING",
            started_at: null,
            finished_at: null,
            params_json: {},
            totals_json: {},
            error: "run not found",
          } satisfies TrendsRun;
        }
        throw error;
      }
      const id = String(row.id ?? row.run_id ?? runId ?? "").trim();
      return {
        id,
        status: String(row.status ?? "UNKNOWN"),
        started_at: (row.started_at as string | null | undefined) ?? null,
        finished_at: (row.finished_at as string | null | undefined) ?? null,
        params_json: (row.params_json as Record<string, unknown> | undefined) ?? {},
        totals_json: (row.totals_json as Record<string, unknown> | undefined) ?? {},
        error: (row.error as string | null | undefined) ?? null,
      } satisfies TrendsRun;
    },
    enabled: Boolean(runId) && enabled,
    refetchInterval: enabled ? 2_000 : false,
  });
}

export function useTrendsRunResults(runId: string | null, limit = 25, enabled = true) {
  return useQuery({
    queryKey: ["trends", "run-results", runId, limit],
    queryFn: async () => {
      try {
        return await apiGet<TrendsRunResults>(`/api/trends/runs/${runId}/results?limit=${limit}`);
      } catch (error) {
        if (isNotFoundError(error)) {
          return {
            run_id: String(runId ?? ""),
            status: "MISSING",
            top_overall: [],
            top_per_channel: {},
            top_by_source: {},
            strategy_status: {
              status: "missing",
              error: "run not found",
            },
          } satisfies TrendsRunResults;
        }
        throw error;
      }
    },
    enabled: Boolean(runId) && enabled,
  });
}

export function useTrendsRunLogs(runId: string | null, limit = 200, enabled = true) {
  return useQuery({
    queryKey: ["trends", "run-logs", runId, limit],
    queryFn: async () => {
      try {
        return await apiGet<TrendsRunLogs>(`/api/trends/runs/${runId}/logs?limit=${limit}`);
      } catch (error) {
        if (isNotFoundError(error)) {
          return {
            run_id: String(runId ?? ""),
            offset: 0,
            next_offset: 0,
            total_lines: 0,
            has_more: false,
            lines: [],
          } satisfies TrendsRunLogs;
        }
        throw error;
      }
    },
    enabled: Boolean(runId) && enabled,
    refetchInterval: enabled ? 3_000 : false,
  });
}

export function useTrendsTopicDetail(topicId: string | null) {
  return useQuery({
    queryKey: ["trends", "topic", topicId],
    queryFn: () => apiGet<TrendsTopicDetail>(`/api/trends/topics/${topicId}`),
    enabled: Boolean(topicId),
  });
}

export function useStartTrendsRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: TrendsRunStartRequest) => apiPost<{ run_id: string }>("/api/trends/runs/start", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["trends", "runs"] });
    },
  });
}

export function useTrendsOpenAiKeyStatus(enabled = true) {
  return useQuery({
    queryKey: ["trends", "openai-key-status"],
    queryFn: () => apiGet<TrendsOpenAiKeyStatus>("/api/trends/openai/key/status"),
    enabled,
    refetchInterval: enabled ? 30_000 : false,
  });
}

export function useSetTrendsOpenAiKey() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (api_key: string) => apiPost<TrendsOpenAiKeyStatus>("/api/trends/openai/key", { api_key }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["trends", "openai-key-status"] });
    },
  });
}

export function useDeleteTrendsRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => apiDelete<{ status: string }>(`/api/trends/runs/${runId}`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["trends", "runs"] });
      client.invalidateQueries({ queryKey: ["trends", "run"] });
      client.invalidateQueries({ queryKey: ["trends", "run-results"] });
    },
  });
}

export function useCancelTrendsRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => apiPost<Record<string, unknown>>(`/api/trends/runs/${runId}/cancel`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["trends", "runs"] });
      client.invalidateQueries({ queryKey: ["trends", "run"] });
      client.invalidateQueries({ queryKey: ["trends", "run-results"] });
    },
  });
}

export function useNudgeTrendsRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => apiPost<Record<string, unknown>>(`/api/trends/runs/${runId}/nudge`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["trends", "runs"] });
      client.invalidateQueries({ queryKey: ["trends", "run"] });
    },
  });
}

export function useTrendTopicAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ topicId, payload }: { topicId: string; payload: TrendsTopicActionRequest }) =>
      apiPost<Record<string, unknown>>(`/api/trends/topics/${topicId}/action`, payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["trends", "run-results"] });
    },
  });
}

export function useTrendsExport() {
  return useMutation({
    mutationFn: (payload: TrendsExportRequest) => apiPost<Record<string, unknown>>("/api/trends/export", payload),
  });
}

export function useTrendsImportTopicFactory() {
  return useMutation({
    mutationFn: async (exported_payload: Record<string, unknown>) => {
      try {
        return await apiPost<TrendsTopicFactoryImportResponse>("/api/trends/topic-factory/import-trends", { exported_payload });
      } catch (err) {
        const message = String((err as Error)?.message ?? "");
        if (message.includes("404")) {
          try {
            return await apiPost<TrendsTopicFactoryImportResponse>("/dashburg/api/topic-factory/import-trends", { exported_payload });
          } catch (legacyErr) {
            const legacyMessage = String((legacyErr as Error)?.message ?? "");
            if (!legacyMessage.includes("404") && !legacyMessage.includes("405")) throw legacyErr;
            try {
              return await apiPost<TrendsTopicFactoryImportResponse>("/api/topic/appgen/import-trends", { exported_payload });
            } catch (topicErr) {
              const topicMessage = String((topicErr as Error)?.message ?? "");
              if (!topicMessage.includes("404") && !topicMessage.includes("405")) throw topicErr;
              return await apiPost<TrendsTopicFactoryImportResponse>("/api/v1/appgen/import-trends", exported_payload);
            }
          }
        }
        throw err;
      }
    },
  });
}

// IdeaVault
export function useIdeaVaultItems(params?: {
  search?: string;
  status?: string;
  type?: string;
  tag?: string;
  pinned?: boolean;
  sort?: "priority" | "newest" | "oldest" | "score";
  limit?: number;
  offset?: number;
  include_payload?: boolean;
  enabled?: boolean;
}) {
  return useQuery({
    queryKey: ["ideavault", "items", params ?? {}],
    queryFn: () => {
      const query = new URLSearchParams();
      if (params?.search) query.set("search", params.search);
      if (params?.status) query.set("status", params.status);
      if (params?.type) query.set("type", params.type);
      if (params?.tag) query.set("tag", params.tag);
      if (typeof params?.pinned === "boolean") query.set("pinned", String(params.pinned));
      if (params?.sort) query.set("sort", params.sort);
      if (typeof params?.limit === "number") query.set("limit", String(params.limit));
      if (typeof params?.offset === "number") query.set("offset", String(params.offset));
      if (typeof params?.include_payload === "boolean") query.set("include_payload", String(params.include_payload));
      const suffix = query.toString() ? `?${query.toString()}` : "";
      return apiGet<IdeaVaultItem[]>(`/api/ideavault/items${suffix}`);
    },
    enabled: params?.enabled ?? true,
    refetchInterval: (params?.enabled ?? true) ? 15_000 : false,
  });
}

export function useIdeaVaultItem(itemId: string | null) {
  return useQuery({
    queryKey: ["ideavault", "item", itemId],
    queryFn: () => apiGet<IdeaVaultItem>(`/api/ideavault/items/${itemId}`),
    enabled: Boolean(itemId),
  });
}

export function useCreateIdeaVaultItem() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: IdeaVaultCreateRequest) => apiPost<IdeaVaultItem>("/api/ideavault/items", payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ["ideavault", "items"] }),
  });
}

export function usePatchIdeaVaultItem() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, payload }: { itemId: string; payload: IdeaVaultPatchRequest }) =>
      apiPatch<IdeaVaultItem>(`/api/ideavault/items/${itemId}`, payload),
    onSuccess: (updated) => {
      client.setQueriesData(
        { queryKey: ["ideavault", "items"] },
        (prev: IdeaVaultItem[] | undefined) => {
          if (!Array.isArray(prev)) return prev;
          return prev.map((row) => (row.id === updated.id ? { ...row, ...updated } : row));
        },
      );
      client.setQueryData(["ideavault", "item", updated.id], updated);
    },
  });
}

export function useDeleteIdeaVaultItem() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) => apiDelete<{ ok: boolean }>(`/api/ideavault/items/${itemId}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["ideavault", "items"] }),
  });
}

export function useReorderIdeaVaultItems() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (orderedIds: string[]) => apiPost<{ ok: boolean }>("/api/ideavault/items/reorder", { orderedIds }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["ideavault", "items"] }),
  });
}

export function useTopicFactoryQueue(enabled = true) {
  return useQuery({
    queryKey: ["topicfactory", "queue"],
    queryFn: () => getTopicFactoryQueue(),
    enabled,
    refetchInterval: enabled ? 10_000 : false,
    retry: (count, error) => !isNotFoundError(error) && count < 2,
    refetchOnWindowFocus: false,
  });
}

export function useEnqueueTopicFactory() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: TopicFactoryQueueCreateRequest) => postTopicFactoryQueue(payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["topicfactory", "queue"] });
      client.invalidateQueries({ queryKey: ["ideavault", "items"] });
    },
  });
}

export function useIdeaVaultLineage(itemId: string | null) {
  return useQuery({
    queryKey: ["ideavault", "lineage", itemId],
    queryFn: () => apiGet<OpportunityLineageTrace>(`/api/ideavault/items/${itemId}/lineage`),
    enabled: Boolean(itemId),
    refetchInterval: itemId ? 20_000 : false,
  });
}

export function useLineageTrace(kind: string | null, nodeId: string | null) {
  return useQuery({
    queryKey: ["lineage", "trace", kind ?? "", nodeId ?? ""],
    queryFn: () => apiGet<OpportunityLineageTrace>(`/api/lineage/trace?kind=${encodeURIComponent(kind ?? "")}&id=${encodeURIComponent(nodeId ?? "")}`),
    enabled: Boolean(kind && nodeId),
    refetchInterval: kind && nodeId ? 20_000 : false,
  });
}

export function useTransformSignalToOpportunities() {
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      apiPost<{ source: Record<string, unknown>; forms: Array<Record<string, unknown>>; next_actions: Array<Record<string, unknown>> }>(
        "/api/appgen/transform/from-signal",
        payload,
      ),
  });
}

export function useStartTopicFactoryQueueItem() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (queueId: string) => postTopicFactoryQueueAction(queueId, "start"),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["topicfactory", "queue"] });
      client.invalidateQueries({ queryKey: ["ideavault", "items"] });
    },
  });
}

export function useCancelTopicFactoryQueueItem() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (queueId: string) => postTopicFactoryQueueAction(queueId, "cancel"),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["topicfactory", "queue"] });
      client.invalidateQueries({ queryKey: ["ideavault", "items"] });
    },
  });
}

export function useDeleteTopicFactoryQueueItem() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (queueId: string) => deleteTopicFactoryQueueItem(queueId),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["topicfactory", "queue"] });
      client.invalidateQueries({ queryKey: ["ideavault", "items"] });
    },
  });
}

// WebAgent
export function useWebAgentOverview() {
  return useQuery({
    queryKey: ["webagent", "overview"],
    queryFn: () => apiGet<WebAgentOverview>("/api/webagent/overview"),
    refetchInterval: 10_000,
    retry: false,
  });
}

export function useWebAgentRuns(filters?: { status?: string; saved_only?: boolean; limit?: number }) {
  const params = new URLSearchParams();
  if (filters?.status) params.set("status", filters.status);
  if (filters?.saved_only) params.set("saved_only", "true");
  if (filters?.limit) params.set("limit", String(filters.limit));
  const query = params.toString();
  return useQuery({
    queryKey: ["webagent", "runs", query],
    queryFn: async () => {
      const payload = await apiGet<{ items: WebAgentRun[] }>(`/api/webagent/runs${query ? `?${query}` : ""}`);
      return payload.items ?? [];
    },
    refetchInterval: 8_000,
    retry: false,
  });
}

export function useWebAgentRun(runId: string | null) {
  return useQuery({
    queryKey: ["webagent", "run", runId],
    queryFn: () => apiGet<WebAgentRun>(`/api/webagent/runs/${runId}`),
    enabled: Boolean(runId),
    refetchInterval: (query) => {
      const row = query.state.data;
      if (!row) return 5_000;
      if (["completed", "failed", "cancelled"].includes(String(row.status))) return false;
      return 5_000;
    },
    retry: false,
  });
}

export function useCreateWebAgentRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      target_url: string;
      run_type: string;
      node_id?: string;
      notes?: string;
      settings: Partial<WebAgentRunSettings>;
    }) => apiPost<WebAgentRun>("/api/webagent/runs", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["webagent", "overview"] });
      client.invalidateQueries({ queryKey: ["webagent", "runs"] });
      client.invalidateQueries({ queryKey: ["remote", "jobs"] });
    },
  });
}

export function useRetryWebAgentRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => apiPost<WebAgentRun>(`/api/webagent/runs/${runId}/retry`, {}),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["webagent", "overview"] });
      client.invalidateQueries({ queryKey: ["webagent", "runs"] });
    },
  });
}

export function useSaveWebAgentReport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, title }: { runId: string; title?: string }) =>
      apiPost<WebAgentReport>(`/api/webagent/runs/${runId}/save-report`, { title: title ?? "" }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["webagent", "runs"] });
      client.invalidateQueries({ queryKey: ["webagent", "reports"] });
    },
  });
}

export function useMarkWebAgentRunUseful() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, is_useful }: { runId: string; is_useful: boolean }) =>
      apiPost<WebAgentRun>(`/api/webagent/runs/${runId}/useful`, { is_useful }),
    onSuccess: (_data, vars) => {
      client.invalidateQueries({ queryKey: ["webagent", "run", vars.runId] });
      client.invalidateQueries({ queryKey: ["webagent", "runs"] });
      client.invalidateQueries({ queryKey: ["webagent", "overview"] });
    },
  });
}

export function useWebAgentReports(limit = 200) {
  return useQuery({
    queryKey: ["webagent", "reports", limit],
    queryFn: async () => {
      const payload = await apiGet<{ items: WebAgentReport[] }>(`/api/webagent/reports?limit=${limit}`);
      return payload.items ?? [];
    },
    refetchInterval: 12_000,
    retry: false,
  });
}

export function useWebAgentStatus(nodeId?: string) {
  const query = nodeId ? `?node_id=${encodeURIComponent(nodeId)}` : "";
  return useQuery({
    queryKey: ["webagent", "status", nodeId ?? ""],
    queryFn: () => apiGet<WebAgentStatus>(`/api/webagent/status${query}`),
    refetchInterval: 15_000,
    retry: false,
  });
}

export function useWebAgentRunLive(runId: string | null) {
  return useQuery({
    queryKey: ["webagent", "run-live", runId],
    queryFn: () => apiGet<WebAgentLiveSession>(`/api/webagent/runs/${runId}/live`),
    enabled: Boolean(runId),
    refetchInterval: 5_000,
    retry: false,
  });
}

export function useWebAgentRunArtifacts(runId: string | null) {
  return useQuery({
    queryKey: ["webagent", "run-artifacts", runId],
    queryFn: () => apiGet<WebAgentArtifactList>(`/api/webagent/runs/${runId}/artifacts`),
    enabled: Boolean(runId),
    refetchInterval: 5_000,
    retry: false,
  });
}

export function useWebAgentRunLogs(runId: string | null, limit = 800) {
  return useQuery({
    queryKey: ["webagent", "run-logs", runId, limit],
    queryFn: () => apiGet<WebAgentLogs>(`/api/webagent/runs/${runId}/logs?limit=${limit}`),
    enabled: Boolean(runId),
    refetchInterval: 4_000,
    retry: false,
  });
}

export function useWebAgentRunReplay(runId: string | null) {
  return useQuery({
    queryKey: ["webagent", "run-replay", runId],
    queryFn: () => apiGet<WebAgentReplayAssets>(`/api/webagent/runs/${runId}/replay`),
    enabled: Boolean(runId),
    refetchInterval: 8_000,
    retry: false,
  });
}

export function useWebAgentRunScreenshots(runId: string | null) {
  return useQuery({
    queryKey: ["webagent", "run-screenshots", runId],
    queryFn: () => apiGet<{ run_id: string; items: Array<Record<string, unknown>>; count: number }>(`/api/webagent/runs/${runId}/screenshots`),
    enabled: Boolean(runId),
    refetchInterval: 5_000,
    retry: false,
  });
}

export function useWebAgentRunGeneratedTests(runId: string | null) {
  return useQuery({
    queryKey: ["webagent", "run-generated-tests", runId],
    queryFn: () => apiGet<WebAgentGeneratedTests>(`/api/webagent/runs/${runId}/generated-tests`),
    enabled: Boolean(runId),
    refetchInterval: 8_000,
    retry: false,
  });
}

export function useWebAgentRunDiscovery(runId: string | null) {
  return useQuery({
    queryKey: ["webagent", "run-discovery", runId],
    queryFn: () => apiGet<WebAgentDiscovery>(`/api/webagent/runs/${runId}/discovery`),
    enabled: Boolean(runId),
    refetchInterval: 8_000,
    retry: false,
  });
}

export function useCreateWebAgentSession() {
  return useMutation({
    mutationFn: (payload: { target_url: string; node_id?: string; settings?: Record<string, unknown>; timeout_seconds?: number }) =>
      apiPost<WebAgentSessionResult>("/api/webagent/sessions", payload),
  });
}

export function useWebAgentSessionStatus() {
  return useMutation({
    mutationFn: ({ sessionId, nodeId, timeoutSeconds }: { sessionId: string; nodeId?: string; timeoutSeconds?: number }) => {
      const params = new URLSearchParams();
      if (nodeId) params.set("node_id", nodeId);
      if (timeoutSeconds) params.set("timeout_seconds", String(timeoutSeconds));
      return apiGet<WebAgentSessionResult>(`/api/webagent/sessions/${encodeURIComponent(sessionId)}${params.toString() ? `?${params.toString()}` : ""}`);
    },
  });
}

export function useCloseWebAgentSession() {
  return useMutation({
    mutationFn: ({ sessionId, nodeId, timeoutSeconds }: { sessionId: string; nodeId?: string; timeoutSeconds?: number }) => {
      const params = new URLSearchParams();
      if (nodeId) params.set("node_id", nodeId);
      if (timeoutSeconds) params.set("timeout_seconds", String(timeoutSeconds));
      return apiDelete<WebAgentSessionResult>(`/api/webagent/sessions/${encodeURIComponent(sessionId)}${params.toString() ? `?${params.toString()}` : ""}`);
    },
  });
}

export function useWebAgentSessionAction() {
  return useMutation({
    mutationFn: ({ sessionId, payload }: { sessionId: string; payload: WebAgentSessionAction & { action: string } }) =>
      apiPost<WebAgentSessionResult>(`/api/webagent/sessions/${encodeURIComponent(sessionId)}/actions`, payload),
  });
}

export function useWebAgentAction() {
  return useMutation({
    mutationFn: (payload: WebAgentSessionAction & { action: string }) => apiPost<WebAgentSessionResult>("/api/webagent/actions", payload),
  });
}

export function useWebAgentTool() {
  return useMutation({
    mutationFn: ({ tool, payload }: { tool: string; payload: WebAgentSessionAction }) =>
      apiPost<WebAgentToolResult>(`/api/webagent/tools/${encodeURIComponent(tool)}`, payload),
  });
}

// Remote Ops
export function useRemoteSettings() {
  return useQuery({
    queryKey: ["remote", "settings"],
    queryFn: () => apiGet<RemoteOpsSettings>("/api/remote/settings"),
  });
}

export function useOrchestrationOverview() {
  return useQuery({
    queryKey: ["orchestration", "overview"],
    queryFn: () => apiGet<OrchestrationOverview>("/api/orchestration/overview"),
    refetchInterval: 4000,
  });
}

export function useOrchestrationSettings() {
  return useQuery({
    queryKey: ["orchestration", "settings"],
    queryFn: () => apiGet<OrchestrationSettings>("/api/orchestration/settings"),
  });
}

export function useUpdateOrchestrationSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: OrchestrationSettings) => apiPut<OrchestrationSettings>("/api/orchestration/settings", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["orchestration"] });
    },
  });
}

export function useOrchestrationNodes() {
  return useQuery({
    queryKey: ["orchestration", "nodes"],
    queryFn: () => apiGet<OrchestrationNodeSummary[]>("/api/orchestration/nodes"),
    refetchInterval: 4000,
  });
}

export function useOrchestrationTerminalLaunch() {
  return useQuery({
    queryKey: ["orchestration", "terminal-launch"],
    queryFn: () => apiGet<OrchestrationTerminalLaunch>("/api/orchestration/terminal/launch"),
  });
}

export function useOrchestrationJobs(status?: string) {
  return useQuery({
    queryKey: ["orchestration", "jobs", status ?? ""],
    queryFn: () => apiGet<OrchestrationJob[]>(`/api/orchestration/jobs${status ? `?status=${encodeURIComponent(status)}` : ""}`),
    refetchInterval: 4000,
  });
}

export function useOrchestrationJob(jobId: string | null) {
  return useQuery({
    queryKey: ["orchestration", "job", jobId],
    queryFn: () => apiGet<OrchestrationJob>(`/api/orchestration/jobs/${jobId}`),
    enabled: Boolean(jobId),
    refetchInterval: 3000,
  });
}

export function useCreateOrchestrationJob() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) => apiPost<OrchestrationJob>("/api/orchestration/jobs", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["orchestration"] });
    },
  });
}

export function useCancelOrchestrationJob() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => apiPost<{ ok: boolean; job: OrchestrationJob }>(`/api/orchestration/jobs/${jobId}/cancel`, {}),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["orchestration"] });
    },
  });
}

export function useRetryOrchestrationJob() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => apiPost<{ ok: boolean; job: OrchestrationJob }>(`/api/orchestration/jobs/${jobId}/retry`, {}),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["orchestration"] });
    },
  });
}

export function useOrchestrationMailbox(params?: { nodeId?: string; direction?: string; jobId?: string; includeArchived?: boolean; limit?: number }) {
  const qs = new URLSearchParams();
  if (params?.nodeId) qs.set("node_id", params.nodeId);
  if (params?.direction) qs.set("direction", params.direction);
  if (params?.jobId) qs.set("job_id", params.jobId);
  if (params?.includeArchived) qs.set("include_archived", "1");
  qs.set("limit", String(params?.limit ?? 100));
  return useQuery({
    queryKey: ["orchestration", "mailbox", params ?? {}],
    queryFn: () => apiGet<{ items: OrchestrationMailboxItem[] }>(`/api/orchestration/mailbox?${qs.toString()}`),
    refetchInterval: 4000,
  });
}

export function useCreateOrchestrationMailboxNote() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ nodeId, payload }: { nodeId: string; payload: Record<string, unknown> }) => {
      const to = String(payload.to ?? "").trim() || `node:${nodeId}/runner`;
      const wrapped = await apiPost<{ message: OrchestrationMailboxItem }>("/api/orchestration/mail/send", {
        ...payload,
        target_node_id: nodeId,
        to,
      });
      return wrapped.message;
    },
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["orchestration"] });
      client.invalidateQueries({ queryKey: ["mailcenter"] });
    },
  });
}

export function useAcknowledgeOrchestrationMailboxItem() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ nodeId, itemId }: { nodeId: string; itemId: string }) =>
      apiPost<OrchestrationMailboxItem>(`/api/orchestration/nodes/${nodeId}/mailbox/${itemId}/ack`, {}),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["orchestration"] });
    },
  });
}

export function useArchiveOrchestrationMailboxItem() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ nodeId, itemId }: { nodeId: string; itemId: string }) =>
      apiPost<OrchestrationMailboxItem>(`/api/orchestration/nodes/${nodeId}/mailbox/${itemId}/archive`, {}),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["orchestration"] });
    },
  });
}

export function useScheduleOpsNodes() {
  return useQuery({
    queryKey: ["scheduleops-nodes"],
    queryFn: async () => {
      const payload = await apiGet<{ items: ScheduleOpsNode[] }>("/api/scheduleops/nodes");
      return payload.items ?? [];
    },
    refetchInterval: 20_000,
  });
}

export function useScheduleOpsNode(nodeId: string | null) {
  return useQuery({
    queryKey: ["scheduleops-node", nodeId],
    queryFn: () => apiGet<ScheduleOpsNodePayload>(`/api/scheduleops/nodes/${nodeId}`),
    enabled: Boolean(nodeId),
  });
}

export function useScheduleOpsStatus() {
  return useQuery({
    queryKey: ["scheduleops-status"],
    queryFn: () => apiGet<ScheduleOpsClusterStatus>("/api/scheduleops/status"),
    refetchInterval: 15_000,
  });
}

export function useRedisBrokerOverview() {
  return useQuery({
    queryKey: ["monitoring-redis-broker-overview"],
    queryFn: () => apiGet<RedisBrokerOverview>("/api/monitoring/redis-broker/overview"),
    staleTime: 60_000,
    refetchInterval: 60_000,
    refetchOnReconnect: false,
  });
}

export function useRedisBrokerProviderConfig() {
  return useQuery({
    queryKey: ["monitoring-redis-broker-provider-config"],
    queryFn: () => apiGet<RedisBrokerProviderConfig>("/api/monitoring/redis-broker/config/providers"),
    refetchInterval: false,
  });
}

export function useValidateRedisBrokerProviderConfig() {
  return useMutation({
    mutationFn: (providers: Array<Record<string, unknown>>) =>
      apiPost<{ ok: boolean; count: number }>("/api/monitoring/redis-broker/config/providers/validate", { providers }),
  });
}

export function useApplyRedisBrokerProviderConfig() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (providers: Array<Record<string, unknown>>) =>
      apiPost<{ ok: boolean; backup_path?: string; providers?: number }>("/api/monitoring/redis-broker/config/providers/apply", {
        providers,
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["monitoring-redis-broker-provider-config"] });
      client.invalidateQueries({ queryKey: ["monitoring-redis-broker-overview"] });
    },
  });
}

export function useRollbackRedisBrokerProviderConfig() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (backupPath?: string) =>
      apiPost<{ ok: boolean; restored_from?: string }>("/api/monitoring/redis-broker/config/providers/rollback", backupPath ? { backup_path: backupPath } : {}),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["monitoring-redis-broker-provider-config"] });
      client.invalidateQueries({ queryKey: ["monitoring-redis-broker-overview"] });
    },
  });
}

export function useScheduleOpsNodeStatus(nodeId: string | null) {
  return useQuery({
    queryKey: ["scheduleops-node-status", nodeId],
    queryFn: () => apiGet<ScheduleOpsNodeStatus>(`/api/scheduleops/nodes/${nodeId}/status`),
    enabled: Boolean(nodeId),
    refetchInterval: 15_000,
  });
}

export function useUpdateScheduleOpsNode() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ nodeId, config }: { nodeId: string; config: ScheduleOpsConfig }) =>
      apiPut<ScheduleOpsNodePayload>(`/api/scheduleops/nodes/${nodeId}`, config),
    onSuccess: (_payload, vars) => {
      client.invalidateQueries({ queryKey: ["scheduleops-node", vars.nodeId] });
      client.invalidateQueries({ queryKey: ["scheduleops-nodes"] });
    },
  });
}

export function useApplyScheduleOpsNode() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (nodeId: string) => apiPost<ScheduleOpsNodePayload>(`/api/scheduleops/nodes/${nodeId}/apply`, {}),
    onSuccess: (_payload, nodeId) => {
      client.invalidateQueries({ queryKey: ["scheduleops-node", nodeId] });
      client.invalidateQueries({ queryKey: ["scheduleops-nodes"] });
    },
  });
}

export function useDelegateNodeDiagnostic() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      node_id: string;
      issue: string;
      repo_path?: string;
      workspace_path?: string;
      title?: string;
      instructions?: string;
      codex_mode?: "read-only" | "workspace-write" | "danger-full-access";
      timeout_seconds?: number;
      priority?: number;
      max_retries?: number;
      metadata?: Record<string, unknown>;
    }) => apiPost<{ job: OrchestrationJob }>("/api/scheduleops/diagnostics/delegate", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["orchestration"] });
    },
  });
}

export function useMailCenterOverview() {
  return useQuery({
    queryKey: ["mailcenter", "overview"],
    queryFn: () => apiGet<MailCenterOverview>("/api/mailcenter/overview"),
    refetchInterval: 10_000,
  });
}

export function useMailCenterMessages(params?: {
  folder?: string;
  status?: string;
  direction?: string;
  account?: string;
  tag?: string;
  recipientNodeId?: string;
  recipientAgentSlug?: string;
  unreadOnly?: boolean;
  q?: string;
  limit?: number;
}) {
  const qs = new URLSearchParams();
  if (params?.folder) qs.set("folder", params.folder);
  if (params?.status) qs.set("status", params.status);
  if (params?.direction) qs.set("direction", params.direction);
  if (params?.account) qs.set("account", params.account);
  if (params?.tag) qs.set("tag", params.tag);
  if (params?.recipientNodeId) qs.set("recipient_node_id", params.recipientNodeId);
  if (params?.recipientAgentSlug) qs.set("recipient_agent_slug", params.recipientAgentSlug);
  if (params?.unreadOnly) qs.set("unread_only", "1");
  if (params?.q) qs.set("q", params.q);
  qs.set("limit", String(params?.limit ?? 150));
  return useQuery({
    queryKey: ["mailcenter", "messages", params ?? {}],
    queryFn: () => apiGet<{ items: MailCenterMessage[] }>(`/api/mailcenter/messages?${qs.toString()}`),
    refetchInterval: 10_000,
  });
}

export function useMailCenterThreads(params?: { folder?: string; q?: string; limit?: number }) {
  const qs = new URLSearchParams();
  if (params?.folder) qs.set("folder", params.folder);
  if (params?.q) qs.set("q", params.q);
  qs.set("limit", String(params?.limit ?? 120));
  return useQuery({
    queryKey: ["mailcenter", "threads", params ?? {}],
    queryFn: () => apiGet<{ items: MailCenterThread[] }>(`/api/mailcenter/threads?${qs.toString()}`),
    refetchInterval: 15_000,
  });
}

export function useMailCenterMessageDetail(messageId: string | null) {
  return useQuery({
    queryKey: ["mailcenter", "message-detail", messageId],
    queryFn: () => apiGet<MailCenterMessageDetail>(`/api/mailcenter/messages/${messageId}`),
    enabled: Boolean(messageId),
    refetchInterval: 10_000,
  });
}

export function useMailCenterRecipients() {
  return useQuery({
    queryKey: ["mailcenter", "recipients"],
    queryFn: () => apiGet<MailCenterRecipients>("/api/mailcenter/recipients"),
    refetchInterval: 30_000,
  });
}

export function useSendMailCenterMessage() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) => apiPost<{ message: MailCenterMessage }>("/api/mailcenter/send", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["mailcenter"] });
      client.invalidateQueries({ queryKey: ["orchestration"] });
    },
  });
}

export function useUpdateRemoteSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: RemoteOpsSettings) => apiPut<RemoteOpsSettings>("/api/remote/settings", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["remote", "settings"] });
    },
  });
}

export function useRemoteNodes() {
  return useQuery({
    queryKey: ["remote", "nodes"],
    queryFn: () => apiGet<RemoteOpsNode[]>("/api/remote/nodes"),
    refetchInterval: 15_000,
  });
}

export function useCreateRemoteNode() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<RemoteOpsNode> & { id: string; label: string; base_url: string }) =>
      apiPost<RemoteOpsNode>("/api/remote/nodes", payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ["remote", "nodes"] }),
  });
}

export function useUpdateRemoteNode() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ nodeId, payload }: { nodeId: string; payload: Partial<RemoteOpsNode> }) =>
      apiPut<RemoteOpsNode>(`/api/remote/nodes/${nodeId}`, payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ["remote", "nodes"] }),
  });
}

export function useDeleteRemoteNode() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (nodeId: string) => apiDelete<{ ok: boolean }>(`/api/remote/nodes/${nodeId}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["remote", "nodes"] }),
  });
}

export function useRotateNodeKey() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ nodeId, disable_previous }: { nodeId: string; disable_previous: boolean }) =>
      apiPost<{ node_id: string; key_id: string; secret: string }>(`/api/remote/nodes/${nodeId}/rotate-key`, {
        disable_previous,
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["remote", "nodes"] }),
  });
}

export function useDisableNodeKey() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ nodeId, keyId }: { nodeId: string; keyId: string }) =>
      apiPost<{ ok: boolean }>(`/api/remote/nodes/${nodeId}/disable-key/${keyId}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["remote", "nodes"] }),
  });
}

export function useTestNode(nodeId: string | null) {
  return useQuery({
    queryKey: ["remote", "node-test", nodeId],
    queryFn: () => apiGet<Record<string, unknown>>(`/api/remote/nodes/${nodeId}/test`),
    enabled: Boolean(nodeId),
  });
}

export function useRemoteServers() {
  return useQuery({
    queryKey: ["remote", "servers"],
    queryFn: () => apiGet<RemoteServer[]>("/api/remote/servers"),
    retry: false,
    refetchInterval: (query) => (query.state.error ? false : 15_000),
  });
}

export function useRemoteNodesHealth() {
  return useQuery({
    queryKey: ["remote", "nodes-health"],
    queryFn: () => apiGet<{ ttl_seconds: number; nodes: RemoteNodeHealth[] }>("/api/remote/nodes/health"),
    retry: false,
    refetchInterval: (query) => (query.state.error ? false : 15_000),
  });
}

export function useRemoteNodesHostMonitor(options?: { includeProcesses?: boolean; includeGpuProcesses?: boolean }) {
  const includeProcesses = options?.includeProcesses ?? true;
  const includeGpuProcesses = options?.includeGpuProcesses ?? true;
  return useQuery({
    queryKey: ["remote", "nodes-host-monitor", includeProcesses, includeGpuProcesses],
    queryFn: () =>
      apiGet<{ ttl_seconds: number; nodes: RemoteNodeHostMonitor[] }>(
        `/api/remote/nodes/host-monitor?include_processes=${includeProcesses ? "true" : "false"}&include_gpu_processes=${includeGpuProcesses ? "true" : "false"}`,
      ),
    retry: false,
    refetchInterval: (query) => (query.state.error ? false : 15_000),
  });
}

export function useRebootRemoteNodeHostMonitor() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ nodeId, reason }: { nodeId: string; reason?: string }) =>
      apiPost<{ ok: boolean; detail?: string; command?: string }>(`/api/remote/nodes/${nodeId}/host-monitor/reboot`, {
        reason: reason ?? "dashburg_node_health",
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["remote", "nodes-host-monitor"] }),
  });
}

export function useRemoteServerDetail(serverId: string | null) {
  return useQuery({
    queryKey: ["remote", "server", serverId],
    queryFn: () => apiGet<RemoteServerDetail>(`/api/remote/servers/${serverId}`),
    enabled: Boolean(serverId),
    retry: false,
    refetchInterval: (query) => (query.state.error ? false : 15_000),
  });
}

export function useRemoteJobs() {
  return useQuery({
    queryKey: ["remote", "jobs"],
    queryFn: () => apiGet<RemoteJob[]>("/api/remote/jobs"),
    retry: false,
    refetchInterval: (query) => (query.state.error ? false : 10_000),
  });
}

export function useRemoteJob(jobId: string | null) {
  return useQuery({
    queryKey: ["remote", "job", jobId],
    queryFn: () => apiGet<RemoteJob>(`/api/remote/jobs/${jobId}`),
    enabled: Boolean(jobId),
    retry: false,
    refetchInterval: (query) => (query.state.error ? false : 5_000),
  });
}

export function useCreateRemoteJob() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ nodeId, type, params }: { nodeId: string; type: string; params: Record<string, unknown> }) =>
      apiPost<RemoteJob>(`/api/remote/servers/${nodeId}/jobs`, { type, params }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["remote", "jobs"] });
      client.invalidateQueries({ queryKey: ["remote", "servers"] });
    },
  });
}

export function usePatchRemoteJob() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ jobId, merged_label, archived }: { jobId: string; merged_label?: boolean; archived?: boolean }) =>
      (() => {
        const adminToken = window.localStorage.getItem("dashburg.remoteops.adminToken") ?? "";
        const headers: Record<string, string> = { "Content-Type": "application/json" };
        if (adminToken) headers["X-RemoteOps-Admin-Token"] = adminToken;
        return fetch(eventsUrl(`/api/remote/jobs/${jobId}`), {
          method: "PATCH",
          headers,
          body: JSON.stringify({ merged_label, archived }),
        });
      })().then(async (resp) => {
        if (!resp.ok) {
          throw new Error(`PATCH /api/remote/jobs/${jobId} failed: ${resp.status}`);
        }
        return (await resp.json()) as RemoteJob;
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["remote", "jobs"] });
    },
  });
}

export function useCreateTerminalSession() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ node_id, cwd, command, forceNew }: { node_id: string; cwd?: string; command?: string; forceNew?: boolean }) =>
      apiPost<{ session_id: string; session: RemoteTerminalSession; reused: boolean }>("/api/remote/terminal/sessions", {
        node_id,
        cwd,
        command,
        forceNew: Boolean(forceNew),
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["remote", "servers"] });
    },
  });
}

export function useActiveTerminalSession(nodeId: string | null) {
  return useQuery({
    queryKey: ["remote", "terminal", "active", nodeId],
    queryFn: () =>
      apiGet<{ session_id: string | null; session: RemoteTerminalSession | null }>(
        nodeId ? `/api/remote/terminal/sessions/active?node_id=${encodeURIComponent(nodeId)}` : "/api/remote/terminal/sessions/active",
      ),
    enabled: true,
    refetchOnWindowFocus: false,
    refetchInterval: 6_000,
  });
}

export function useKillTerminalSession() {
  return useMutation({
    mutationFn: (sessionId: string) =>
      apiPost<{ ok: boolean; session_id: string }>(`/api/remote/terminal/sessions/${sessionId}/kill`),
  });
}

// LocalOps
export function useLocalOpsSettings() {
  return useQuery({
    queryKey: ["localops", "settings"],
    queryFn: () => apiGet<LocalOpsSettings>("/api/localops/settings"),
  });
}

export function useUpdateLocalOpsSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: LocalOpsSettings) => apiPut<LocalOpsSettings>("/api/localops/settings", payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ["localops", "settings"] }),
  });
}

export function useLocalOpsProviders() {
  return useQuery({
    queryKey: ["localops", "providers"],
    queryFn: () => apiGet<{ providers: LocalOpsProvider[] }>("/api/localops/providers").then((data) => data.providers ?? []),
  });
}

export function useCreateLocalOpsProvider() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: Omit<LocalOpsProvider, "id"> & { api_key?: string }) => apiPost<LocalOpsProvider>("/api/localops/providers", payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ["localops", "providers"] }),
  });
}

export function useUpdateLocalOpsProvider() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ providerId, payload }: { providerId: number; payload: Omit<LocalOpsProvider, "id" | "provider_id"> & { api_key?: string } }) =>
      apiPut<LocalOpsProvider>(`/api/localops/providers/${providerId}`, payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ["localops", "providers"] }),
  });
}

export function useDeleteLocalOpsProvider() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (providerId: number) => apiDelete<{ ok: boolean }>(`/api/localops/providers/${providerId}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["localops", "providers"] }),
  });
}

export function useTestOllama() {
  return useMutation({
    mutationFn: (base_url: string) => apiPost<{ ok: boolean; version?: Record<string, unknown>; models_count?: number }>("/api/localops/providers/ollama/test", { base_url }),
  });
}

export function useOllamaModels(baseUrl: string | null) {
  return useQuery({
    queryKey: ["localops", "ollama-models", baseUrl],
    queryFn: () =>
      apiGet<{ models: string[] }>(`/api/localops/providers/ollama/models?base_url=${encodeURIComponent(baseUrl ?? "")}`).then((data) => data.models ?? []),
    enabled: Boolean(baseUrl),
  });
}

export function useOpenAiModels() {
  return useQuery({
    queryKey: ["localops", "openai-models"],
    queryFn: () => apiGet<{ models: string[] }>("/api/localops/providers/openai/models").then((data) => data.models ?? []),
  });
}

export function useOpenAiOauthStatus() {
  return useQuery({
    queryKey: ["localops", "openai-key-status"],
    queryFn: () => apiGet<LocalOpsOpenAiStatus>("/api/localops/openai/key/status"),
    refetchInterval: 30_000,
  });
}

export function useLocalOpsChatUiConfig() {
  return useQuery({
    queryKey: ["localops", "chatui-config"],
    queryFn: () => apiGet<{ enabled: boolean; url: string }>("/api/localops/chat-ui/config"),
  });
}

export function useDisconnectOpenAiOauth() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<{ configured: boolean; source: string; masked: string }>("/api/localops/openai/key/clear"),
    onSuccess: () => client.invalidateQueries({ queryKey: ["localops", "openai-key-status"] }),
  });
}

export function useSetOpenAiApiKey() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (api_key: string) =>
      apiPost<{ configured: boolean; source: string; masked: string }>("/api/localops/openai/key", { api_key }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["localops", "openai-key-status"] }),
  });
}

export function useLocalOpsThreads() {
  return useQuery({
    queryKey: ["localops", "threads"],
    queryFn: () => apiGet<{ threads: LocalOpsThread[] }>("/api/localops/threads").then((data) => data.threads ?? []),
  });
}

export function useCreateLocalOpsThread() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: { title: string; provider_id: "openai" | "ollama"; provider_endpoint_id?: number | null; model: string; execution_mode: LocalOpsSettings["execution_mode"] }) =>
      apiPost<LocalOpsThread>("/api/localops/threads", payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ["localops", "threads"] }),
  });
}

export function useDeleteLocalOpsThread() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (threadId: string) => apiDelete<{ ok: boolean }>(`/api/localops/threads/${threadId}`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["localops", "threads"] });
      client.invalidateQueries({ queryKey: ["localops", "thread"] });
    },
  });
}

export function useLocalOpsThread(threadId: string | null) {
  return useQuery({
    queryKey: ["localops", "thread", threadId],
    queryFn: () =>
      apiGet<{ thread: LocalOpsThread; messages: LocalOpsMessage[] }>(`/api/localops/threads/${threadId}`),
    enabled: Boolean(threadId),
    retry: false,
  });
}

export function usePostLocalOpsMessage() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      threadId,
      payload,
    }: {
      threadId: string;
      payload: { content: string; provider_id: "openai" | "ollama"; provider_endpoint_id?: number | null; model: string; execution_mode: LocalOpsSettings["execution_mode"] };
    }) => apiPost<{ run_id: string }>(`/api/localops/threads/${threadId}/messages`, payload),
    onSuccess: (_res, vars) => {
      client.invalidateQueries({ queryKey: ["localops", "threads"] });
      client.invalidateQueries({ queryKey: ["localops", "thread", vars.threadId] });
    },
  });
}

export function useLocalOpsRun(runId: string | null) {
  return useQuery({
    queryKey: ["localops", "run", runId],
    queryFn: () => apiGet<{ run: LocalOpsRun; tool_calls: LocalOpsToolCall[] }>(`/api/localops/runs/${runId}`),
    enabled: Boolean(runId),
    refetchInterval: 3_000,
  });
}

export function useCancelLocalOpsRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => apiPost<{ ok: boolean; canceled: boolean }>(`/api/localops/runs/${runId}/cancel`),
    onSuccess: (_res, runId) => client.invalidateQueries({ queryKey: ["localops", "run", runId] }),
  });
}

export function useApproveLocalOpsToolCall() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, toolCallId }: { runId: string; toolCallId: string }) =>
      apiPost<{ ok: boolean; status: string }>(`/api/localops/runs/${runId}/approveToolCall`, { tool_call_id: toolCallId }),
    onSuccess: (_res, vars) => client.invalidateQueries({ queryKey: ["localops", "run", vars.runId] }),
  });
}

export function useLocalOpsActiveTerminalSession() {
  return useQuery({
    queryKey: ["localops", "terminal", "active"],
    queryFn: () =>
      apiGet<{ session_id: string | null; session?: LocalOpsTerminalSession | null }>("/api/localops/terminal/sessions/active"),
    refetchInterval: 6_000,
  });
}

export function useCreateLocalOpsTerminalSession() {
  return useMutation({
    mutationFn: (payload?: { force_new?: boolean; cwd?: string; command?: string }) =>
      apiPost<{ session_id: string; reused: boolean; session?: LocalOpsTerminalSession }>(
        "/api/localops/terminal/sessions",
        payload ?? {},
      ),
  });
}

export function useKillLocalOpsTerminalSession() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) => apiPost<{ ok: boolean; session_id: string }>(`/api/localops/terminal/sessions/${sessionId}/kill`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["localops", "terminal", "active"] }),
  });
}

export function useLocalOpsAgentPacks() {
  return useQuery({
    queryKey: ["localops", "agents", "packs"],
    queryFn: () => apiGet<{ agents: LocalOpsAgentPack[] }>("/api/localops/agents/packs").then((data) => data.agents ?? []),
    staleTime: 120_000,
  });
}

export function useLocalOpsAgentSessions() {
  return useQuery({
    queryKey: ["localops", "agents", "sessions"],
    queryFn: () =>
      apiGet<{ sessions: LocalOpsAgentSession[] }>("/api/localops/agents/sessions").then((data) => data.sessions ?? []),
    refetchInterval: 8_000,
  });
}

export function useCreateLocalOpsAgentSession() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: { agent_slug: string; title?: string; seed_markdown?: string; agent_name?: string; workspace_root?: string; codex_model?: string }) =>
      apiPost<LocalOpsAgentSession>("/api/localops/agents/sessions", payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ["localops", "agents", "sessions"] }),
  });
}

export function useUpdateLocalOpsAgentSession() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      session_id: string;
      name?: string;
      title?: string;
      codex_model?: string;
      input_file?: string;
      output_file?: string;
      state_file?: string;
      memory_file?: string;
      notes_file?: string;
    }) => apiPut<LocalOpsAgentSession>(`/api/localops/agents/sessions/${payload.session_id}`, payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ["localops", "agents", "sessions"] }),
  });
}

export function useUpsertLocalOpsAgentPack() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: { slug: string; title?: string; instructions: string; tooling?: string; skill_md?: string }) =>
      apiPost<LocalOpsAgentPack>("/api/localops/agents/packs", payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ["localops", "agents", "packs"] }),
  });
}

export function useRunLocalOpsAgentSession() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: { session_id: string; task: string; sandbox_mode?: string; timeout_s?: number }) =>
      apiPost<{ session: LocalOpsAgentSession; result: Record<string, unknown> }>(
        `/api/localops/agents/sessions/${payload.session_id}/run`,
        { task: payload.task, sandbox_mode: payload.sandbox_mode ?? "workspace-write", timeout_s: payload.timeout_s ?? 600 },
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: ["localops", "agents", "sessions"] }),
  });
}

export function useLocalOpsAgentSessionFile(sessionId: string, fileKey: string, enabled = true) {
  return useQuery({
    queryKey: ["localops", "agents", "session-file", sessionId, fileKey],
    queryFn: () =>
      apiGet<LocalOpsAgentSessionFile>(`/api/localops/agents/sessions/${sessionId}/files/${encodeURIComponent(fileKey)}`),
    enabled: Boolean(sessionId && fileKey && enabled),
  });
}

export function useSaveLocalOpsAgentSessionFile() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ sessionId, fileKey, content }: { sessionId: string; fileKey: string; content: string }) =>
      apiPut<{ saved: boolean; bytes: number }>(`/api/localops/agents/sessions/${sessionId}/files/${encodeURIComponent(fileKey)}`, { content }),
    onSuccess: (_data, vars) => {
      client.invalidateQueries({ queryKey: ["localops", "agents", "session-file", vars.sessionId, vars.fileKey] });
      client.invalidateQueries({ queryKey: ["localops", "agents", "sessions"] });
    },
  });
}

// ViralVideo
export function useViralVideoOverview() {
  return useQuery({
    queryKey: ["viralvideo", "overview"],
    queryFn: () => apiGet<ViralVideoOverview>("/api/viralvideo/overview"),
    refetchInterval: 10_000,
  });
}

export function useViralVideoScripts(status?: string, ideavaultItemId?: string) {
  return useQuery({
    queryKey: ["viralvideo", "scripts", status ?? "", ideavaultItemId ?? ""],
    queryFn: () => {
      const q = new URLSearchParams();
      if (status) q.set("status", status);
      if (ideavaultItemId) q.set("ideavault_item_id", ideavaultItemId);
      const suffix = q.toString() ? `?${q.toString()}` : "";
      return apiGet<ViralVideoScript[]>(`/api/viralvideo/scripts${suffix}`);
    },
    refetchInterval: 8_000,
  });
}

export function useGenerateViralVideoScript() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      ideavault_item_id: string;
      channel_profile_id?: string;
      generation_params?: Record<string, unknown>;
      length_seconds?: number;
      style_preset?: string;
      tone?: string;
      voice?: string;
      research_depth?: string;
      hook_strength?: string;
      cta_style?: string;
      visual_density?: string;
      slide_count?: number;
      max_text_per_slide?: number;
      upload_enabled?: boolean;
      include_sources?: Record<string, boolean>;
      compliance?: Record<string, boolean>;
      style_overrides?: Record<string, unknown>;
    }) => apiPost<ViralVideoScript>(`/api/ideavault/${payload.ideavault_item_id}/viralvideo/generate`, payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["viralvideo", "scripts"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "overview"] });
    },
  });
}

export function useSendIdeaVaultToViralVideoFuture() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      ideavault_item_id: string;
      script_id?: string;
      channel_profile_id?: string;
      generation_params?: Record<string, unknown>;
    }) => apiPost<ViralVideoScript>(`/api/ideavault/${payload.ideavault_item_id}/viralvideo/send-to-future`, payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["viralvideo", "scripts"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "overview"] });
    },
  });
}

export function useSetViralVideoScriptFuture() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (scriptId: string) => apiPost<ViralVideoScript>(`/api/viralvideo/scripts/${scriptId}/future`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["viralvideo", "scripts"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "overview"] });
    },
  });
}

export function useSetViralVideoScriptQueue() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (scriptId: string) => apiPost<ViralVideoScript>(`/api/viralvideo/scripts/${scriptId}/queue`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["viralvideo", "scripts"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "overview"] });
    },
  });
}

export function useDeleteViralVideoScript() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ scriptId, cascade = false }: { scriptId: string; cascade?: boolean }) =>
      apiDelete<{ ok: boolean }>(`/api/viralvideo/scripts/${scriptId}${cascade ? "?cascade=true" : ""}`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["viralvideo", "scripts"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "runs"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "overview"] });
    },
  });
}

export function usePatchViralVideoScript() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ scriptId, payload }: { scriptId: string; payload: Record<string, unknown> }) =>
      apiPatch<ViralVideoScript>(`/api/viralvideo/scripts/${scriptId}`, payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["viralvideo", "scripts"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "runs"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "overview"] });
    },
  });
}

export function useStartViralVideoScript() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (scriptId: string) => apiPost<ViralVideoRun>(`/api/viralvideo/scripts/${scriptId}/start`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["viralvideo", "runs"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "scripts"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "overview"] });
    },
  });
}

export function useStartNextViralVideoQueue() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<{ ok: boolean; run?: ViralVideoRun }>("/api/viralvideo/queue/start-next"),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["viralvideo", "runs"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "scripts"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "overview"] });
    },
  });
}

export function useViralVideoRuns() {
  return useQuery({
    queryKey: ["viralvideo", "runs"],
    queryFn: () => apiGet<ViralVideoRun[]>("/api/viralvideo/runs"),
    refetchInterval: 4_000,
  });
}

export function useViralVideoRun(runId: string | null) {
  return useQuery({
    queryKey: ["viralvideo", "run", runId],
    queryFn: () => apiGet<ViralVideoRun>(`/api/viralvideo/runs/${runId}`),
    enabled: Boolean(runId),
    refetchInterval: runId ? 3_000 : false,
  });
}

export function useCancelViralVideoRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => apiPost<ViralVideoRun>(`/api/viralvideo/runs/${runId}/cancel`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["viralvideo", "runs"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "scripts"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "overview"] });
    },
  });
}

export function useDeleteViralVideoRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ runId, deleteFiles = true }: { runId: string; deleteFiles?: boolean }) =>
      apiDelete<{ ok: boolean }>(`/api/viralvideo/runs/${runId}?delete_files=${deleteFiles ? "true" : "false"}`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["viralvideo", "runs"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "scripts"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "overview"] });
    },
  });
}

export function useViralVideoSettings() {
  return useQuery({
    queryKey: ["viralvideo", "settings"],
    queryFn: () => apiGet<Record<string, unknown>>("/api/viralvideo/settings"),
  });
}

export function useUpdateViralVideoSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) => apiPut<Record<string, unknown>>("/api/viralvideo/settings", payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ["viralvideo", "settings"] }),
  });
}

export function useViralVideoAutomationSettings() {
  return useQuery({
    queryKey: ["viralvideo", "automation-settings"],
    queryFn: () => apiGet<ViralVideoAutomationSettings>("/api/viralvideo/automation/settings"),
  });
}

export function useUpdateViralVideoAutomationSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<ViralVideoAutomationSettings>) =>
      apiPut<ViralVideoAutomationSettings>("/api/viralvideo/automation/settings", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["viralvideo", "automation-settings"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "insights-summary"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "insights-plan"] });
    },
  });
}

export function useRunViralVideoAutomationNow() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<Record<string, unknown>>("/api/viralvideo/automation/run-now"),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["viralvideo", "runs"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "scripts"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "overview"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "insights-summary"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "insights-posts"] });
    },
  });
}

export function useAnalyzeViralVideoNow() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (dayKey?: string | null) =>
      apiPost<Record<string, unknown>>("/api/viralvideo/automation/analyze-now", dayKey ? { day_key: dayKey } : {}),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["viralvideo", "insights-summary"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "insights-days"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "insights-plan"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "insights-posts"] });
    },
  });
}

export function useViralVideoInsightsSummary() {
  return useQuery({
    queryKey: ["viralvideo", "insights-summary"],
    queryFn: () => apiGet<ViralVideoInsightsSummary>("/api/viralvideo/insights/summary"),
    refetchInterval: 20_000,
  });
}

export function useViralVideoInsightDays(limit = 30) {
  return useQuery({
    queryKey: ["viralvideo", "insights-days", limit],
    queryFn: () => apiGet<ViralVideoInsightDay[]>(`/api/viralvideo/insights/days?limit=${Math.max(1, Math.min(limit, 180))}`),
    refetchInterval: 30_000,
  });
}

export function useViralVideoInsightPosts(dayKey?: string | null) {
  return useQuery({
    queryKey: ["viralvideo", "insights-posts", dayKey ?? ""],
    queryFn: () => {
      const qs = dayKey ? `?day=${encodeURIComponent(dayKey)}` : "";
      return apiGet<ViralVideoInsightPost[]>(`/api/viralvideo/insights/posts${qs}`);
    },
    refetchInterval: 30_000,
  });
}

export function useViralVideoInsightsPlan() {
  return useQuery({
    queryKey: ["viralvideo", "insights-plan"],
    queryFn: () => apiGet<Record<string, unknown>>("/api/viralvideo/insights/plan"),
    refetchInterval: 30_000,
  });
}

export function useViralVideoChannelProfiles() {
  return useQuery({
    queryKey: ["viralvideo", "channel-profiles"],
    queryFn: () => apiGet<ViralVideoChannelProfile[]>("/api/viralvideo/channel-profiles"),
    refetchInterval: 30_000,
  });
}

export function useCreateViralVideoChannelProfile() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      name: string;
      creator_type: "vidmaker" | "slidemaker";
      creator_repo_path?: string;
      upload_profile_id: string;
      platform?: string;
      defaults?: Record<string, unknown>;
      enabled?: boolean;
    }) => apiPost<ViralVideoChannelProfile>("/api/viralvideo/channel-profiles", payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ["viralvideo", "channel-profiles"] }),
  });
}

export function usePatchViralVideoChannelProfile() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ profileId, payload }: { profileId: string; payload: Record<string, unknown> }) =>
      apiPatch<ViralVideoChannelProfile>(`/api/viralvideo/channel-profiles/${profileId}`, payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ["viralvideo", "channel-profiles"] }),
  });
}

export function useDeleteViralVideoChannelProfile() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (profileId: string) => apiDelete<{ ok: boolean }>(`/api/viralvideo/channel-profiles/${profileId}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["viralvideo", "channel-profiles"] }),
  });
}

export function useSyncViralVideoChannelProfiles() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiPost<{ created: string[]; updated: string[]; found_repos: string[]; count: number }>(
        "/api/viralvideo/channel-profiles/sync-creators",
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: ["viralvideo", "channel-profiles"] }),
  });
}

export function useAiVideoFactoryUploadOptions() {
  return useQuery({
    queryKey: ["aivideofactory", "upload-options"],
    queryFn: () => apiGet<AiVideoFactoryUploadOption[]>("/api/aivideofactory/upload-options"),
    staleTime: 120_000,
  });
}

// ViralCreator
export function useViralCreatorState() {
  return useQuery({
    queryKey: ["viralcreator", "state"],
    queryFn: () => apiGet<ViralCreatorState>("/api/viralcreator/state"),
    refetchInterval: 15_000,
  });
}

export function useViralCreatorChannels() {
  return useQuery({
    queryKey: ["viralcreator", "channels"],
    queryFn: () => apiGet<ViralCreatorChannelOverview[]>("/api/viralcreator/channels"),
    refetchInterval: 20_000,
  });
}

export function useViralCreatorRuns(limit = 100) {
  return useQuery({
    queryKey: ["viralcreator", "runs", limit],
    queryFn: () => apiGet<ViralCreatorOrchestrationRun[]>(`/api/viralcreator/runs?limit=${Math.max(1, Math.min(limit, 500))}`),
    refetchInterval: 5_000,
  });
}

export function useViralCreatorInbox(limit = 120) {
  return useQuery({
    queryKey: ["viralcreator", "inbox", limit],
    queryFn: () => apiGet<ViralCreatorInboxItem[]>(`/api/viralcreator/inbox?limit=${Math.max(1, Math.min(limit, 500))}`),
    refetchInterval: 10_000,
  });
}

export function useCreateViralCreatorInboxItem() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) => apiPost<ViralCreatorInboxItem>("/api/viralcreator/inbox", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["viralcreator", "inbox"] });
      client.invalidateQueries({ queryKey: ["viralcreator", "state"] });
    },
  });
}

export function useRunViralCreatorResearch() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) => apiPost<ViralCreatorResearchResult>("/api/viralcreator/research/run", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["viralcreator", "state"] });
      client.invalidateQueries({ queryKey: ["viralcreator", "inbox"] });
    },
  });
}

export function useGenerateViralCreatorCreativeDraft() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) => apiPost<ViralCreatorCreativeDraft>("/api/viralcreator/creative/generate", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["viralcreator", "state"] });
      client.invalidateQueries({ queryKey: ["viralcreator", "runs"] });
    },
  });
}

export function useIterateViralCreatorRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => apiPost<Record<string, unknown>>(`/api/viralcreator/iterate/from-run/${encodeURIComponent(runId)}`, {}),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["viralcreator", "inbox"] });
      client.invalidateQueries({ queryKey: ["viralcreator", "state"] });
    },
  });
}

export function useStartViralCreatorRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) => apiPost<Record<string, unknown>>("/api/viralcreator/runs", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["viralcreator", "state"] });
      client.invalidateQueries({ queryKey: ["viralcreator", "runs"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "scripts"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "runs"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "overview"] });
    },
  });
}

export function useViralCreatorAutonomousState() {
  return useQuery({
    queryKey: ["viralcreator", "autonomous", "state"],
    queryFn: () => apiGet<ViralCreatorAutonomousState>("/api/viralcreator/autonomous/state"),
    refetchInterval: 15_000,
  });
}

export function useViralCreatorAutonomousProfiles() {
  return useQuery({
    queryKey: ["viralcreator", "autonomous", "profiles"],
    queryFn: () => apiGet<ViralCreatorAutonomousProfile[]>("/api/viralcreator/autonomous/profiles"),
    refetchInterval: 20_000,
  });
}

export function useViralCreatorAutonomousHistory(limit = 40) {
  return useQuery({
    queryKey: ["viralcreator", "autonomous", "history", limit],
    queryFn: () => apiGet<ViralCreatorAutonomousHistoryItem[]>(`/api/viralcreator/autonomous/history?limit=${Math.max(1, Math.min(limit, 200))}`),
    refetchInterval: 15_000,
  });
}

export function useCreateViralCreatorAutonomousProfile() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) => apiPost<ViralCreatorAutonomousProfile>("/api/viralcreator/autonomous/profiles", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["viralcreator", "state"] });
      client.invalidateQueries({ queryKey: ["viralcreator", "autonomous"] });
    },
  });
}

export function useUpdateViralCreatorAutonomousProfile() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ profileId, payload }: { profileId: string; payload: Record<string, unknown> }) =>
      apiPatch<ViralCreatorAutonomousProfile>(`/api/viralcreator/autonomous/profiles/${encodeURIComponent(profileId)}`, payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["viralcreator", "state"] });
      client.invalidateQueries({ queryKey: ["viralcreator", "autonomous"] });
    },
  });
}

export function useRunViralCreatorAutonomousProfileNow() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (profileId: string) => apiPost<Record<string, unknown>>(`/api/viralcreator/autonomous/profiles/${encodeURIComponent(profileId)}/run-now`, {}),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["viralcreator", "state"] });
      client.invalidateQueries({ queryKey: ["viralcreator", "runs"] });
      client.invalidateQueries({ queryKey: ["viralcreator", "autonomous"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "scripts"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "runs"] });
      client.invalidateQueries({ queryKey: ["viralvideo", "overview"] });
    },
  });
}

export function useViralCreatorDailyReview() {
  return useQuery({
    queryKey: ["viralcreator", "daily-review"],
    queryFn: () => apiGet<Record<string, unknown>>("/api/viralcreator/review/daily"),
    refetchInterval: 20_000,
  });
}

export function useViralCreatorWeeklyReview() {
  return useQuery({
    queryKey: ["viralcreator", "weekly-review"],
    queryFn: () => apiGet<Record<string, unknown>>("/api/viralcreator/review/weekly"),
    refetchInterval: 30_000,
  });
}

export function useFactoryOverview() {
  return useQuery({
    queryKey: ["factory", "overview"],
    queryFn: (): Promise<FactoryOverviewPayload> => getFactoryOverview(),
    refetchInterval: 20_000,
  });
}

export function useFactoryRuns(params: { status?: string; search?: string } = {}) {
  return useQuery({
    queryKey: ["factory", "runs", params.status ?? "", params.search ?? ""],
    queryFn: (): Promise<FactoryRunRow[]> => getFactoryRuns({ status: params.status, search: params.search, limit: 1000 }),
    refetchInterval: 10_000,
  });
}

export function useFactoryRunDetail(runId: string | null) {
  return useQuery({
    queryKey: ["factory", "run-detail", runId],
    queryFn: (): Promise<FactoryRunDetail> => getFactoryRunDetail(String(runId)),
    enabled: Boolean(runId),
    refetchInterval: (query) => {
      const status = String(query.state.data?.run?.status ?? "").toLowerCase();
      if (!runId) return false;
      return status === "running" || status === "queued" ? 5_000 : 20_000;
    },
  });
}

export function useFactoryInbox(params: { runId?: string; sender?: string; recipient?: string } = {}) {
  return useQuery({
    queryKey: ["factory", "inbox", params.runId ?? "", params.sender ?? "", params.recipient ?? ""],
    queryFn: (): Promise<FactoryInboxMessage[]> =>
      getFactoryInbox({ run_id: params.runId, sender: params.sender, recipient: params.recipient, limit: 250 }),
    refetchInterval: 15_000,
  });
}

export function useFactoryIssues(params: { runId?: string; severity?: string; status?: string } = {}) {
  return useQuery({
    queryKey: ["factory", "issues", params.runId ?? "", params.severity ?? "", params.status ?? ""],
    queryFn: (): Promise<FactoryIssue[]> => getFactoryIssues({ run_id: params.runId, severity: params.severity, status: params.status, limit: 250 }),
    refetchInterval: 15_000,
  });
}

export function useFactoryArtifacts(params: { kind?: string; runId?: string } = {}) {
  return useQuery({
    queryKey: ["factory", "artifacts", params.kind ?? "", params.runId ?? ""],
    queryFn: (): Promise<FactoryArtifact[]> => getFactoryArtifacts({ kind: params.kind, run_id: params.runId, limit: 250 }),
    refetchInterval: 20_000,
  });
}

export function useFactoryMetricsSummary() {
  return useQuery({
    queryKey: ["factory", "metrics"],
    queryFn: (): Promise<FactoryMetricsSummary> => getFactoryMetricsSummary(),
    refetchInterval: 25_000,
  });
}

export function useFactoryTemplates() {
  return useQuery({
    queryKey: ["factory", "templates"],
    queryFn: (): Promise<RunTemplate[]> => getFactoryTemplates(),
    staleTime: 60_000,
  });
}

export function useFactoryPromptPresets() {
  return useQuery({
    queryKey: ["factory", "prompt-presets"],
    queryFn: (): Promise<PromptPreset[]> => getFactoryPromptPresets(),
    staleTime: 60_000,
  });
}

export function useFactoryWorkspaces() {
  return useQuery({
    queryKey: ["factory", "workspaces"],
    queryFn: (): Promise<Workspace[]> => getFactoryWorkspaces(),
    staleTime: 60_000,
  });
}

export function useCreateFactoryWorkspace() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: FactoryWorkspaceCreateRequest): Promise<Workspace> => createFactoryWorkspace(payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["factory", "workspaces"] });
    },
  });
}

export function useBootstrapFactoryWorkspace() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: FactoryWorkspaceBootstrapRequest): Promise<FactoryWorkspaceBootstrapResponse> =>
      bootstrapFactoryWorkspace(payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["factory", "workspaces"] });
    },
  });
}

export function useFactoryAgents() {
  return useQuery({
    queryKey: ["factory", "agents"],
    queryFn: (): Promise<FactoryAgent[]> => getFactoryAgents(),
    staleTime: 60_000,
  });
}

export function useFactoryModes() {
  return useQuery({
    queryKey: ["factory", "modes"],
    queryFn: (): Promise<FactoryMode[]> => getFactoryModes(),
    staleTime: 60_000,
  });
}

export function useFactoryHealthChecks() {
  return useQuery({
    queryKey: ["factory", "health-checks"],
    queryFn: (): Promise<FactoryHealthStatus[]> => getFactoryHealthChecks(),
    refetchInterval: 20_000,
  });
}

export function useFactoryApiBase() {
  return getFactoryApiBase();
}

export function useComposeFactoryRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: FactoryComposeRunRequest): Promise<FactoryComposeRunResponse> => composeFactoryRun(payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["factory", "overview"] });
      client.invalidateQueries({ queryKey: ["factory", "runs"] });
    },
  });
}

export function useStartFactoryRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (runId: string): Promise<FactoryRun> => startFactoryRun(runId),
    onSuccess: (_, runId) => {
      client.invalidateQueries({ queryKey: ["factory", "overview"] });
      client.invalidateQueries({ queryKey: ["factory", "runs"] });
      client.invalidateQueries({ queryKey: ["factory", "run-detail", runId] });
    },
  });
}

export function useStartFactoryPreview() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: FactoryPreviewStartRequest): Promise<FactoryPreviewStartResponse> => startFactoryPreview(payload),
    onSuccess: (_, payload) => {
      if (payload.run_id) client.invalidateQueries({ queryKey: ["factory", "run-detail", payload.run_id] });
    },
  });
}

export function useStopFactoryPreview() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: FactoryPreviewStopRequest): Promise<FactoryPreviewStopResponse> => stopFactoryPreview(payload),
    onSuccess: (_, payload) => {
      if (payload.run_id) client.invalidateQueries({ queryKey: ["factory", "run-detail", payload.run_id] });
    },
  });
}

export function useSkilledAgentsHealth() {
  return useQuery({
    queryKey: ["skilled-agents", "health"],
    queryFn: () => apiGet<SkilledAgentsHealth>("/api/skilled-agents/health"),
    refetchInterval: 20_000,
  });
}

export function useSkilledSkills() {
  return useQuery({
    queryKey: ["skilled-agents", "skills"],
    queryFn: () => apiGet<SkilledSkillSummary[]>("/api/skilled-agents/skills"),
    staleTime: 60_000,
  });
}

export function useCreateSkilledSkill() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: SkilledSkillCreateRequest) =>
      apiPost<SkilledSkillDetail>("/api/skilled-agents/skills", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["skilled-agents", "skills"] });
    },
  });
}

export function useSkilledTemplates() {
  return useQuery({
    queryKey: ["skilled-agents", "templates"],
    queryFn: () => apiGet<SkilledAgentTemplateSummary[]>("/api/skilled-agents/templates"),
    staleTime: 60_000,
  });
}

export function useSkilledTemplate(templateId: string | null) {
  return useQuery({
    queryKey: ["skilled-agents", "templates", templateId],
    queryFn: () => apiGet<SkilledAgentTemplateDetail>(`/api/skilled-agents/templates/${encodeURIComponent(String(templateId))}`),
    enabled: Boolean(templateId),
    staleTime: 60_000,
  });
}

export function useSkilledStarterTemplates(topOnly = false) {
  return useQuery({
    queryKey: ["skilled-agents", "starter-templates", topOnly ? "top" : "all"],
    queryFn: () => apiGet<SkilledStarterTemplate[]>(`/api/skilled-agents/starter-templates${topOnly ? "?top_only=true" : ""}`),
    staleTime: 30_000,
  });
}

export function useSkilledStarterTemplate(slug: string | null) {
  return useQuery({
    queryKey: ["skilled-agents", "starter-templates", slug],
    queryFn: () => apiGet<SkilledStarterTemplate>(`/api/skilled-agents/starter-templates/${encodeURIComponent(String(slug))}`),
    enabled: Boolean(slug),
    staleTime: 30_000,
  });
}

export function useImportSkilledStarterTemplatesBatch() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (zipPaths: string[]) =>
      apiPost<{ count: number; results: Array<Record<string, unknown>> }>("/api/skilled-agents/starter-templates/import-batch", { zip_paths: zipPaths }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["skilled-agents", "starter-templates"] }),
  });
}

export function useImportAgencyStarterTemplates() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: { root_path: string; purge_first?: boolean; seed_top_agents?: boolean }) =>
      apiPost<Record<string, unknown>>("/api/skilled-agents/starter-templates/import-agency", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["skilled-agents", "starter-templates"] });
      client.invalidateQueries({ queryKey: ["skilled-agents", "health"] });
    },
  });
}

export function useClearSkilledStarterTemplates() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiDelete<Record<string, unknown>>("/api/skilled-agents/starter-templates"),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["skilled-agents", "starter-templates"] });
      client.invalidateQueries({ queryKey: ["skilled-agents", "health"] });
    },
  });
}

export function useSkilledSkillDetail(skillId: string | null) {
  return useQuery({
    queryKey: ["skilled-agents", "skills", skillId],
    queryFn: () => apiGet<SkilledSkillDetail>(`/api/skilled-agents/skills/${encodeURIComponent(String(skillId))}`),
    enabled: Boolean(skillId),
    staleTime: 60_000,
  });
}

export function useSkilledAgents() {
  return useQuery({
    queryKey: ["skilled-agents", "agents"],
    queryFn: () => apiGet<SkilledAgent[]>("/api/skilled-agents/agents"),
    refetchInterval: 10_000,
  });
}

export function useDeleteSkilledAgents() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiDelete<Record<string, unknown>>("/api/skilled-agents/agents"),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["skilled-agents", "agents"] });
      client.invalidateQueries({ queryKey: ["skilled-agents", "health"] });
    },
  });
}

export function useSkilledAgent(agentId: string | null) {
  return useQuery({
    queryKey: ["skilled-agents", "agent", agentId],
    queryFn: () => apiGet<SkilledAgent>(`/api/skilled-agents/agents/${encodeURIComponent(String(agentId))}`),
    enabled: Boolean(agentId),
    refetchInterval: 8_000,
  });
}

export function useCreateSkilledAgent() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: SkilledAgentCreateRequest) => apiPost<SkilledAgent>("/api/skilled-agents/agents", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["skilled-agents", "agents"] });
      client.invalidateQueries({ queryKey: ["skilled-agents", "health"] });
    },
  });
}

export function useCreateSkilledAgentFromTemplate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      apiPost<SkilledAgent>("/api/skilled-agents/agents/from-template", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["skilled-agents", "agents"] });
      client.invalidateQueries({ queryKey: ["skilled-agents", "health"] });
    },
  });
}

export function usePreviewSkilledAgentFromTemplate() {
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      apiPost<{ template_slug: string; preview: SkilledTemplatePreview }>("/api/skilled-agents/agents/preview-from-template", payload),
  });
}

export function useUpdateSkilledAgent() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, payload }: { agentId: string; payload: SkilledAgentUpdateRequest }) =>
      apiPatch<SkilledAgent>(`/api/skilled-agents/agents/${encodeURIComponent(agentId)}`, payload),
    onSuccess: (_data, vars) => {
      client.invalidateQueries({ queryKey: ["skilled-agents", "agents"] });
      client.invalidateQueries({ queryKey: ["skilled-agents", "agent", vars.agentId] });
    },
  });
}

export function useAttachSkilledSkill() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, skillId }: { agentId: string; skillId: string }) =>
      apiPost(`/api/skilled-agents/agents/${encodeURIComponent(agentId)}/skills`, { skill_id: skillId }),
    onSuccess: (_data, vars) => {
      client.invalidateQueries({ queryKey: ["skilled-agents", "agents"] });
      client.invalidateQueries({ queryKey: ["skilled-agents", "agent", vars.agentId] });
    },
  });
}

export function useDetachSkilledSkill() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, skillId }: { agentId: string; skillId: string }) =>
      apiDelete(`/api/skilled-agents/agents/${encodeURIComponent(agentId)}/skills/${encodeURIComponent(skillId)}`),
    onSuccess: (_data, vars) => {
      client.invalidateQueries({ queryKey: ["skilled-agents", "agents"] });
      client.invalidateQueries({ queryKey: ["skilled-agents", "agent", vars.agentId] });
    },
  });
}

function useSkilledAction(action: "prepare" | "deploy" | "run" | "stop") {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, payload }: { agentId: string; payload?: SkilledAgentRunRequest | Record<string, unknown> }) =>
      apiPost<SkilledAgentActionResponse>(`/api/skilled-agents/agents/${encodeURIComponent(agentId)}/${action}`, payload ?? {}),
    onSuccess: (_data, vars) => {
      client.invalidateQueries({ queryKey: ["skilled-agents", "agents"] });
      client.invalidateQueries({ queryKey: ["skilled-agents", "agent", vars.agentId] });
      client.invalidateQueries({ queryKey: ["skilled-agents", "status", vars.agentId] });
      client.invalidateQueries({ queryKey: ["skilled-agents", "logs", vars.agentId] });
      client.invalidateQueries({ queryKey: ["skilled-agents", "workspace", vars.agentId] });
      client.invalidateQueries({ queryKey: ["skilled-agents", "manifest", vars.agentId] });
    },
  });
}

export function useSkilledPrepareAgent() {
  return useSkilledAction("prepare");
}

export function useSkilledDeployAgent() {
  return useSkilledAction("deploy");
}

export function useSkilledRunAgent() {
  return useSkilledAction("run");
}

export function useSkilledStopAgent() {
  return useSkilledAction("stop");
}

export function useSkilledAgentStatus(agentId: string | null) {
  return useQuery({
    queryKey: ["skilled-agents", "status", agentId],
    queryFn: () => apiGet<SkilledAgentStatus>(`/api/skilled-agents/agents/${encodeURIComponent(String(agentId))}/status`),
    enabled: Boolean(agentId),
    refetchInterval: 5_000,
  });
}

export function useSkilledAgentLogs(agentId: string | null, limit = 300) {
  return useQuery({
    queryKey: ["skilled-agents", "logs", agentId, limit],
    queryFn: () =>
      apiGet<SkilledAgentLogsResponse>(
        `/api/skilled-agents/agents/${encodeURIComponent(String(agentId))}/logs?limit=${limit}`,
      ),
    enabled: Boolean(agentId),
    refetchInterval: 5_000,
  });
}

export function useSkilledAgentWorkspace(agentId: string | null) {
  return useQuery({
    queryKey: ["skilled-agents", "workspace", agentId],
    queryFn: () =>
      apiGet<SkilledAgentWorkspaceResponse>(`/api/skilled-agents/agents/${encodeURIComponent(String(agentId))}/workspace`),
    enabled: Boolean(agentId),
    refetchInterval: 10_000,
  });
}

export function useSkilledAgentManifest(agentId: string | null) {
  return useQuery({
    queryKey: ["skilled-agents", "manifest", agentId],
    queryFn: () =>
      apiGet<SkilledAgentManifestResponse>(`/api/skilled-agents/agents/${encodeURIComponent(String(agentId))}/manifest`),
    enabled: Boolean(agentId),
    refetchInterval: 10_000,
  });
}

export function useSkilledAgentSnapshots(agentId: string | null) {
  return useQuery({
    queryKey: ["skilled-agents", "snapshots", agentId],
    queryFn: () =>
      apiGet<SkilledAgentSnapshotsResponse>(`/api/skilled-agents/agents/${encodeURIComponent(String(agentId))}/snapshots`),
    enabled: Boolean(agentId),
    refetchInterval: 8_000,
  });
}

export function useSkilledAgentLatestSnapshot(agentId: string | null) {
  return useQuery({
    queryKey: ["skilled-agents", "latest-snapshot", agentId],
    queryFn: () =>
      apiGet<SkilledAgentLatestSnapshotResponse>(`/api/skilled-agents/agents/${encodeURIComponent(String(agentId))}/latest-snapshot`),
    enabled: Boolean(agentId),
    refetchInterval: 8_000,
  });
}

function useSkilledCheckAction(action: "run-validation" | "run-smoke-test") {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId }: { agentId: string }) =>
      apiPost<Record<string, unknown>>(`/api/skilled-agents/agents/${encodeURIComponent(agentId)}/${action}`, {}),
    onSuccess: (_data, vars) => {
      client.invalidateQueries({ queryKey: ["skilled-agents", "agent", vars.agentId] });
      client.invalidateQueries({ queryKey: ["skilled-agents", "logs", vars.agentId] });
      client.invalidateQueries({ queryKey: ["skilled-agents", "latest-snapshot", vars.agentId] });
    },
  });
}

export function useSkilledRunValidation() {
  return useSkilledCheckAction("run-validation");
}

export function useSkilledRunSmokeTest() {
  return useSkilledCheckAction("run-smoke-test");
}

export function useMemoryHealth() {
  return useQuery({
    queryKey: ["memory", "health"],
    queryFn: () => apiGet<MemoryHealth>("/api/memory/health"),
    refetchInterval: 10_000,
  });
}

export function useMemorySettings() {
  return useQuery({
    queryKey: ["memory", "settings"],
    queryFn: () => apiGet<MemorySettings>("/api/memory/settings"),
  });
}

export function useMemorySearch(payload: {
  query: string;
  node_id?: string;
  repo_path?: string;
  limit?: number;
  include_docs?: boolean;
  include_knowledge?: boolean;
  rerank?: boolean;
}) {
  return useMutation({
    mutationFn: () => apiPost<MemorySearchResponse>("/api/memory/search", payload),
  });
}

export function useMemoryBrief() {
  return useMutation({
    mutationFn: (payload: {
      query?: string;
      node_id?: string;
      repo_path?: string;
      max_chars?: number;
      rerank?: boolean;
    }) => apiPost<MemoryBriefResponse>("/api/memory/brief", payload),
  });
}

export function useMemorySessions(params?: { q?: string; limit?: number }) {
  const qs = new URLSearchParams();
  if (params?.q) qs.set("q", params.q);
  qs.set("limit", String(params?.limit ?? 100));
  return useQuery({
    queryKey: ["memory", "sessions", params ?? {}],
    queryFn: () => apiGet<{ items: Record<string, unknown>[] }>(`/api/memory/sessions?${qs.toString()}`),
    refetchInterval: 10_000,
  });
}

export function useMemoryCandidates(params?: { q?: string; limit?: number }) {
  const qs = new URLSearchParams();
  if (params?.q) qs.set("q", params.q);
  qs.set("limit", String(params?.limit ?? 100));
  return useQuery({
    queryKey: ["memory", "candidates", params ?? {}],
    queryFn: () => apiGet<{ items: Record<string, unknown>[] }>(`/api/memory/candidates?${qs.toString()}`),
    refetchInterval: 10_000,
  });
}

export function useMemoryRelationships(params?: { q?: string; limit?: number }) {
  const qs = new URLSearchParams();
  if (params?.q) qs.set("q", params.q);
  qs.set("limit", String(params?.limit ?? 100));
  return useQuery({
    queryKey: ["memory", "relationships", params ?? {}],
    queryFn: () => apiGet<{ items: Record<string, unknown>[] }>(`/api/memory/relationships?${qs.toString()}`),
    refetchInterval: 10_000,
  });
}

export function useMemoryCompact() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload?: { candidate?: Record<string, unknown>; promote?: boolean; limit?: number }) =>
      apiPost<MemoryCompactResponse>("/api/memory/compact", payload ?? {}),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["memory"] });
    },
  });
}

export function useDiscordSettings() {
  return useQuery({
    queryKey: ["discord", "settings"],
    queryFn: () => apiGet<DiscordSettings>("/api/discord/settings"),
  });
}

export function useSaveDiscordSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) => apiPost<DiscordSettings>("/api/discord/settings", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["discord"] });
    },
  });
}

export function useDiscordStatus() {
  return useQuery({
    queryKey: ["discord", "status"],
    queryFn: () => apiGet<DiscordStatusPayload>("/api/discord/status"),
    refetchInterval: 12_000,
  });
}

export function useDiscordTestConnectivity() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: { include_bridge?: boolean; include_redis?: boolean; include_memory?: boolean }) =>
      apiPost<Record<string, unknown>>("/api/discord/test", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["discord", "status"] });
    },
  });
}

export function useDiscordReindexMemory() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: { dry_run?: boolean }) => apiPost<Record<string, unknown>>("/api/discord/reindex-memory", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["discord", "status"] });
    },
  });
}

export function useDiscordMemoryAppend() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: { note: string; kind?: string; relevance?: number; dry_run?: boolean }) =>
      apiPost<Record<string, unknown>>("/api/discord/memory/append", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["discord", "status"] });
    },
  });
}

export function useDiscordDispatchTargets() {
  return useQuery({
    queryKey: ["discord", "dispatch-targets"],
    queryFn: () => apiGet<{ targets: DiscordDispatchTarget[]; summary: Record<string, unknown> }>("/api/discord/dispatch-targets"),
    refetchInterval: 20_000,
  });
}

export function useDiscordSessionBootstrap() {
  return useMutation({
    mutationFn: (payload: {
      user_id: string;
      guild_id?: string;
      channel_id?: string;
      model?: string;
      temperature?: number;
      metadata?: Record<string, unknown>;
    }) => apiPost<Record<string, unknown>>("/api/discord/session/bootstrap", payload),
  });
}

export function useDiscordSessionResolve() {
  return useMutation({
    mutationFn: (payload: { user_id: string; guild_id?: string; channel_id?: string }) =>
      apiPost<Record<string, unknown>>("/api/discord/session/resolve", payload),
  });
}

export function useDiscordPolicyEvaluate() {
  return useMutation({
    mutationFn: (payload: {
      action_type: string;
      target?: string;
      args?: Record<string, unknown>;
      requester?: Record<string, unknown>;
    }) => apiPost<Record<string, unknown>>("/api/discord/policy/evaluate", payload),
  });
}

export function useDiscordDispatchRequests(params?: { status?: string; limit?: number }) {
  const qs = new URLSearchParams();
  if (params?.status) qs.set("status", params.status);
  qs.set("limit", String(params?.limit ?? 100));
  return useQuery({
    queryKey: ["discord", "requests", params ?? {}],
    queryFn: () => apiGet<{ items: DiscordDispatchRequest[] }>(`/api/discord/requests?${qs.toString()}`),
    refetchInterval: 8_000,
  });
}

export function useDiscordDispatchRequestDetail(requestId: string | null) {
  return useQuery({
    queryKey: ["discord", "request", requestId],
    queryFn: () => apiGet<Record<string, unknown>>(`/api/discord/requests/${encodeURIComponent(String(requestId))}`),
    enabled: Boolean(requestId),
    refetchInterval: 8_000,
  });
}

export function useDiscordApprovals(params?: { status?: string; limit?: number }) {
  const qs = new URLSearchParams();
  if (params?.status) qs.set("status", params.status);
  qs.set("limit", String(params?.limit ?? 100));
  return useQuery({
    queryKey: ["discord", "approvals", params ?? {}],
    queryFn: () => apiGet<{ items: DiscordApprovalRequest[] }>(`/api/discord/approvals?${qs.toString()}`),
    refetchInterval: 6_000,
  });
}

export function useDiscordDispatch() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      command?: string;
      action_type?: string;
      target?: string;
      args?: Record<string, unknown>;
      prompt?: string;
      requester?: Record<string, unknown>;
      session?: Record<string, unknown>;
      metadata?: Record<string, unknown>;
    }) => apiPost<Record<string, unknown>>("/api/discord/dispatch", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["discord", "requests"] });
      client.invalidateQueries({ queryKey: ["discord", "approvals"] });
      client.invalidateQueries({ queryKey: ["discord", "status"] });
    },
  });
}

export function useDiscordApprove() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: { dispatch_request_id: string; approver_user_id: string; reason?: string; replay_token: string }) =>
      apiPost<Record<string, unknown>>("/api/discord/approve", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["discord", "requests"] });
      client.invalidateQueries({ queryKey: ["discord", "approvals"] });
      client.invalidateQueries({ queryKey: ["discord", "status"] });
    },
  });
}

export function useDiscordReject() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: { dispatch_request_id: string; approver_user_id: string; reason?: string; replay_token: string }) =>
      apiPost<Record<string, unknown>>("/api/discord/reject", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["discord", "requests"] });
      client.invalidateQueries({ queryKey: ["discord", "approvals"] });
      client.invalidateQueries({ queryKey: ["discord", "status"] });
    },
  });
}

export function useDiscordWorkers(limit = 100) {
  return useQuery({
    queryKey: ["discord", "workers", limit],
    queryFn: () => apiGet<{ items: DispatchWorkerStatus[] }>(`/api/discord/workers?limit=${limit}`),
    refetchInterval: 10_000,
  });
}

export function useDiscordAudit(auditId: string | null) {
  return useQuery({
    queryKey: ["discord", "audit", auditId],
    queryFn: () => apiGet<Record<string, unknown>>(`/api/discord/audit/${encodeURIComponent(String(auditId))}`),
    enabled: Boolean(auditId),
    refetchInterval: 8_000,
  });
}

export function useChatSessions(limit = 50) {
  return useQuery({
    queryKey: ["chat", "sessions", limit],
    queryFn: () => apiGet<ChatSessionListResponse>(`/api/chat/sessions?limit=${limit}`),
    refetchInterval: 10_000,
  });
}

export function useCreateChatSession() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      session_id?: string;
      title?: string;
      model?: string;
      provider?: string;
      source_types?: string[];
      metadata?: Record<string, unknown>;
    }) => apiPost<ChatSession>("/api/chat/sessions", payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["chat", "sessions"] });
    },
  });
}

export function useChatSession(sessionId: string | null) {
  return useQuery({
    queryKey: ["chat", "session", sessionId],
    queryFn: () => apiGet<ChatSession>(`/api/chat/sessions/${encodeURIComponent(String(sessionId))}`),
    enabled: Boolean(sessionId),
    retry: (failureCount, error) => !isNotFoundError(error) && failureCount < 2,
  });
}

export function useChatMessages(sessionId: string | null, limit = 200) {
  return useQuery({
    queryKey: ["chat", "messages", sessionId, limit],
    queryFn: () =>
      apiGet<ChatMessageListResponse>(`/api/chat/sessions/${encodeURIComponent(String(sessionId))}/messages?limit=${limit}`),
    enabled: Boolean(sessionId),
    refetchInterval: 8_000,
    retry: (failureCount, error) => !isNotFoundError(error) && failureCount < 2,
  });
}

export function useAppendChatMessage(sessionId: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      role?: string;
      source?: string;
      content: string;
      model?: string;
      provider?: string;
      metadata?: Record<string, unknown>;
      tool_payload?: Record<string, unknown> | null;
      audit_id?: string | null;
    }) => apiPost<ChatMessage>(`/api/chat/sessions/${encodeURIComponent(String(sessionId))}/messages`, payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["chat", "messages", sessionId] });
      client.invalidateQueries({ queryKey: ["chat", "session", sessionId] });
      client.invalidateQueries({ queryKey: ["chat", "sessions"] });
    },
  });
}

export function useAttachDiscordChatSession(sessionId: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: { guild_id?: string; channel_id?: string; user_id?: string; source_types?: string[] }) =>
      apiPost<ChatSession>(`/api/chat/sessions/${encodeURIComponent(String(sessionId))}/attach-discord`, payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["chat", "session", sessionId] });
      client.invalidateQueries({ queryKey: ["chat", "sessions"] });
    },
  });
}

export function useSyncChatSession(sessionId: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: { messages: Array<Record<string, unknown>> }) =>
      apiPost<{ ok: boolean; synced: number }>(`/api/chat/sessions/${encodeURIComponent(String(sessionId))}/sync`, payload),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["chat", "messages", sessionId] });
      client.invalidateQueries({ queryKey: ["chat", "session", sessionId] });
      client.invalidateQueries({ queryKey: ["chat", "sessions"] });
    },
  });
}
