import { describe, expect, it } from "vitest";
import { describeMediaError } from "./media";

describe("media failure diagnostics", () => {
  it("does not diagnose an HTML/unsupported-source response as a certain codec failure", () => {
    const message = describeMediaError({ code: 4, message: "Format error" });
    expect(message).toContain("不一定是编码问题");
    expect(message).toContain("错误码 4");
    expect(message).not.toContain("系统 WebView 不支持此编码");
  });
  it("distinguishes read failures and decode failures", () => {
    expect(describeMediaError({ code: 2, message: "" })).toContain("读取失败");
    expect(describeMediaError({ code: 3, message: "" })).toContain("解码失败");
    expect(describeMediaError(null)).toContain("重试");
  });
  it("bounds native error messages", () => {
    expect(
      describeMediaError({ code: 4, message: "x".repeat(10000) }).length,
    ).toBeLessThan(350);
  });
});
