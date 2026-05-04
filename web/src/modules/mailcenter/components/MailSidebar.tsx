import { Card, CardContent, CardHeader, CardTitle } from "../../../shared/components/ui/card";
import type { MailCenterOverview } from "../../../shared/api/types";
import { fmtTs } from "./mailUtils";

export function MailSidebar({
  overview,
  folder,
  onSelectFolder,
}: {
  overview: MailCenterOverview | undefined;
  folder: string;
  onSelectFolder: (folderKey: string) => void;
}) {
  return (
    <Card className="h-fit">
      <CardHeader className="pb-2"><CardTitle>Mailboxes</CardTitle></CardHeader>
      <CardContent className="space-y-2">
        {(overview?.folders ?? []).map((entry) => {
          const active = folder === entry.key;
          return (
            <button
              key={entry.key}
              type="button"
              onClick={() => onSelectFolder(entry.key)}
              className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-sm transition-colors ${active ? "border-primary/50 bg-primary/12 text-foreground" : "border-border bg-background/30 text-muted-foreground hover:text-foreground"}`}
            >
              <span>{entry.label}</span>
              <span className="text-xs">{entry.count}</span>
            </button>
          );
        })}
        <div className="mt-3 rounded-lg border border-border bg-background/20 p-3 text-xs text-muted-foreground">
          <p className="font-medium text-foreground">Subsystem</p>
          <p className="mt-1 capitalize">{overview?.subsystem.status ?? "unknown"}</p>
          <p className="mt-1">Last activity: {fmtTs(overview?.subsystem.last_activity_at)}</p>
        </div>
      </CardContent>
    </Card>
  );
}
