import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Plus, FolderKanban, Play, X, Trash2 } from "lucide-react";

import { apiDelete, apiGet, apiPost, apiPut } from "../../shared/api/client";
import { Button } from "../../shared/components/ui/button";
import { Input, Textarea } from "../../shared/components/ui/input";
import { PageHeader } from "../../shared/components/ui/page-header";

type AnyBlock = Record<string, unknown>;

type WorkspaceTab = {
  id: string;
  type: "workspace_site_tab";
  title: string;
  url: string;
  login_url?: string;
  state?: "active" | "closed";
  created_at?: string;
  updated_at?: string;
};

type WorkspaceTask = {
  id: string;
  type: "task";
  scope: "project" | "tab";
  tab_id?: string;
  content: string;
  status?: string;
  priority?: string;
  created_at?: string;
};

type WorkspaceNote = {
  id: string;
  type: "note" | "heading";
  scope: "project" | "tab";
  tab_id?: string;
  content: string;
  created_at?: string;
};

type WorkspaceMeta = {
  type: "workspace_meta";
  last_active_tab_id?: string;
};

type CredentialStatus = {
  tab_id: string;
  has_credentials: boolean;
  kinds: string[];
  username: string;
  updated_at: string;
};

type WorkspaceResponse = {
  project_id: number;
  blocks: AnyBlock[];
  active_sessions: Array<{
    tab_id: string;
    node_id: string;
    session_id: string;
    status: string;
    live_url: string;
    updated_at: string;
  }>;
  credential_status: CredentialStatus[];
};

type Project = {
  id: number;
  title: string;
  description: string;
};

function genId() {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

function normalizeUrl(raw: string): string {
  const value = raw.trim();
  if (!value) return "";
  if (/^https?:\/\//i.test(value)) return value;
  if (/^(localhost|127\.0\.0\.1|\d{1,3}(\.\d{1,3}){3})(:\d+)?(\/.*)?$/i.test(value)) return `http://${value}`;
  return `https://${value}`;
}

function asMeta(blocks: AnyBlock[]): WorkspaceMeta {
  const row = blocks.find((b) => String(b.type || "") === "workspace_meta");
  if (!row) return { type: "workspace_meta" };
  return {
    type: "workspace_meta",
    last_active_tab_id: String(row.last_active_tab_id || "") || undefined,
  };
}

function asTabs(blocks: AnyBlock[]): WorkspaceTab[] {
  return blocks
    .filter((b) => String(b.type || "") === "workspace_site_tab")
    .map((b) => ({
      id: String(b.id || ""),
      type: "workspace_site_tab" as const,
      title: String(b.title || b.name || "Untitled"),
      url: String(b.url || ""),
      login_url: String(b.login_url || "") || undefined,
      state: (String(b.state || "closed") === "active" ? "active" : "closed") as "active" | "closed",
      created_at: String(b.created_at || "") || undefined,
      updated_at: String(b.updated_at || "") || undefined,
    }))
    .filter((t) => t.id && t.url);
}

function asTasks(blocks: AnyBlock[]): WorkspaceTask[] {
  return blocks
    .filter((b) => String(b.type || "") === "task")
    .map((b) => ({
      id: String(b.id || ""),
      type: "task" as const,
      scope: (String(b.scope || "project") === "tab" ? "tab" : "project") as "project" | "tab",
      tab_id: String(b.tab_id || "") || undefined,
      content: String(b.content || ""),
      status: String(b.status || "todo"),
      priority: String(b.priority || "medium"),
      created_at: String(b.created_at || "") || undefined,
    }))
    .filter((t) => t.id && t.content);
}

function asNotes(blocks: AnyBlock[]): WorkspaceNote[] {
  return blocks
    .filter((b) => {
      const t = String(b.type || "");
      return t === "note" || t === "heading";
    })
    .map((b) => ({
      id: String(b.id || ""),
      type: (String(b.type || "note") === "heading" ? "heading" : "note") as "note" | "heading",
      scope: (String(b.scope || "project") === "tab" ? "tab" : "project") as "project" | "tab",
      tab_id: String(b.tab_id || "") || undefined,
      content: String(b.content || ""),
      created_at: String(b.created_at || "") || undefined,
    }))
    .filter((n) => n.id && n.content);
}

function replaceBlocks(base: AnyBlock[], tabs: WorkspaceTab[], notes: WorkspaceNote[], tasks: WorkspaceTask[], meta: WorkspaceMeta): AnyBlock[] {
  const other = base.filter((b) => {
    const t = String(b.type || "");
    return !["workspace_site_tab", "workspace_meta", "note", "heading", "task"].includes(t);
  });
  return [meta as AnyBlock, ...tabs as AnyBlock[], ...notes as AnyBlock[], ...tasks as AnyBlock[], ...other];
}

export function ProjectsWorkspacePage() {
  const { id } = useParams();
  const queryClient = useQueryClient();
  const projectId = Number(id || 0);

  const { data: project } = useQuery({
    queryKey: ["project", id],
    queryFn: () => apiGet<Project>(`/api/projects/${id}`),
    enabled: Boolean(id),
  });

  const workspaceQ = useQuery({
    queryKey: ["project-workspace", id],
    queryFn: () => apiGet<WorkspaceResponse>(`/api/projects/${id}/workspace`),
    enabled: Boolean(id),
  });

  const [blocks, setBlocks] = useState<AnyBlock[]>([]);
  const [selectedTabId, setSelectedTabId] = useState("");
  const [scope, setScope] = useState<"project" | "tab">("project");
  const [newTabTitle, setNewTabTitle] = useState("");
  const [newTabUrl, setNewTabUrl] = useState("");
  const [newTabLoginUrl, setNewTabLoginUrl] = useState("");
  const [taskText, setTaskText] = useState("");
  const [noteText, setNoteText] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [cookieBundle, setCookieBundle] = useState("");

  useEffect(() => {
    if (!workspaceQ.data) return;
    setBlocks(workspaceQ.data.blocks || []);
    const meta = asMeta(workspaceQ.data.blocks || []);
    const tabs = asTabs(workspaceQ.data.blocks || []);
    const picked = meta.last_active_tab_id && tabs.some((t) => t.id === meta.last_active_tab_id)
      ? meta.last_active_tab_id
      : tabs[0]?.id || "";
    setSelectedTabId(picked);
  }, [workspaceQ.data]);

  const saveWorkspace = useMutation({
    mutationFn: (nextBlocks: AnyBlock[]) => apiPut<WorkspaceResponse>(`/api/projects/${id}/workspace`, { blocks: nextBlocks }),
    onSuccess: (data) => {
      setBlocks(data.blocks || []);
      queryClient.invalidateQueries({ queryKey: ["project-workspace", id] });
    },
  });

  const closeTabMutation = useMutation({
    mutationFn: (tabId: string) => apiPost(`/api/projects/${id}/tabs/${encodeURIComponent(tabId)}/close`, {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["project-workspace", id] }),
  });

  const saveCredsMutation = useMutation({
    mutationFn: () => apiPost(`/api/projects/${id}/tabs/${encodeURIComponent(selectedTabId)}/credentials`, {
      username,
      password: password || undefined,
      token: token || undefined,
      cookie_bundle: cookieBundle || undefined,
    }),
    onSuccess: () => {
      setPassword("");
      setToken("");
      setCookieBundle("");
      queryClient.invalidateQueries({ queryKey: ["project-workspace", id] });
    },
  });

  const deleteCredsMutation = useMutation({
    mutationFn: () => apiDelete(`/api/projects/${id}/tabs/${encodeURIComponent(selectedTabId)}/credentials`),
    onSuccess: () => {
      setPassword("");
      setToken("");
      setCookieBundle("");
      queryClient.invalidateQueries({ queryKey: ["project-workspace", id] });
    },
  });

  const tabs = useMemo(() => asTabs(blocks), [blocks]);
  const notes = useMemo(() => asNotes(blocks), [blocks]);
  const tasks = useMemo(() => asTasks(blocks), [blocks]);
  const meta = useMemo(() => asMeta(blocks), [blocks]);

  const selectedTab = tabs.find((t) => t.id === selectedTabId);
  const credentialStatus = (workspaceQ.data?.credential_status || []).find((c) => c.tab_id === selectedTabId);

  const scopedNotes = notes.filter((n) => n.scope === scope && (scope === "project" || n.tab_id === selectedTabId));
  const scopedTasks = tasks.filter((t) => t.scope === scope && (scope === "project" || t.tab_id === selectedTabId));

  function persist(nextTabs: WorkspaceTab[], nextNotes: WorkspaceNote[], nextTasks: WorkspaceTask[], nextMeta?: WorkspaceMeta) {
    const merged = replaceBlocks(blocks, nextTabs, nextNotes, nextTasks, nextMeta || meta);
    setBlocks(merged);
    saveWorkspace.mutate(merged);
  }

  function createTab() {
    const url = normalizeUrl(newTabUrl);
    const loginUrl = normalizeUrl(newTabLoginUrl);
    if (!url) return;
    const now = new Date().toISOString();
    const tab: WorkspaceTab = {
      id: genId(),
      type: "workspace_site_tab",
      title: newTabTitle.trim() || url,
      url,
      login_url: loginUrl || undefined,
      state: "closed",
      created_at: now,
      updated_at: now,
    };
    const nextTabs = [...tabs, tab];
    const nextMeta = { ...meta, last_active_tab_id: tab.id };
    persist(nextTabs, notes, tasks, nextMeta);
    setSelectedTabId(tab.id);
    setNewTabTitle("");
    setNewTabUrl("");
    setNewTabLoginUrl("");
  }

  function setTabState(tabId: string, state: "active" | "closed") {
    const now = new Date().toISOString();
    const nextTabs = tabs.map((t) => (t.id === tabId ? { ...t, state, updated_at: now } : t));
    const nextMeta = { ...meta, last_active_tab_id: tabId };
    persist(nextTabs, notes, tasks, nextMeta);
  }

  function deleteTab(tabId: string) {
    const nextTabs = tabs.filter((t) => t.id !== tabId);
    const nextNotes = notes.filter((n) => n.tab_id !== tabId);
    const nextTasks = tasks.filter((t) => t.tab_id !== tabId);
    const nextMeta = { ...meta, last_active_tab_id: nextTabs[0]?.id };
    persist(nextTabs, nextNotes, nextTasks, nextMeta);
    if (selectedTabId === tabId) setSelectedTabId(nextTabs[0]?.id || "");
  }

  function addTask() {
    if (!taskText.trim()) return;
    if (scope === "tab" && !selectedTabId) return;
    const task: WorkspaceTask = {
      id: genId(),
      type: "task",
      scope,
      tab_id: scope === "tab" ? selectedTabId : undefined,
      content: taskText.trim(),
      status: "todo",
      priority: "medium",
      created_at: new Date().toISOString(),
    };
    persist(tabs, notes, [...tasks, task]);
    setTaskText("");
  }

  function addNote() {
    if (!noteText.trim()) return;
    if (scope === "tab" && !selectedTabId) return;
    const note: WorkspaceNote = {
      id: genId(),
      type: "note",
      scope,
      tab_id: scope === "tab" ? selectedTabId : undefined,
      content: noteText.trim(),
      created_at: new Date().toISOString(),
    };
    persist(tabs, [...notes, note], tasks);
    setNoteText("");
  }

  function toggleTaskDone(taskId: string) {
    const nextTasks = tasks.map((t) =>
      t.id === taskId ? { ...t, status: t.status === "done" ? "todo" : "done" } : t,
    );
    persist(tabs, notes, nextTasks);
  }

  function removeTask(taskId: string) {
    persist(tabs, notes, tasks.filter((t) => t.id !== taskId));
  }

  function removeNote(noteId: string) {
    persist(tabs, notes.filter((n) => n.id !== noteId), tasks);
  }

  const boardTabs = tabs;
  const selectedTabUrl = selectedTab ? normalizeUrl(selectedTab.url) : "";

  function openInBrowser(url: string) {
    if (!url) return;
    window.open(url, "_blank", "noopener,noreferrer");
  }

  return (
    <div className="space-y-6 stagger-children">
      <Link to="/projects" className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors">
        <FolderKanban size={13} />
        TaskVault
      </Link>

      <PageHeader
        title={project?.title ? `${project.title} Workspace` : "Workspace"}
        description="Persistent project site board with scoped notes and tasks"
        actions={<Link to={`/projects/${id}`}><Button variant="outline">Open Project Detail</Button></Link>}
      />

      <div className="rounded-xl border border-border bg-card p-4 space-y-2">
        <p className="text-xs font-semibold">Add Site Tab</p>
        <div className="grid gap-2 md:grid-cols-3">
          <Input placeholder="Tab label" value={newTabTitle} onChange={(e) => setNewTabTitle(e.target.value)} />
          <Input placeholder="Homepage URL" value={newTabUrl} onChange={(e) => setNewTabUrl(e.target.value)} />
          <Input placeholder="Login URL (optional)" value={newTabLoginUrl} onChange={(e) => setNewTabLoginUrl(e.target.value)} />
        </div>
        <div>
          <Button onClick={createTab} disabled={!newTabUrl.trim() || saveWorkspace.isPending}><Plus size={13} />Add Tab</Button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[360px,1fr]">
        <div className="space-y-3">
          <div className="rounded-xl border border-border bg-card p-3 space-y-2">
            <p className="text-xs font-semibold">Open Board</p>
            {boardTabs.length === 0 ? (
              <p className="text-xs text-muted-foreground">No tabs yet.</p>
            ) : (
              <div className="space-y-2 max-h-72 overflow-auto">
                {boardTabs.map((tab) => {
                  const isActive = tab.id === selectedTabId;
                  return (
                    <div key={tab.id} className={`rounded-lg border p-2 ${isActive ? "border-primary/50" : "border-border"}`}>
                      <button className="w-full text-left" onClick={() => setSelectedTabId(tab.id)}>
                        <p className="text-sm font-medium truncate">{tab.title}</p>
                        <p className="text-[11px] text-muted-foreground truncate">{tab.url}</p>
                      </button>
                      <div className="mt-2 flex items-center gap-1 flex-wrap">
                        <span className="text-[10px] rounded bg-border/40 px-1.5 py-0.5">{tab.state || "closed"}</span>
                        <Button size="sm" variant="outline" onClick={() => {
                          setSelectedTabId(tab.id);
                          setTabState(tab.id, "active");
                          openInBrowser(normalizeUrl(tab.url));
                        }}><Play size={12} />Open</Button>
                        <Button size="sm" variant="outline" onClick={() => {
                          setTabState(tab.id, "closed");
                          closeTabMutation.mutate(tab.id);
                        }}><X size={12} />Close</Button>
                        <Button size="sm" variant="outline" onClick={() => deleteTab(tab.id)}><Trash2 size={12} />Delete</Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="rounded-xl border border-border bg-card p-3 space-y-2">
            <div className="flex items-center gap-2">
              <Button size="sm" variant={scope === "project" ? "default" : "outline"} onClick={() => setScope("project")}>Project Scope</Button>
              <Button size="sm" variant={scope === "tab" ? "default" : "outline"} onClick={() => setScope("tab")} disabled={!selectedTabId}>Tab Scope</Button>
            </div>
            <p className="text-xs text-muted-foreground">Notes / tasks for {scope === "project" ? "whole project" : "current tab"}.</p>
            <div className="space-y-1">
              {scopedTasks.map((t) => (
                <div key={t.id} className="flex items-center gap-2 rounded border border-border/70 px-2 py-1">
                  <input type="checkbox" checked={t.status === "done"} onChange={() => toggleTaskDone(t.id)} />
                  <span className={`flex-1 text-xs ${t.status === "done" ? "line-through text-muted-foreground" : "text-foreground"}`}>{t.content}</span>
                  <button className="text-xs text-muted-foreground hover:text-foreground" onClick={() => removeTask(t.id)}>remove</button>
                </div>
              ))}
              {scopedTasks.length === 0 ? <p className="text-xs text-muted-foreground">No tasks.</p> : null}
            </div>
            <div className="flex items-center gap-2">
              <Input placeholder="Add task" value={taskText} onChange={(e) => setTaskText(e.target.value)} />
              <Button onClick={addTask} disabled={!taskText.trim()}>Add</Button>
            </div>
            <div className="space-y-1">
              {scopedNotes.map((n) => (
                <div key={n.id} className="rounded border border-border/70 px-2 py-1.5">
                  <p className="text-xs whitespace-pre-wrap">{n.content}</p>
                  <button className="text-[11px] text-muted-foreground hover:text-foreground" onClick={() => removeNote(n.id)}>remove</button>
                </div>
              ))}
              {scopedNotes.length === 0 ? <p className="text-xs text-muted-foreground">No notes.</p> : null}
            </div>
            <Textarea rows={3} placeholder="Add note" value={noteText} onChange={(e) => setNoteText(e.target.value)} />
            <Button onClick={addNote} disabled={!noteText.trim()}>Add Note</Button>
          </div>

          {selectedTab ? (
            <div className="rounded-xl border border-border bg-card p-3 space-y-2">
              <p className="text-xs font-semibold">Credentials (Encrypted)</p>
              <p className="text-[11px] text-muted-foreground">Saved kinds: {(credentialStatus?.kinds || []).join(", ") || "none"}</p>
              <form
                className="space-y-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  saveCredsMutation.mutate();
                }}
              >
                <Input placeholder="Username / email" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />
                <Input type="password" placeholder="Password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
                <Input placeholder="Token" value={token} onChange={(e) => setToken(e.target.value)} />
                <Textarea rows={3} placeholder="Cookie bundle JSON" value={cookieBundle} onChange={(e) => setCookieBundle(e.target.value)} />
                <div className="flex items-center gap-2">
                  <Button type="submit" disabled={!selectedTabId}>Save</Button>
                  <Button type="button" variant="outline" onClick={() => deleteCredsMutation.mutate()} disabled={!selectedTabId}>Delete</Button>
                </div>
              </form>
            </div>
          ) : null}
        </div>

        <div className="rounded-xl border border-border bg-card p-3 space-y-2 min-h-[680px]">
          {selectedTab ? (
            <>
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <p className="text-sm font-medium">{selectedTab.title}</p>
                <div className="flex items-center gap-2">
                  <a href={selectedTabUrl || selectedTab.url} target="_blank" rel="noreferrer">
                    <Button size="sm" variant="outline"><ExternalLink size={12} />Open External</Button>
                  </a>
                </div>
              </div>
              <div className="rounded border border-border bg-background p-6 space-y-3">
                <p className="text-sm text-foreground">Embedded frame removed.</p>
                <p className="text-xs text-muted-foreground">
                  Use `Open` from the board or `Open External` here to work in normal browser tabs.
                </p>
                <p className="text-xs text-muted-foreground break-all">
                  Current URL: {selectedTabUrl || "(invalid url)"}
                </p>
                {!selectedTabUrl ? (
                  <p className="text-xs text-warning">
                    Invalid tab URL. Use full URL, e.g. `https://example.com` or `http://127.0.0.1:3000`.
                  </p>
                ) : null}
              </div>
            </>
          ) : (
            <div className="h-[240px] flex items-center justify-center text-sm text-muted-foreground">Select or add a tab to begin.</div>
          )}
        </div>
      </div>

      {(saveWorkspace.isPending || closeTabMutation.isPending) ? (
        <p className="text-xs text-muted-foreground">Saving changes…</p>
      ) : null}

      {!projectId && <p className="text-sm text-danger">Missing project id.</p>}
    </div>
  );
}
