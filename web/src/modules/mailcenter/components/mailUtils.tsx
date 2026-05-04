import { ArrowDownLeft, ArrowUpRight } from "lucide-react";

import type { MailCenterMessage } from "../../../shared/api/types";

export function fmtTs(value: string | null | undefined): string {
  const raw = String(value || "").trim();
  if (!raw) return "-";
  const ms = Date.parse(raw);
  if (!Number.isFinite(ms)) return raw;
  return new Date(ms).toLocaleString();
}

export function statusTone(status: string): string {
  const value = status.toLowerCase();
  if (["succeeded", "completed", "sent", "received", "ok", "done"].includes(value)) return "bg-success/15 text-success";
  if (["failed", "error", "timed_out"].includes(value)) return "bg-danger/15 text-danger";
  if (["running", "processing", "preparing"].includes(value)) return "bg-sky-500/20 text-sky-200";
  if (["queued", "new", "draft", "pending"].includes(value)) return "bg-amber-500/20 text-amber-100";
  return "bg-muted text-muted-foreground";
}

export function directionIcon(direction: string) {
  return direction === "outbound" ? <ArrowUpRight size={12} /> : <ArrowDownLeft size={12} />;
}

export function pickDisplayName(message: MailCenterMessage): string {
  return message.direction === "outbound" ? (message.to || "-") : (message.from || "-");
}
