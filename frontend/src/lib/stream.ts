import type { AnalysisStream, BallTrack, Job } from "../api/types";

export interface OverlayStream {
  jobId: string;
  tracks: BallTrack[];
  table?: number[];
  seconds: number;
  tableStart?: number;
}

/** Accumulate overlay deltas; tracks are only ever appended within one job. */
export function mergeOverlay(
  previous: OverlayStream | null,
  update: AnalysisStream,
): OverlayStream {
  if (previous && previous.jobId === update.job_id) {
    return {
      ...previous,
      tracks: update.tracks?.length
        ? [...previous.tracks, ...update.tracks]
        : previous.tracks,
      table: update.table_bounds != null ? update.table_bounds : previous.table,
      tableStart:
        update.table_bounds != null &&
        JSON.stringify(update.table_bounds) !==
          JSON.stringify(previous.table ?? [])
          ? (update.processed_seconds ?? previous.seconds)
          : previous.tableStart,
      seconds: update.processed_seconds ?? previous.seconds,
    };
  }
  return {
    jobId: update.job_id,
    tracks: update.tracks ?? [],
    table: update.table_bounds ?? [],
    tableStart: update.processed_seconds ?? 0,
    seconds: update.processed_seconds ?? 0,
  };
}

/**
 * Overlay data is only live for the job the UI is currently showing. The worker
 * uses its own request id, so the backend must stamp updates with the manager's
 * job id; a mismatch silently disables the track/table toggles.
 */
export function liveOverlay(
  stream: OverlayStream | null,
  job: Job | undefined,
): OverlayStream | null {
  if (!stream || !job) return null;
  if (job.status !== "running" || stream.jobId !== job.id) return null;
  return stream;
}
