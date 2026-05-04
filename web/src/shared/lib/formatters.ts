// ── Time formatting ──────────────────────────────────────────────────────────

export function relativeTime(ts: string | undefined | null): string {
  if (!ts) return "Never";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  const diff = Math.max(0, Date.now() - d.getTime());
  const sec = Math.floor(diff / 1000);
  if (sec < 10) return "just now";
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  return `${Math.floor(hr / 24)}d ago`;
}

// ── Number / string coercion ─────────────────────────────────────────────────

export function toNum(value: unknown): number {
  if (typeof value === "number") return Number.isFinite(value) ? value : 0;
  if (typeof value === "string") {
    const cleaned = value.replace(/,/g, "").trim();
    if (!cleaned) return 0;
    const parsed = Number(cleaned);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

export function toStr(value: unknown, fallback = ""): string {
  const text = String(value ?? "").trim();
  return text || fallback;
}

export function asRows(value: unknown): Array<Record<string, unknown>> {
  if (Array.isArray(value)) return value as Array<Record<string, unknown>>;
  if (value && typeof value === "object") {
    const obj = value as Record<string, unknown>;
    const candidates = [obj.items, obj.data, obj.results, obj.ideas, obj.runs];
    for (const candidate of candidates) {
      if (Array.isArray(candidate)) return candidate as Array<Record<string, unknown>>;
    }
  }
  return [];
}

// ── Status color mapping ─────────────────────────────────────────────────────

export type StatusTone = {
  text: string;
  bg: string;
  border: string;
  /** Combined className string */
  cls: string;
};

const STATUS_TONES: Record<string, StatusTone> = {
  // Success states
  succeeded: { text: "text-success", bg: "bg-success/10", border: "border-success/20", cls: "text-success bg-success/10 border-success/20" },
  success: { text: "text-success", bg: "bg-success/10", border: "border-success/20", cls: "text-success bg-success/10 border-success/20" },
  done: { text: "text-success", bg: "bg-success/10", border: "border-success/20", cls: "text-success bg-success/10 border-success/20" },
  healthy: { text: "text-success", bg: "bg-success/10", border: "border-success/20", cls: "text-success bg-success/10 border-success/20" },
  ok: { text: "text-success", bg: "bg-success/10", border: "border-success/20", cls: "text-success bg-success/10 border-success/20" },
  deployed: { text: "text-success", bg: "bg-success/10", border: "border-success/20", cls: "text-success bg-success/10 border-success/20" },
  // Danger states
  failed: { text: "text-danger", bg: "bg-danger/10", border: "border-danger/20", cls: "text-danger bg-danger/10 border-danger/20" },
  error: { text: "text-danger", bg: "bg-danger/10", border: "border-danger/20", cls: "text-danger bg-danger/10 border-danger/20" },
  timed_out: { text: "text-danger", bg: "bg-danger/10", border: "border-danger/20", cls: "text-danger bg-danger/10 border-danger/20" },
  unreachable: { text: "text-danger", bg: "bg-danger/10", border: "border-danger/20", cls: "text-danger bg-danger/10 border-danger/20" },
  down: { text: "text-danger", bg: "bg-danger/10", border: "border-danger/20", cls: "text-danger bg-danger/10 border-danger/20" },
  // Active/running states
  running: { text: "text-accent", bg: "bg-accent/10", border: "border-accent/20", cls: "text-accent bg-accent/10 border-accent/20" },
  preparing: { text: "text-accent", bg: "bg-accent/10", border: "border-accent/20", cls: "text-accent bg-accent/10 border-accent/20" },
  deploying: { text: "text-accent", bg: "bg-accent/10", border: "border-accent/20", cls: "text-accent bg-accent/10 border-accent/20" },
  dispatched: { text: "text-accent", bg: "bg-accent/10", border: "border-accent/20", cls: "text-accent bg-accent/10 border-accent/20" },
  accepted: { text: "text-accent", bg: "bg-accent/10", border: "border-accent/20", cls: "text-accent bg-accent/10 border-accent/20" },
  busy: { text: "text-accent", bg: "bg-accent/10", border: "border-accent/20", cls: "text-accent bg-accent/10 border-accent/20" },
  // Warning states
  slow: { text: "text-warning", bg: "bg-warning/10", border: "border-warning/20", cls: "text-warning bg-warning/10 border-warning/20" },
  pending: { text: "text-warning", bg: "bg-warning/10", border: "border-warning/20", cls: "text-warning bg-warning/10 border-warning/20" },
  queued: { text: "text-warning", bg: "bg-warning/10", border: "border-warning/20", cls: "text-warning bg-warning/10 border-warning/20" },
  blocked: { text: "text-warning", bg: "bg-warning/10", border: "border-warning/20", cls: "text-warning bg-warning/10 border-warning/20" },
  // Muted states
  canceled: { text: "text-muted-foreground", bg: "bg-border/30", border: "border-border", cls: "text-muted-foreground bg-border/30 border-border" },
  disabled: { text: "text-muted-foreground", bg: "bg-border/30", border: "border-border", cls: "text-muted-foreground bg-border/30 border-border" },
  archived: { text: "text-muted-foreground", bg: "bg-border/30", border: "border-border", cls: "text-muted-foreground bg-border/30 border-border" },
};

const FALLBACK_TONE: StatusTone = {
  text: "text-muted-foreground",
  bg: "bg-border/30",
  border: "border-border",
  cls: "text-muted-foreground bg-border/30 border-border",
};

export function getStatusTone(status: string | undefined | null): StatusTone {
  if (!status) return FALLBACK_TONE;
  return STATUS_TONES[status.toLowerCase()] ?? FALLBACK_TONE;
}

/** Returns combined className for a status badge/pill */
export function statusCls(status: string): string {
  return getStatusTone(status).cls;
}
