import type { AnalysisSummary, ProcessingPerformance } from "../api/types";
import {
  estimateRemainingSeconds,
  fpsText,
  remainingText,
  summaryRates,
} from "../performance";

const processingHelp =
  "真实完成帧数 ÷ 实际耗时；包含解码、预处理、推理、后处理。不是素材帧率，也不是纯 GPU FPS。";

export function LiveProcessingStats({
  stats,
  active,
  elapsed,
  duration,
  progress,
}: {
  stats: ProcessingPerformance;
  active: boolean;
  /** Job wall clock, including preparation. */
  elapsed?: number;
  /** Source duration in seconds; only used to estimate the remaining time. */
  duration?: number;
  /** Job progress 0-1 (timestamp/duration*0.94). */
  progress?: number;
}) {
  // The first sample arrives right after model loading with a single scored
  // frame, so it reads as "0.1 FPS" and looks like a hang. Wait for a real
  // sample before showing rates and an ETA.
  const warming =
    active && (stats.processed_frames < 20 || stats.elapsed_seconds < 5);
  const remaining =
    active && !warming
      ? estimateRemainingSeconds(elapsed, progress, duration)
      : undefined;
  return (
    <div
      className="processing-stats live-processing"
      aria-label="实时处理速度"
      title={processingHelp}
    >
      <span className="processing-caption">
        {!active
          ? "任务结束前统计"
          : stats.stage === "finalizing"
            ? "画面处理完成"
            : "画面处理"}
      </span>
      {active && stats.stage === "inference" && !warming && (
        <span>
          最近 <strong>{fpsText(stats.recent_fps)}</strong>
        </span>
      )}
      <span>
        平均{" "}
        <strong>{warming ? "统计中…" : fpsText(stats.average_fps)}</strong>
      </span>
      {elapsed !== undefined && elapsed > 0 && Number.isFinite(elapsed) && (
        <span title="任务启动后的完成帧数 ÷ 墙钟耗时，包含指纹校验、音轨提取、模型加载和校准。">
          任务均速{" "}
          <strong>
            {warming ? "统计中…" : fpsText(stats.processed_frames / elapsed)}
          </strong>{" "}
          · {elapsed.toFixed(1)}s
        </span>
      )}
      {remaining !== undefined && (
        <span title="按当前速度线性外推，包含准备阶段；只用于判断还要等多久。">
          预计还需 <strong>{remainingText(remaining)}</strong>
        </span>
      )}
      <span className="processing-count">
        已处理 {stats.processed_frames.toLocaleString()} 帧 ·{" "}
        {stats.elapsed_seconds.toFixed(1)} 秒
      </span>
    </div>
  );
}

export function CompletedProcessingStats({
  summary,
}: {
  summary: AnalysisSummary;
}) {
  const rates = summaryRates(summary);
  return (
    <div className="processing-stats" aria-label="分析性能统计">
      <span className="processing-caption">结果记录</span>
      <span title={processingHelp}>
        画面处理平均 <strong>{fpsText(rates.processing)}</strong>
      </span>
      <span title="包括模型加载、校准、画面处理及声音融合；不包括 Go 的原片指纹校验与外部音轨提取。">
        分析平均 <strong>{fpsText(rates.analysis)}</strong>
      </span>
      {summary.decoder && (
        <span>
          {summary.hardware_decode
            ? "VideoToolbox 硬解（实验）"
            : "OpenCV 解码"}
        </span>
      )}
      {summary.pipeline_timings && (
        <span
          className="processing-stages"
          title="各阶段并行重叠，不能将阶段时间相加当总耗时。前向包含批量准备、GPU 计算和传回。"
        >
          {[
            ["producer_seconds", "解码/预处理"],
            ["forward_seconds", "前向/传回"],
            ["postprocess_seconds", "后处理"],
          ].map(([key, label]) => {
            const value = summary.pipeline_timings?.[key];
            return value !== undefined && Number.isFinite(value) ? (
              <span key={key}>
                {label} {value.toFixed(2)}s
              </span>
            ) : null;
          })}
        </span>
      )}
    </div>
  );
}
