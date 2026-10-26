import { useEffect, useState } from "react";
import { Cpu, Gauge, Scissors, Settings, X } from "lucide-react";
import type { ExportSettings, Rules } from "../api/types";
import EncodingOptions from "./EncodingOptions";
import { SKIP_STEPS } from "../playback";
import { shortcutKeys } from "../lib/shortcuts";

export type SettingsTab = "buffer" | "export" | "playback";

interface Props {
  /** Project settings are only editable with a project open. */
  hasProject: boolean;
  disabled: boolean;
  rules: Rules;
  onRules: (rules: Rules) => void;
  exportSettings?: ExportSettings;
  sourceBitRate: number;
  onExportSettings: (settings: ExportSettings) => void;
  skipStep: number;
  onSkipStep: (step: number) => void;
  onClose: () => void;
}

const TABS: { id: SettingsTab; label: string; icon: typeof Cpu }[] = [
  { id: "buffer", label: "片段缓冲", icon: Scissors },
  { id: "export", label: "导出编码", icon: Cpu },
  { id: "playback", label: "播放", icon: Gauge },
];

/** ⌘, settings page: project clip / export settings plus playback prefs. */
export default function SettingsDialog(props: Props) {
  const { onClose } = props;
  const [tab, setTab] = useState<SettingsTab>("buffer");
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [onClose]);
  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <section
        className="settings-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header>
          <h2 id="settings-title">
            <Settings size={16} />
            设置
          </h2>
          <button
            className="icon-button"
            aria-label="关闭设置"
            title="关闭（Esc）"
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </header>
        <div className="settings-body">
          <nav className="settings-nav" role="tablist" aria-label="设置分类">
            {TABS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                role="tab"
                aria-selected={tab === id}
                className={tab === id ? "current" : ""}
                onClick={() => setTab(id)}
              >
                <Icon size={14} />
                {label}
              </button>
            ))}
          </nav>
          <div className="settings-pane" role="tabpanel">
            {tab === "buffer" && <BufferPane {...props} />}
            {tab === "export" && <ExportPane {...props} />}
            {tab === "playback" && <PlaybackPane {...props} />}
          </div>
        </div>
      </section>
    </div>
  );
}

function ProjectScope({ hasProject }: { hasProject: boolean }) {
  return (
    <p className="settings-scope">
      {hasProject
        ? "保存在当前项目中，只影响这个项目。"
        : "打开项目后才能设置。"}
    </p>
  );
}

function BufferPane({ hasProject, disabled, rules, onRules }: Props) {
  const [draft, setDraft] = useState(rules);
  useEffect(() => setDraft(rules), [rules]);
  const valid = Object.values(draft).every(
    (v) => Number.isFinite(v) && v >= 0 && v <= 60,
  );
  const field = (
    id: string,
    label: string,
    key: keyof Rules,
    step: string,
    hint: string,
  ) => (
    <div className="rule-row">
      <label htmlFor={id}>
        {label}
        <small>{hint}</small>
      </label>
      <div>
        <input
          id={id}
          type="number"
          step={step}
          min="0"
          max="60"
          value={Number.isFinite(draft[key]) ? draft[key] : ""}
          onChange={(e) =>
            setDraft({
              ...draft,
              [key]: e.target.value === "" ? NaN : Number(e.target.value),
            })
          }
        />{" "}
        s
      </div>
    </div>
  );
  return (
    <>
      <h3>片段缓冲</h3>
      <p className="muted small">
        导出时在每个回合前后多保留一点，让起手与落点更完整；不改变识别出的回合边界。
      </p>
      <ProjectScope hasProject={hasProject} />
      <fieldset disabled={disabled || !hasProject}>
        {field("pre", "回合前保留", "pre_roll", "0.1", "发球前")}
        {field("post", "回合后保留", "post_roll", "0.1", "回合结束后")}
        {field(
          "min",
          "长回合阈值",
          "min_duration",
          "1",
          "“长回合”按钮勾选不短于它的回合",
        )}
        <button
          className="button ghost full"
          disabled={!valid}
          onClick={() => onRules(draft)}
        >
          应用剪辑规则
        </button>
      </fieldset>
    </>
  );
}

function ExportPane({
  hasProject,
  disabled,
  exportSettings,
  sourceBitRate,
  onExportSettings,
}: Props) {
  return (
    <>
      <h3>导出编码</h3>
      <ProjectScope hasProject={hasProject} />
      <EncodingOptions
        settings={exportSettings}
        sourceBitRate={sourceBitRate}
        disabled={disabled || !hasProject}
        onSave={onExportSettings}
      />
    </>
  );
}

function PlaybackPane({ skipStep, onSkipStep }: Props) {
  return (
    <>
      <h3>播放</h3>
      <p className="settings-scope">本机偏好，对所有项目生效。</p>
      <div className="rule-row">
        <label htmlFor="settings-step">
          快进 / 快退步长
          <small>
            {shortcutKeys("skipBack")} / {shortcutKeys("skipForward")}{" "}
            每次跳转的秒数，与播放器“步长”同步
          </small>
        </label>
        <div>
          <select
            id="settings-step"
            value={skipStep}
            onChange={(e) => onSkipStep(Number(e.target.value))}
          >
            {SKIP_STEPS.map((step) => (
              <option key={step} value={step}>
                {step}s
              </option>
            ))}
          </select>
        </div>
      </div>
    </>
  );
}
