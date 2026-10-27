import {
  Check,
  CircleAlert,
  Download,
  LoaderCircle,
  RotateCw,
  ShieldCheck,
} from "lucide-react";
import type { SetupState } from "../api/types";
import { setupPercent, setupSteps } from "../lib/setup";

interface Props {
  state: SetupState;
  busy?: boolean;
  onStart: () => void;
  onRecheck: () => void;
}

export function SetupScreen({
  state,
  busy = false,
  onStart,
  onRecheck,
}: Props) {
  const percent = setupPercent(state);
  const checking = state.state === "checking";
  const running = state.state === "running";
  const failed = state.state === "failed";
  const blocked = busy || checking || running;
  const title = checking
    ? "正在检查运行环境"
    : failed
      ? "环境准备未完成"
      : running
        ? "正在准备运行环境"
        : "先准备环境，再开始剪辑";
  return (
    <main
      className="setup-screen"
      aria-labelledby="setup-title"
      aria-busy={running || checking}
    >
      <section className="setup-card">
        <div className="setup-brand">
          <span className="brand-mark" aria-hidden="true">
            <span />
            <span />
            <i />
          </span>
          <strong>rallycut</strong>
          <span className="setup-edition">首次使用准备</span>
        </div>
        <div className="setup-platform">
          {state.platform || "正在识别当前平台"}
        </div>
        <h1 id="setup-title">{title}</h1>
        <p className="setup-lead">
          {checking
            ? "自动检测 Python、视频处理工具、分析依赖和模型。这里只检查，不会自动下载。"
            : running
              ? "正在为当前平台下载、安装并校验依赖。可以保留窗口等待；全部自检通过后，自动进入项目列表。"
              : "检测到环境尚未就绪。点击下方按钮，为当前 Windows 或 macOS 准备缺少的依赖；不需要手动安装 Python 或 FFmpeg。"}
        </p>
        <ol className="setup-steps" aria-label="环境准备步骤">
          {setupSteps(state).map((step) => (
            <li key={step.id} className={step.status}>
              <span className="setup-step-icon" aria-hidden="true">
                {step.status === "done" ? (
                  <Check size={14} />
                ) : step.status === "failed" ? (
                  <CircleAlert size={14} />
                ) : step.status === "active" ? (
                  <LoaderCircle size={14} className="spin" />
                ) : (
                  <i />
                )}
              </span>
              <span>{step.label}</span>
              <span className="setup-step-status">
                {
                  {
                    done: "已就绪",
                    active: "准备中",
                    failed: "未完成",
                    pending: checking ? "待检查" : "待准备",
                  }[step.status]
                }
              </span>
            </li>
          ))}
        </ol>
        {(running || failed || checking) && (
          <div className="setup-progress-area">
            <div
              className={`setup-progress${failed ? " failed" : ""}${state.indeterminate || checking ? " indeterminate" : ""}`}
              role="progressbar"
              aria-valuenow={checking ? undefined : percent}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="环境准备进度"
              aria-valuetext={
                checking
                  ? "正在检测依赖"
                  : `整体阶段进度 ${percent}%，${state.message}`
              }
            >
              <div
                className="setup-progress-bar"
                style={{ transform: `scaleX(${checking ? 0 : percent / 100})` }}
              />
            </div>
            <div className="setup-percent">
              {checking
                ? "正在检测，不下载依赖"
                : `整体阶段进度 ${percent}%${state.indeterminate && running ? " · 当前步骤处理中" : ""}`}
            </div>
          </div>
        )}
        <p className="setup-detail" role="status" aria-live="polite">
          {state.message}
        </p>
        {state.detail && (
          <p className="setup-log" title={state.detail}>
            {state.detail}
          </p>
        )}
        {failed && (
          <div className="setup-error" role="alert">
            <CircleAlert size={15} />
            <span>
              {state.error || "准备失败，请检查网络或磁盘空间后重试。"}
            </span>
          </div>
        )}
        {!checking && !running && (
          <>
            <p className="setup-consent">
              首次准备需要联网，下载量可能从数百 MB 到数
              GB，耗时取决于网络和平台。建议预留至少 5 GB 空间。依赖只安装在
              RallyCut 的专用目录，不替换系统 Python、不修改全局 PATH。
            </p>
            <div className="setup-actions">
              <button
                className="button primary"
                disabled={blocked}
                onClick={onStart}
              >
                {busy ? (
                  <LoaderCircle size={15} className="spin" />
                ) : failed ? (
                  <RotateCw size={15} />
                ) : (
                  <Download size={15} />
                )}
                {failed ? "重试准备环境" : "开始准备环境"}
              </button>
              <button
                className="button ghost"
                disabled={blocked}
                onClick={onRecheck}
              >
                <RotateCw size={14} />
                重新检测
              </button>
            </div>
          </>
        )}
        <p className="setup-blocked-note">
          环境未就绪前，不能进入剪辑界面。关闭应用会中断准备，下次可重新检查并重试。
        </p>
        <p className="setup-footnote">
          <ShieldCheck size={13} />
          <span>
            视频和项目不会上传。依赖来自固定版本上游源；下载服务可能记录访问日志。
          </span>
        </p>
      </section>
    </main>
  );
}
