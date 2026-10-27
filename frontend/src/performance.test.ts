import { describe, expect, it } from "vitest";
import { estimateRemainingSeconds, remainingText } from "./performance";

describe("analysis remaining-time estimate", () => {
  it("extrapolates from processed video time, not from frame counts", () => {
    // 300 s source at progress 0.47 means 150 s of video are done; 600 s of
    // wall clock so far means 2x slower than realtime -> about 600 s left.
    expect(estimateRemainingSeconds(600, 0.47, 300)).toBeCloseTo(600, 0);
  });

  it("stays silent until there is enough progress to extrapolate", () => {
    expect(estimateRemainingSeconds(600, 0.01, 300)).toBeUndefined();
    expect(estimateRemainingSeconds(2, 0.5, 300)).toBeUndefined();
    expect(estimateRemainingSeconds(60, 0.95, 300)).toBeUndefined();
    expect(estimateRemainingSeconds(60, 0.5, 0)).toBeUndefined();
    expect(estimateRemainingSeconds(Number.NaN, 0.5, 300)).toBeUndefined();
  });

  it("formats coarse durations", () => {
    expect(remainingText(undefined)).toBe("未记录");
    expect(remainingText(30)).toBe("不到 1 分钟");
    expect(remainingText(42 * 60)).toBe("约 42 分钟");
    expect(remainingText(80 * 60)).toBe("约 1 小时 20 分钟");
    expect(remainingText(120 * 60)).toBe("约 2 小时");
  });
});
