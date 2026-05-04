import { useState, useEffect, useRef } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Plus,
  Check,
  Trash2,
  ChevronLeft,
  FolderKanban,
  Circle,
  Loader2,
  Ban,
  CheckCircle2,
  Flag,
  StickyNote,
  ListTodo,
  MoreHorizontal,
  Tag,
  ArrowUpDown,
  Filter,
} from "lucide-react";

import { apiGet, apiPatch, apiPost, apiPut } from "../../shared/api/client";
import type { Project, ProjectPage, ProjectTaskPreview } from "../../shared/api/types";
import { useProjectReorder } from "../../shared/projects/useProjectReorder";
import { Button } from "../../shared/components/ui/button";
import { Input } from "../../shared/components/ui/input";
import { Textarea } from "../../shared/components/ui/input";
import { PageHeader } from "../../shared/components/ui/page-header";
import { useStreamingMode } from "../../app/useStreamingMode";
import { withStreamingObfuscation } from "../../app/streamingObfuscation";

// ── Types for enhanced block model ──────────────────────────────────────────

type TaskStatus = "todo" | "in_progress" | "done" | "blocked";
type TaskPriority = "low" | "medium" | "high" | "critical";
type ProjectStatus = "active" | "on_hold" | "completed" | "archived";

interface TaskBlock {
  id: string;
  type: "task";
  content: string;
  status: TaskStatus;
  priority: TaskPriority;
  created_at: string;
}

interface NoteBlock {
  id: string;
  type: "note" | "heading";
  content: string;
  created_at: string;
}

interface MetaBlock {
  type: "__meta__";
  project_status: ProjectStatus;
  tags: string[];
}

type Block = TaskBlock | NoteBlock | MetaBlock;

function genId(): string {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

// ── Status / Priority helpers ────────────────────────────────────────────────

const STATUS_CONFIG: Record<
  TaskStatus,
  { label: string; icon: React.ElementType; cls: string; dot: string }
> = {
  todo: {
    label: "Todo",
    icon: Circle,
    cls: "text-muted-foreground",
    dot: "bg-muted-foreground/40",
  },
  in_progress: {
    label: "In progress",
    icon: Loader2,
    cls: "text-accent",
    dot: "bg-accent",
  },
  done: {
    label: "Done",
    icon: CheckCircle2,
    cls: "text-success",
    dot: "bg-success",
  },
  blocked: {
    label: "Blocked",
    icon: Ban,
    cls: "text-danger",
    dot: "bg-danger",
  },
};

const PRIORITY_CONFIG: Record<
  TaskPriority,
  { label: string; cls: string; dot: string }
> = {
  low: { label: "Low", cls: "text-muted-foreground", dot: "bg-muted-foreground/30" },
  medium: { label: "Medium", cls: "text-warning", dot: "bg-warning" },
  high: { label: "High", cls: "text-primary", dot: "bg-primary" },
  critical: { label: "Critical", cls: "text-danger", dot: "bg-danger" },
};

const PROJECT_STATUS_CONFIG: Record<
  ProjectStatus,
  { label: string; cls: string }
> = {
  active: { label: "Active", cls: "text-success bg-success/10 border-success/20" },
  on_hold: { label: "On hold", cls: "text-warning bg-warning/10 border-warning/20" },
  completed: { label: "Completed", cls: "text-muted-foreground bg-border/30 border-border" },
  archived: { label: "Archived", cls: "text-muted-foreground/50 bg-border/20 border-border/50" },
};

// ── Block parsing helpers ────────────────────────────────────────────────────

function parseMeta(blocks: Array<Record<string, unknown>>): MetaBlock {
  const found = blocks.find((b) => b.type === "__meta__") as MetaBlock | undefined;
  return found ?? { type: "__meta__", project_status: "active", tags: [] };
}

function parseTasks(blocks: Array<Record<string, unknown>>): TaskBlock[] {
  return blocks.filter((b) => b.type === "task") as unknown as TaskBlock[];
}

function parseNotes(blocks: Array<Record<string, unknown>>): NoteBlock[] {
  return blocks.filter(
    (b) => b.type === "note" || b.type === "heading",
  ) as unknown as NoteBlock[];
}

function rebuildBlocks(
  raw: Array<Record<string, unknown>>,
  meta: MetaBlock,
  tasks: TaskBlock[],
  notes: NoteBlock[],
): Block[] {
  // Keep any unknown block types, replace meta/task/note
  const other = raw.filter(
    (b) => b.type !== "__meta__" && b.type !== "task" && b.type !== "note" && b.type !== "heading",
  ) as unknown as Block[];
  return [meta, ...tasks, ...notes, ...other];
}

// ── Projects list page ───────────────────────────────────────────────────────

export function ProjectsListPage() {
  const { streamingMode } = useStreamingMode();
  const displayTaskVaultText = (value: string, prefix = "item") => withStreamingObfuscation(value, streamingMode, prefix);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [dragProjectId, setDragProjectId] = useState<number | null>(null);
  const queryClient = useQueryClient();
  const nav = useNavigate();
  const { moveProject } = useProjectReorder<Project>(["projects", "priority-list"]);

  const { data = [] } = useQuery({
    queryKey: ["projects", "priority-list"],
    queryFn: () => apiGet<Project[]>("/api/projects?order=priority"),
  });

  const { data: pagesMap } = useQuery({
    queryKey: ["projects-pages"],
    queryFn: async () => {
      const results: Record<number, ProjectPage> = {};
      await Promise.all(
        data.map(async (p) => {
          try {
            results[p.id] = await apiGet<ProjectPage>(`/api/projects/${p.id}/page`);
          } catch {
            results[p.id] = { blocks: [] };
          }
        }),
      );
      return results;
    },
    enabled: data.length > 0,
  });

  const createProject = useMutation({
    mutationFn: () => apiPost<Project>("/api/projects", { title, description }),
    onSuccess: (project) => {
      setTitle("");
      setDescription("");
      setCreating(false);
      queryClient.invalidateQueries({ queryKey: ["projects", "priority-list"] });
      nav(`/projects/${project.id}`);
    },
  });

  return (
    <div className="space-y-6 stagger-children">
      <PageHeader
        title="TaskVault"
        description={`${data.length} project${data.length !== 1 ? "s" : ""}`}
        actions={
          <Button onClick={() => setCreating((v) => !v)} size="md">
            <Plus size={14} />
            New project
          </Button>
        }
      />

      {/* Create form */}
      {creating && (
        <div className="rounded-xl border border-primary/25 bg-primary/5 p-4 animate-fade-up">
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground mb-3">
            New project
          </p>
          <div className="space-y-2">
            <Input
              autoFocus
              placeholder="Project title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && title.trim()) createProject.mutate();
              }}
            />
            <Input
              placeholder="Description (optional)"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
            <div className="flex items-center gap-2 pt-1">
              <Button
                disabled={!title.trim() || createProject.isPending}
                onClick={() => createProject.mutate()}
              >
                {createProject.isPending ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <Plus size={13} />
                )}
                Create project
              </Button>
              <Button variant="ghost" onClick={() => setCreating(false)}>
                Cancel
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Project grid */}
      {data.length === 0 ? (
        <div className="rounded-xl border border-border border-dashed bg-card p-12 text-center">
          <FolderKanban size={32} className="text-muted-foreground/30 mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">No projects yet</p>
          <p className="text-xs text-muted-foreground/60 mt-1">
            Create a project to start tracking tasks
          </p>
        </div>
      ) : (
        <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
          {data.map((project) => {
            const page = pagesMap?.[project.id];
            const tasks = page ? parseTasks(page.blocks) : [];
            const meta = page ? parseMeta(page.blocks) : null;
            const done = tasks.filter((t) => t.status === "done").length;
            const statusCfg =
              meta ? PROJECT_STATUS_CONFIG[meta.project_status] : PROJECT_STATUS_CONFIG.active;

            return (
              <div
                key={project.id}
                draggable
                onDragStart={() => setDragProjectId(project.id)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => {
                  if (dragProjectId !== null) moveProject(dragProjectId, project.id);
                  setDragProjectId(null);
                }}
                className="group rounded-xl border border-border bg-card p-4 hover:border-primary/25 transition-all duration-150 block"
              >
                <Link to={`/projects/${project.id}`} className="block">
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <h3 className="font-semibold text-foreground group-hover:text-primary transition-colors truncate">
                      {displayTaskVaultText(project.title, "project")}
                    </h3>
                    <div className="flex items-center gap-1">
                      <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">#{project.priority_rank ?? "-"}</span>
                      {meta && (
                        <span
                          className={`shrink-0 rounded-md border px-1.5 py-0.5 text-[10px] font-medium ${statusCfg.cls}`}
                        >
                          {statusCfg.label}
                        </span>
                      )}
                      <ArrowUpDown size={12} className="text-muted-foreground/70" />
                    </div>
                  </div>

                  {project.description && (
                    <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2 mb-3">
                      {displayTaskVaultText(project.description, "desc")}
                    </p>
                  )}

                  {tasks.length > 0 && (
                    <div className="space-y-1.5">
                      {/* Progress bar */}
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-1 rounded-full bg-border overflow-hidden">
                          <div
                            className="h-full bg-success rounded-full transition-all"
                            style={{
                              width: `${tasks.length ? (done / tasks.length) * 100 : 0}%`,
                            }}
                          />
                        </div>
                        <span className="text-[10px] text-muted-foreground font-mono shrink-0">
                          {done}/{tasks.length}
                        </span>
                      </div>
                      {/* Status breakdown */}
                      <div className="flex items-center gap-2 flex-wrap">
                        {(["in_progress", "blocked"] as TaskStatus[])
                          .filter((s) => tasks.some((t) => t.status === s))
                          .map((s) => {
                            const count = tasks.filter((t) => t.status === s).length;
                            const cfg = STATUS_CONFIG[s];
                            return (
                              <span
                                key={s}
                                className={`text-[10px] font-medium ${cfg.cls} flex items-center gap-1`}
                              >
                                <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
                                {count} {cfg.label.toLowerCase()}
                              </span>
                            );
                          })}
                      </div>
                    </div>
                  )}

                  {tasks.length === 0 && (
                    <p className="text-[11px] text-muted-foreground/50">No tasks yet</p>
                  )}

                  <div className="mt-3 pt-3 border-t border-border/50 text-[10px] text-muted-foreground/50">
                    Updated {relativeTime(project.updated_at)}
                  </div>
                </Link>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Project detail page ──────────────────────────────────────────────────────

type ActiveTab = "tasks" | "notes";
type SortMode = "priority" | "status" | "created";
type FilterStatus = "all" | TaskStatus;

export function ProjectDetailPage() {
  const { streamingMode } = useStreamingMode();
  const displayTaskVaultText = (value: string, prefix = "item") => withStreamingObfuscation(value, streamingMode, prefix);
  const { id } = useParams();
  const queryClient = useQueryClient();

  const { data: project } = useQuery({
    queryKey: ["project", id],
    queryFn: () => apiGet<Project>(`/api/projects/${id}`),
    enabled: Boolean(id),
  });

  const { data: page } = useQuery({
    queryKey: ["project-page", id],
    queryFn: () => apiGet<ProjectPage>(`/api/projects/${id}/page`),
    enabled: Boolean(id),
  });
  const { data: topTasks = [] } = useQuery({
    queryKey: ["project-top-tasks", id],
    queryFn: () => apiGet<ProjectTaskPreview[]>(`/api/projects/${id}/top-tasks?limit=5`),
    enabled: Boolean(id),
  });

  const rawBlocks: Array<Record<string, unknown>> = page?.blocks ?? [];
  const meta = parseMeta(rawBlocks);
  const tasks = parseTasks(rawBlocks);
  const notes = parseNotes(rawBlocks);

  const [activeTab, setActiveTab] = useState<ActiveTab>("tasks");
  const [sortMode, setSortMode] = useState<SortMode>("priority");
  const [filterStatus, setFilterStatus] = useState<FilterStatus>("all");

  // Task creation
  const [newTaskContent, setNewTaskContent] = useState("");
  const [newTaskPriority, setNewTaskPriority] = useState<TaskPriority>("medium");

  // Note creation
  const [newNoteType, setNewNoteType] = useState<"note" | "heading">("note");
  const [newNoteContent, setNewNoteContent] = useState("");

  const savePage = useMutation({
    mutationFn: (blocks: Block[]) =>
      apiPut<ProjectPage>(`/api/projects/${id}/page`, { blocks }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-page", id] });
      queryClient.invalidateQueries({ queryKey: ["projects-pages"] });
    },
  });
  const patchTopTask = useMutation({
    mutationFn: ({ taskId, title, completed }: { taskId: string; title?: string; completed?: boolean }) =>
      apiPatch(`/api/projects/tasks/${taskId}`, { project_id: Number(id), title, completed }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-top-tasks", id] });
      queryClient.invalidateQueries({ queryKey: ["project-page", id] });
      queryClient.invalidateQueries({ queryKey: ["projects-pages"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-top-projects"] });
    },
  });
  const [editingTopTaskId, setEditingTopTaskId] = useState<string | null>(null);
  const [editingTopTaskValue, setEditingTopTaskValue] = useState("");

  const saveBlocks = (newMeta: MetaBlock, newTasks: TaskBlock[], newNotes: NoteBlock[]) => {
    const blocks = rebuildBlocks(rawBlocks, newMeta, newTasks, newNotes);
    savePage.mutate(blocks);
  };

  // ── Task actions ──────────────────────────────────────────────────────────

  const addTask = () => {
    if (!newTaskContent.trim()) return;
    const task: TaskBlock = {
      id: genId(),
      type: "task",
      content: newTaskContent.trim(),
      status: "todo",
      priority: newTaskPriority,
      created_at: new Date().toISOString(),
    };
    setNewTaskContent("");
    saveBlocks(meta, [...tasks, task], notes);
  };

  const updateTask = (id: string, patch: Partial<TaskBlock>) => {
    saveBlocks(
      meta,
      tasks.map((t) => (t.id === id ? { ...t, ...patch } : t)),
      notes,
    );
  };

  const deleteTask = (id: string) => {
    saveBlocks(
      meta,
      tasks.filter((t) => t.id !== id),
      notes,
    );
  };

  const toggleTaskStatus = (task: TaskBlock) => {
    const next: TaskStatus =
      task.status === "done"
        ? "todo"
        : task.status === "todo"
          ? "in_progress"
          : task.status === "in_progress"
            ? "done"
            : "todo";
    updateTask(task.id, { status: next });
  };

  // ── Note actions ──────────────────────────────────────────────────────────

  const addNote = () => {
    if (!newNoteContent.trim()) return;
    const note: NoteBlock = {
      id: genId(),
      type: newNoteType,
      content: newNoteContent.trim(),
      created_at: new Date().toISOString(),
    };
    setNewNoteContent("");
    saveBlocks(meta, tasks, [...notes, note]);
  };

  const deleteNote = (id: string) => {
    saveBlocks(
      meta,
      tasks,
      notes.filter((n) => n.id !== id),
    );
  };

  const updateNoteContent = (id: string, content: string) => {
    saveBlocks(
      meta,
      tasks,
      notes.map((n) => (n.id === id ? { ...n, content } : n)),
    );
  };

  // ── Project status ────────────────────────────────────────────────────────

  const setProjectStatus = (status: ProjectStatus) => {
    saveBlocks({ ...meta, project_status: status }, tasks, notes);
  };

  // ── Filtered & sorted tasks ───────────────────────────────────────────────

  const filteredTasks = tasks.filter(
    (t) => filterStatus === "all" || t.status === filterStatus,
  );

  const PRIORITY_ORDER: Record<TaskPriority, number> = {
    critical: 0,
    high: 1,
    medium: 2,
    low: 3,
  };
  const STATUS_ORDER: Record<TaskStatus, number> = {
    blocked: 0,
    in_progress: 1,
    todo: 2,
    done: 3,
  };

  const sortedTasks = [...filteredTasks].sort((a, b) => {
    if (sortMode === "priority") return PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority];
    if (sortMode === "status") return STATUS_ORDER[a.status] - STATUS_ORDER[b.status];
    return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
  });

  const donePct = tasks.length ? Math.round((tasks.filter((t) => t.status === "done").length / tasks.length) * 100) : 0;

  return (
    <div className="space-y-6 stagger-children">
      {/* Back nav */}
      <Link
        to="/projects"
        className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <ChevronLeft size={13} />
        TaskVault
      </Link>

      {/* Project header */}
      <PageHeader
        title={project?.title ? displayTaskVaultText(project.title, "project") : "…"}
        description={project?.description ? displayTaskVaultText(project.description, "desc") : undefined}
        actions={
          <div className="flex items-center gap-1.5 flex-wrap shrink-0">
            <Link to={`/projects/${id}/workspace`}>
              <Button size="sm" variant="outline">
                Workspace
              </Button>
            </Link>
            {(Object.keys(PROJECT_STATUS_CONFIG) as ProjectStatus[]).map((s) => {
              const cfg = PROJECT_STATUS_CONFIG[s];
              const active = meta.project_status === s;
              return (
                <button
                  key={s}
                  onClick={() => setProjectStatus(s)}
                  className={`rounded-md border px-2.5 py-1 text-[11px] font-medium transition-all ${
                    active
                      ? cfg.cls
                      : "border-border text-muted-foreground hover:border-border/80 hover:text-foreground"
                  }`}
                >
                  {cfg.label}
                </button>
              );
            })}
          </div>
        }
      >

        {/* Progress */}
        {tasks.length > 0 && (
          <div className="mt-4 space-y-1.5">
            <div className="flex items-center justify-between text-[11px] text-muted-foreground">
              <span>
                {tasks.filter((t) => t.status === "done").length} of {tasks.length} tasks done
              </span>
              <span className="font-mono">{donePct}%</span>
            </div>
            <div className="h-1.5 rounded-full bg-border overflow-hidden">
              <div
                className="h-full bg-success rounded-full transition-all duration-500"
                style={{ width: `${donePct}%` }}
              />
            </div>
          </div>
        )}
        <div className="mt-4 rounded-lg border border-border/60 bg-background/30 p-3">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-xs font-semibold text-foreground">Top Tasks</p>
            <button
              className="text-xs text-primary hover:underline"
              onClick={() => setActiveTab("tasks")}
            >
              Open full task list
            </button>
          </div>
          <div className="space-y-1.5">
            {topTasks.map((task) => (
              <div key={task.id} className="flex items-center gap-2 rounded border border-border/70 bg-card px-2 py-1.5">
                <input
                  type="checkbox"
                  className="h-3.5 w-3.5"
                  checked={task.status === "done"}
                  onChange={() => patchTopTask.mutate({ taskId: task.id, completed: task.status !== "done" })}
                />
                {editingTopTaskId === task.id ? (
                  <input
                    autoFocus
                    value={editingTopTaskValue}
                    onChange={(e) => setEditingTopTaskValue(e.target.value)}
                    onBlur={() => {
                      patchTopTask.mutate({ taskId: task.id, title: editingTopTaskValue || task.content });
                      setEditingTopTaskId(null);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        patchTopTask.mutate({ taskId: task.id, title: editingTopTaskValue || task.content });
                        setEditingTopTaskId(null);
                      }
                      if (e.key === "Escape") setEditingTopTaskId(null);
                    }}
                    className="min-w-0 flex-1 rounded border border-border bg-input px-2 py-0.5 text-xs text-foreground"
                  />
                ) : (
                  <button
                    className="min-w-0 flex-1 truncate text-left text-xs text-foreground hover:text-primary"
                    onClick={() => {
                      if (streamingMode) return;
                      setEditingTopTaskId(task.id);
                      setEditingTopTaskValue(task.content);
                    }}
                  >
                    {displayTaskVaultText(task.content, "task")}
                  </button>
                )}
                <span className="rounded bg-border/40 px-1.5 py-0.5 text-[10px] text-muted-foreground">{task.status}</span>
              </div>
            ))}
            {topTasks.length === 0 ? <p className="text-xs text-muted-foreground">No open tasks.</p> : null}
          </div>
        </div>
      </PageHeader>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-border pb-0">
        <TabButton
          active={activeTab === "tasks"}
          onClick={() => setActiveTab("tasks")}
          icon={<ListTodo size={13} />}
          label={`Tasks${tasks.length ? ` (${tasks.length})` : ""}`}
        />
        <TabButton
          active={activeTab === "notes"}
          onClick={() => setActiveTab("notes")}
          icon={<StickyNote size={13} />}
          label={`Notes${notes.length ? ` (${notes.length})` : ""}`}
        />
      </div>

      {/* Tasks tab */}
      {activeTab === "tasks" && (
        <div className="space-y-2.5 animate-fade-up">
          {/* Toolbar */}
          <div className="flex items-center gap-2 flex-wrap">
            {/* Filter */}
            <div className="flex items-center gap-1 rounded-lg border border-border bg-card p-1">
              <Filter size={11} className="text-muted-foreground ml-1.5" />
              {(["all", "todo", "in_progress", "done", "blocked"] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setFilterStatus(s)}
                  className={`rounded-md px-2 py-0.5 text-[11px] font-medium transition-colors ${
                    filterStatus === s
                      ? "bg-primary/15 text-primary"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {s === "all" ? "All" : STATUS_CONFIG[s].label}
                </button>
              ))}
            </div>

            {/* Sort */}
            <button
              onClick={() =>
                setSortMode((m) =>
                  m === "priority" ? "status" : m === "status" ? "created" : "priority",
                )
              }
              className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-2.5 py-1.5 text-[11px] text-muted-foreground hover:text-foreground transition-colors"
            >
              <ArrowUpDown size={11} />
              Sort: {sortMode}
            </button>

            <div className="ml-auto text-[11px] text-muted-foreground">
              {filteredTasks.length} task{filteredTasks.length !== 1 ? "s" : ""}
            </div>
          </div>

          {/* Task list */}
          {sortedTasks.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border bg-card p-8 text-center">
              <ListTodo size={24} className="text-muted-foreground/20 mx-auto mb-2" />
              <p className="text-sm text-muted-foreground">
                {filterStatus !== "all" ? "No matching tasks" : "No tasks yet"}
              </p>
            </div>
          ) : (
            <div className="space-y-1.5">
              {sortedTasks.map((task) => (
                <TaskRow
                  key={task.id}
                  task={task}
                  streamingMode={streamingMode}
                  onToggle={() => toggleTaskStatus(task)}
                  onDelete={() => deleteTask(task.id)}
                  onUpdatePriority={(p) => updateTask(task.id, { priority: p })}
                  onUpdateStatus={(s) => updateTask(task.id, { status: s })}
                  onUpdateContent={(c) => updateTask(task.id, { content: c })}
                />
              ))}
            </div>
          )}

          {/* New task input */}
          <div className="rounded-xl border border-border bg-card p-3">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground mb-2.5">
              Add task
            </p>
            <div className="flex items-center gap-2">
              <Input
                placeholder="Task description…"
                value={newTaskContent}
                onChange={(e) => setNewTaskContent(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") addTask();
                }}
                className="flex-1"
              />
              {/* Priority picker */}
              <div className="flex items-center gap-1 rounded-lg border border-border bg-input p-1 shrink-0">
                <Flag size={11} className="text-muted-foreground ml-1" />
                {(["low", "medium", "high", "critical"] as TaskPriority[]).map((p) => {
                  const cfg = PRIORITY_CONFIG[p];
                  return (
                    <button
                      key={p}
                      onClick={() => setNewTaskPriority(p)}
                      title={cfg.label}
                      className={`w-5 h-5 rounded-md flex items-center justify-center transition-colors ${
                        newTaskPriority === p ? "bg-white/10" : "hover:bg-white/5"
                      }`}
                    >
                      <span
                        className={`w-2 h-2 rounded-full ${cfg.dot} ${
                          newTaskPriority === p ? "opacity-100" : "opacity-40"
                        }`}
                      />
                    </button>
                  );
                })}
              </div>
              <Button
                onClick={addTask}
                disabled={!newTaskContent.trim() || savePage.isPending}
              >
                <Plus size={13} />
                Add
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Notes tab */}
      {activeTab === "notes" && (
        <div className="space-y-2.5 animate-fade-up">
          {/* Existing notes */}
          {notes.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border bg-card p-8 text-center">
              <StickyNote size={24} className="text-muted-foreground/20 mx-auto mb-2" />
              <p className="text-sm text-muted-foreground">No notes yet</p>
            </div>
          ) : (
            <div className="space-y-2">
              {notes.map((note) => (
                <NoteRow
                  key={note.id}
                  note={note}
                  streamingMode={streamingMode}
                  onDelete={() => deleteNote(note.id)}
                  onUpdate={(content) => updateNoteContent(note.id, content)}
                />
              ))}
            </div>
          )}

          {/* New note input */}
          <div className="rounded-xl border border-border bg-card p-3">
            <div className="flex items-center gap-2 mb-2.5">
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                Add note
              </p>
              <div className="ml-auto flex items-center gap-1 rounded-lg border border-border p-1">
                {(["note", "heading"] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => setNewNoteType(t)}
                    className={`rounded-md px-2 py-0.5 text-[11px] font-medium capitalize transition-colors ${
                      newNoteType === t
                        ? "bg-white/10 text-foreground"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>
            <Textarea
              placeholder={newNoteType === "heading" ? "Section heading…" : "Write a note…"}
              value={newNoteContent}
              onChange={(e) => setNewNoteContent(e.target.value)}
              rows={3}
            />
            <div className="mt-2 flex justify-end">
              <Button
                onClick={addNote}
                disabled={!newNoteContent.trim() || savePage.isPending}
              >
                <Plus size={13} />
                Add note
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Task row ─────────────────────────────────────────────────────────────────

function TaskRow({
  task,
  streamingMode,
  onToggle,
  onDelete,
  onUpdatePriority,
  onUpdateStatus,
  onUpdateContent,
}: {
  task: TaskBlock;
  streamingMode: boolean;
  onToggle: () => void;
  onDelete: () => void;
  onUpdatePriority: (p: TaskPriority) => void;
  onUpdateStatus: (s: TaskStatus) => void;
  onUpdateContent: (c: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(task.content);
  const [showActions, setShowActions] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const commitEdit = () => {
    if (editValue.trim() && editValue !== task.content) {
      onUpdateContent(editValue.trim());
    } else {
      setEditValue(task.content);
    }
    setEditing(false);
  };

  const statusCfg = STATUS_CONFIG[task.status];
  const priorityCfg = PRIORITY_CONFIG[task.priority];
  const StatusIcon = statusCfg.icon;

  return (
    <div
      className={`group flex items-center gap-2.5 rounded-xl border p-2.5 transition-all duration-150 ${
        task.status === "done"
          ? "border-border/40 bg-card/50 opacity-60"
          : "border-border bg-card hover:border-border/80"
      }`}
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
    >
      {/* Status toggle */}
      <button
        onClick={onToggle}
        className={`shrink-0 transition-colors ${statusCfg.cls} hover:opacity-80`}
        title={`Status: ${statusCfg.label}. Click to advance`}
      >
        {task.status === "in_progress" ? (
          <StatusIcon size={16} className="animate-spin" style={{ animationDuration: "2s" }} />
        ) : (
          <StatusIcon size={16} />
        )}
      </button>

      {/* Content */}
      {editing && !streamingMode ? (
        <input
          ref={inputRef}
          className="flex-1 bg-transparent text-sm text-foreground focus:outline-none border-b border-primary/50"
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onBlur={commitEdit}
          onKeyDown={(e) => {
            if (e.key === "Enter") commitEdit();
            if (e.key === "Escape") {
              setEditValue(task.content);
              setEditing(false);
            }
          }}
        />
      ) : (
        <span
          className={`flex-1 text-sm cursor-pointer select-none ${
            task.status === "done" ? "line-through text-muted-foreground" : "text-foreground"
          }`}
          onDoubleClick={() => {
            if (!streamingMode) setEditing(true);
          }}
          title="Double-click to edit"
        >
          {withStreamingObfuscation(task.content, streamingMode, "task")}
        </span>
      )}

      {/* Priority dot */}
      <span
        className={`shrink-0 text-[10px] font-medium ${priorityCfg.cls} flex items-center gap-1`}
        title={`Priority: ${priorityCfg.label}`}
      >
        <span className={`w-1.5 h-1.5 rounded-full ${priorityCfg.dot}`} />
        <span className="hidden sm:inline">{priorityCfg.label}</span>
      </span>

      {/* Actions (hover) */}
      <div
        className={`flex items-center gap-1 transition-opacity shrink-0 ${
          showActions ? "opacity-100" : "opacity-0"
        }`}
      >
        {/* Status menu */}
        <div className="relative">
          <ActionMenu
            trigger={
              <button
                className="flex items-center gap-1 rounded-md px-1.5 py-1 text-[10px] font-medium text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors"
                title="Change status"
              >
                <MoreHorizontal size={12} />
              </button>
            }
          >
            <div className="p-1 min-w-[140px]">
              <p className="px-2 py-1 text-[9px] uppercase tracking-widest text-muted-foreground/60 font-semibold">
                Status
              </p>
              {(Object.keys(STATUS_CONFIG) as TaskStatus[]).map((s) => {
                const cfg = STATUS_CONFIG[s];
                const SIcon = cfg.icon;
                return (
                  <button
                    key={s}
                    onClick={() => onUpdateStatus(s)}
                    className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs transition-colors ${
                      task.status === s
                        ? `${cfg.cls} bg-white/5`
                        : "text-muted-foreground hover:text-foreground hover:bg-white/5"
                    }`}
                  >
                    <SIcon size={12} />
                    {cfg.label}
                    {task.status === s && <Check size={10} className="ml-auto" />}
                  </button>
                );
              })}
              <div className="my-1 h-px bg-border" />
              <p className="px-2 py-1 text-[9px] uppercase tracking-widest text-muted-foreground/60 font-semibold">
                Priority
              </p>
              {(Object.keys(PRIORITY_CONFIG) as TaskPriority[]).map((p) => {
                const cfg = PRIORITY_CONFIG[p];
                return (
                  <button
                    key={p}
                    onClick={() => onUpdatePriority(p)}
                    className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs transition-colors ${
                      task.priority === p
                        ? `${cfg.cls} bg-white/5`
                        : "text-muted-foreground hover:text-foreground hover:bg-white/5"
                    }`}
                  >
                    <span className={`w-2 h-2 rounded-full ${cfg.dot}`} />
                    {cfg.label}
                    {task.priority === p && <Check size={10} className="ml-auto" />}
                  </button>
                );
              })}
            </div>
          </ActionMenu>
        </div>

        <button
          onClick={onDelete}
          className="rounded-md p-1 text-muted-foreground hover:text-danger hover:bg-danger/10 transition-colors"
          title="Delete task"
        >
          <Trash2 size={12} />
        </button>
      </div>
    </div>
  );
}

// ── Note row ─────────────────────────────────────────────────────────────────

function NoteRow({
  note,
  streamingMode,
  onDelete,
  onUpdate,
}: {
  note: NoteBlock;
  streamingMode: boolean;
  onDelete: () => void;
  onUpdate: (content: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(note.content);

  const commit = () => {
    if (value.trim() !== note.content) onUpdate(value.trim() || note.content);
    setEditing(false);
  };

  return (
    <div className="group rounded-xl border border-border bg-card p-3.5 transition-all hover:border-border/80">
      {editing && !streamingMode ? (
        <Textarea
          autoFocus
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onBlur={commit}
          rows={note.type === "heading" ? 1 : 3}
          className={note.type === "heading" ? "font-display text-lg font-bold" : "text-sm"}
        />
      ) : (
        <div className="flex items-start gap-2">
          {note.type === "heading" ? (
            <h3
                className="flex-1 font-display text-lg font-bold text-foreground cursor-pointer"
                onDoubleClick={() => {
                  if (!streamingMode) setEditing(true);
                }}
                title="Double-click to edit"
              >
                {withStreamingObfuscation(note.content, streamingMode, "note")}
              </h3>
            ) : (
              <p
                className="flex-1 text-sm text-foreground/85 leading-relaxed cursor-pointer whitespace-pre-wrap"
                onDoubleClick={() => {
                  if (!streamingMode) setEditing(true);
                }}
                title="Double-click to edit"
              >
                {withStreamingObfuscation(note.content, streamingMode, "note")}
              </p>
            )}
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
            <button
              onClick={onDelete}
              className="rounded-md p-1 text-muted-foreground hover:text-danger hover:bg-danger/10 transition-colors"
            >
              <Trash2 size={12} />
            </button>
          </div>
        </div>
      )}
      <div className="mt-1.5 flex items-center gap-1.5 text-[10px] text-muted-foreground/40">
        {note.type === "heading" ? <Tag size={9} /> : <StickyNote size={9} />}
        {note.type} · {relativeTime(note.created_at)}
      </div>
    </div>
  );
}

// ── Tab button ────────────────────────────────────────────────────────────────

function TabButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium border-b-2 transition-all duration-150 ${
        active
          ? "border-primary text-primary"
          : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}

// ── Action menu (dropdown) ────────────────────────────────────────────────────

function ActionMenu({
  trigger,
  children,
}: {
  trigger: React.ReactNode;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <div onClick={() => setOpen((v) => !v)}>{trigger}</div>
      {open && (
        <div
          className="absolute right-0 top-full mt-1 z-50 rounded-xl border border-border bg-card shadow-2xl shadow-black/40 animate-fade-up"
          onClick={() => setOpen(false)}
        >
          {children}
        </div>
      )}
    </div>
  );
}

// ── Utilities ────────────────────────────────────────────────────────────────

function relativeTime(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}
