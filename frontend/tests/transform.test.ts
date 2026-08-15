import { describe, it, expect } from "vitest";
import {
  screenToLabelMap,
  labelMapToScreen,
  type Viewport,
  type Point,
} from "../src/geometry/transform";

/**
 * Coverage for the single shared screen<->label-map transform (PITFALLS.md
 * Pitfall 7): "test at extreme zoom-in and extreme zoom-out, not just
 * mid-zoom" is a literal requirement here, not a suggestion.
 */

const identityViewport: Viewport = {
  zoom: 1,
  panX: 0,
  panY: 0,
  devicePixelRatio: 1,
  panelOffset: { x: 0, y: 0 },
};

describe("screenToLabelMap", () => {
  it("maps a screen point to the same label-map coordinate under an identity viewport", () => {
    const p: Point = { x: 42, y: 17 };
    expect(screenToLabelMap(p, identityViewport)).toEqual({ x: 42, y: 17 });
  });

  it("floors 3.99 down to region 3, not up to 4", () => {
    const vp: Viewport = { ...identityViewport, panX: 0 };
    const p: Point = { x: 3.99, y: 3.99 };
    expect(screenToLabelMap(p, vp)).toEqual({ x: 3, y: 3 });
  });

  it("floors an exact integer boundary (4.0) to 4, not to 3", () => {
    const p: Point = { x: 4.0, y: 4.0 };
    expect(screenToLabelMap(p, identityViewport)).toEqual({ x: 4, y: 4 });
  });

  it("never returns a non-integer component, matching NumPy's floor-based pixel binning", () => {
    const vp: Viewport = {
      zoom: 2.37,
      panX: 5.5,
      panY: -3.25,
      devicePixelRatio: 1.5,
      panelOffset: { x: 12.1, y: -4.9 },
    };
    const result = screenToLabelMap({ x: 123.456, y: -78.9 }, vp);
    expect(Number.isInteger(result.x)).toBe(true);
    expect(Number.isInteger(result.y)).toBe(true);
  });

  it("floors toward negative infinity for points above/left of the panel origin (-0.5 -> -1, not 0)", () => {
    const p: Point = { x: -0.5, y: -0.5 };
    expect(screenToLabelMap(p, identityViewport)).toEqual({ x: -1, y: -1 });
  });

  it("halves the label-map delta for the same screen delta under devicePixelRatio: 2", () => {
    const vp1: Viewport = { ...identityViewport, devicePixelRatio: 1 };
    const vp2: Viewport = { ...identityViewport, devicePixelRatio: 2 };
    const screenDelta = 20;
    const r1 = screenToLabelMap({ x: screenDelta, y: 0 }, vp1);
    const r2 = screenToLabelMap({ x: screenDelta, y: 0 }, vp2);
    expect(r2.x).toBe(r1.x / 2);
  });

  it("shifts label-map coordinates by exactly the panelOffset", () => {
    const vpNoOffset: Viewport = { ...identityViewport, panelOffset: { x: 0, y: 0 } };
    const vpWithOffset: Viewport = { ...identityViewport, panelOffset: { x: 10, y: 5 } };
    const screenPoint: Point = { x: 50, y: 50 };
    const noOffset = screenToLabelMap(screenPoint, vpNoOffset);
    const withOffset = screenToLabelMap(screenPoint, vpWithOffset);
    expect(withOffset).toEqual({ x: noOffset.x - 10, y: noOffset.y - 5 });
  });
});

describe("round trip: labelMapToScreen then screenToLabelMap", () => {
  const points: Point[] = [
    { x: 0, y: 0 },
    { x: 4327, y: 6891 },
  ];

  it("recovers the original label-map point at extreme zoom-in (zoom: 64)", () => {
    const vp: Viewport = {
      zoom: 64,
      panX: 100,
      panY: 200,
      devicePixelRatio: 1,
      panelOffset: { x: 0, y: 0 },
    };
    for (const p of points) {
      const screen = labelMapToScreen(p, vp);
      const back = screenToLabelMap(screen, vp);
      expect(back).toEqual(p);
    }
  });

  it("recovers the original label-map point at extreme zoom-out (zoom: 0.05)", () => {
    const vp: Viewport = {
      zoom: 0.05,
      panX: -50,
      panY: 30,
      devicePixelRatio: 1,
      panelOffset: { x: 0, y: 0 },
    };
    for (const p of points) {
      const screen = labelMapToScreen(p, vp);
      const back = screenToLabelMap(screen, vp);
      expect(back).toEqual(p);
    }
  });

  it("recovers the original label-map point at extreme zoom-in (zoom: 64) with a large coordinate", () => {
    const vp: Viewport = {
      zoom: 64,
      panX: -1000,
      panY: 2500,
      devicePixelRatio: 1,
      panelOffset: { x: 0, y: 0 },
    };
    const p: Point = { x: 999999, y: 1 };
    const screen = labelMapToScreen(p, vp);
    const back = screenToLabelMap(screen, vp);
    expect(back).toEqual(p);
  });
});

describe("labelMapToScreen", () => {
  it("is the continuous inverse direction: converting back and forth stays close under floating-point drift", () => {
    const vp: Viewport = {
      zoom: 1.333,
      panX: 10,
      panY: -20,
      devicePixelRatio: 1,
      panelOffset: { x: 3, y: 3 },
    };
    const p: Point = { x: 100, y: 200 };
    const screen = labelMapToScreen(p, vp);
    const expectedX = (p.x + vp.panelOffset.x) * vp.zoom * vp.devicePixelRatio + vp.panX;
    const expectedY = (p.y + vp.panelOffset.y) * vp.zoom * vp.devicePixelRatio + vp.panY;
    expect(screen.x).toBeCloseTo(expectedX);
    expect(screen.y).toBeCloseTo(expectedY);
  });
});
