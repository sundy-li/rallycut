/** Preview playback speed and skip-step preferences (UI only, never exported). */

// Capped at 2×: above that macOS WebView (AVFoundation) may fall back to
// keyframe-only "trick play", which looks like a slideshow on 1 s GOP footage.
export const PLAYBACK_RATES = [0.5, 1, 1.25, 1.5, 2] as const;
export const SKIP_STEPS = [1, 2, 5, 10, 15, 30] as const;
export const DEFAULT_RATE = 1;
export const DEFAULT_STEP = 5;

const RATE_KEY = "rallycut.preview.rate";
const STEP_KEY = "rallycut.preview.skipStep";
const RALLY_ONLY_KEY = "rallycut.preview.rallyOnly";

type Store = Pick<Storage, "getItem" | "setItem">;

function storage(): Store | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null; // storage disabled; fall back to defaults
  }
}

function read(key: string, allowed: readonly number[], fallback: number) {
  const value = Number(storage()?.getItem(key));
  return allowed.includes(value) ? value : fallback;
}

function write(key: string, value: number) {
  try {
    storage()?.setItem(key, String(value));
  } catch {
    // Quota / private mode: the preference just isn't remembered.
  }
}

export const loadRate = () => read(RATE_KEY, PLAYBACK_RATES, DEFAULT_RATE);
export const loadStep = () => read(STEP_KEY, SKIP_STEPS, DEFAULT_STEP);
export const saveRate = (rate: number) => write(RATE_KEY, rate);
export const saveStep = (step: number) => write(STEP_KEY, step);
export const loadRallyOnly = () => storage()?.getItem(RALLY_ONLY_KEY) === "1";
export const saveRallyOnly = (on: boolean) => write(RALLY_ONLY_KEY, on ? 1 : 0);

/** Next preset in `direction` (+1 faster / -1 slower), clamped at the ends. */
export function stepRate(current: number, direction: 1 | -1): number {
  const rates: readonly number[] = PLAYBACK_RATES;
  const index = rates.indexOf(current);
  if (index < 0) return DEFAULT_RATE;
  return rates[Math.max(0, Math.min(rates.length - 1, index + direction))];
}

/** Target time for a relative skip, clamped to [0, duration]. */
export function skipTarget(
  current: number,
  delta: number,
  duration: number,
): number {
  const end = Number.isFinite(duration) && duration > 0 ? duration : 0;
  return Math.max(0, Math.min(end, current + delta));
}

export interface PlaySpan {
  id: string; // first rally in the span; focused when playback enters it
  start: number;
  end: number;
}

/** Rally-only playback spans: sorted, overlapping / near-touching merged. */
export function playSpans(
  rallies: readonly { id: string; start: number; end: number }[],
  joinGap = 0.5,
): PlaySpan[] {
  const out: PlaySpan[] = [];
  for (const r of [...rallies]
    .filter((r) => r.end > r.start)
    .sort((a, b) => a.start - b.start)) {
    const last = out[out.length - 1];
    if (last && r.start - last.end <= joinGap)
      last.end = Math.max(last.end, r.end);
    else out.push({ id: r.id, start: r.start, end: r.end });
  }
  return out;
}

/**
 * Where rally-only playback should go from `t`: null keeps playing (inside a
 * span), a span means seek to its start, "stop" means no later rally.
 */
export function rallyOnlyTarget(
  t: number,
  spans: readonly PlaySpan[],
  tolerance = 0.05,
): PlaySpan | "stop" | null {
  for (const span of spans) {
    if (t < span.start - tolerance) return span;
    if (t < span.end) return null;
  }
  return "stop";
}

export const rateLabel = (rate: number) => `${rate}×`;
