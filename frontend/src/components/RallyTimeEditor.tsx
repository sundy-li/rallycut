import { useRef, useState } from "react";
import { Check, Crosshair, X } from "lucide-react";
import {
  formatRallyTime,
  parseRallyTime,
  rallyTimeError,
} from "../lib/rallies";

interface Props {
  start: number;
  end: number;
  duration: number;
  playhead: number;
  onSave: (start: number, end: number) => void;
  onCancel: () => void;
}

/**
 * Inline start/end editor shown on a rally card after double-clicking its time
 * range. Enter or leaving the editor saves; Esc cancels. Leaving with invalid
 * input cancels so a half-typed value can never be committed.
 */
export default function RallyTimeEditor({
  start,
  end,
  duration,
  playhead,
  onSave,
  onCancel,
}: Props) {
  const [startText, setStartText] = useState(formatRallyTime(start));
  const [endText, setEndText] = useState(formatRallyTime(end));
  const [error, setError] = useState("");
  const root = useRef<HTMLDivElement>(null);
  const done = useRef(false);

  const finish = (fromBlur: boolean) => {
    if (done.current) return;
    const s = parseRallyTime(startText);
    const e = parseRallyTime(endText);
    const problem = rallyTimeError(s, e, duration);
    if (problem) {
      if (fromBlur) {
        done.current = true;
        onCancel();
      } else setError(problem);
      return;
    }
    done.current = true;
    if (Math.abs(s! - start) < 1e-3 && Math.abs(e! - end) < 1e-3) onCancel();
    else onSave(Math.round(s! * 1000) / 1000, Math.round(e! * 1000) / 1000);
  };
  const cancel = () => {
    if (done.current) return;
    done.current = true;
    onCancel();
  };

  const field = (
    label: string,
    value: string,
    set: (v: string) => void,
    autoFocus: boolean,
  ) => (
    <span className="rally-time-field">
      <input
        aria-label={label}
        value={value}
        autoFocus={autoFocus}
        spellCheck={false}
        inputMode="decimal"
        onFocus={(e) => e.currentTarget.select()}
        onChange={(e) => {
          set(e.target.value);
          setError("");
        }}
      />
      <button
        type="button"
        title={`${label}设为播放器当前时间`}
        aria-label={`${label}设为当前时间`}
        // Keep focus in the editor so this doesn't count as leaving it.
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => {
          set(formatRallyTime(playhead));
          setError("");
        }}
      >
        <Crosshair size={11} />
      </button>
    </span>
  );

  return (
    <div
      ref={root}
      className="rally-time-editor"
      role="group"
      aria-label="修改回合起止时间"
      onClick={(e) => e.stopPropagation()}
      onDoubleClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        e.stopPropagation();
        if (e.key === "Enter") {
          e.preventDefault();
          finish(false);
        } else if (e.key === "Escape") {
          e.preventDefault();
          cancel();
        }
      }}
      onBlur={(e) => {
        if (!root.current?.contains(e.relatedTarget as Node | null))
          finish(true);
      }}
    >
      <div className="rally-time-row">
        {field("开始时间", startText, setStartText, true)}
        <i>—</i>
        {field("结束时间", endText, setEndText, false)}
        <button
          type="button"
          className="rally-time-action"
          title="保存（Enter）"
          aria-label="保存起止时间"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => finish(false)}
        >
          <Check size={13} />
        </button>
        <button
          type="button"
          className="rally-time-action"
          title="取消（Esc）"
          aria-label="取消修改"
          onMouseDown={(e) => e.preventDefault()}
          onClick={cancel}
        >
          <X size={13} />
        </button>
      </div>
      {error ? (
        <p className="rally-time-error" role="alert">
          {error}
        </p>
      ) : (
        <p className="rally-time-hint">Enter 保存 · Esc 取消</p>
      )}
    </div>
  );
}
