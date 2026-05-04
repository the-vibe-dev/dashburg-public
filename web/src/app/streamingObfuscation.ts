function hashLabel(value: string): number {
  let hash = 5381;
  for (let i = 0; i < value.length; i += 1) {
    hash = ((hash << 5) + hash) ^ value.charCodeAt(i);
  }
  return Math.abs(hash);
}

export function obfuscateStreamingLabel(value: string, prefix = "channel"): string {
  const cleaned = String(value ?? "").trim();
  if (!cleaned) return `${prefix}-hidden`;
  const id = (hashLabel(cleaned) % 9999) + 1;
  return `${prefix}-${id}`;
}

export function withStreamingObfuscation(value: string, enabled: boolean, prefix = "channel"): string {
  if (!enabled) return value;
  return obfuscateStreamingLabel(value, prefix);
}
