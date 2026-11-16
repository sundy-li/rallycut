import { describe, expect, it } from "vitest";
import { buildLabel, buildTitle } from "./build";

describe("buildLabel", () => {
  it("shows version, commit and dirty state", () => {
    expect(
      buildLabel({
        version: "0.1.0-alpha.4",
        commit: "8bb27b772238",
        dirty: true,
        build_time: "",
      }),
    ).toBe("v0.1.0-alpha.4 · 8bb27b772238 · 含未提交修改");
    expect(
      buildLabel({ version: "dev", commit: "", dirty: false, build_time: "" }),
    ).toBe("开发版 · 提交未知");
    expect(buildLabel(undefined)).toBe("");
  });

  it("adds the build time on hover only when valid", () => {
    const build = {
      version: "0.1.0",
      commit: "abc",
      dirty: false,
      build_time: "2026-11-16T04:30:00Z",
    };
    expect(buildTitle(build)).toContain("构建于");
    expect(buildTitle({ ...build, build_time: "bad" })).toBe("v0.1.0 · abc");
  });
});
