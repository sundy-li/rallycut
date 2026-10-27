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
  { id: "model", label: "模型权重" },
  { id: "verify", label: "环境自检" },
];

export type SetupStepStatus = "done" | "active" | "pending" | "failed";

export function setupSteps(
  state: SetupState,
): (SetupStep & { status: SetupStepStatus })[] {
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
