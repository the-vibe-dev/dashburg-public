import { useEffect, useMemo, useState } from "react";
import { Bot, Loader2, RefreshCcw, Send, User } from "lucide-react";
import {
  AssistantRuntimeProvider,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useAuiState,
  useLocalRuntime,
} from "@assistant-ui/react";
import type { ThreadMessageLike } from "@assistant-ui/react";

import {
  useChatMessages,
  useChatSession,
  useChatSessions,
  useCreateChatSession,
} from "../../api/hooks";
import { eventsUrl } from "../../api/client";
import type { ChatMessage, ChatMessageSource } from "../../api/types";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";

export type DashburgAssistantPanelProps = {
  sessionId?: string;
  title?: string;
  subtitle?: string;
  defaultModel?: string;
  allowSessionSwitch?: boolean;
  showHeader?: boolean;
  compact?: boolean;
  heightClass?: string;
  sourceFilter?: ChatMessageSource[];
  readonly?: boolean;
  showMetadata?: boolean;
  showSessionControls?: boolean;
};

function envString(name: string): string {
  const env = import.meta.env as Record<string, string | undefined>;
  return String(env[name] ?? "").trim();
}

function is404Error(error: unknown): boolean {
  const status = (error as { status?: unknown } | null)?.status;
  return typeof status === "number" && status === 404;
}

function remoteOpsHeaders(path: string): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  const adminToken = window.localStorage.getItem("dashburg.remoteops.adminToken") ?? "";
  const clientToken = window.localStorage.getItem("dashburg.remoteops.clientToken") ?? "";
  if (path.startsWith("/api/chat/") && adminToken) headers["X-RemoteOps-Admin-Token"] = adminToken;
  if (path.startsWith("/api/chat/") && clientToken) headers["X-RemoteOps-Client-Token"] = clientToken;
  return headers;
}

function parseSseChunk(buffer: string): { events: Array<{ event: string; data: string }>; remainder: string } {
  const blocks = buffer.split("\n\n");
  const remainder = blocks.pop() ?? "";
  const events: Array<{ event: string; data: string }> = [];

  for (const block of blocks) {
    const lines = block.split("\n");
    let event = "message";
    const dataLines: string[] = [];
    for (const line of lines) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (dataLines.length) events.push({ event, data: dataLines.join("\n") });
  }

  return { events, remainder };
}

function toThreadMessageLike(message: ChatMessage): ThreadMessageLike {
  const normalizedRole = message.role === "tool" ? "system" : message.role;
  const custom: Record<string, unknown> = {
    source: message.source,
    model: message.model,
    provider: message.provider,
    status: message.status,
    ...(message.metadata ?? {}),
  };
  return {
    id: message.id,
    role: normalizedRole,
    content: message.content,
    createdAt: new Date(message.created_at),
    ...(normalizedRole === "assistant" ? { status: { type: "complete", reason: "stop" as const } } : {}),
    metadata: { custom },
  };
}

function sourceTone(source: string): string {
  if (source === "discord") return "bg-indigo-500/20 text-indigo-200";
  if (source === "agent") return "bg-success/20 text-success";
  if (source === "tool") return "bg-amber-500/20 text-amber-100";
  if (source === "system") return "bg-slate-500/20 text-slate-200";
  return "bg-primary/20 text-primary";
}

function ChatMessageBubble({ showMetadata = true }: { showMetadata?: boolean }) {
  const role = useAuiState((s) => s.message.role);
  const isUser = role === "user";
  const createdAt = useAuiState((s) => s.message.createdAt);
  const custom = useAuiState((s) => (s.message.metadata?.custom as Record<string, unknown> | undefined) ?? {});
  const source = String(custom.source ?? (isUser ? "web" : "agent"));
  const model = String(custom.model ?? "");

  return (
    <MessagePrimitive.Root className={`w-full ${isUser ? "flex justify-end" : "flex justify-start"}`}>
      <div className={`max-w-[92%] rounded-xl border p-3 text-sm ${isUser ? "border-primary/40 bg-primary/10" : "border-border bg-background/70"}`}>
        <div className="mb-1 flex items-center gap-2 text-[11px] uppercase tracking-wide text-muted-foreground">
          {isUser ? <User size={11} /> : <Bot size={11} />}
          <span>{role}</span>
          <span className={`rounded-full px-2 py-0.5 ${sourceTone(source)}`}>{source}</span>
          {showMetadata && model ? <span className="rounded-full bg-muted px-2 py-0.5 font-mono normal-case">{model}</span> : null}
          {showMetadata && createdAt ? <span className="normal-case">{new Date(createdAt).toLocaleTimeString()}</span> : null}
        </div>
        <MessagePrimitive.Parts />
      </div>
    </MessagePrimitive.Root>
  );
}

function RuntimeHost({
  activeSessionId,
  model,
  initialMessages,
  readonly,
  showMetadata,
}: {
  activeSessionId: string;
  model: string;
  initialMessages: ThreadMessageLike[];
  readonly?: boolean;
  showMetadata?: boolean;
}) {
  const runtime = useLocalRuntime(
    {
      async *run(options) {
        const userText = options.messages
          .filter((m) => m.role === "user")
          .map((m) => {
            const part = m.content.find((p) => p.type === "text");
            return part && "text" in part ? String(part.text ?? "") : "";
          })
          .filter(Boolean)
          .at(-1) ?? "";

        const path = `/api/chat/sessions/${encodeURIComponent(activeSessionId)}/stream`;
        const response = await fetch(eventsUrl(path), {
          method: "POST",
          headers: remoteOpsHeaders(path),
          body: JSON.stringify({
            content: userText,
            source: "web",
            model,
            provider: "ollama",
            include_memory: true,
          }),
        });

        if (!response.ok || !response.body) {
          yield {
            status: {
              type: "incomplete" as const,
              reason: "error" as const,
              error: `chat stream failed (${response.status})`,
            },
            metadata: { custom: { source: "agent", session_id: activeSessionId } },
          };
          return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let pending = "";
        let accumulated = "";
        let finalized = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          pending += decoder.decode(value, { stream: true });
          const parsed = parseSseChunk(pending);
          pending = parsed.remainder;

          for (const evt of parsed.events) {
            if (evt.event === "delta") {
              try {
                const payload = JSON.parse(evt.data) as { text?: string };
                const piece = String(payload.text ?? "");
                if (piece) {
                  accumulated += piece;
                  yield {
                    content: [{ type: "text", text: accumulated }],
                    metadata: { custom: { source: "agent", model, session_id: activeSessionId } },
                  };
                }
              } catch {
                // ignore malformed chunks; keep stream resilient
              }
            }
            if (evt.event === "final") {
              try {
                const payload = JSON.parse(evt.data) as { message?: { content?: string } };
                finalized = String(payload.message?.content ?? "");
              } catch {
                // ignore malformed final payload
              }
            }
            if (evt.event === "error") {
              try {
                const payload = JSON.parse(evt.data) as { error?: string };
                yield {
                  status: {
                    type: "incomplete" as const,
                    reason: "error" as const,
                    error: String(payload.error ?? "chat stream error"),
                  },
                  metadata: { custom: { source: "agent", model, session_id: activeSessionId } },
                };
                return;
              } catch {
                yield {
                  status: {
                    type: "incomplete" as const,
                    reason: "error" as const,
                    error: "chat stream error",
                  },
                  metadata: { custom: { source: "agent", model, session_id: activeSessionId } },
                };
                return;
              }
            }
          }
        }

        yield {
          content: [{ type: "text", text: finalized || accumulated || "(no assistant output)" }],
          status: { type: "complete" as const, reason: "stop" as const },
          metadata: { custom: { source: "agent", model, session_id: activeSessionId } },
        };
        return;
      },
    },
    {
      initialMessages,
    },
  );

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ThreadPrimitive.Root className="flex h-full flex-col">
        <ThreadPrimitive.Viewport className="flex-1 overflow-auto px-1">
          <ThreadPrimitive.Messages
            components={{
              Message: () => <ChatMessageBubble showMetadata={showMetadata} />,
            }}
          />
        </ThreadPrimitive.Viewport>

        <ComposerPrimitive.Root className="mt-3 flex items-end gap-2 border-t border-border pt-3">
          <ComposerPrimitive.Input
            className="min-h-[64px] flex-1 rounded-lg border border-border bg-input px-3 py-2 text-sm text-foreground"
            placeholder={readonly ? "Read-only panel" : "Ask Dashburg..."}
            disabled={readonly}
          />
          <ComposerPrimitive.Send asChild>
            <Button size="sm" disabled={readonly}>
              <Send size={12} />
              Send
            </Button>
          </ComposerPrimitive.Send>
        </ComposerPrimitive.Root>
      </ThreadPrimitive.Root>
    </AssistantRuntimeProvider>
  );
}

export function DashburgAssistantPanel({
  sessionId,
  title = "Dashburg Assistant",
  subtitle = "Redis-backed shared session for web and Discord chat.",
  defaultModel = envString("VITE_CHAT_DEFAULT_MODEL") || "qwen3:14b",
  allowSessionSwitch = false,
  showHeader = true,
  compact = false,
  heightClass = "h-[340px]",
  sourceFilter,
  readonly,
  showMetadata = true,
  showSessionControls = true,
}: DashburgAssistantPanelProps) {
  const [activeSessionId, setActiveSessionId] = useState(sessionId ?? "");
  const [model, setModel] = useState(defaultModel);

  const sessionsQuery = useChatSessions(80);
  const createSession = useCreateChatSession();
  const sessionQuery = useChatSession(activeSessionId || null);
  const messagesQuery = useChatMessages(activeSessionId || null, 300);
  const sessionNotFound = sessionQuery.isError && is404Error(sessionQuery.error);
  const refetchSession = sessionQuery.refetch;
  const refetchMessages = messagesQuery.refetch;

  useEffect(() => {
    if (sessionId) setActiveSessionId(sessionId);
  }, [sessionId]);

  useEffect(() => {
    if (!activeSessionId && !createSession.isPending) {
      const sessionPrefix = envString("VITE_CHAT_SESSION_PREFIX") || "dashburg-web";
      const generated = sessionId || `${sessionPrefix}-${new Date().toISOString().slice(0, 10)}`;
      createSession.mutate(
        {
          session_id: generated,
          title,
          model: defaultModel,
          provider: "ollama",
          source_types: ["web"],
          metadata: { panel: title },
        },
        {
          onSuccess: (row) => {
            setActiveSessionId(row.id);
            setModel(row.model || defaultModel);
          },
        },
      );
    }
  }, [activeSessionId, createSession, defaultModel, sessionId, title]);

  useEffect(() => {
    if (!activeSessionId || createSession.isPending || !sessionNotFound) return;
    createSession.mutate(
      {
        session_id: activeSessionId,
        title,
        model: defaultModel,
        provider: "ollama",
        source_types: ["web", "discord"],
        metadata: { panel: title },
      },
      {
        onSuccess: (row) => {
          setModel(row.model || defaultModel);
          void refetchSession();
          void refetchMessages();
        },
      },
    );
  }, [activeSessionId, createSession, defaultModel, sessionNotFound, title, refetchSession, refetchMessages]);

  useEffect(() => {
    if (sessionQuery.data?.model) setModel(sessionQuery.data.model);
  }, [sessionQuery.data?.model]);

  const filteredMessages = useMemo(() => {
    const raw = messagesQuery.data?.items ?? [];
    if (!sourceFilter?.length) return raw;
    const set = new Set(sourceFilter);
    return raw.filter((message) => set.has(message.source));
  }, [messagesQuery.data?.items, sourceFilter]);

  const initialMessages = useMemo<ThreadMessageLike[]>(() => {
    return filteredMessages.map((m) => toThreadMessageLike(m));
  }, [filteredMessages]);

  const runtimeSeed = useMemo(() => {
    const last = filteredMessages.at(-1);
    return `${activeSessionId}:${filteredMessages.length}:${last?.id ?? "none"}`;
  }, [activeSessionId, filteredMessages]);

  const isLoading = createSession.isPending || (!activeSessionId && !createSession.isError);

  return (
    <Card>
      {showHeader ? (
        <CardHeader className={compact ? "pb-2" : undefined}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle>{title}</CardTitle>
            <div className="flex flex-wrap gap-2">
              {showSessionControls ? (
                <>
                  {allowSessionSwitch ? (
                    <select
                      className="h-8 rounded border border-border bg-input px-2 text-xs text-foreground"
                      value={activeSessionId}
                      onChange={(e) => setActiveSessionId(e.target.value)}
                    >
                      <option value="">Select session</option>
                      {(sessionsQuery.data?.items ?? []).map((row) => (
                        <option key={row.id} value={row.id}>{row.title} ({row.id})</option>
                      ))}
                    </select>
                  ) : null}
                  <input
                    className="h-8 min-w-[220px] rounded border border-border bg-input px-2 text-xs text-foreground"
                    value={activeSessionId}
                    onChange={(e) => setActiveSessionId(e.target.value)}
                    placeholder="session id"
                  />
                  <input
                    className="h-8 min-w-[180px] rounded border border-border bg-input px-2 text-xs font-mono text-foreground"
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    placeholder="model"
                  />
                </>
              ) : null}
              <Button size="sm" variant="outline" onClick={() => { void sessionQuery.refetch(); void messagesQuery.refetch(); }}>
                <RefreshCcw size={12} />
                Refresh
              </Button>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">{subtitle}</p>
        </CardHeader>
      ) : null}

      <CardContent className="space-y-2">
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span className="rounded-full bg-muted px-2 py-1 font-mono">session: {activeSessionId || "-"}</span>
          <span className="rounded-full bg-muted px-2 py-1 font-mono">model: {model}</span>
          {sessionQuery.data?.discord_link?.channel_id ? (
            <span className="rounded-full bg-indigo-500/20 px-2 py-1 text-indigo-200">discord-linked</span>
          ) : null}
        </div>

        <div className={`${heightClass} rounded border border-border bg-background/30 p-2`}>
          {isLoading ? (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              <Loader2 size={14} className="mr-2 animate-spin" />
              Initializing chat session...
            </div>
          ) : null}

          {!isLoading && activeSessionId ? (
            <RuntimeHost
              key={runtimeSeed}
              activeSessionId={activeSessionId}
              model={model}
              initialMessages={initialMessages}
              readonly={readonly}
              showMetadata={showMetadata}
            />
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
