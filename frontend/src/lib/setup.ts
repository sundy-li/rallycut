import type { SetupState } from "../api/types";

// Wails events and RPC responses can arrive in a different order. A late
// running/required response must not hide a newer verified-ready event.
export function mergeSetup(
  current: SetupState | undefined,
  incoming: SetupState,
): SetupState {
  return (current?.revision ?? 0) > (incoming.revision ?? 0)
    ? current!
    : incoming;
}

export interface SetupStep {
  id: string;
  label: string;
}

export const SETUP_STEPS: SetupStep[] = [
  { id: "python", label: "Python 运行时" },
  { id: "media", label: "视频处理工具（FFmpeg / FFprobe）" },
  { id: "packages", label: "视觉依赖（NumPy / OpenCV / PyTorch）" },
  { id: "model", label: "模型文件（下载与校验）" },
  { id: "verify", label: "模型加载与运行自检" },
];

export type SetupStepStatus = "done" | "active" | "pending" | "failed";

export function setupSteps(
  state: SetupState,
): (SetupStep & { status: SetupStepStatus })[] {
  if (state.runtime_mode === "installed") {
    const ready = (id: string) =>
      state.checks?.some((check) => check.id === id && check.ready) ||
      state.state === "ready";
    const runtimeReady = ["python", "media", "packages"].every(ready);
    const status = (id: string, done: boolean): SetupStepStatus => {
      if (done) return "done";
      if (state.state === "failed" && (id === "installed" || state.step === id))
        return "failed";
      if (
        state.state === "running" &&
        (id === state.step ||
          (id === "installed" &&
            ["python", "media", "packages"].includes(state.step)))
      )
        return "active";
      return "pending";
    };
    return [
      {
        id: "installed",
        label: "软件内置运行环境",
        status: status("installed", runtimeReady),
      },
      {
        id: "model",
        label: "首次模型文件（约 6 MB）",
        status: status("model", ready("model")),
      },
      {
        id: "verify",
        label: "模型运行自检",
        status: status("verify", ready("verify")),
      },
    ];
  }
  if (state.state === "ready") {
    return SETUP_STEPS.map((step) => ({ ...step, status: "done" }));
  }
  if (state.state === "required" || state.state === "checking") {
    return SETUP_STEPS.map((step) => ({
      ...step,
      status: state.checks?.find((item) => item.id === step.id)?.ready
        ? "done"
        : "pending",
    }));
  }
  const current = SETUP_STEPS.findIndex((step) => step.id === state.step);
  return SETUP_STEPS.map((step, index) => ({
    ...step,
    status:
      current < 0
        ? "pending"
        : index < current
          ? "done"
          : index === current
            ? state.state === "failed"
              ? "failed"
              : "active"
            : "pending",
  }));
}

export function setupPercent(state: SetupState): number {
  if (state.state === "ready") return 100;
  const progress = Number.isFinite(state.progress) ? state.progress : 0;
  return Math.max(0, Math.min(99, Math.round(progress * 100)));
}
