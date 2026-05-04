import { FitAddon } from "@xterm/addon-fit";
import type { Terminal } from "@xterm/xterm";
import { type CSSProperties, type RefObject, useEffect, useMemo, useRef, useState } from "react";
import { useXTerm } from "react-xtermjs";

import { hardFit } from "./hardFit";

function cx(...parts: Array<string | undefined | false>): string {
  return parts.filter(Boolean).join(" ");
}

export type TerminalSurfaceApi = {
  write: (data: string) => void;
  clear: () => void;
  focus: () => void;
  fit: () => void;
  getViewportSize: () => { width: number; height: number };
  getTerminalSize: () => { cols: number; rows: number };
};

type TerminalSurfaceProps = {
  isActive?: boolean;
  autoFocus?: boolean;
  className?: string;
  viewportClassName?: string;
  style?: CSSProperties;
  options?: Record<string, unknown>;
  onData?: (data: string) => void;
  inputEnabled?: boolean;
  onReady?: (api: TerminalSurfaceApi | null) => void;
  onResize?: (size: { width: number; height: number }) => void;
  onError?: (message: string) => void;
};

type TerminalCoreProps = {
  options?: Record<string, unknown>;
  viewportClassName?: string;
  inputEnabled: boolean;
  isActive: boolean;
  autoFocus: boolean;
  onReady?: (api: TerminalSurfaceApi | null) => void;
  onResize?: (size: { width: number; height: number }) => void;
  onData?: (data: string) => void;
  onError?: (message: string) => void;
};

function TerminalCore({
  options,
  viewportClassName,
  inputEnabled,
  isActive,
  autoFocus,
  onReady,
  onResize,
  onData,
  onError,
}: TerminalCoreProps) {
  const mergedOptions = useMemo(
    () => ({
      cursorBlink: true,
      convertEol: true,
      fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
      fontSize: 13,
      lineHeight: 1.25,
      theme: {
        background: "#0f1115",
        foreground: "#d6deeb",
        cursor: "#a6accd",
        selectionBackground: "#3a4458",
      },
      ...(options ?? {}),
    }),
    [options],
  );

  const fitAddon = useMemo(() => new FitAddon(), []);
  const addons = useMemo(() => [fitAddon], [fitAddon]);
  const { instance, ref: viewportRef } = useXTerm({ options: mergedOptions, addons });

  const mountedRef = useRef(false);
  const fitScheduledRef = useRef(false);
  const retryRafRef = useRef<number | null>(null);
  const fitRafRef = useRef<number | null>(null);
  const activeFocusRafRef = useRef<number | null>(null);
  const inputSubRef = useRef<{ dispose: () => void } | null>(null);
  const observerRef = useRef<ResizeObserver | null>(null);
  const lastInputRef = useRef<{ data: string; ts: number }>({ data: "", ts: 0 });
  const lastViewportRef = useRef<{ width: number; height: number }>({ width: 0, height: 0 });
  const lastTermSizeRef = useRef<{ cols: number; rows: number }>({ cols: 0, rows: 0 });

  const onReadyRef = useRef<typeof onReady>(onReady);
  const onResizeRef = useRef<typeof onResize>(onResize);
  const onDataRef = useRef<typeof onData>(onData);
  const onErrorRef = useRef<typeof onError>(onError);

  useEffect(() => {
    onReadyRef.current = onReady;
  }, [onReady]);

  useEffect(() => {
    onResizeRef.current = onResize;
  }, [onResize]);

  useEffect(() => {
    onDataRef.current = onData;
  }, [onData]);

  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  const getViewportSize = () => {
    const viewport = viewportRef.current;
    if (!viewport) return { width: 0, height: 0 };
    const rect = viewport.getBoundingClientRect();
    return { width: Math.max(0, rect.width), height: Math.max(0, rect.height) };
  };

  const fitNow = (attempt = 0) => {
    if (!mountedRef.current || !instance) return;
    const viewport = viewportRef.current;
    if (!viewport) return;
    const ok = hardFit(instance as unknown as Terminal, fitAddon, viewport);
    if (!ok && attempt < 12) {
      retryRafRef.current = requestAnimationFrame(() => fitNow(attempt + 1));
      return;
    }
    const viewportSize = getViewportSize();
    const termSize = { cols: Number(instance.cols) || 0, rows: Number(instance.rows) || 0 };
    const viewportChanged =
      Math.abs(viewportSize.width - lastViewportRef.current.width) > 0.5 ||
      Math.abs(viewportSize.height - lastViewportRef.current.height) > 0.5;
    const termChanged =
      termSize.cols !== lastTermSizeRef.current.cols || termSize.rows !== lastTermSizeRef.current.rows;
    lastViewportRef.current = viewportSize;
    lastTermSizeRef.current = termSize;
    if (viewportChanged || termChanged) {
      onResizeRef.current?.(viewportSize);
    }
  };

  const scheduleFit = () => {
    if (fitScheduledRef.current) return;
    fitScheduledRef.current = true;
    fitRafRef.current = requestAnimationFrame(() => {
      fitScheduledRef.current = false;
      try {
        fitNow(0);
      } catch (err) {
        onErrorRef.current?.(`terminal fit failed: ${String(err)}`);
      }
    });
  };

  const focusTerminal = () => {
    if (!instance || !isActive || !autoFocus) return;
    try {
      instance.focus();
      const rows = Number(instance.rows) || 0;
      if (rows > 0) {
        instance.refresh(0, rows - 1);
      }
    } catch {
      // focus failures are non-fatal when tab/container is still activating
    }
  };

  useEffect(() => {
    if (!instance || !viewportRef.current) return;
    mountedRef.current = true;

    const api: TerminalSurfaceApi = {
      write: (data: string) => instance.write(data),
      clear: () => instance.clear(),
      focus: () => instance.focus(),
      fit: () => scheduleFit(),
      getViewportSize,
      getTerminalSize: () => ({ cols: Number(instance.cols) || 0, rows: Number(instance.rows) || 0 }),
    };
    onReadyRef.current?.(api);

    observerRef.current = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const width = entry.contentRect.width;
      const height = entry.contentRect.height;
      const changed =
        Math.abs(width - lastViewportRef.current.width) > 0.5 ||
        Math.abs(height - lastViewportRef.current.height) > 0.5;
      if (changed) scheduleFit();
    });
    observerRef.current.observe(viewportRef.current);

    requestAnimationFrame(() => requestAnimationFrame(() => scheduleFit()));

    if (document.fonts?.ready) {
      document.fonts.ready.then(() => scheduleFit()).catch(() => {
        // ignore fonts.ready errors
      });
    }

    return () => {
      mountedRef.current = false;
      if (retryRafRef.current !== null) cancelAnimationFrame(retryRafRef.current);
      if (fitRafRef.current !== null) cancelAnimationFrame(fitRafRef.current);
      if (activeFocusRafRef.current !== null) cancelAnimationFrame(activeFocusRafRef.current);
      observerRef.current?.disconnect();
      observerRef.current = null;
      inputSubRef.current?.dispose();
      inputSubRef.current = null;
      onReadyRef.current?.(null);
    };
  }, [instance, fitAddon]);

  useEffect(() => {
    inputSubRef.current?.dispose();
    inputSubRef.current = null;
    if (!mountedRef.current || !instance || !onDataRef.current || !inputEnabled) return;
    inputSubRef.current = instance.onData((data) => {
      const now = Date.now();
      const last = lastInputRef.current;
      const pasteLike = data.length > 1 || data.includes("\n") || data.includes("\r") || data.includes("\t");
      // Guard against duplicate paste bursts from rapid remount/reconnect listener churn.
      if (pasteLike && last.data === data && now - last.ts < 50) {
        return;
      }
      lastInputRef.current = { data, ts: now };
      onDataRef.current?.(data);
    });
    return () => {
      inputSubRef.current?.dispose();
      inputSubRef.current = null;
    };
  }, [instance, inputEnabled]);

  useEffect(() => {
    if (!isActive) return;
    activeFocusRafRef.current = requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        scheduleFit();
        focusTerminal();
      }),
    );
    return () => {
      if (activeFocusRafRef.current !== null) {
        cancelAnimationFrame(activeFocusRafRef.current);
        activeFocusRafRef.current = null;
      }
    };
  }, [isActive, instance, autoFocus]);

  useEffect(() => {
    if (!isActive) return;
    const onWindowResize = () => {
      scheduleFit();
      focusTerminal();
    };
    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        scheduleFit();
        focusTerminal();
      }
    };
    const onWindowFocus = () => {
      scheduleFit();
      focusTerminal();
    };
    window.addEventListener("resize", onWindowResize);
    window.addEventListener("focus", onWindowFocus);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("resize", onWindowResize);
      window.removeEventListener("focus", onWindowFocus);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [isActive, instance, autoFocus]);

  return (
    <div
      ref={viewportRef as RefObject<HTMLDivElement>}
      className={cx("terminalViewport", viewportClassName)}
      onMouseDown={() => focusTerminal()}
    />
  );
}

export function TerminalSurface({
  isActive = true,
  autoFocus = true,
  className,
  viewportClassName,
  style,
  options,
  onData,
  inputEnabled = true,
  onReady,
  onResize,
  onError,
}: TerminalSurfaceProps) {
  return (
    <div className={cx("terminalHost", className)} style={style}>
      <TerminalCore
        options={options}
        viewportClassName={viewportClassName}
        inputEnabled={inputEnabled}
        isActive={isActive}
        autoFocus={autoFocus}
        onReady={onReady}
        onResize={onResize}
        onData={onData}
        onError={onError}
      />
    </div>
  );
}
