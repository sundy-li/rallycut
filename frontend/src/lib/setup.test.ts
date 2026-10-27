import { describe, expect, it } from "vitest";
import { mergeSetup, setupPercent, setupSteps } from "./setup";
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
      "done",
      "active",
      "pending",
    ]);
  });

  it("does not mark pending checks as installing before consent", () => {
    const steps = setupSteps(
      state({
        state: "required",
        step: "python",
        checks: [{ id: "media", label: "视频工具", ready: true }],
      }),
    );
    expect(steps.find((step) => step.id === "media")?.status).toBe("done");
    expect(steps.some((step) => step.status === "active")).toBe(false);
  });
  it("shows a failed stage without a perpetual spinner", () => {
    expect(
      setupSteps(state({ state: "failed", step: "media" }))[1].status,
    ).toBe("failed");
  });
  it("marks everything done once ready", () => {
    const steps = setupSteps(
      state({ state: "ready", step: "ready", progress: 1 }),
    );
    expect(steps.every((step) => step.status === "done")).toBe(true);
  });
});

describe("mergeSetup", () => {
  it("ignores old RPC responses after newer progress/ready events", () => {
    const ready = state({ state: "ready", revision: 8 });
    expect(mergeSetup(ready, state({ revision: 7 }))).toBe(ready);
    expect(
      mergeSetup(ready, state({ state: "checking", revision: 9 })).state,
    ).toBe("checking");
  });
});

describe("setupPercent", () => {
  it("clamps progress into 0-100", () => {
    expect(setupPercent(state({ progress: 0.426 }))).toBe(43);
    expect(setupPercent(state({ progress: -1 }))).toBe(0);
    expect(setupPercent(state({ progress: 3 }))).toBe(99);
    expect(setupPercent(state({ progress: NaN }))).toBe(0);
    expect(setupPercent(state({ state: "ready", progress: 1 }))).toBe(100);
  });
});
