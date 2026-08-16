import { describe, it, expect } from "vitest";
import type { Shape } from "../../src/editor/polygonState";
import {
  createUndoStack,
  pushOp,
  popOp,
  clearStack,
  invert,
  stackDepth,
  UNDO_CAP,
  type UndoOp,
} from "../../src/editor/undoStack";

function moveOp(vertexIndex: number): UndoOp {
  return { kind: "move-vertex", shapeId: 1, vertexIndex, from: { x: 0, y: 0 } };
}

describe("UNDO_CAP", () => {
  it("is 20, per UI-SPEC §6 (last 20 committed operations)", () => {
    expect(UNDO_CAP).toBe(20);
  });
});

describe("pushOp", () => {
  it("pushing 21 operations leaves a stack of depth 20, dropping the oldest (not refusing the newest)", () => {
    let stack = createUndoStack();
    for (let i = 0; i < 21; i++) {
      stack = pushOp(stack, moveOp(i));
    }
    expect(stackDepth(stack)).toBe(20);
    // The first-pushed op (vertexIndex 0) is gone; the 21st (vertexIndex 20) is present.
    expect(stack.ops.some((op) => op.kind === "move-vertex" && op.vertexIndex === 0)).toBe(false);
    expect(stack.ops.some((op) => op.kind === "move-vertex" && op.vertexIndex === 20)).toBe(true);
  });

  it("does not mutate the passed-in stack object", () => {
    const stack = createUndoStack();
    const before = stack.ops;
    pushOp(stack, moveOp(1));
    expect(stack.ops).toBe(before);
    expect(stack.ops).toHaveLength(0);
  });
});

describe("popOp", () => {
  it("returns { op: null } and an unchanged stack when empty", () => {
    const stack = createUndoStack();
    const result = popOp(stack);
    expect(result.op).toBeNull();
    expect(result.stack).toEqual(stack);
  });

  it("returns the most recently pushed op and a stack without it", () => {
    let stack = createUndoStack();
    stack = pushOp(stack, moveOp(1));
    stack = pushOp(stack, moveOp(2));
    const result = popOp(stack);
    expect(result.op).toEqual(moveOp(2));
    expect(stackDepth(result.stack)).toBe(1);
  });

  it("does not mutate the passed-in stack object", () => {
    let stack = createUndoStack();
    stack = pushOp(stack, moveOp(1));
    const before = stack.ops;
    popOp(stack);
    expect(stack.ops).toBe(before);
  });
});

describe("clearStack", () => {
  it("empties the stack", () => {
    let stack = createUndoStack();
    stack = pushOp(stack, moveOp(1));
    const cleared = clearStack(stack);
    expect(stackDepth(cleared)).toBe(0);
  });
});

describe("invert", () => {
  it("move-vertex inverts to a move back to `from`", () => {
    const op: UndoOp = { kind: "move-vertex", shapeId: 1, vertexIndex: 0, from: { x: 3, y: 4 } };
    expect(invert(op)).toEqual({ kind: "move-vertex", shapeId: 1, vertexIndex: 0, point: { x: 3, y: 4 } });
  });

  it("insert-vertex inverts to a delete of that index", () => {
    const op: UndoOp = { kind: "insert-vertex", shapeId: 1, vertexIndex: 2 };
    expect(invert(op)).toEqual({ kind: "delete-vertex", shapeId: 1, vertexIndex: 2 });
  });

  it("delete-vertex inverts to an insert of the recorded point at that index", () => {
    const op: UndoOp = { kind: "delete-vertex", shapeId: 1, vertexIndex: 2, point: { x: 5, y: 6 } };
    expect(invert(op)).toEqual({ kind: "insert-vertex", shapeId: 1, vertexIndex: 2, point: { x: 5, y: 6 } });
  });

  it("add-shape inverts to a delete of that shape id", () => {
    const op: UndoOp = { kind: "add-shape", shapeId: 7 };
    expect(invert(op)).toEqual({ kind: "delete-shape", shapeId: 7 });
  });

  it("remove-shape inverts to a create carrying the removed shape's last-known polygon and kind", () => {
    const shape: Shape = { id: 9, polygon: [{ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 1, y: 1 }], kind: "bubble" };
    const op: UndoOp = { kind: "remove-shape", shape };
    expect(invert(op)).toEqual({ kind: "create-shape", shape });
  });
});
