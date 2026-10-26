import { describe, expect, it } from "vitest";
import {
  formatRallyTime,
  parseRallyTime,
  rallyTimeError,
  defaultOriginFilter,
  editHiddenByFilter,
  rallyOrigin,
} from "./rallies";

const machine = (id: string) => ({ id, edited: false });
const corrected = (id: string) => ({ id, edited: true });
const manual = (id: string) => ({ id: `manual-${id}`, edited: true });

describe("default origin filter", () => {
  it("opens on machine rallies when nothing was added by hand", () => {
    expect(defaultOriginFilter([])).toBe("analysis");
    expect(defaultOriginFilter([machine("a"), corrected("b")])).toBe(
      "analysis",
    );
  });
  it("opens on hand-added rallies once any exist", () => {
    expect(defaultOriginFilter([machine("a"), manual("x")])).toBe("manual");
  });
});

describe("edits never vanish behind the origin filter", () => {
  const origins = (rs: { id: string; edited: boolean }[]) =>
    new Map(rs.map((r) => [r.id, rallyOrigin(r)]));
  it("a re-timed machine rally becomes a correction and is revealed", () => {
    const before = origins([machine("a"), machine("b")]);
    expect(
      editHiddenByFilter(before, [corrected("a"), machine("b")], "analysis"),
    ).toBe(true);
  });
  it("split halves with new ids are revealed", () => {
    const before = origins([machine("a")]);
    expect(
      editHiddenByFilter(
        before,
        [corrected("a"), corrected("a-2")],
        "analysis",
      ),
    ).toBe(true);
  });
  it("selection-only changes and deletions keep the filter", () => {
    const before = origins([machine("a"), machine("b")]);
    expect(editHiddenByFilter(before, [machine("a")], "analysis")).toBe(false);
    expect(editHiddenByFilter(before, [corrected("a")], "all")).toBe(false);
  });
});

describe("rally time editing", () => {
  it("parses minutes, hours and plain seconds", () => {
    expect(parseRallyTime("00:14.6")).toBeCloseTo(14.6);
    expect(parseRallyTime("1:05")).toBe(65);
    expect(parseRallyTime("1:02:03.5")).toBeCloseTo(3723.5);
    expect(parseRallyTime("14.6")).toBeCloseTo(14.6);
    expect(parseRallyTime(" 01：14,5 ")).toBeCloseTo(74.5);
  });
  it("rejects malformed input", () => {
    for (const bad of ["", "abc", "1:2:3:4", "00:75", "-3", "1..2", "1:"])
      expect(parseRallyTime(bad)).toBeNull();
  });
  it("formats with two decimals and round-trips", () => {
    expect(formatRallyTime(74.509)).toBe("01:14.51");
    expect(formatRallyTime(3723.5)).toBe("1:02:03.50");
    expect(parseRallyTime(formatRallyTime(14.6))).toBeCloseTo(14.6);
  });
  it("validates bounds and ordering", () => {
    expect(rallyTimeError(1, 3, 30)).toBe("");
    expect(rallyTimeError(null, 3, 30)).toMatch("开始时间");
    expect(rallyTimeError(5, 3, 30)).toMatch("晚于");
    expect(rallyTimeError(1, 31, 30)).toMatch("超出");
  });
});
