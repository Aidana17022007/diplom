export type Confusion = [[number, number], [number, number]];
export type CountKey = 'tn' | 'fp' | 'fn' | 'tp';
export type CountMode = 'observations' | 'per1000';
export type ThresholdMetrics = Record<'accuracy' | 'recall' | 'precision' | 'specificity' | 'f1' | 'balanced_accuracy' | 'npv' | 'mcc', number | null>;
export type ThresholdPoint = {
  threshold: number;
  source: 'grid' | 'working';
  confusion: Confusion;
  counts: Record<CountKey, number>;
  n: number;
  positive: number;
  negative: number;
  metrics: ThresholdMetrics;
};

const ratio = (numerator: number, denominator: number) => denominator > 0 ? numerator / denominator : null;

/** Counts are unweighted validation observations, with rows=true and columns=predicted. */
export function thresholdPoint(threshold: unknown, matrix: unknown, source: ThresholdPoint['source'] = 'grid'): ThresholdPoint | null {
  if (typeof threshold !== 'number' || !Number.isFinite(threshold) || threshold < 0 || threshold > 1) return null;
  if (!Array.isArray(matrix) || matrix.length !== 2 || matrix.some(row => !Array.isArray(row) || row.length !== 2)) return null;
  const cells = matrix.flat();
  if (cells.some(value => !Number.isSafeInteger(value) || value < 0)) return null;
  const [tn, fp, fn, tp] = cells as number[];
  const n = tn + fp + fn + tp, positive = tp + fn, negative = tn + fp;
  if (!Number.isSafeInteger(n) || n <= 0) return null;
  const recall = ratio(tp, positive), specificity = ratio(tn, negative);
  return {
    threshold, source, confusion: [[tn, fp], [fn, tp]], counts: {tn, fp, fn, tp}, n, positive, negative,
    metrics: {
      accuracy: (tn + tp) / n,
      precision: ratio(tp, tp + fp), recall, specificity,
      f1: ratio(2 * tp, 2 * tp + fp + fn),
      balanced_accuracy: recall === null || specificity === null ? null : (recall + specificity) / 2,
      npv: ratio(tn, tn + fn),
      mcc: ratio(tp * tn - fp * fn, Math.sqrt((tp + fp) * positive * negative * (tn + fn))),
    },
  };
}

/** Insert the exact saved working point; never approximate it with the nearest grid threshold. */
export function buildThresholdLab(research: any) {
  const selection = research?.selection;
  const model = Array.isArray(research?.full) ? research.full.find((row: any) => row?.name === selection?.deployed_model) : null;
  let baseline = model?.threshold === selection?.threshold
    ? thresholdPoint(selection?.threshold, model?.validation?.confusion, 'working') : null;
  if (baseline && typeof research?.protocol?.validation === 'number' && baseline.n !== research.protocol.validation) baseline = null;
  const pointsByThreshold = new Map<number, ThresholdPoint>();
  for (const row of Array.isArray(research?.threshold_curve) ? research.threshold_curve : []) {
    const point = thresholdPoint(row?.threshold, row?.confusion);
    if (!point || (baseline && (point.positive !== baseline.positive || point.negative !== baseline.negative))) continue;
    if (!pointsByThreshold.has(point.threshold)) pointsByThreshold.set(point.threshold, point);
  }
  const gridCount = pointsByThreshold.size;
  if (baseline) pointsByThreshold.set(baseline.threshold, baseline);
  const points = [...pointsByThreshold.values()].sort((a, b) => a.threshold - b.threshold);
  return {points, baseline, gridCount, baselineIndex: baseline ? points.findIndex(point => point.source === 'working') : -1};
}

export function displayedCounts(point: ThresholdPoint, mode: CountMode): Record<CountKey, number> {
  const scale = mode === 'per1000' ? 1000 / point.n : 1;
  return {tn: point.counts.tn * scale, fp: point.counts.fp * scale, fn: point.counts.fn * scale, tp: point.counts.tp * scale};
}

/** Preserve a nonzero delta's direction when its rounded magnitude would otherwise be zero. */
export function formatSignedDelta(value: number | null, digits: number, locale: string): string {
  if (value === null || !Number.isFinite(value)) return '—';
  const formatter = new Intl.NumberFormat(locale, {minimumFractionDigits: digits, maximumFractionDigits: digits});
  const magnitude = Math.abs(value), unit = 10 ** -digits;
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  return sign + (magnitude > 0 && magnitude < unit / 2 ? `<${formatter.format(unit)}` : formatter.format(magnitude));
}

export function compareThresholds(reference: ThresholdPoint, alternative: ThresholdPoint, mode: CountMode = 'observations') {
  if (reference.positive !== alternative.positive || reference.negative !== alternative.negative) {
    throw new Error('Thresholds must describe the same validation class totals.');
  }
  const counts = displayedCounts(alternative, mode), baseCounts = displayedCounts(reference, mode);
  const countDelta = Object.fromEntries((['tn', 'fp', 'fn', 'tp'] as const).map(key => [key, counts[key] - baseCounts[key]])) as Record<CountKey, number>;
  const metricDelta = Object.fromEntries(Object.entries(alternative.metrics).map(([key, value]) => {
    const base = reference.metrics[key as keyof ThresholdMetrics];
    return [key, value === null || base === null ? null : value - base];
  })) as ThresholdMetrics;
  return {counts, baseCounts, countDelta, metricDelta};
}

/** Two comparable aggregate rows; exact thresholds and raw counts are retained in every display mode. */
export function thresholdComparisonCsv(reference: ThresholdPoint, alternative: ThresholdPoint, model: string): string {
  const delta = compareThresholds(reference, alternative);
  const keys = Object.keys(reference.metrics) as (keyof ThresholdMetrics)[];
  const counts = ['tn', 'fp', 'fn', 'tp'] as const;
  const header = ['dataset', 'model', 'evaluation', 'weighting', 'decision_rule', 'role', 'threshold', 'reference_threshold', 'n', 'positive', 'negative', ...counts, ...counts.map(k => `${k}_per_1000`), ...counts.map(k => `delta_${k}`), ...keys, ...keys.map(k => `delta_${k}`)];
  const rows = [reference, alternative].map((point, index) => {
    const scaled = displayedCounts(point, 'per1000');
    return ['brfss', model, 'validation', 'unweighted', 'probability >= threshold', index === 0 ? 'working_reference' : 'research_alternative', point.threshold, reference.threshold, point.n, point.positive, point.negative,
      ...counts.map(k => point.counts[k]), ...counts.map(k => scaled[k]), ...counts.map(k => index === 0 ? 0 : delta.countDelta[k]),
      ...keys.map(k => point.metrics[k]), ...keys.map(k => index === 0 ? (point.metrics[k] === null ? null : 0) : delta.metricDelta[k])];
  });
  const cell = (value: unknown) => {
    if (value === null || value === undefined) return '';
    // Text fields may come from report metadata; keep spreadsheet formulas inert.
    const text = typeof value === 'string' && /^[=+\-@\t\r]/.test(value) ? `'${value}` : String(value);
    return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  return [header, ...rows].map(row => row.map(cell).join(',')).join('\r\n') + '\r\n';
}
