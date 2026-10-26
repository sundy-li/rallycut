import { describe, expect, it } from "vitest";
import { clampedBoundary, markedRange } from "./marks";

describe("markedRange", () => {
  it("creates a range and accepts reversed marks", () => {
    expect(markedRange(4, 1, 10)).toEqual({ start: 1, end: 4 });
  });
  it("clamps to the video duration", () => {
    expect(markedRange(-2, 20, 10)).toEqual({ start: 0, end: 10 });
  });
  it("rejects empty and invalid ranges", () => {
    expect(markedRange(2, 2, 10)).toBeNull();
    expect(markedRange(Number.NaN, 2, 10)).toBeNull();
    expect(markedRange(1, 2, 0)).toBeNull();
  });
});

describe("clampedBoundary", () => {
  it("moves start/end without crossing the other boundary", () => {
    expect(clampedBoundary(2, 8, 1, "start", 10)).toEqual({ start: 1, end: 8 });
    expect(clampedBoundary(2, 8, 9, "end", 10)).toEqual({ start: 2, end: 9 });
    expect(clampedBoundary(2, 8, 20, "start", 10)).toEqual({
      start: 7.9,
      end: 8,
    });
    expect(clampedBoundary(2, 8, 0, "end", 10)).toEqual({ start: 2, end: 2.1 });
  });
  it("clamps the playhead to the video edges", () => {
    expect(clampedBoundary(2, 8, -1, "start", 10)).toEqual({
      start: 0,
      end: 8,
    });
    expect(clampedBoundary(2, 8, 11, "end", 10)).toEqual({ start: 2, end: 10 });
  });
  it("rejects invalid input", () => {
    expect(clampedBoundary(8, 2, 4, "start", 10)).toBeNull();
    expect(clampedBoundary(2, 8, Number.NaN, "end", 10)).toBeNull();
  });
});
