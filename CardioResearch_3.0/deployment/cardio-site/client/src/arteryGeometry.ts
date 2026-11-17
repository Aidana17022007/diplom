// Normalized educational geometry, independent of questionnaires and ML outputs.
export const MAX_NARROWING = 80;
export const HALF_ARTERY_LENGTH = 3.6;

export function clampNarrowing(value: number): number {
  return Math.max(0, Math.min(MAX_NARROWING, Number.isFinite(value) ? value : 0));
}

export function lumenRadius(x: number, narrowing: number): number {
  const bump = Math.pow(Math.max(0, 1 - (x / 2.6) ** 2), 2);
  return 1 - clampNarrowing(narrowing) / 100 * bump;
}

export function remainingArea(narrowing: number): number {
  return (1 - clampNarrowing(narrowing) / 100) ** 2 * 100;
}

export function clampSectionPosition(value: number): number {
  return Math.max(-HALF_ARTERY_LENGTH, Math.min(HALF_ARTERY_LENGTH, Number.isFinite(value) ? value : 0));
}

// The radius is normalized to the unchanged lumen. Values describe geometry,
// not clinical stenosis measurements, blood flow or probabilities.
export function sectionMetrics(position: number, narrowing: number) {
  const x = clampSectionPosition(position);
  const radius = lumenRadius(x, narrowing);
  const diameterPercent = radius * 100;
  const areaPercent = radius ** 2 * 100;
  return {position:x, radius, diameterPercent, narrowingPercent:100-diameterPercent,
    areaPercent, areaLossPercent:100-areaPercent};
}
