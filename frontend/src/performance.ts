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

/**
 * Remaining wall-clock time for a running analysis.
 *
 * The worker reports progress as timestamp/duration*0.94, so progress is
 * already proportional to processed video time; elapsed comes from the job
 * clock and therefore includes model loading and audio extraction. Returns
 * undefined until there is enough progress to extrapolate — a two-frame
 * sample would otherwise promise hours or minutes at random.
 */
export function estimateRemainingSeconds(
  elapsedSeconds: number | undefined,
  progress: number | undefined,
  durationSeconds: number | undefined,
): number | undefined {
  if (
    elapsedSeconds === undefined ||
    !Number.isFinite(elapsedSeconds) ||
    elapsedSeconds < 15 ||
    progress === undefined ||
    !Number.isFinite(progress) ||
    durationSeconds === undefined ||
    !Number.isFinite(durationSeconds) ||
    durationSeconds <= 0 ||
    progress < 0.02 ||
    progress >= 0.94
  ) {
    return undefined;
  }
  const done = (progress / 0.94) * durationSeconds;
  if (done <= 0) return undefined;
  const rate = done / elapsedSeconds;
  if (!Number.isFinite(rate) || rate <= 0) return undefined;
  return (durationSeconds - done) / rate;
}

/** "约 42 分钟" — coarse on purpose; a long CPU run is not predictable to the second. */
export function remainingText(seconds: number | undefined): string {
  if (seconds === undefined || !Number.isFinite(seconds) || seconds < 0) {
    return "未记录";
  }
  if (seconds < 60) return "不到 1 分钟";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `约 ${minutes} 分钟`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest === 0 ? `约 ${hours} 小时` : `约 ${hours} 小时 ${rest} 分钟`;
}
