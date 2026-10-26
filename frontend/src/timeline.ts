import type { OverlapMode, Rally, Rules } from "./api/types";

const overlapEpsilon = 0.04;
const isHuman = (r: Rally) => r.edited || r.id.startsWith("manual-");
const exportedRally = (r: Rally) => r.selected && !r.invalid;
const overlapping = (a: Rally, b: Rally) =>
  Math.min(a.end, b.end) - Math.max(a.start, b.start) > overlapEpsilon;

export const overlapOptions: {
  value: OverlapMode;
  label: string;
  hint: string;
}[] = [
  {
    value: "sequential",
    label: "按先后顺序覆盖",
    hint: "先开始的回合保留，与它重叠、后开始的回合整段不导出。",
  },
  {
    value: "human",
    label: "人工回合覆盖分析回合",
    hint: "人工添加 / 修正的回合保留，与之重叠的分析回合整段不导出。",
  },
  {
    value: "machine",
    label: "分析回合覆盖人工回合",
    hint: "分析回合保留，与之重叠的人工回合整段不导出。",
  },
  {
    value: "merge",
    label: "合并区间，不重叠",
    hint: "重叠的回合合并为一段连续画面，所有画面都保留。",
  },
];

/** Mirrors backend timeline.OverlapConflicts: exported human/machine pairs. */
export function overlapConflicts(rallies: Rally[]): number {
  let n = 0;
  rallies.forEach((a, i) => {
    for (const b of rallies.slice(i + 1)) {
      if (
        exportedRally(a) &&
        exportedRally(b) &&
        isHuman(a) !== isHuman(b) &&
        overlapping(a, b)
      )
        n++;
    }
  });
  return n;
}

/** Mirrors backend timeline.ResolveOverlaps: losers are deselected copies. */
export function resolveOverlaps(rallies: Rally[], mode: OverlapMode = "merge") {
  const out = rallies.map((r) => ({ ...r }));
  if (mode === "merge") return out;
  const order = out
    .map((r, i) => ({ r, i }))
    .filter(({ r }) => exportedRally(r))
    .sort((a, b) => a.r.start - b.r.start)
    .map(({ i }) => i);
  const hits = (r: Rally, wantHuman: boolean, among: number[]) =>
    among.some((j) => isHuman(out[j]) === wantHuman && overlapping(r, out[j]));
  const kept: number[] = [];
  for (const i of order) {
    const r = out[i];
    const drop =
      mode === "human"
        ? !isHuman(r) && hits(r, true, order)
        : mode === "machine"
          ? isHuman(r) && hits(r, false, order)
          : hits(r, !isHuman(r), kept);
    if (drop) out[i].selected = false;
    else kept.push(i);
  }
  return out;
}

export function exportSpans(
  rallies: Rally[],
  rules: Rules,
  duration: number,
  mode: OverlapMode = "merge",
) {
  return spans(resolveOverlaps(rallies, mode), rules, duration);
}
export function timecode(seconds: number, decimals = false): string {
  if (!Number.isFinite(seconds)) return "--:--";
  const n = decimals
    ? Math.round(Math.max(0, seconds) * 100) / 100
    : Math.max(0, seconds);
  const hours = Math.floor(n / 3600);
  const minutes = Math.floor(n / 60) % 60;
  const s = decimals
    ? (n % 60).toFixed(2).padStart(5, "0")
    : Math.floor(n % 60)
        .toString()
        .padStart(2, "0");
  return `${hours ? `${hours}:` : ""}${String(minutes).padStart(2, "0")}:${s}`;
}
export function spans(
  rallies: Rally[],
  rules: Rules,
  duration: number,
): { start: number; end: number }[] {
  const ordered = [...rallies].sort((a, b) => a.start - b.start);
  const cuts = new Map<number, number>();
  const barriers = new Set<number>();
  let furthest = 0;
  let exported = 0;
  for (const [i, r] of ordered.entries()) {
    // Mirrors backend: an exported rally whose content crosses a protected
    // boundary overrides it (merge, no duplicated footage).
    if (r.boundary_before && exported <= r.start) {
      const cut = i > 0 ? (Math.min(furthest, r.start) + r.start) / 2 : r.start;
      cuts.set(i, cut);
      barriers.add(cut);
    }
    furthest = Math.max(furthest, r.end);
    if (r.selected && !r.invalid) exported = Math.max(exported, r.end);
  }
  const upper: number[] = [];
  let ceiling = duration;
  for (let i = ordered.length - 1; i >= 0; i--) {
    upper[i] = ceiling;
    if (cuts.has(i)) ceiling = cuts.get(i)!;
  }
  let floor = 0;
  const items = ordered
    .flatMap((r, i) => {
      if (cuts.has(i)) floor = cuts.get(i)!;
      if (!r.selected || r.invalid) return [];
      return [
        {
          start: Math.max(floor, 0, r.start - rules.pre_roll),
          end: Math.min(upper[i], duration, r.end + rules.post_roll),
        },
      ];
    })
    .sort((a, b) => a.start - b.start);
  const out: { start: number; end: number }[] = [];
  for (const item of items) {
    const last = out.at(-1);
    if (last && item.start <= last.end && !barriers.has(item.start))
      last.end = Math.max(last.end, item.end);
    else out.push({ ...item });
  }
  return out;
}
