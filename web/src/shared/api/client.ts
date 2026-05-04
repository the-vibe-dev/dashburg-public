function resolveApiBase(): string {
  const explicit = String(import.meta.env.VITE_API_URL ?? "").trim();
  if (explicit) return explicit.replace(/\/+$/, "");
  if (typeof window === "undefined") return "";
  const { protocol, hostname } = window.location;
  return `${protocol}//${hostname}:8321`;
}

const API_BASE = resolveApiBase();

export class ApiError extends Error {
  status: number;
  path: string;
  method: string;

  constructor(message: string, status: number, method: string, path: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.path = path;
    this.method = method;
  }
}

function buildHeaders(path: string, extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = { ...(extra ?? {}) };
  const adminToken = typeof window !== "undefined" ? window.localStorage.getItem("dashburg.remoteops.adminToken") ?? "" : "";
  const clientToken = typeof window !== "undefined" ? window.localStorage.getItem("dashburg.remoteops.clientToken") ?? "" : "";
  const localOpsToken = typeof window !== "undefined" ? window.localStorage.getItem("dashburg.localops.token") ?? "" : "";
  const isRemoteOpsPath = path.startsWith("/api/remote/");
  const isOrchestrationPath = path.startsWith("/api/orchestration/");
  const isScheduleOpsPath = path.startsWith("/api/scheduleops/");
  const isMemoryPath = path.startsWith("/api/memory/");
  const isMonitoringPath = path.startsWith("/api/monitoring/");
  const isDiscordPath = path.startsWith("/api/discord/");
  const isChatPath = path.startsWith("/api/chat/");
  const isLocalOpsPath = path.startsWith("/api/localops/");
  if ((isRemoteOpsPath || isOrchestrationPath || isScheduleOpsPath || isMemoryPath || isMonitoringPath || isDiscordPath || isChatPath) && adminToken) {
    headers["X-RemoteOps-Admin-Token"] = adminToken;
  }
  if ((isRemoteOpsPath || isOrchestrationPath || isScheduleOpsPath || isMemoryPath || isMonitoringPath || isDiscordPath || isChatPath) && clientToken) {
    headers["X-RemoteOps-Client-Token"] = clientToken;
  }
  if (isLocalOpsPath && localOpsToken) {
    headers["X-LocalOps-Token"] = localOpsToken;
  }
  return headers;
}

async function parseResponse<T>(resp: Response, method: string, path: string): Promise<T> {
  if (!resp.ok) {
    let detail = `${method} ${path} failed: ${resp.status}`;
    try {
      const body = (await resp.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (body.detail && typeof body.detail === "object") {
        detail = JSON.stringify(body.detail);
      }
    } catch {
      // ignore parse failures and keep default message
    }
    throw new ApiError(detail, resp.status, method, path);
  }
  return (await resp.json()) as T;
}

async function fetchJson<T>(method: string, path: string): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, { headers: buildHeaders(path) });
  return parseResponse<T>(resp, method, path);
}

function isVideoIdeasPath(path: string): boolean {
  return path.startsWith("/api/topic/video_ideas") || path.startsWith("/video_ideas");
}

function isVideoIdeasTopPath(path: string): boolean {
  return path.startsWith("/api/topic/video_ideas/top") || path.startsWith("/video_ideas/top");
}

function isVideoIdeasDetailPath(path: string): boolean {
  return /\/video_ideas\/[^/?#]+/.test(path);
}

function videoIdeasUnavailableShape(path: string): unknown {
  if (isVideoIdeasTopPath(path)) return { items: [] as unknown[] };
  if (isVideoIdeasDetailPath(path)) return {};
  return { video_ideas: [] as unknown[] };
}

function toVideoIdeasFallbackPath(path: string): string | null {
  if (path.startsWith("/api/topic/video_ideas")) {
    return path.replace("/api/topic/video_ideas", "/video_ideas");
  }
  return null;
}

export async function apiGet<T>(path: string): Promise<T> {
  if (isVideoIdeasPath(path)) {
    try {
      return await fetchJson<T>("GET", path);
    } catch (error) {
      const err = error as ApiError;
      if (err.status !== 404) throw error;

      const fallbackPath = toVideoIdeasFallbackPath(path);
      if (fallbackPath) {
        try {
          return await fetchJson<T>("GET", fallbackPath);
        } catch (fallbackError) {
          const fallbackErr = fallbackError as ApiError;
          if (fallbackErr.status !== 404) throw fallbackError;
        }
      }
      return videoIdeasUnavailableShape(path) as T;
    }
  }

  return fetchJson<T>("GET", path);
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: buildHeaders(path, { "Content-Type": "application/json" }),
    body: body ? JSON.stringify(body) : undefined,
  });
  return parseResponse<T>(resp, "POST", path);
}

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    method: "PUT",
    headers: buildHeaders(path, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  return parseResponse<T>(resp, "PUT", path);
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    method: "PATCH",
    headers: buildHeaders(path, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  return parseResponse<T>(resp, "PATCH", path);
}

export async function apiDelete<T>(path: string): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, { method: "DELETE", headers: buildHeaders(path) });
  return parseResponse<T>(resp, "DELETE", path);
}

export function eventsUrl(path: string): string {
  return `${API_BASE}${path}`;
}

export function websocketUrl(path: string, query?: URLSearchParams): string {
  const base = API_BASE || (typeof window !== "undefined" ? window.location.origin : "");
  const url = new URL(path, base);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  if (query && query.toString()) url.search = query.toString();
  return url.toString();
}
