export type HardFitTerminal = {
  resize: (cols: number, rows: number) => void;
  cols?: number;
  rows?: number;
};

export type HardFitAddon = {
  fit: () => void;
  proposeDimensions?: () => { cols: number; rows: number } | undefined;
};

export function hardFit(term: HardFitTerminal, fitAddon: HardFitAddon, containerEl: HTMLElement | null): boolean {
  if (!containerEl || !containerEl.isConnected) return false;
  const rect = containerEl.getBoundingClientRect();
  if (rect.width < 10 || rect.height < 10) return false;
  fitAddon.fit();
  const dims = fitAddon.proposeDimensions?.();
  if (dims?.cols && dims?.rows) {
    const nextCols = Math.max(2, Math.floor(dims.cols));
    const nextRows = Math.max(2, Math.floor(dims.rows));
    if (term.cols !== nextCols || term.rows !== nextRows) {
      term.resize(nextCols, nextRows);
    }
  }
  return true;
}
