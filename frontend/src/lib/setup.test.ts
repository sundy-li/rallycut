import { describe, expect, it } from "vitest";
import { setupPercent, setupSteps } from "./setup";
import type { SetupState } from "../api/types";

const state = (overrides: Partial<SetupState> = {}): SetupState => ({
  state: "running",
  step: "python",
  message: "",
  detail: "",
  progress: 0,
  needs_network: true,
  ...overrides,
});

describe("setupSteps", () => {
  it("marks finished, current and pending steps", () => {
    const steps = setupSteps(state({ step: "model", progress: 0.84 }));
    expect(steps.map((step) => step.status)).toEqual([
      "done",
      "done",
      "active",
      "pending",
    ]);
  });

  it("marks everything done once ready", () => {
    const steps = setupSteps(
      state({ state: "ready", step: "ready", progress: 1 }),
    );
    expect(steps.every((step) => step.status === "done")).toBe(true);
  });
});

describe("setupPercent", () => {
  it("clamps progress into 0-100", () => {
    expect(setupPercent(state({ progress: 0.426 }))).toBe(43);
    expect(setupPercent(state({ progress: -1 }))).toBe(0);
    expect(setupPercent(state({ progress: 3 }))).toBe(100);
  });
});
