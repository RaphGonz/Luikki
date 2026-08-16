/**
 * Zoom-invariant vertex, edge and shape hit-testing for the editor's hand-
 * rolled 2D render surface (D-26 -- no Konva, no third-party render library).
 *
 * Load-bearing rule: distances are compared in SCREEN space, by converting
 * each candidate page-space vertex through `labelMapToScreen` and measuring
 * against the raw pointer position. Never convert the pointer to page space
 * and compare there: a fixed page-space radius would grow and shrink with
 * zoom, which is exactly the "correction holds only at the zoom level it was
 * made" failure success criterion 2 forbids.
 *
 * `hitTestShape` is the one exception -- polygon containment is an area
 * test, scale-free and correct in page space, so the pointer is converted
 * once via `screenToLabelMap` and `pointInPolygon` runs in page space.
 *
 * Pure arithmetic only: no DOM access, no render-surface context, imports
 * only from `../geometry/transform`.
 */
import { labelMapToScreen, screenToLabelMap, type Point, type Viewport } from "../geometry/transform";

/** UI-SPEC Spacing Scale: 8px visible vertex diameter, 16px invisible hit radius. */
export const VERTEX_HIT_RADIUS_SCREEN = 16;
/** UI-SPEC Spacing Scale: 6px edge-midpoint "add vertex" ghost, appears within 12px of an edge. */
export const EDGE_HOVER_RADIUS_SCREEN = 12;
/** UI-SPEC §9: snap-to-close halo shown within 12 screen px of the first draft vertex. */
export const SNAP_CLOSE_RADIUS_SCREEN = 12;

export interface PolygonShape {
  id: number;
  polygon: Point[];
}

export interface VertexHit {
  shapeId: number;
  vertexIndex: number;
  distance: number;
}

export interface EdgeHit {
  shapeId: number;
  edgeIndex: number;
  point: Point;
  distance: number;
}

function screenDistance(a: Point, b: Point): number {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  return Math.sqrt(dx * dx + dy * dy);
}

/** Nearest vertex within `VERTEX_HIT_RADIUS_SCREEN` screen px of the pointer, or null. */
export function hitTestVertex(screenPoint: Point, shapes: PolygonShape[], vp: Viewport): VertexHit | null {
  let best: VertexHit | null = null;
  for (const shape of shapes) {
    for (let i = 0; i < shape.polygon.length; i++) {
      const vertexScreen = labelMapToScreen(shape.polygon[i], vp);
      const distance = screenDistance(screenPoint, vertexScreen);
      if (distance <= VERTEX_HIT_RADIUS_SCREEN && (best === null || distance < best.distance)) {
        best = { shapeId: shape.id, vertexIndex: i, distance };
      }
    }
  }
  return best;
}

function projectPointToSegment(p: Point, a: Point, b: Point): { point: Point; distance: number } {
  const abx = b.x - a.x;
  const aby = b.y - a.y;
  const lengthSq = abx * abx + aby * aby;
  const rawT = lengthSq === 0 ? 0 : ((p.x - a.x) * abx + (p.y - a.y) * aby) / lengthSq;
  const t = Math.max(0, Math.min(1, rawT));
  const point = { x: a.x + t * abx, y: a.y + t * aby };
  return { point, distance: screenDistance(p, point) };
}

/**
 * Nearest edge within `EDGE_HOVER_RADIUS_SCREEN` screen px, with the
 * projected point expressed back in page space via `screenToLabelMap` --
 * that is what gets POSTed as the inserted vertex. Returns null whenever a
 * vertex is within its own (larger) hit radius, so the caller never has to
 * disambiguate a simultaneous vertex/edge hit itself: a vertex's own edges
 * can never be strictly farther than the vertex (the vertex is a valid
 * candidate point on each), so ceding priority to the vertex hit is always
 * correct, not just a tie-break.
 */
export function hitTestEdge(screenPoint: Point, shapes: PolygonShape[], vp: Viewport): EdgeHit | null {
  if (hitTestVertex(screenPoint, shapes, vp) !== null) return null;

  let best: EdgeHit | null = null;
  for (const shape of shapes) {
    const n = shape.polygon.length;
    for (let i = 0; i < n; i++) {
      const a = labelMapToScreen(shape.polygon[i], vp);
      const b = labelMapToScreen(shape.polygon[(i + 1) % n], vp);
      const projected = projectPointToSegment(screenPoint, a, b);
      if (projected.distance <= EDGE_HOVER_RADIUS_SCREEN && (best === null || projected.distance < best.distance)) {
        best = {
          shapeId: shape.id,
          edgeIndex: i,
          point: screenToLabelMap(projected.point, vp),
          distance: projected.distance,
        };
      }
    }
  }

  return best;
}

/**
 * Topmost shape (last in draw order) whose polygon contains the pointer, or
 * null outside every shape. The pointer is converted once via
 * `screenToLabelMap`; containment is an area test and is correct in page
 * space regardless of zoom.
 */
export function hitTestShape(screenPoint: Point, shapes: PolygonShape[], vp: Viewport): number | null {
  const pagePoint = screenToLabelMap(screenPoint, vp);
  for (let i = shapes.length - 1; i >= 0; i--) {
    if (pointInPolygon(pagePoint, shapes[i].polygon)) {
      return shapes[i].id;
    }
  }
  return null;
}

/** Standard ray-casting point-in-polygon test. Handles concave polygons correctly. */
export function pointInPolygon(point: Point, polygon: Point[]): boolean {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const xi = polygon[i].x;
    const yi = polygon[i].y;
    const xj = polygon[j].x;
    const yj = polygon[j].y;
    const intersects =
      yi > point.y !== yj > point.y && point.x < ((xj - xi) * (point.y - yi)) / (yj - yi) + xi;
    if (intersects) inside = !inside;
  }
  return inside;
}

/** True within `SNAP_CLOSE_RADIUS_SCREEN` screen px of the first draft vertex. */
export function isWithinSnapClose(screenPoint: Point, firstVertex: Point, vp: Viewport): boolean {
  const vertexScreen = labelMapToScreen(firstVertex, vp);
  return screenDistance(screenPoint, vertexScreen) <= SNAP_CLOSE_RADIUS_SCREEN;
}
