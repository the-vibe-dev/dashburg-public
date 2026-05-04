import { useEffect, useMemo, useState } from "react";
import { RefreshCcw, Settings2 } from "lucide-react";

import { useMailCenterMessageDetail, useMailCenterMessages, useMailCenterOverview, useMailCenterRecipients, useMailCenterThreads, useSendMailCenterMessage } from "../../shared/api/hooks";
import { Button } from "../../shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../shared/components/ui/card";
import { Input, Textarea } from "../../shared/components/ui/input";
import { PageHeader } from "../../shared/components/ui/page-header";
import { MailMessageList } from "./components/MailMessageList";
import { MailSidebar } from "./components/MailSidebar";
import { MailSummaryStrip } from "./components/MailSummaryStrip";
import { MailThreadPanel } from "./components/MailThreadPanel";
import { fmtTs } from "./components/mailUtils";

function summaryValue(value: number | undefined): string {
  return String(value ?? 0);
}

export function MailCenterPage() {
  const [folder, setFolder] = useState("all");
  const [direction, setDirection] = useState<string | undefined>(undefined);
  const [status, setStatus] = useState<string | undefined>(undefined);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const overview = useMailCenterOverview();
  const recipients = useMailCenterRecipients();
  const sendMessage = useSendMailCenterMessage();
  const messages = useMailCenterMessages({ folder, direction, status, unreadOnly, q, limit: 180 });
  const threads = useMailCenterThreads({ folder, q, limit: 140 });
  const detail = useMailCenterMessageDetail(selectedId);
  const items = messages.data?.items ?? [];

  useEffect(() => {
    const handle = window.setTimeout(() => setQ(qInput.trim()), 220);
    return () => window.clearTimeout(handle);
  }, [qInput]);

  useEffect(() => {
    if (selectedId && items.some((item) => item.id === selectedId)) return;
    setSelectedId(items[0]?.id ?? null);
  }, [items, selectedId]);

  const selected = detail.data?.message ?? items.find((item) => item.id === selectedId) ?? null;
  const thread = detail.data?.thread;
  const [toAddress, setToAddress] = useState("");
  const [subjectDraft, setSubjectDraft] = useState("");
  const [bodyDraft, setBodyDraft] = useState("");

  const recipientOptions = useMemo(() => {
    const nodes = (recipients.data?.nodes ?? []).map((row) => ({ value: row.address, label: `${row.label} (${row.address})` }));
    const agents = (recipients.data?.agents ?? []).map((row) => ({ value: row.address, label: `${row.name} (${row.address})` }));
    return [...agents, ...nodes];
  }, [recipients.data?.agents, recipients.data?.nodes]);

  useEffect(() => {
    if (toAddress || recipientOptions.length === 0) return;
    setToAddress(recipientOptions[0]?.value ?? "");
  }, [recipientOptions, toAddress]);

  const cards = useMemo(
    () => [
      { label: "Total Inbox", value: summaryValue(overview.data?.counts?.inbox), key: "inbox" },
      { label: "Sent Today", value: summaryValue(overview.data?.counts?.sent), key: "sent" },
      { label: "Queued", value: summaryValue(overview.data?.counts?.queued), key: "queued" },
      { label: "Failed", value: summaryValue(overview.data?.counts?.failed), key: "failed" },
      { label: "Awaiting Review", value: summaryValue(overview.data?.counts?.replies_needed), key: "review" },
    ],
    [overview.data?.counts],
  );

  const loading = overview.isLoading || messages.isLoading;
  const error = overview.error || messages.error;

  return (
    <div className="space-y-4">
      <PageHeader compact title="MailCenter">
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => { void overview.refetch(); void messages.refetch(); void threads.refetch(); }}>
            <RefreshCcw size={13} />
            Refresh
          </Button>
          <Button size="sm" variant="outline" disabled>
            <Settings2 size={13} />
            Automations
          </Button>
        </div>
      </PageHeader>

      <MailSummaryStrip cards={cards} />

      <div className="grid gap-4 xl:grid-cols-[250px_minmax(420px,1fr)_minmax(380px,1fr)]">
        <MailSidebar
          overview={overview.data}
          folder={folder}
          onSelectFolder={(folderKey) => {
            setFolder(folderKey);
            setStatus(undefined);
            setDirection(undefined);
            setUnreadOnly(false);
          }}
        />

        <MailMessageList
          loading={loading}
          error={error}
          items={items}
          selectedId={selectedId}
          searchInput={qInput}
          onSearchInputChange={setQInput}
          unreadOnly={unreadOnly}
          onToggleUnreadOnly={() => setUnreadOnly((v) => !v)}
          direction={direction}
          onDirectionChange={setDirection}
          status={status}
          onStatusChange={setStatus}
          onSelectMessage={setSelectedId}
        />

        <MailThreadPanel selected={selected} thread={thread} />
      </div>

      <Card>
        <CardHeader className="pb-2"><CardTitle>Compose</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          <label className="text-xs text-muted-foreground">
            Recipient
            <select
              value={toAddress}
              onChange={(e) => setToAddress(e.target.value)}
              className="mt-1 w-full rounded border border-border bg-input px-2 py-2 text-sm text-foreground"
            >
              <option value="">Select recipient</option>
              {recipientOptions.map((row) => (
                <option key={row.value} value={row.value}>{row.label}</option>
              ))}
            </select>
          </label>
          <label className="text-xs text-muted-foreground">
            Subject
            <Input value={subjectDraft} onChange={(e) => setSubjectDraft(e.target.value)} placeholder="Message subject" />
          </label>
          <label className="text-xs text-muted-foreground">
            Message
            <Textarea rows={4} value={bodyDraft} onChange={(e) => setBodyDraft(e.target.value)} placeholder="Describe the task or request" />
          </label>
          <Button
            size="sm"
            onClick={() => {
              sendMessage.mutate(
                {
                  to: toAddress,
                  subject: subjectDraft,
                  body: bodyDraft,
                  type: "note",
                  severity: "info",
                  tags: ["mailcenter", "operator_mail"],
                },
                {
                  onSuccess: () => {
                    setSubjectDraft("");
                    setBodyDraft("");
                    void messages.refetch();
                    void threads.refetch();
                    void overview.refetch();
                  },
                },
              );
            }}
            disabled={!toAddress || !subjectDraft.trim() || !bodyDraft.trim() || sendMessage.isPending}
          >
            Send Message
          </Button>
          {sendMessage.error ? <p className="text-xs text-danger">{String(sendMessage.error)}</p> : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2"><CardTitle>Thread Index</CardTitle></CardHeader>
        <CardContent>
          {(threads.data?.items ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">No threads available for current filters.</p>
          ) : (
            <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
              {(threads.data?.items ?? []).slice(0, 12).map((threadRow) => (
                <button
                  key={threadRow.thread_id}
                  type="button"
                  onClick={() => setSelectedId(threadRow.latest_message_id)}
                  className="rounded-lg border border-border bg-background/20 px-3 py-2 text-left hover:bg-background/30"
                >
                  <p className="truncate text-sm font-medium text-foreground">{threadRow.subject || "(no subject)"}</p>
                  <p className="truncate text-xs text-muted-foreground">{threadRow.snippet || "-"}</p>
                  <div className="mt-1.5 flex items-center justify-between text-[11px] text-muted-foreground">
                    <span>{threadRow.message_count} msgs</span>
                    <span>{fmtTs(threadRow.latest_at)}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
