import { describe, expect, it } from "vitest";
import { liveOverlay, mergeOverlay } from "./stream";
import type { AnalysisStream, BallTrack, Job } from "../api/types";

const job = (overrides: Partial<Job> = {}): Job => ({
  id: "job-1",
  kind: "analysis",
  status: "running",
  progress: 0.2,
  message: "",
  ...overrides,
});

const track = (id: string): BallTrack => ({ id, points: [] });
const update = (overrides: Partial<AnalysisStream> = {}): AnalysisStream => ({
  job_id: "job-1",
  ...overrides,
});

describe("mergeOverlay", () => {
  it("appends tracks and keeps the last table for the same job", () => {
    const first = mergeOverlay(
      null,
      update({
        tracks: [track("a")],
        table_bounds: [0, 0, 1, 1],
        processed_seconds: 5,
      }),
    );
    const second = mergeOverlay(
      first,
      update({ tracks: [track("b")], processed_seconds: 9 }),
    );
    expect(second.tracks.map((item) => item.id)).toEqual(["a", "b"]);
    expect(second.table).toEqual([0, 0, 1, 1]);
    expect(second.seconds).toBe(9);
  });

  it("an explicit empty table clears the old shot but keeps trajectories", () => {
    const first = mergeOverlay(
      null,
      update({
        tracks: [track("a")],
        table_bounds: [0.1, 0.3, 0.9, 0.5],
        processed_seconds: 2,
      }),
    );
    const next = mergeOverlay(
      first,
      update({ table_bounds: [], processed_seconds: 6 }),
    );
    expect(next.table).toEqual([]);
    expect(next.tableStart).toBe(6);
    expect(next.tracks).toEqual(first.tracks);
    const later = mergeOverlay(
      next,
      update({ tracks: [track("b")], processed_seconds: 8 }),
    );
    expect(later.table).toEqual([]);
    expect(later.tracks).toHaveLength(2);
  });
  it("starts over when another job reports", () => {
    const first = mergeOverlay(null, update({ tracks: [track("a")] }));
    const second = mergeOverlay(
      first,
      update({ job_id: "job-2", tracks: [track("b")] }),
    );
    expect(second.jobId).toBe("job-2");
    expect(second.tracks.map((item) => item.id)).toEqual(["b"]);
  });
});

describe("liveOverlay", () => {
  it("rejects updates stamped with the worker request id", () => {
    const stream = mergeOverlay(
      null,
      update({ job_id: "worker-internal", tracks: [track("a")] }),
    );
    expect(liveOverlay(stream, job())).toBeNull();
  });

  it("accepts the running job the UI is showing", () => {
    const stream = mergeOverlay(null, update({ tracks: [track("a")] }));
    expect(liveOverlay(stream, job())).toBe(stream);
  });

  it("drops overlay data once the job stops running", () => {
    const stream = mergeOverlay(null, update({ tracks: [track("a")] }));
    expect(liveOverlay(stream, job({ status: "completed" }))).toBeNull();
  });
});
