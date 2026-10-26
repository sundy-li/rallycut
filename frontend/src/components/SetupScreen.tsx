import {
  Check,
  CircleAlert,
  LoaderCircle,
  RotateCw,
  ShieldCheck,
} from "lucide-react";
import type { SetupState } from "../api/types";
import { setupPercent, setupSteps } from "../lib/setup";

interface Props {
  state: SetupState;
  onRetry: () => void;
}

export function SetupScreen({ state, onRetry }: Props) {
  const percent = setupPercent(state);
  const failed = state.state === "failed";
  return (
    <div className="setup-screen">
      <div className="setup-card">
        <div className="setup-brand">
          <span className="brand-mark">
            <span />
            <span />
            <i />
          </span>
          <strong>rallycut</strong>
          <span className="setup-edition">LOCAL STUDIO</span>
        </div>
        <h1>{failed ? "运行环境准备失败" : "正在准备运行环境"}</h1>
        <p className="setup-lead">
          首次启动需要安装 Python 依赖并下载模型权重，约 1–3
          分钟；完成后即可离线使用。
        </p>
        <div
          className={`setup-progress${failed ? " failed" : ""}`}
          role="progressbar"
          aria-valuenow={percent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="环境准备进度"
        >
          <div
            className="setup-progress-bar"
            style={{ width: `${percent}%` }}
          />
        </div>
        <div className="setup-percent">{percent}%</div>
        <ol className="setup-steps">
          {setupSteps(state).map((step) => (
            <li key={step.id} className={step.status}>
              <span className="setup-step-icon">
                {step.status === "done" ? (
                  <Check size={12} />
                ) : step.status === "active" ? (
                  <LoaderCircle size={12} className="spin" />
                ) : (
                  <i />
                )}
              </span>
              <span>{step.label}</span>
            </li>
          ))}
        </ol>
        <p className="setup-detail" title={`${state.message} ${state.detail}`}>
          {state.detail || state.message}
        </p>
        {failed && (
          <div className="setup-error" role="alert">
            <CircleAlert size={14} />
            <span>{state.error || "初始化失败"}</span>
            <button className="button subtle small-button" onClick={onRetry}>
              <RotateCw size={13} />
              重试
            </button>
          </div>
        )}
        <p className="setup-footnote">
          <ShieldCheck size={12} />
          依赖与权重只从官方源下载，不收集任何数据。
        </p>
      </div>
    </div>
  );
}
