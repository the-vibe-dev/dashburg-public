import { useCallback, useEffect, useState } from "react";

const STREAMING_MODE_KEY = "dashburg.streaming-mode";
const STREAMING_MODE_EVENT = "dashburg:streaming-mode";

function readStreamingMode(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(STREAMING_MODE_KEY) === "1";
}

export function setStreamingMode(next: boolean) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STREAMING_MODE_KEY, next ? "1" : "0");
  window.dispatchEvent(new CustomEvent(STREAMING_MODE_EVENT, { detail: { enabled: next } }));
}

export function useStreamingMode() {
  const [enabled, setEnabled] = useState<boolean>(() => readStreamingMode());

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key && event.key !== STREAMING_MODE_KEY) return;
      setEnabled(readStreamingMode());
    };
    const onCustom = () => setEnabled(readStreamingMode());
    window.addEventListener("storage", onStorage);
    window.addEventListener(STREAMING_MODE_EVENT, onCustom);
    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener(STREAMING_MODE_EVENT, onCustom);
    };
  }, []);

  const toggle = useCallback(() => {
    const next = !readStreamingMode();
    setStreamingMode(next);
  }, []);

  return { streamingMode: enabled, toggleStreamingMode: toggle };
}

