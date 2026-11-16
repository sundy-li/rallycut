import type { BuildInfo } from "../api/types";

/** "v0.1.0-alpha.4 · 8bb27b772238 · 含未提交修改", or "" before state loads. */
export function buildLabel(build?: BuildInfo): string {
  if (!build?.version) return "";
  const parts = [build.version === "dev" ? "开发版" : `v${build.version}`];
  parts.push(build.commit || "提交未知");
  if (build.dirty) parts.push("含未提交修改");
  return parts.join(" · ");
}

/** Hover text with the build time in local time. */
export function buildTitle(build?: BuildInfo): string {
  const label = buildLabel(build);
  if (!label || !build?.build_time) return label;
  const time = new Date(build.build_time);
  return Number.isNaN(time.getTime())
    ? label
    : `${label}\n构建于 ${time.toLocaleString()}`;
}
