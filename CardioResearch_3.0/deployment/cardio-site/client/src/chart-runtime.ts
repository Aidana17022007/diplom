export interface ChartRuntime {
  react(node: HTMLElement, data: any[], layout: any, config: any): Promise<unknown>;
  purge(node: HTMLElement): void;
  Plots: {resize(node: HTMLElement): Promise<unknown> | void};
  downloadImage(node: HTMLElement, options: {format: 'png'; filename: string; width: number; height: number; scale: number}): Promise<unknown>;
}

/** All charts share one lazy chunk; a failed load may be retried from the chart UI. */
export function createChartRuntimeLoader(load: () => Promise<ChartRuntime>) {
  let pendingRuntime: Promise<ChartRuntime> | undefined;
  return () => pendingRuntime ??= load().catch(error => {
      pendingRuntime = undefined;
      throw error;
    });
}

export const loadChartRuntime = createChartRuntimeLoader(() => import('plotly.js-cartesian-dist-min').then(module => module.default as ChartRuntime));

export function chartFileName(label: string): string {
  const safeLabel = label.normalize('NFKC').replace(/[^\p{L}\p{N}_-]+/gu, '-').replace(/^-+|-+$/g, '').slice(0, 80).replace(/-+$/g, '');
  return `CardioResearch-${safeLabel || 'chart'}`;
}
