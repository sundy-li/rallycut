import type { AnalysisSummary } from "./api/types";

export function fpsText(value: number | undefined): string {
  return value !== undefined && Number.isFinite(value) && value >= 0
    ? `${value.toFixed(1)} FPS`
    : "未记录";
}
export function summaryRates(summary: AnalysisSummary) {
  const count = summary.sampled_frames;
  const ratio = (seconds: number | undefined) =>
    seconds !== undefined &&
    Number.isFinite(seconds) &&
    seconds > 0 &&
    Number.isFinite(count) &&
    count >= 0
      ? count / seconds
      : undefined;
  return {
    processing:
      summary.processing_fps ?? ratio(summary.pipeline_timings?.wall_seconds),
    analysis: summary.analysis_fps ?? ratio(summary.elapsed_seconds),
  };
}
