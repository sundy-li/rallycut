import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  LiveProcessingStats,
  CompletedProcessingStats,
} from "./ProcessingStats";
import { fpsText, summaryRates } from "../performance";
import type { AnalysisSummary } from "../api/types";

const summary = {
  sampled_frames: 900,
  elapsed_seconds: 10,
  pipeline_timings: {
    wall_seconds: 6,
    producer_seconds: 5.8,
    forward_seconds: 3.7,
    postprocess_seconds: 0.2,
  },
} as unknown as AnalysisSummary;
const stats = {
  stage: "inference" as const,
  processed_frames: 900,
  elapsed_seconds: 6,
  recent_fps: 120,
  average_fps: 150,
};

describe("actual processing FPS, not source FPS", () => {
  it("distinguishes inference-wall throughput from core analysis average", () => {
    expect(summaryRates(summary)).toEqual({ processing: 150, analysis: 90 });
    const html = renderToStaticMarkup(
      createElement(CompletedProcessingStats, { summary }),
    );
    expect(html).toContain("150.0 FPS");
    expect(html).toContain("90.0 FPS");
    expect(html).toContain("5.80s");
  });
  it("shows recent speed only while inference is actually running", () => {
    const active = renderToStaticMarkup(
      createElement(LiveProcessingStats, { stats, active: true }),
    );
    expect(active).toContain("120.0 FPS");
    expect(active).toContain("150.0 FPS");
    for (const props of [
      { stats, active: false },
      { stats: { ...stats, stage: "finalizing" as const }, active: true },
    ]) {
      const html = renderToStaticMarkup(
        createElement(LiveProcessingStats, props),
      );
      expect(html).not.toContain("120.0 FPS");
      expect(html).toContain("150.0 FPS");
    }
  });
  it("does not invent infinite/missing speeds for old projects", () => {
    expect(fpsText(NaN)).toBe("未记录");
    expect(fpsText(Infinity)).toBe("未记录");
    expect(
      summaryRates({
        ...summary,
        pipeline_timings: undefined,
        elapsed_seconds: 0,
      }),
    ).toEqual({ processing: undefined, analysis: undefined });
  });
});
