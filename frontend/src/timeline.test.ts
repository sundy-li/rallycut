import { describe, it, expect } from "vitest";
import {
  exportSpans,
  overlapConflicts,
  resolveOverlaps,
  spans,
  timecode,
} from "./timeline";
import type { Rally } from "./api/types";
const rally = (
  id: string,
  start: number,
  end: number,
  selected = true,
): Rally => ({
  id,
  start,
  end,
  selected,
  confidence: 0,
  score: 0,
  edited: false,
});
describe("timeline", () => {
  it("formats seconds and hours", () => {
    expect(timecode(65)).toBe("01:05");
    expect(timecode(3665)).toBe("1:01:05");
    expect(timecode(5.25, true)).toBe("00:05.25");
    expect(timecode(NaN)).toBe("--:--");
  });
  it("matches backend clamp and overlap semantics", () => {
    expect(
      spans(
        [
          rally("c", 8, 9.8),
          rally("b", 3, 5),
          rally("a", 0.2, 2.5),
          rally("d", 6, 7, false),
        ],
        { pre_roll: 1, post_roll: 1, min_duration: 6 },
        10,
      ),
    ).toEqual([
      { start: 0, end: 6 },
      { start: 7, end: 10 },
    ]);
  });
  it("does not let context padding erase dead-ball boundaries", () => {
    const first = {
      ...rally("first", 10, 17.92),
      end_reason: "out_without_table_bounce",
      end_event_time: 17.92,
    };
    const next = { ...rally("next", 18.1, 23), boundary_before: true };
    const rules = { pre_roll: 2, post_roll: 2, min_duration: 6 };
    const cut = (first.end + next.start) / 2;
    expect(spans([first, next], rules, 30)).toEqual([
      { start: 8, end: cut },
      { start: cut, end: 25 },
    ]);
    expect(spans([first, { ...next, start: 17.92 }], rules, 30)).toHaveLength(
      2,
    );
    expect(spans([{ ...first, selected: false }, next], rules, 30)).toEqual([
      { start: cut, end: 25 },
    ]);
  });
  it("does not count invalid rallies in the real export", () => {
    expect(
      spans(
        [
          rally("valid", 1, 3),
          { ...rally("invalid-net-serve", 5, 7), invalid: true },
        ],
        { pre_roll: 0.5, post_roll: 0.5, min_duration: 6 },
        10,
      ),
    ).toEqual([{ start: 0.5, end: 3.5 }]);
    expect(
      spans(
        [{ ...rally("invalid", 1, 3), invalid: true }],
        { pre_roll: 0, post_roll: 0, min_duration: 6 },
        10,
      ),
    ).toEqual([]);
  });
  it("does not count unselected clips", () => {
    expect(
      spans(
        [rally("a", 0, 2, false)],
        { pre_roll: 1, post_roll: 1, min_duration: 6 },
        10,
      ),
    ).toEqual([]);
  });
  it("exports a rally overlapping a protected boundary as one merged span", () => {
    const rules = { pre_roll: 0.5, post_roll: 0.8, min_duration: 6 };
    const manual = { ...rally("manual", 114.71, 119.22), edited: true };
    const machine = {
      ...rally("machine", 116.02, 119.9),
      boundary_before: true,
    };
    const after = { ...rally("after", 125, 128), boundary_before: true };
    const out = spans([manual, machine, after], rules, 200);
    expect(out).toHaveLength(2);
    expect(out[0].start).toBeCloseTo(114.21);
    expect(out[0].end).toBeCloseTo(120.7);
    expect(out[1].start).toBeCloseTo(124.5);
    expect(
      spans([{ ...manual, selected: false }, machine, after], rules, 200)[0]
        .start,
    ).toBe(116.02);
  });
});

describe("export overlap policy", () => {
  const human = (id: string, s: number, e: number): Rally => ({
    ...rally(`manual-${id}`, s, e),
    edited: true,
  });
  const rs = [
    human("h1", 10, 20),
    rally("m1", 15, 30),
    rally("m2", 40, 50),
    human("h2", 45, 60),
    rally("m3", 70, 80),
  ];
  const kept = (mode: Parameters<typeof resolveOverlaps>[1]) =>
    resolveOverlaps(rs, mode)
      .filter((r) => r.selected)
      .map((r) => r.id);
  it("matches backend ResolveOverlaps for every mode", () => {
    expect(overlapConflicts(rs)).toBe(2);
    expect(kept("merge")).toEqual(["manual-h1", "m1", "m2", "manual-h2", "m3"]);
    expect(kept("human")).toEqual(["manual-h1", "manual-h2", "m3"]);
    expect(kept("machine")).toEqual(["m1", "m2", "m3"]);
    expect(kept("sequential")).toEqual(["manual-h1", "m2", "m3"]);
  });
  it("skips the losing rally entirely and never mutates input", () => {
    const rules = { pre_roll: 0, post_roll: 0, min_duration: 0 };
    expect(exportSpans(rs, rules, 100, "human").slice(0, 2)).toEqual([
      { start: 10, end: 20 },
      { start: 45, end: 60 },
    ]);
    expect(exportSpans(rs, rules, 100).slice(0, 2)).toEqual([
      { start: 10, end: 30 },
      { start: 40, end: 60 },
    ]);
    expect(rs.every((r) => r.selected)).toBe(true);
  });
  it("same-kind overlaps are not conflicts and always merge", () => {
    const same = [rally("a", 0, 10), rally("b", 8, 15)];
    expect(overlapConflicts(same)).toBe(0);
    expect(
      exportSpans(
        same,
        { pre_roll: 0, post_roll: 0, min_duration: 0 },
        100,
        "machine",
      ),
    ).toEqual([{ start: 0, end: 15 }]);
  });
});
