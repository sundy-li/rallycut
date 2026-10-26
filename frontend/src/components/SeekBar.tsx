import { useRef, useState } from "react";
import { timecode } from "../timeline";

interface Segment {
  start: number;
  end: number;
}
interface Props {
  duration: number;
  time: number;
  disabled?: boolean;
  /** Rally spans drawn as faint bands; purely informational. */
  segments?: Segment[];
  onSeek: (t: number) => void;
  /** Called with true when a drag starts and false when it ends. */
  onScrub?: (active: boolean) => void;
}

/** Draggable video progress bar, independent of any rally data. */
export default function SeekBar({
  duration,
  time,
  disabled,
  segments = [],
  onSeek,
  onScrub,
}: Props) {
  const track = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [dragging, setDragging] = useState(false);
  const usable = !disabled && duration > 0;
  const at = (clientX: number) => {
    const rect = track.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0) return 0;
    const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    return ratio * duration;
  };
  const pct = (t: number) =>
    `${duration > 0 ? Math.min(100, Math.max(0, (t / duration) * 100)) : 0}%`;
  const end = () => {
    if (!dragging) return;
    setDragging(false);
    onScrub?.(false);
  };
  return (
    <div
      ref={track}
      className={`seek-bar${dragging ? " dragging" : ""}${usable ? "" : " disabled"}`}
      role="slider"
      tabIndex={usable ? 0 : -1}
      aria-label="视频进度"
      aria-valuemin={0}
      aria-valuemax={Math.max(0, Math.round(duration * 10) / 10)}
      aria-valuenow={Math.round(time * 10) / 10}
      aria-valuetext={`${timecode(time)} / ${timecode(duration)}`}
      aria-disabled={!usable}
      onPointerDown={(e) => {
        if (!usable || e.button !== 0) return;
        e.preventDefault();
        e.currentTarget.setPointerCapture(e.pointerId);
        e.currentTarget.focus();
        setDragging(true);
        onScrub?.(true);
        onSeek(at(e.clientX));
      }}
      onPointerMove={(e) => {
        if (!usable) return;
        const t = at(e.clientX);
        setHover(t);
        if (dragging) onSeek(t);
      }}
      onPointerUp={end}
      onPointerCancel={end}
      onLostPointerCapture={end}
      onPointerLeave={() => setHover(null)}
      onKeyDown={(e) => {
        if (!usable) return;
        const step = e.shiftKey ? 5 : 1;
        const target =
          e.key === "ArrowLeft" || e.key === "ArrowDown"
            ? time - step
            : e.key === "ArrowRight" || e.key === "ArrowUp"
              ? time + step
              : e.key === "Home"
                ? 0
                : e.key === "End"
                  ? duration
                  : null;
        if (target === null) return;
        e.preventDefault();
        e.stopPropagation();
        onSeek(Math.min(duration, Math.max(0, target)));
      }}
    >
      <div className="seek-rail">
        {segments.map((s, i) => (
          <span
            key={i}
            className="seek-segment"
            style={{
              left: pct(s.start),
              width: `calc(${pct(s.end)} - ${pct(s.start)})`,
            }}
          />
        ))}
        <span className="seek-fill" style={{ width: pct(time) }} />
      </div>
      <span className="seek-knob" style={{ left: pct(time) }} />
      {hover !== null && usable && (
        <span className="seek-tip" style={{ left: pct(hover) }}>
          {timecode(hover)}
        </span>
      )}
    </div>
  );
}
