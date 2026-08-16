import { describe, it, expect } from "vitest";
import type { Point } from "../../src/geometry/transform";
import type { Shape } from "../../src/editor/polygonState";
import {
  createEditorState,
  moveVertex,
  insertVertex,
  deleteVertex,
  addShape,
  removeShape,
  selectShape,
  selectVertex,
  beginDraft,
  appendDraftPoint,
  closeDraft,
  cancelDraft,
  replaceShapes,
  setDrawKind,
  MIN_POLYGON_VERTICES,
} from "../../src/editor/polygonState";

/** Deep-freezes an object graph so any accidental mutation throws in strict mode / is a no-op that fails an identity check. */
function deepFreeze<T>(obj: T): T {
  Object.getOwnPropertyNames(obj as object).forEach((key) => {
    const value = (obj as Record<string, unknown>)[key];
    if (value && typeof value === "object") deepFreeze(value);
  });
  return Object.freeze(obj);
}

const square: Point[] = [
  { x: 0, y: 0 },
  { x: 10, y: 0 },
  { x: 10, y: 10 },
  { x: 0, y: 10 },
];

function stateWithShape(polygon: Point[] = square): ReturnType<typeof createEditorState> {
  const base = createEditorState();
  return addShape(base, { id: 1, polygon });
}

describe("MIN_POLYGON_VERTICES", () => {
  it("is 3, matching the UI-SPEC refusal copy 'A panel needs at least 3 points.'", () => {
    expect(MIN_POLYGON_VERTICES).toBe(3);
  });
});

describe("moveVertex", () => {
  it("returns a new state without mutating the frozen input", () => {
    const state = deepFreeze(stateWithShape());
    const moved = moveVertex(state, 1, 0, { x: 99, y: 99 });
    expect(() => moveVertex(state, 1, 0, { x: 99, y: 99 })).not.toThrow();
    expect(moved).not.toBe(state);
    expect(moved.shapes[0].polygon[0]).toEqual({ x: 99, y: 99 });
    // Original untouched.
    expect(state.shapes[0].polygon[0]).toEqual({ x: 0, y: 0 });
  });
});

describe("insertVertex", () => {
  it("places the new vertex between edgeIndex and edgeIndex + 1, preserving winding", () => {
    const state = stateWithShape();
    const inserted = insertVertex(state, 1, 0, { x: 5, y: -5 });
    expect(inserted.shapes[0].polygon).toEqual([
      { x: 0, y: 0 },
      { x: 5, y: -5 },
      { x: 10, y: 0 },
      { x: 10, y: 10 },
      { x: 0, y: 10 },
    ]);
    // Original unaffected.
    expect(state.shapes[0].polygon).toHaveLength(4);
  });
});

describe("deleteVertex", () => {
  it("removes a vertex from a 4-vertex polygon and reports refused: false", () => {
    const state = stateWithShape();
    const result = deleteVertex(state, 1, 0);
    expect(result.refused).toBe(false);
    expect(result.state.shapes[0].polygon).toHaveLength(3);
  });

  it("refuses to drop a triangle below 3 vertices, returning the state unchanged by identity", () => {
    const triangle: Point[] = [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 5, y: 10 }];
    const state = stateWithShape(triangle);
    const result = deleteVertex(state, 1, 0);
    expect(result.refused).toBe(true);
    expect(result.state).toBe(state);
    expect(result.state.shapes[0].polygon).toHaveLength(3);
  });
});

describe("addShape", () => {
  it("appends the caller-supplied shape without assigning its own id", () => {
    const state = createEditorState();
    const added = addShape(state, { id: 42, polygon: square });
    expect(added.shapes).toHaveLength(1);
    expect(added.shapes[0].id).toBe(42);
  });
});

describe("removeShape", () => {
  it("drops the shape and clears selectedShapeId when it was the removed one", () => {
    const state = selectShape(stateWithShape(), 1);
    expect(state.selectedShapeId).toBe(1);
    const removed = removeShape(state, 1);
    expect(removed.shapes).toHaveLength(0);
    expect(removed.selectedShapeId).toBeNull();
  });

  it("leaves selectedShapeId intact when a different shape is removed", () => {
    let state = addShape(createEditorState(), { id: 1, polygon: square });
    state = addShape(state, { id: 2, polygon: square });
    state = selectShape(state, 1);
    const removed = removeShape(state, 2);
    expect(removed.selectedShapeId).toBe(1);
  });
});

describe("draft lifecycle", () => {
  it("beginDraft/appendDraftPoint accumulate points", () => {
    let state = beginDraft(createEditorState());
    state = appendDraftPoint(state, { x: 0, y: 0 });
    state = appendDraftPoint(state, { x: 10, y: 0 });
    expect(state.draft).toEqual([{ x: 0, y: 0 }, { x: 10, y: 0 }]);
  });

  it("closeDraft returns the polygon and clears the draft at 3+ points", () => {
    let state = beginDraft(createEditorState());
    state = appendDraftPoint(state, { x: 0, y: 0 });
    state = appendDraftPoint(state, { x: 10, y: 0 });
    state = appendDraftPoint(state, { x: 5, y: 10 });
    const result = closeDraft(state);
    expect(result.polygon).toEqual([{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 5, y: 10 }]);
    expect(result.state.draft).toBeNull();
  });

  it("closeDraft returns null and leaves the draft intact below 3 points", () => {
    let state = beginDraft(createEditorState());
    state = appendDraftPoint(state, { x: 0, y: 0 });
    state = appendDraftPoint(state, { x: 10, y: 0 });
    const result = closeDraft(state);
    expect(result.polygon).toBeNull();
    expect(result.state.draft).toEqual([{ x: 0, y: 0 }, { x: 10, y: 0 }]);
  });

  it("cancelDraft always clears without producing a polygon", () => {
    let state = beginDraft(createEditorState());
    state = appendDraftPoint(state, { x: 0, y: 0 });
    state = appendDraftPoint(state, { x: 10, y: 0 });
    state = appendDraftPoint(state, { x: 5, y: 10 });
    const cancelled = cancelDraft(state);
    expect(cancelled.draft).toBeNull();
  });
});

describe("replaceShapes", () => {
  it("swaps the shape list, preserving selectedShapeId if it still exists", () => {
    let state = addShape(createEditorState(), { id: 1, polygon: square });
    state = selectShape(state, 1);
    const replaced = replaceShapes(state, [{ id: 1, polygon: square }, { id: 2, polygon: square }]);
    expect(replaced.selectedShapeId).toBe(1);
    expect(replaced.shapes).toHaveLength(2);
  });

  it("clears selectedShapeId when it no longer exists in the replacement list", () => {
    let state = addShape(createEditorState(), { id: 1, polygon: square });
    state = selectShape(state, 1);
    const replaced = replaceShapes(state, [{ id: 2, polygon: square }]);
    expect(replaced.selectedShapeId).toBeNull();
  });
});

describe("selectShape / selectVertex", () => {
  it("selectShape sets selectedShapeId", () => {
    const state = selectShape(createEditorState(), 7);
    expect(state.selectedShapeId).toBe(7);
  });

  it("selectVertex sets selectedVertex", () => {
    const state = selectVertex(createEditorState(), { shapeId: 1, vertexIndex: 2 });
    expect(state.selectedVertex).toEqual({ shapeId: 1, vertexIndex: 2 });
  });
});

describe("setDrawKind", () => {
  it("updates drawKind", () => {
    const state = setDrawKind(createEditorState(), "sfx");
    expect(state.drawKind).toBe("sfx");
  });
});

describe("readingOrder is never computed here", () => {
  it("addShape copies readingOrder verbatim from the caller-supplied shape, not from geometry", () => {
    const shape: Shape = { id: 1, polygon: square, readingOrder: 3 };
    const state = addShape(createEditorState(), shape);
    expect(state.shapes[0].readingOrder).toBe(3);
  });
});
