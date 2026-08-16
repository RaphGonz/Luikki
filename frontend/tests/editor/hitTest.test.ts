import { describe, it, expect } from "vitest";
import { labelMapToScreen, type Point, type Viewport } from "../../src/geometry/transform";
import {
  hitTestVertex,
  hitTestEdge,
  hitTestShape,
  pointInPolygon,
  isWithinSnapClose,
  VERTEX_HIT_RADIUS_SCREEN,
  EDGE_HOVER_RADIUS_SCREEN,
  SNAP_CLOSE_RADIUS_SCREEN,
  type PolygonShape,
} from "../../src/editor/hitTest";

/**
 * Coverage for zoom-invariant hit-testing (success criterion 2): the same
 * page-space vertex must resolve to the same hit/miss outcome at every zoom
 * level, because distances are always compared in SCREEN space via
 * `labelMapToScreen`, never in page space.
 */

function vpAt(zoom: number, dpr = 1): Viewport {
  return { zoom, panX: 37, panY: -21, devicePixelRatio: dpr, panelOffset: { x: 3, y: 3 } };
}

const square: Point[] = [
  { x: 0, y: 0 },
  { x: 100, y: 0 },
  { x: 100, y: 100 },
  { x: 0, y: 100 },
];

// Large enough that even at zoom 0.05 the vertices stay well-separated in
// screen space (5000 * 0.05 = 250 screen px apart) -- otherwise the
// "nearest of two vertices" ambiguity would swamp the zoom-invariance
// assertion below, which is about a single isolated vertex.
const largeSquare: Point[] = [
  { x: 0, y: 0 },
  { x: 5000, y: 0 },
  { x: 5000, y: 5000 },
  { x: 0, y: 5000 },
];

describe("hitTestVertex — zoom invariance (success criterion 2)", () => {
  for (const zoom of [0.05, 1, 64]) {
    it(`hits the vertex at 15 screen px away and misses at 17 screen px away, at zoom ${zoom}`, () => {
      const vp = vpAt(zoom);
      const shapes: PolygonShape[] = [{ id: 1, polygon: largeSquare }];
      const vertexScreen = labelMapToScreen(largeSquare[0], vp);

      const near = { x: vertexScreen.x + 15, y: vertexScreen.y };
      const hit = hitTestVertex(near, shapes, vp);
      expect(hit).not.toBeNull();
      expect(hit?.shapeId).toBe(1);
      expect(hit?.vertexIndex).toBe(0);

      const far = { x: vertexScreen.x + 17, y: vertexScreen.y };
      expect(hitTestVertex(far, shapes, vp)).toBeNull();
    });
  }

  it("chooses the nearest of two vertices in range", () => {
    const vp = vpAt(1);
    const shapes: PolygonShape[] = [
      { id: 1, polygon: [{ x: 0, y: 0 }, { x: 1, y: 0 }] },
    ];
    const a = labelMapToScreen({ x: 0, y: 0 }, vp);
    const b = labelMapToScreen({ x: 1, y: 0 }, vp);
    // Pointer sits between the two screen positions, closer to b.
    const pointer = { x: a.x + (b.x - a.x) * 0.75, y: a.y };
    const hit = hitTestVertex(pointer, shapes, vp);
    expect(hit?.vertexIndex).toBe(1);
  });

  it("does not change which vertex is hit for a fixed screen-pixel offset as devicePixelRatio varies", () => {
    const shapes: PolygonShape[] = [{ id: 1, polygon: square }];
    for (const dpr of [1, 2, 3]) {
      const vp = vpAt(2, dpr);
      const vertexScreen = labelMapToScreen(square[0], vp);
      const pointer = { x: vertexScreen.x + 10, y: vertexScreen.y };
      const hit = hitTestVertex(pointer, shapes, vp);
      expect(hit).not.toBeNull();
      expect(hit?.vertexIndex).toBe(0);
    }
  });
});

describe("hitTestEdge", () => {
  it("returns the nearest edge within 12 screen px with the projected page-space point", () => {
    const vp = vpAt(1);
    const shapes: PolygonShape[] = [{ id: 1, polygon: square }];
    // Midpoint of the top edge (0,0)-(100,0), nudged 5 screen px away.
    const midScreen = labelMapToScreen({ x: 50, y: 0 }, vp);
    const pointer = { x: midScreen.x, y: midScreen.y + 5 };
    const hit = hitTestEdge(pointer, shapes, vp);
    expect(hit).not.toBeNull();
    expect(hit?.shapeId).toBe(1);
    expect(hit?.edgeIndex).toBe(0);
    expect(hit?.point.x).toBeCloseTo(50);
    expect(hit?.point.y).toBeCloseTo(0);
  });

  it("returns null when the pointer is nearer a vertex than an edge (a vertex hit takes priority)", () => {
    const vp = vpAt(1);
    const shapes: PolygonShape[] = [{ id: 1, polygon: square }];
    const vertexScreen = labelMapToScreen({ x: 0, y: 0 }, vp);
    // Within the vertex's own hit radius -- a vertex's adjacent edges can
    // never be strictly farther than the vertex itself (the vertex is a
    // valid candidate point on each edge), so the vertex always wins here.
    const pointer = { x: vertexScreen.x + 2, y: vertexScreen.y + 2 };
    expect(hitTestEdge(pointer, shapes, vp)).toBeNull();
  });

  it("returns null when nothing is within 12 screen px", () => {
    const vp = vpAt(1);
    const shapes: PolygonShape[] = [{ id: 1, polygon: square }];
    const far = { x: -500, y: -500 };
    expect(hitTestEdge(far, shapes, vp)).toBeNull();
  });
});

describe("hitTestShape", () => {
  it("returns the topmost (last-drawn) shape when polygons overlap", () => {
    const vp = vpAt(1);
    const shapes: PolygonShape[] = [
      { id: 1, polygon: square },
      { id: 2, polygon: [{ x: 25, y: 25 }, { x: 75, y: 25 }, { x: 75, y: 75 }, { x: 25, y: 75 }] },
    ];
    const insideBoth = labelMapToScreen({ x: 50, y: 50 }, vp);
    expect(hitTestShape(insideBoth, shapes, vp)).toBe(2);
  });

  it("returns null outside every shape", () => {
    const vp = vpAt(1);
    const shapes: PolygonShape[] = [{ id: 1, polygon: square }];
    const outside = labelMapToScreen({ x: 500, y: 500 }, vp);
    expect(hitTestShape(outside, shapes, vp)).toBeNull();
  });
});

describe("pointInPolygon", () => {
  it("returns true for a point inside a convex polygon", () => {
    expect(pointInPolygon({ x: 50, y: 50 }, square)).toBe(true);
  });

  it("returns false for a point in the concavity of a concave polygon", () => {
    // A "C" shape / notch cut out of the right side.
    const concave: Point[] = [
      { x: 0, y: 0 },
      { x: 100, y: 0 },
      { x: 100, y: 40 },
      { x: 40, y: 40 },
      { x: 40, y: 60 },
      { x: 100, y: 60 },
      { x: 100, y: 100 },
      { x: 0, y: 100 },
    ];
    // (70, 50) sits inside the bounding box but inside the notch, not the shape.
    expect(pointInPolygon({ x: 70, y: 50 }, concave)).toBe(false);
    // (20, 50) is inside the actual filled region.
    expect(pointInPolygon({ x: 20, y: 50 }, concave)).toBe(true);
  });
});

describe("isWithinSnapClose", () => {
  for (const zoom of [0.05, 1, 64]) {
    it(`is true within 12 screen px and false beyond, at zoom ${zoom}`, () => {
      const vp = vpAt(zoom);
      const first: Point = { x: 10, y: 10 };
      const firstScreen = labelMapToScreen(first, vp);
      const near = { x: firstScreen.x + 12, y: firstScreen.y };
      const far = { x: firstScreen.x + 13, y: firstScreen.y };
      expect(isWithinSnapClose(near, first, vp)).toBe(true);
      expect(isWithinSnapClose(far, first, vp)).toBe(false);
    });
  }
});

describe("exported radius constants", () => {
  it("match the UI-SPEC fixed screen-space radii", () => {
    expect(VERTEX_HIT_RADIUS_SCREEN).toBe(16);
    expect(EDGE_HOVER_RADIUS_SCREEN).toBe(12);
    expect(SNAP_CLOSE_RADIUS_SCREEN).toBe(12);
  });
});
