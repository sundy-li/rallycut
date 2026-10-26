import { useMemo } from "react";
import type { BallTrack } from "../api/types";

interface Props {
  tracks: BallTrack[];
  time: number;
  aspect: number;
  bounds?: number[] | null;
  method?: string;
  showTracks: boolean;
  showTable: boolean;
}

export function validTableBounds(bounds?: number[] | null): bounds is number[] {
  return Boolean(
    bounds?.length === 4 &&
    bounds.every((n) => Number.isFinite(n) && n >= 0 && n <= 1) &&
    bounds[0] < bounds[2] &&
    bounds[1] < bounds[3],
  );
}

export default function TrajectoryOverlay({
  tracks,
  time,
  aspect,
  bounds,
  method,
  showTracks,
  showTable,
}: Props) {
  const height =
    1000 / (Number.isFinite(aspect) && aspect > 0 ? aspect : 16 / 9);
  const drawTable = showTable && validTableBounds(bounds);
  const visible = useMemo(
    () =>
      showTracks
        ? tracks
            .filter(
              (track) =>
                (track.points[0]?.t ?? Infinity) <= time + 0.1 &&
                (track.points.at(-1)?.t ?? -Infinity) >= time - 0.3,
            )
            .map((track) => ({
              ...track,
              points: track.points.filter(
                (p) => p.t >= time - 0.3 && p.t <= time + 0.1,
              ),
            }))
        : [],
    [tracks, time, showTracks],
  );

  if (!showTracks && !drawTable) return null;
  return (
    <svg
      className="trajectory-overlay"
      viewBox={`0 0 1000 ${height}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="视频分析叠加层"
    >
      {drawTable && (
        <g data-testid="table-overlay" aria-label="球桌范围">
          <rect
            x={bounds![0] * 1000}
            y={bounds![1] * height}
            width={(bounds![2] - bounds![0]) * 1000}
            height={(bounds![3] - bounds![1]) * height}
            fill="none"
            stroke="#b6ee83"
            strokeWidth="1.5"
            strokeDasharray="6 5"
          />
          <text x="14" y={showTracks ? 41 : 23} fill="#b6ee83" fontSize="12">
            主球桌校准范围 · 近似 ROI
          </text>
        </g>
      )}
      {showTracks && (
        <g data-testid="ball-tracks-overlay" aria-label="球轨迹">
          {visible.map((track) => (
            <g key={track.id}>
              <polyline
                points={track.points
                  .map((p) => `${p.x * 1000},${p.y * height}`)
                  .join(" ")}
                fill="none"
                stroke="#ffbd68"
                strokeWidth="2"
              />
              {track.points.slice(-1).map((p) => (
                <circle
                  key={p.t}
                  cx={p.x * 1000}
                  cy={p.y * height}
                  r="7"
                  stroke="#ffbd68"
                  strokeWidth="2"
                  fill="none"
                />
              ))}
            </g>
          ))}
          <text x="14" y="23" fill="#ffbd68" fontSize="12">
            {method === "blurball-pretrained-v1"
              ? "PRETRAINED TRACKS"
              : "CLASSICAL BALL CANDIDATES"}
          </text>
        </g>
      )}
    </svg>
  );
}
