import { afterEach, describe, expect, it } from "vitest";
import {
  DEFAULT_RATE,
  DEFAULT_STEP,
  loadRallyOnly,
  loadRate,
  playSpans,
  rallyOnlyTarget,
  saveRallyOnly,
  loadStep,
  rateLabel,
  saveRate,
  saveStep,
  skipTarget,
  stepRate,
} from "./playback";

function fakeStorage() {
  const data = new Map<string, string>();
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
  };
}

describe("preview playback preferences", () => {
  afterEach(() => {
    delete (globalThis as { localStorage?: unknown }).localStorage;
  });
  it("steps speed through presets and clamps at both ends", () => {
    expect(stepRate(1, -1)).toBe(0.5);
    expect(stepRate(0.5, -1)).toBe(0.5);
    expect(stepRate(2, 1)).toBe(2); // capped: >2× may degrade to keyframes
    expect(stepRate(1, 1)).toBe(1.25);
    expect(stepRate(3, 1)).toBe(DEFAULT_RATE);
    expect(rateLabel(1.5)).toBe("1.5×");
  });
  it("clamps skips to the source duration", () => {
    expect(skipTarget(3, -5, 100)).toBe(0);
    expect(skipTarget(97, 10, 100)).toBe(100);
    expect(skipTarget(20, 10, 100)).toBe(30);
    expect(skipTarget(20, 10, Number.NaN)).toBe(0);
  });
  it("remembers valid choices and ignores tampered or missing values", () => {
    expect(loadRate()).toBe(DEFAULT_RATE); // no storage at all
    const store = fakeStorage();
    (globalThis as { localStorage?: unknown }).localStorage = store;
    saveRate(2);
    saveStep(10);
    expect(loadRate()).toBe(2);
    expect(loadStep()).toBe(10);
    expect(loadRallyOnly()).toBe(false);
    saveRallyOnly(true);
    expect(loadRallyOnly()).toBe(true);
    store.setItem("rallycut.preview.rate", "3"); // old 3× preset is dropped
    store.setItem("rallycut.preview.skipStep", "abc");
    expect(loadRate()).toBe(DEFAULT_RATE);
    expect(loadStep()).toBe(DEFAULT_STEP);
  });
  it("merges rally spans and skips gaps between them", () => {
    const spans = playSpans([
      { id: "c", start: 30, end: 34 },
      { id: "a", start: 10, end: 14 },
      { id: "b", start: 13, end: 16 }, // overlaps a
      { id: "d", start: 34.3, end: 36 }, // joins c (gap < 0.5 s)
      { id: "z", start: 40, end: 40 }, // empty, ignored
    ]);
    expect(spans).toEqual([
      { id: "a", start: 10, end: 16 },
      { id: "c", start: 30, end: 36 },
    ]);
    expect(rallyOnlyTarget(2, spans)).toEqual(spans[0]);
    expect(rallyOnlyTarget(9.97, spans)).toBeNull(); // seek landed a hair early
    expect(rallyOnlyTarget(12, spans)).toBeNull();
    expect(rallyOnlyTarget(16.2, spans)).toEqual(spans[1]);
    expect(rallyOnlyTarget(36.1, spans)).toBe("stop");
  });
});
