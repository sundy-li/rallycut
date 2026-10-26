import type { Rally } from "../api/types";

export type RallyOrigin = "manual" | "edited" | "analysis";

/** Distinguish user-created rallies from model candidates and manual corrections. */
export function rallyOrigin(rally: Pick<Rally, "id" | "edited">): RallyOrigin {
  if (rally.id.startsWith("manual-")) return "manual";
  return rally.edited ? "edited" : "analysis";
}

export function rallyOriginLabel(rally: Pick<Rally, "id" | "edited">): string {
  switch (rallyOrigin(rally)) {
    case "manual":
      return "人工";
    case "edited":
      return "人工修正";
    default:
      return "分析";
  }
}

/**
 * The rally list opens on machine-detected rallies; once the user has added
 * rallies by hand (I/O or "+"), it opens on those instead.
 */
export function defaultOriginFilter(
  rallies: Pick<Rally, "id" | "edited">[],
): RallyOrigin {
  return rallies.some((r) => rallyOrigin(r) === "manual")
    ? "manual"
    : "analysis";
}

/**
 * After an edit, rallies that are new or whose origin changed (a machine rally
 * that was split, merged or re-timed becomes a correction) must not silently
 * disappear behind the current origin filter.
 */
export function editHiddenByFilter(
  before: Map<string, RallyOrigin>,
  after: Pick<Rally, "id" | "edited">[],
  filter: RallyOrigin | "all",
): boolean {
  if (filter === "all") return false;
  return after.some((r) => {
    const origin = rallyOrigin(r);
    return before.get(r.id) !== origin && origin !== filter;
  });
}

/** Shortest rally the backend accepts (project.ValidateRallies). */
export const MIN_RALLY_SECONDS = 0.04;

/**
 * Parse a typed rally time: "mm:ss(.s)", "h:mm:ss(.s)" or plain seconds.
 * Full-width colons and decimal commas are accepted. Returns null if invalid.
 */
export function parseRallyTime(text: string): number | null {
  const parts = text.trim().replace(/：/g, ":").replace(/,/g, ".").split(":");
  if (parts.length > 3 || parts.some((p) => !/^\d+(\.\d+)?$|^\.\d+$/.test(p)))
    return null;
  const nums = parts.map(Number);
  if (nums.length > 1 && nums.slice(1).some((n) => n >= 60)) return null;
  const seconds = nums.reduce((total, n) => total * 60 + n, 0);
  return Number.isFinite(seconds) ? seconds : null;
}

/** Format a rally time for editing, e.g. 74.509 → "01:14.51". */
export function formatRallyTime(seconds: number): string {
  const n = Math.round(Math.max(0, seconds) * 100) / 100;
  const h = Math.floor(n / 3600);
  const m = Math.floor(n / 60) % 60;
  const s = (n - Math.floor(n / 60) * 60).toFixed(2).padStart(5, "0");
  return `${h ? `${h}:` : ""}${String(m).padStart(2, "0")}:${s}`;
}

/** Validate an edited [start, end]; returns an error message or "". */
export function rallyTimeError(
  start: number | null,
  end: number | null,
  duration: number,
): string {
  if (start === null) return "开始时间格式不对，例如 00:14.6 或 14.6";
  if (end === null) return "结束时间格式不对，例如 00:20.9 或 20.9";
  if (end > duration + 1e-6)
    return `结束时间超出视频长度 ${formatRallyTime(duration)}`;
  if (end - start < MIN_RALLY_SECONDS) return "结束时间必须晚于开始时间";
  return "";
}
