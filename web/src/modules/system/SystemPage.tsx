import { useQuery } from "@tanstack/react-query";
import { Boxes } from "lucide-react";
import { Link } from "react-router-dom";

import { apiGet } from "../../shared/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "../../shared/components/ui/card";
import { PageHeader } from "../../shared/components/ui/page-header";

export function SystemPage() {
  const { data } = useQuery({ queryKey: ["config"], queryFn: () => apiGet<{ runs_directory: string; poll_interval_seconds: number }>("/api/config") });
  const installedQuery = useQuery({ queryKey: ["module-system", "installed"], queryFn: () => apiGet<{ installed: string[] }>("/api/module-system/installed") });

  return (
    <div className="space-y-4">
      <PageHeader compact title="System" description="Runtime configuration, service defaults, and module management." />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>System Settings</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-muted-foreground">
            <p>Runs directory: {data?.runs_directory ?? "-"}</p>
            <p>Poll interval: {data?.poll_interval_seconds ?? "-"}s</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Optional Modules</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <div className="flex items-center gap-2 text-foreground">
              <Boxes size={16} />
              <span className="font-medium">Installed add-ons: {installedQuery.data?.installed.length ?? 0}</span>
            </div>
            <p>Use the module catalog to install IdeaVault, TopicInsights, IdeaFactory, Discord Control, WebAgent, Skilled Agents, Trends Researcher, and ScheduleOps.</p>
            <Link to="/settings/modules" className="inline-flex rounded-lg border border-primary/30 bg-primary/10 px-3 py-2 text-sm font-medium text-primary hover:bg-primary/15">
              Open Add Modules
            </Link>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
