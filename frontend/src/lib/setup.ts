import type { SetupState } from "../api/types";

export interface SetupStep {
  id: string;
  label: string;
}

export const SETUP_STEPS: SetupStep[] = [
  { id: "python", label: "Python 运行时" },
  { id: "packages", label: "视觉依赖（NumPy / OpenCV / PyTorch）" },
  { id: "model", label: "模型权重" },
  { id: "verify", label: "环境自检" },
];

export type SetupStepStatus = "done" | "active" | "pending";

export function setupSteps(
  state: SetupState,
): (SetupStep & { status: SetupStepStatus })[] {
  if (state.state === "ready") {
    return SETUP_STEPS.map((step) => ({ ...step, status: "done" }));
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
            ? "active"
            : "pending",
  }));
}

export function setupPercent(state: SetupState): number {
  return Math.max(0, Math.min(100, Math.round((state.progress ?? 0) * 100)));
}
