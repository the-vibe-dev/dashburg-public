import { AlertCircle, Archive, Send } from "lucide-react";

import type { MailCenterMessage, MailCenterMessageDetail } from "../../../shared/api/types";
import { Button } from "../../../shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../shared/components/ui/card";
import { directionIcon, fmtTs, statusTone } from "./mailUtils";

export function MailThreadPanel({
  selected,
  thread,
}: {
  selected: MailCenterMessage | null;
  thread: MailCenterMessageDetail["thread"] | undefined;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle>Thread Detail</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {!selected ? <div className="rounded-lg border border-border bg-background/30 p-6 text-sm text-muted-foreground">Select a message to inspect details.</div> : null}
        {selected ? (
          <>
            <div className="rounded-lg border border-border bg-background/30 p-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold text-foreground">{selected.subject || "(no subject)"}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">Thread {selected.thread_id}</p>
                </div>
                <div className={`rounded-full px-2 py-0.5 text-[11px] ${statusTone(selected.status)}`}>{selected.status}</div>
              </div>
              <div className="mt-3 grid gap-2 text-xs md:grid-cols-2">
                <div><span className="text-muted-foreground">From:</span> {selected.from || "-"}</div>
                <div><span className="text-muted-foreground">To:</span> {selected.to || "-"}</div>
                <div><span className="text-muted-foreground">Direction:</span> {selected.direction}</div>
                <div><span className="text-muted-foreground">Account:</span> {selected.account || "-"}</div>
                <div><span className="text-muted-foreground">Received:</span> {fmtTs(selected.received_at)}</div>
                <div><span className="text-muted-foreground">Updated:</span> {fmtTs(selected.updated_at)}</div>
                <div><span className="text-muted-foreground">Recipient Node:</span> {selected.recipient_node_id || "-"}</div>
                <div><span className="text-muted-foreground">Recipient Agent:</span> {selected.recipient_agent_slug || "-"}</div>
              </div>
              <div className="mt-3 rounded border border-border/70 bg-background/40 p-3 text-sm whitespace-pre-wrap">
                {selected.body || selected.snippet || "(empty body)"}
              </div>
            </div>

            <div className="rounded-lg border border-border bg-background/25 p-3">
              <p className="text-xs font-medium text-foreground">Processing + Routing</p>
              <div className="mt-2 grid gap-2 text-xs md:grid-cols-2">
                <div><span className="text-muted-foreground">State:</span> {selected.processing_state || "-"}</div>
                <div><span className="text-muted-foreground">Classification:</span> {selected.classification || "-"}</div>
                <div><span className="text-muted-foreground">Automation:</span> {selected.automation_rule || "-"}</div>
                <div><span className="text-muted-foreground">Reply Draft:</span> {selected.reply_draft_state || "-"}</div>
                <div className="md:col-span-2"><span className="text-muted-foreground">Failure:</span> {selected.failure_reason || "-"}</div>
              </div>
            </div>

            <div className="rounded-lg border border-border bg-background/25 p-3">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-xs font-medium text-foreground">Conversation Timeline</p>
                <p className="text-xs text-muted-foreground">{thread?.message_count ?? 0} messages</p>
              </div>
              {(thread?.messages ?? []).length ? (
                <div className="max-h-[230px] space-y-2 overflow-auto pr-1">
                  {(thread?.messages ?? []).map((message) => (
                    <div key={message.id} className="rounded border border-border/60 bg-background/40 p-2 text-xs">
                      <div className="flex items-center justify-between gap-2">
                        <span className="inline-flex items-center gap-1 text-muted-foreground">{directionIcon(message.direction)} {message.direction}</span>
                        <span className="text-muted-foreground">{fmtTs(message.created_at)}</span>
                      </div>
                      <p className="mt-1 font-medium text-foreground">{message.subject || "(no subject)"}</p>
                      <p className="line-clamp-2 text-muted-foreground">{message.snippet || message.body || "-"}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">No timeline items.</p>
              )}
            </div>

            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={() => navigator.clipboard.writeText(selected.id).catch(() => undefined)}>
                <Send size={13} />
                Copy Message ID
              </Button>
              <Button size="sm" variant="outline" disabled>
                <Archive size={13} />
                Archive
              </Button>
              <Button size="sm" variant="outline" disabled>
                <AlertCircle size={13} />
                Retry
              </Button>
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
