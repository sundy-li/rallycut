export interface TimeRange {
  start: number;
  end: number;
}

const clamp = (time: number, duration: number) =>
  Math.max(0, Math.min(duration, time));

/** Normalize an I/O mark into a valid rally range. Reversed marks are allowed. */
export function markedRange(
  first: number,
  second: number,
  duration: number,
): TimeRange | null {
  if (![first, second, duration].every(Number.isFinite) || duration <= 0)
    return null;
  const start = clamp(Math.min(first, second), duration);
  const end = clamp(Math.max(first, second), duration);
  return end - start >= 0.1 ? { start, end } : null;
}

/** Move one boundary to the playhead without producing an empty/invalid range. */
export function clampedBoundary(
  start: number,
  end: number,
  playhead: number,
  side: "start" | "end",
  duration: number,
): TimeRange | null {
  if (
    ![start, end, playhead, duration].every(Number.isFinite) ||
    end <= start ||
    duration <= 0
  )
    return null;
  const time = clamp(playhead, duration);
  if (side === "start") {
    const next = Math.min(time, end - 0.1);
    return next >= 0 ? { start: next, end } : null;
  }
  const next = Math.max(time, start + 0.1);
  return next <= duration ? { start, end: next } : null;
}
