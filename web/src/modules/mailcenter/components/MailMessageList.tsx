import { Paperclip, Search } from "lucide-react";

import type { MailCenterMessage } from "../../../shared/api/types";
import { Card, CardContent, CardHeader, CardTitle } from "../../../shared/components/ui/card";
import { Input } from "../../../shared/components/ui/input";
import { directionIcon, fmtTs, pickDisplayName, statusTone } from "./mailUtils";

export function MailMessageList({
  loading,
  error,
  items,
  selectedId,
  searchInput,
  onSearchInputChange,
  unreadOnly,
  onToggleUnreadOnly,
  direction,
  onDirectionChange,
  status,
  onStatusChange,
  onSelectMessage,
}: {
  loading: boolean;
  error: unknown;
  items: MailCenterMessage[];
  selectedId: string | null;
  searchInput: string;
  onSearchInputChange: (value: string) => void;
  unreadOnly: boolean;
  onToggleUnreadOnly: () => void;
  direction: string | undefined;
  onDirectionChange: (value: string | undefined) => void;
  status: string | undefined;
  onStatusChange: (value: string | undefined) => void;
  onSelectMessage: (id: string) => void;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle>Messages</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-2">
          <div className="relative">
            <Search size={14} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={searchInput}
              onChange={(e) => onSearchInputChange(e.target.value)}
              placeholder="Search sender, subject, snippet, tags..."
              className="pl-8"
            />
          </div>
          <div className="flex flex-wrap gap-1.5">
            {[
              { key: "unread", label: "Unread", on: unreadOnly, click: onToggleUnreadOnly },
              { key: "failed", label: "Failed", on: status === "failed", click: () => onStatusChange(status === "failed" ? undefined : "failed") },
              { key: "inbound", label: "Inbound", on: direction === "inbound", click: () => onDirectionChange(direction === "inbound" ? undefined : "inbound") },
              { key: "outbound", label: "Outbound", on: direction === "outbound", click: () => onDirectionChange(direction === "outbound" ? undefined : "outbound") },
              { key: "queued", label: "Queued", on: status === "queued", click: () => onStatusChange(status === "queued" ? undefined : "queued") },
              { key: "processing", label: "Processing", on: status === "running", click: () => onStatusChange(status === "running" ? undefined : "running") },
            ].map((chip) => (
              <button
                key={chip.key}
                type="button"
                onClick={chip.click}
                className={`rounded-full border px-2 py-1 text-[11px] ${chip.on ? "border-primary/60 bg-primary/15 text-foreground" : "border-border text-muted-foreground hover:text-foreground"}`}
              >
                {chip.label}
              </button>
            ))}
          </div>
        </div>

        {error ? (
          <div className="rounded-lg border border-danger/40 bg-danger/10 p-3 text-sm text-danger">MailCenter failed to load. Retry after backend is reachable.</div>
        ) : null}

        {loading ? (
          <div className="space-y-2">
            {Array.from({ length: 8 }).map((_, idx) => <div key={idx} className="h-16 animate-pulse rounded-lg border border-border bg-background/40" />)}
          </div>
        ) : null}

        {!loading && !error && items.length === 0 ? (
          <div className="rounded-lg border border-border bg-background/30 p-6 text-center text-sm text-muted-foreground">
            No messages in this view.
          </div>
        ) : null}

        {!loading && !error && items.length > 0 ? (
          <div className="max-h-[66vh] space-y-1.5 overflow-auto pr-1">
            {items.map((message) => {
              const active = selectedId === message.id;
              return (
                <button
                  key={message.id}
                  type="button"
                  onClick={() => onSelectMessage(message.id)}
                  className={`w-full rounded-lg border px-3 py-2 text-left transition-colors ${active ? "border-primary/60 bg-primary/10" : "border-border bg-background/20 hover:bg-background/30"}`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className={`truncate text-sm ${message.unread ? "font-semibold text-foreground" : "text-foreground/90"}`}>{pickDisplayName(message)}</p>
                      <p className="truncate text-sm">{message.subject || "(no subject)"}</p>
                    </div>
                    <p className="shrink-0 text-[11px] text-muted-foreground">{fmtTs(message.created_at)}</p>
                  </div>
                  <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">{message.snippet || message.body || "-"}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px]">
                    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 ${statusTone(message.status)}`}>{directionIcon(message.direction)}{message.status}</span>
                    <span className={`rounded-full px-2 py-0.5 ${statusTone(message.processing_state)}`}>{message.processing_state}</span>
                    {message.has_attachments ? <span className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-muted-foreground"><Paperclip size={10} />attachments</span> : null}
                    {message.unread ? <span className="rounded-full border border-primary/40 px-2 py-0.5 text-primary">unread</span> : null}
                  </div>
                </button>
              );
            })}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
