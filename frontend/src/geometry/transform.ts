/**
 * The single shared screen<->label-map coordinate transform every Phase 2/3
 * canvas editor routes through (click hit-test, hover-highlight, freehand
 * stroke). `.planning/research/PITFALLS.md` Pitfall 7 is specifically about
 * what happens when each editor rolls its own instead of sharing this one.
 *
 * This module has **no consumer in Phase 1** and is built ahead of the
 * Phase 2/3 editors on purpose -- the ROADMAP phase goal names it as one of
 * three foundation primitives that must exist before an editor does, since
 * retrofitting them after an editor exists is far costlier than building
 * them first. `Viewport` is expected to gain fields when real usage reveals
 * them; extending it later is fine, forking it is not.
 *
 * `screenToLabelMap` uses `Math.floor` -- never nearest-integer rounding --
 * on the label-map side. This is deliberate: `src/comiccolor/model/masks.py`
 * stores a panel's regions as a 0-indexed `int32` array, and NumPy indexes
 * that array with floor-based pixel binning. Rounding to nearest instead of
 * flooring would make a click one sub-pixel from a region boundary resolve
 * to a different region on the client than the server would report for the
 * same point -- the two sides of the transform must agree exactly, not
 * approximately.
 *
 * Pure arithmetic only: no DOM access, no imports.
 */

export interface Point {
  x: number;
  y: number;
}

export interface Viewport {
  /** Screen px per label-map px. */
  zoom: number;
  /** Screen-space offset of the viewport origin. */
  panX: number;
  panY: number;
  devicePixelRatio: number;
  /** The panel's bbox origin in page-pixel space. */
  panelOffset: Point;
}

/**
 * Screen-space point -> integer label-map coordinate.
 *
 * Divides out `zoom * devicePixelRatio` to recover page-pixel space, then
 * subtracts `panelOffset` to land in the panel's own label-map space, then
 * floors both components to match `masks.py`'s 0-indexed, floor-based
 * NumPy array indexing exactly.
 */
export function screenToLabelMap(point: Point, vp: Viewport): Point {
  const pageX = (point.x - vp.panX) / (vp.zoom * vp.devicePixelRatio);
  const pageY = (point.y - vp.panY) / (vp.zoom * vp.devicePixelRatio);
  return {
    x: Math.floor(pageX - vp.panelOffset.x),
    y: Math.floor(pageY - vp.panelOffset.y),
  };
}

/**
 * Label-map coordinate -> screen-space point. The inverse of
 * `screenToLabelMap`, without flooring: screen space is continuous, not
 * pixel-indexed, so there is nothing to bin here.
 */
export function labelMapToScreen(point: Point, vp: Viewport): Point {
  const pageX = point.x + vp.panelOffset.x;
  const pageY = point.y + vp.panelOffset.y;
  return {
    x: pageX * vp.zoom * vp.devicePixelRatio + vp.panX,
    y: pageY * vp.zoom * vp.devicePixelRatio + vp.panY,
  };
}
