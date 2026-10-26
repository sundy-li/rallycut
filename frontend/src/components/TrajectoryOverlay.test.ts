import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import TrajectoryOverlay, { validTableBounds } from "./TrajectoryOverlay";

const props = {
  tracks: [
    {
      id: "unit-track",
      points: [
        { t: 2, x: 0.2, y: 0.3, confidence: 0.9 },
        { t: 2.04, x: 0.3, y: 0.3, confidence: 0.9 },
        { t: 2.08, x: 0.4, y: 0.3, confidence: 0.9 },
      ],
    },
  ],
  time: 2.08,
  aspect: 16 / 9,
  bounds: [0.1, 0.4, 0.9, 0.6],
  method: "blurball-pretrained-v1",
};
const render = (
  showTracks: boolean,
  showTable: boolean,
  bounds = props.bounds,
) =>
  renderToStaticMarkup(
    createElement(TrajectoryOverlay, {
      ...props,
      showTracks,
      showTable,
      bounds,
    }),
  );

describe("independent video overlays", () => {
  it("renders nothing with both switches off", () =>
    expect(render(false, false)).toBe(""));
  it("shows ball trajectories without table geometry", () => {
    const markup = render(true, false);
    expect(markup).toContain('data-testid="ball-tracks-overlay"');
    expect(markup).toContain("<circle");
    expect(markup).toContain("PRETRAINED TRACKS");
    expect(markup).not.toContain('data-testid="table-overlay"');
    expect(markup).not.toContain("<rect");
  });
  it("shows table geometry without ball trajectories or trajectory label", () => {
    const markup = render(false, true);
    expect(markup).toContain('data-testid="table-overlay"');
    expect(markup).toContain("<rect");
    expect(markup).not.toContain('data-testid="ball-tracks-overlay"');
    expect(markup).not.toContain("<circle");
    expect(markup).not.toContain("PRETRAINED TRACKS");
  });
  it("can show both independently", () => {
    const markup = render(true, true);
    expect(markup).toContain('data-testid="table-overlay"');
    expect(markup).toContain('data-testid="ball-tracks-overlay"');
  });
  it("rejects invalid ROI without hiding available trajectories", () => {
    for (const bounds of [
      [],
      [0, 0.1, NaN, 0.5],
      [0.8, 0.1, 0.2, 0.5],
      [-0.1, 0, 0.8, 0.8],
    ]) {
      expect(validTableBounds(bounds)).toBe(false);
      expect(render(false, true, bounds)).toBe("");
      expect(render(true, true, bounds)).toContain(
        'data-testid="ball-tracks-overlay"',
      );
    }
  });
});
