export function normalizeFactoryStatus(value: string | null | undefined): string {
  const next = String(value ?? "").trim().toLowerCase();
  if (!next) return "unknown";
  if (next === "completed") return "succeeded";
  return next;
}

export function normalizeFactorySeverity(value: string | null | undefined): "critical" | "high" | "medium" | "low" {
  const next = String(value ?? "").trim().toLowerCase();
  if (next === "p0" || next === "critical") return "critical";
  if (next === "p1" || next === "high") return "high";
  if (next === "p2" || next === "medium") return "medium";
  return "low";
}
