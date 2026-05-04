import { useMemo, useState } from "react";

import {
  useMemoryBrief,
  useMemoryCandidates,
  useMemoryCompact,
  useMemoryHealth,
  useMemoryRelationships,
  useMemorySearch,
  useMemorySessions,
  useMemorySettings,
} from "../../shared/api/hooks";
import { Button } from "../../shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../shared/components/ui/card";
import { Input, Textarea } from "../../shared/components/ui/input";
import { PageHeader } from "../../shared/components/ui/page-header";
import { Tabs } from "../../shared/components/ui/tabs";

function pretty(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function MemoryPage() {
  const [activeTab, setActiveTab] = useState("overview");
  const [query, setQuery] = useState("");
  const [nodeId, setNodeId] = useState("");
  const [repoPath, setRepoPath] = useState("");
  const [searchLimit, setSearchLimit] = useState(30);
  const [includeDocs, setIncludeDocs] = useState(false);
  const [rerank, setRerank] = useState(false);

  const health = useMemoryHealth();
  const settings = useMemorySettings();
  const sessions = useMemorySessions({ limit: 40, q: query });
  const candidates = useMemoryCandidates({ limit: 40, q: query });
  const relationships = useMemoryRelationships({ limit: 40, q: query });
  const search = useMemorySearch({
    query,
    node_id: nodeId || undefined,
    repo_path: repoPath || undefined,
    limit: searchLimit,
    include_docs: includeDocs,
    include_knowledge: true,
    rerank,
  });
  const brief = useMemoryBrief();
  const compact = useMemoryCompact();

  const counts = useMemo(() => {
    return {
      sessions: sessions.data?.items?.length ?? 0,
      candidates: candidates.data?.items?.length ?? 0,
      relationships: relationships.data?.items?.length ?? 0,
    };
  }, [sessions.data?.items?.length, candidates.data?.items?.length, relationships.data?.items?.length]);

  const errorMessages = [
    health.error instanceof Error ? `health: ${health.error.message}` : "",
    settings.error instanceof Error ? `settings: ${settings.error.message}` : "",
    sessions.error instanceof Error ? `sessions: ${sessions.error.message}` : "",
    candidates.error instanceof Error ? `candidates: ${candidates.error.message}` : "",
    relationships.error instanceof Error ? `relationships: ${relationships.error.message}` : "",
  ].filter(Boolean);

  return (
    <div className="space-y-4">
      <PageHeader compact title="Memory">
        <p className="text-sm text-muted-foreground">Shared NFS memory control plane with compact retrieval briefs and compaction queue.</p>
      </PageHeader>

      <Tabs
        active={activeTab}
        onChange={setActiveTab}
        tabs={[
          { id: "overview", label: "Memory Overview" },
          { id: "candidates", label: "Candidate Queue" },
          { id: "sessions", label: "Session Index" },
          { id: "relationships", label: "Relationships" },
          { id: "search", label: "Memory Search" },
        ]}
      />

      {errorMessages.length ? (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle>Memory API Errors</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-xs text-red-600">
            {errorMessages.map((msg) => (
              <p key={msg}>{msg}</p>
            ))}
          </CardContent>
        </Card>
      ) : null}

      {activeTab === "overview" ? (
        <div className="grid gap-4 xl:grid-cols-[2fr,1fr]">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle>Memory Health</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs">
              <pre className="overflow-auto rounded border border-border p-3">{pretty(health.data ?? { loading: true })}</pre>
              <pre className="overflow-auto rounded border border-border p-3">{pretty(settings.data ?? { loading: true })}</pre>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle>Queue Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs">
              <p>Sessions: {counts.sessions}</p>
              <p>Candidates: {counts.candidates}</p>
              <p>Relationships: {counts.relationships}</p>
              <Button
                type="button"
                size="sm"
                onClick={() => void compact.mutateAsync({ limit: 200 })}
                disabled={compact.isPending}
              >
                Trigger Compaction
              </Button>
              {compact.data ? <pre className="overflow-auto rounded border border-border p-2">{pretty(compact.data)}</pre> : null}
            </CardContent>
          </Card>
        </div>
      ) : null}

      {activeTab === "candidates" ? (
        <Card>
          <CardHeader className="pb-2"><CardTitle>Candidate Queue</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-xs">
            {(candidates.data?.items ?? []).map((row, idx) => (
              <pre key={idx} className="overflow-auto rounded border border-border p-2">{pretty(row)}</pre>
            ))}
            {candidates.data && (candidates.data.items ?? []).length === 0 ? <p className="text-muted-foreground">No candidates yet.</p> : null}
          </CardContent>
        </Card>
      ) : null}

      {activeTab === "sessions" ? (
        <Card>
          <CardHeader className="pb-2"><CardTitle>Session Index</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-xs">
            {(sessions.data?.items ?? []).map((row, idx) => (
              <pre key={idx} className="overflow-auto rounded border border-border p-2">{pretty(row)}</pre>
            ))}
            {sessions.data && (sessions.data.items ?? []).length === 0 ? <p className="text-muted-foreground">No indexed sessions yet.</p> : null}
          </CardContent>
        </Card>
      ) : null}

      {activeTab === "relationships" ? (
        <Card>
          <CardHeader className="pb-2"><CardTitle>Relationships</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-xs">
            {(relationships.data?.items ?? []).map((row, idx) => (
              <pre key={idx} className="overflow-auto rounded border border-border p-2">{pretty(row)}</pre>
            ))}
            {relationships.data && (relationships.data.items ?? []).length === 0 ? <p className="text-muted-foreground">No relationships yet.</p> : null}
          </CardContent>
        </Card>
      ) : null}

      {activeTab === "search" ? (
        <Card>
          <CardHeader className="pb-2"><CardTitle>Memory Search</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-xs">
            <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
              <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="query" />
              <Input value={nodeId} onChange={(e) => setNodeId(e.target.value)} placeholder="node_id (optional)" />
              <Input value={repoPath} onChange={(e) => setRepoPath(e.target.value)} placeholder="repo_path (optional)" />
              <Input value={String(searchLimit)} onChange={(e) => setSearchLimit(Number(e.target.value) || 30)} placeholder="limit" />
            </div>
            <div className="flex items-center gap-3">
              <label className="inline-flex items-center gap-2"><input type="checkbox" checked={includeDocs} onChange={(e) => setIncludeDocs(e.target.checked)} /> include docs</label>
              <label className="inline-flex items-center gap-2"><input type="checkbox" checked={rerank} onChange={(e) => setRerank(e.target.checked)} /> rerank</label>
              <Button type="button" size="sm" onClick={() => void search.mutateAsync()} disabled={search.isPending}>Search</Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void brief.mutateAsync({ query, node_id: nodeId || undefined, repo_path: repoPath || undefined, max_chars: 1800, rerank })}
                disabled={brief.isPending}
              >
                Generate Brief
              </Button>
            </div>
            {search.data ? <pre className="overflow-auto rounded border border-border p-2">{pretty(search.data)}</pre> : null}
            {brief.data ? <Textarea readOnly value={brief.data.brief} rows={14} /> : null}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
