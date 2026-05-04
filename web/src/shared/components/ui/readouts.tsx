import { ReactNode } from "react";

import { cn } from "../../lib/utils";

type Primitive = string | number | boolean | null | undefined;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function humanizeKey(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (m) => m.toUpperCase());
}

function formatPrimitive(value: Primitive): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "-";
  return String(value);
}

function summarizeValue(value: unknown): string {
  if (Array.isArray(value)) return `${value.length} items`;
  if (isRecord(value)) return `${Object.keys(value).length} fields`;
  return formatPrimitive(value as Primitive);
}

function flattenObjectForDisplay(input: Record<string, unknown>): Array<{ label: string; value: string }> {
  return Object.entries(input).map(([key, value]) => ({
    label: humanizeKey(key),
    value: summarizeValue(value),
  }));
}

export function KeyValueList({
  rows,
  className,
}: {
  rows: Array<{ label: string; value: ReactNode }>;
  className?: string;
}) {
  return (
    <div className={cn("grid gap-2", className)}>
      {rows.map((row) => (
        <div key={String(row.label)} className="rounded-lg border border-border/60 bg-background/30 px-3 py-2">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{row.label}</p>
          <div className="mt-1 text-sm text-foreground">{row.value}</div>
        </div>
      ))}
    </div>
  );
}

export function ObjectReadout({
  data,
  emptyLabel = "No data available.",
  className,
}: {
  data: Record<string, unknown> | null | undefined;
  emptyLabel?: string;
  className?: string;
}) {
  if (!data || Object.keys(data).length === 0) {
    return <p className={cn("text-sm text-muted-foreground", className)}>{emptyLabel}</p>;
  }
  return <KeyValueList className={className} rows={flattenObjectForDisplay(data).map((r) => ({ ...r, value: r.value }))} />;
}

function inferColumns(rows: Array<Record<string, unknown>>, maxCols: number): string[] {
  const counts = new Map<string, number>();
  for (const row of rows) {
    for (const key of Object.keys(row)) counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, maxCols)
    .map(([k]) => k);
}

export function RecordTableReadout({
  rows,
  maxRows = 20,
  maxCols = 6,
  emptyLabel = "No rows available.",
}: {
  rows: Array<Record<string, unknown>>;
  maxRows?: number;
  maxCols?: number;
  emptyLabel?: string;
}) {
  if (rows.length === 0) return <p className="text-sm text-muted-foreground">{emptyLabel}</p>;
  const cols = inferColumns(rows, maxCols);
  return (
    <div className="overflow-auto rounded-lg border border-border/60 bg-background/30">
      <table className="w-full text-left text-xs">
        <thead className="border-b border-border/60 text-muted-foreground">
          <tr>
            {cols.map((col) => (
              <th key={col} className="px-2 py-1.5">{humanizeKey(col)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, maxRows).map((row, idx) => (
            <tr key={idx} className="border-b border-border/40 last:border-0">
              {cols.map((col) => (
                <td key={`${idx}:${col}`} className="px-2 py-1.5 align-top text-foreground">
                  <span className="line-clamp-2">{summarizeValue(row[col])}</span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function NarrativeReadout({
  title,
  data,
  emptyLabel = "No narrative available.",
}: {
  title?: string;
  data: unknown;
  emptyLabel?: string;
}) {
  if (!data) return <p className="text-sm text-muted-foreground">{emptyLabel}</p>;
  if (typeof data === "string") {
    return (
      <div className="rounded-lg border border-border/60 bg-background/30 p-3">
        {title ? <p className="text-xs font-semibold text-muted-foreground">{title}</p> : null}
        <p className="mt-1 text-sm text-foreground whitespace-pre-wrap">{data}</p>
      </div>
    );
  }
  if (isRecord(data)) return <ObjectReadout data={data} emptyLabel={emptyLabel} />;
  if (Array.isArray(data)) {
    const objectRows = data.filter((x) => isRecord(x)) as Array<Record<string, unknown>>;
    if (objectRows.length === data.length) return <RecordTableReadout rows={objectRows} />;
    return (
      <ul className="space-y-1 rounded-lg border border-border/60 bg-background/30 p-3 text-sm text-foreground">
        {data.slice(0, 25).map((item, idx) => <li key={idx}>- {summarizeValue(item)}</li>)}
      </ul>
    );
  }
  return <p className="text-sm text-foreground">{summarizeValue(data)}</p>;
}

export function AdvancedRawJson({
  data,
  title = "Advanced Raw Data",
  defaultOpen = false,
}: {
  data: unknown;
  title?: string;
  defaultOpen?: boolean;
}) {
  return (
    <details open={defaultOpen}>
      <summary className="cursor-pointer text-xs text-muted-foreground">{title}</summary>
      <pre className="mt-2 max-h-64 overflow-auto rounded-lg border border-border/60 bg-background/30 p-2 text-[11px] text-muted-foreground">
        {JSON.stringify(data ?? {}, null, 2)}
      </pre>
    </details>
  );
}

