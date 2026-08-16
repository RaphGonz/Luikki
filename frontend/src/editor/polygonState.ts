/**
 * Pure immutable reducer for vertex and shape mutation, plus draw-in-progress
 * (draft) state. One reducer serves both tool modes -- "panels" and
 * "protected" -- because UI-SPEC §3 reuses panel editing's interaction
 * vocabulary verbatim for protected masks; the module holds no notion of
 * "panels" versus "protected" beyond the `ToolMode` type itself.
 *
 * Every function returns a brand-new state object; nothing here mutates its
 * input, which is what makes an undo stack (undoStack.ts) and a live-drag
 * preview safe to build on top of this.
 *
 * Pure arithmetic only: no DOM access, no render-surface context, imports
 * only `Point` from `../geometry/transform` and `PolygonShape` from
 * `./hitTest`.
 */
import type { Point } from "../geometry/transform";
import type { PolygonShape } from "./hitTest";

export type ToolMode = "panels" | "protected";
export type Tool = "select" | "draw";
export type MaskKind = "bubble" | "sfx";

/**
 * `readingOrder` is present only on panels and is always the server's
 * value, never computed here -- `_reading_order()`'s tiering logic is not
 * ported to TypeScript, and the client renders whatever the last mutating
 * response carried.
 */
export interface Shape extends PolygonShape {
  readingOrder?: number;
  kind?: MaskKind;
  touched?: boolean;
}

export interface EditorState {
  shapes: Shape[];
  selectedShapeId: number | null;
  selectedVertex: { shapeId: number; vertexIndex: number } | null;
  draft: Point[] | null;
  drawKind: MaskKind;
}

/** UI-SPEC refusal copy: "A panel needs at least 3 points." */
export const MIN_POLYGON_VERTICES = 3;

export function createEditorState(): EditorState {
  return {
    shapes: [],
    selectedShapeId: null,
    selectedVertex: null,
    draft: null,
    drawKind: "bubble",
  };
}

function mapShape(state: EditorState, shapeId: number, fn: (shape: Shape) => Shape): EditorState {
  return {
    ...state,
    shapes: state.shapes.map((shape) => (shape.id === shapeId ? fn(shape) : shape)),
  };
}

export function moveVertex(state: EditorState, shapeId: number, vertexIndex: number, point: Point): EditorState {
  return mapShape(state, shapeId, (shape) => ({
    ...shape,
    polygon: shape.polygon.map((v, i) => (i === vertexIndex ? point : v)),
  }));
}

/** Places the new vertex between `edgeIndex` and `edgeIndex + 1`, preserving the polygon's winding. */
export function insertVertex(state: EditorState, shapeId: number, edgeIndex: number, point: Point): EditorState {
  return mapShape(state, shapeId, (shape) => {
    const polygon = [...shape.polygon];
    polygon.splice(edgeIndex + 1, 0, point);
    return { ...shape, polygon };
  });
}

/**
 * Deletes a vertex, refusing when doing so would drop the polygon below
 * `MIN_POLYGON_VERTICES`. On refusal, the returned state is identical by
 * reference to the input -- callers can rely on `===` to detect a no-op.
 */
export function deleteVertex(
  state: EditorState,
  shapeId: number,
  vertexIndex: number,
): { state: EditorState; refused: boolean } {
  const shape = state.shapes.find((s) => s.id === shapeId);
  if (!shape || shape.polygon.length <= MIN_POLYGON_VERTICES) {
    return { state, refused: true };
  }
  const next = mapShape(state, shapeId, (s) => ({
    ...s,
    polygon: s.polygon.filter((_, i) => i !== vertexIndex),
  }));
  return { state: next, refused: false };
}

/**
 * Appends `shape` as-is. The caller supplies the server-assigned id --
 * this function never mints one, because the server is the system of
 * record.
 */
export function addShape(state: EditorState, shape: Shape): EditorState {
  return { ...state, shapes: [...state.shapes, shape] };
}

/** Drops the shape and clears `selectedShapeId` when it was the removed one. */
export function removeShape(state: EditorState, shapeId: number): EditorState {
  return {
    ...state,
    shapes: state.shapes.filter((s) => s.id !== shapeId),
    selectedShapeId: state.selectedShapeId === shapeId ? null : state.selectedShapeId,
  };
}

export function selectShape(state: EditorState, shapeId: number | null): EditorState {
  return { ...state, selectedShapeId: shapeId };
}

export function selectVertex(
  state: EditorState,
  vertex: { shapeId: number; vertexIndex: number } | null,
): EditorState {
  return { ...state, selectedVertex: vertex };
}

export function beginDraft(state: EditorState): EditorState {
  return { ...state, draft: [] };
}

export function appendDraftPoint(state: EditorState, point: Point): EditorState {
  return { ...state, draft: [...(state.draft ?? []), point] };
}

/**
 * Returns the accumulated polygon and clears the draft when there are at
 * least `MIN_POLYGON_VERTICES` points; otherwise returns null and leaves
 * the draft intact so the artist can keep adding points.
 */
export function closeDraft(state: EditorState): { state: EditorState; polygon: Point[] | null } {
  const draft = state.draft ?? [];
  if (draft.length < MIN_POLYGON_VERTICES) {
    return { state, polygon: null };
  }
  return { state: { ...state, draft: null }, polygon: draft };
}

/** Always clears the draft without producing a polygon. */
export function cancelDraft(state: EditorState): EditorState {
  return { ...state, draft: null };
}

/**
 * Swaps the whole shape list -- consumed after every mutating request's
 * server-recomputed panel/mask list -- preserving `selectedShapeId` if that
 * id still exists in the new list and clearing it otherwise.
 */
export function replaceShapes(state: EditorState, shapes: Shape[]): EditorState {
  const stillExists = state.selectedShapeId !== null && shapes.some((s) => s.id === state.selectedShapeId);
  return {
    ...state,
    shapes,
    selectedShapeId: stillExists ? state.selectedShapeId : null,
  };
}

export function setDrawKind(state: EditorState, kind: MaskKind): EditorState {
  return { ...state, drawKind: kind };
}
