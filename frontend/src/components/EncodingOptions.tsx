import { useEffect, useState } from "react";
import { Cpu } from "lucide-react";
import type { ExportSettings } from "../api/types";

export const defaultExport: ExportSettings = {
  codec: "h264",
  encoder: "auto",
  bit_rate: 0,
};
interface Props {
  settings?: ExportSettings;
  sourceBitRate: number;
  disabled: boolean;
  onSave: (settings: ExportSettings) => void;
}

export default function EncodingOptions({
  settings,
  sourceBitRate,
  disabled,
  onSave,
}: Props) {
  const [draft, setDraft] = useState(settings ?? defaultExport);
  const [mbps, setMbps] = useState(
    settings?.bit_rate ? String(settings.bit_rate / 1e6) : "",
  );
  useEffect(() => {
    setDraft(settings ?? defaultExport);
    setMbps(settings?.bit_rate ? String(settings.bit_rate / 1e6) : "");
  }, [settings]);
  const bitrate = mbps === "" ? 0 : Math.round(Number(mbps) * 1e6);
  const valid =
    Number.isFinite(bitrate) &&
    (bitrate === 0 || (bitrate >= 500000 && bitrate <= 200000000));
  return (
    <section className="encoding-options">
      <div className="eyebrow">
        <Cpu size={12} />
        导出编码
      </div>
      <fieldset disabled={disabled}>
        <label htmlFor="codec">
          视频格式
          <select
            id="codec"
            value={draft.codec}
            onChange={(e) =>
              setDraft({
                ...draft,
                codec: e.target.value as ExportSettings["codec"],
              })
            }
          >
            <option value="h264">H.264 · 兼容优先</option>
            <option value="hevc">HEVC · H.265</option>
          </select>
        </label>
        <label htmlFor="encoder">
          编码方式
          <select
            id="encoder"
            value={draft.encoder}
            onChange={(e) =>
              setDraft({
                ...draft,
                encoder: e.target.value as ExportSettings["encoder"],
              })
            }
          >
            <option value="auto">VideoToolbox 优先</option>
            <option value="software">软件编码</option>
          </select>
        </label>
        <label htmlFor="bitrate">
          目标码率 <span>Mbps</span>
          <input
            id="bitrate"
            type="number"
            min="0.5"
            max="200"
            step="0.1"
            placeholder={
              sourceBitRate > 0
                ? `${(sourceBitRate / 1e6).toFixed(2)}（原片）`
                : "自动"
            }
            value={mbps}
            onChange={(e) => setMbps(e.target.value)}
          />
        </label>
        <p className="muted small">
          留空跟随原片码率。硬件不可用时整批回退软件编码；软件默认使用质量模式。
        </p>
        <button
          className="button ghost full"
          disabled={!valid}
          onClick={() => onSave({ ...draft, bit_rate: bitrate })}
        >
          应用导出设置
        </button>
      </fieldset>
    </section>
  );
}
