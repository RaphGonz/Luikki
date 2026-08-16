/**
 * 20-op, undo-only, session-scoped stack for the canvas editor.
 *
 * Scope boundary: Phase 3 formally owns undo/redo against the label-map
 * invariant, and this is explicitly not that. This exists only to make
 * UI-SPEC §5's no-confirmation deletion feel safe. Deliberate
 * simplification: undo re-issues the inverse mutation as a fresh API call
 * and is not guaranteed to restore the same row id, only the same visible
 * geometry.
 *
 * No timers, no persistence -- the stack is session state held by the view
 * and dies with it, which is what "does not survive a page reload" means
 * concretely (edits commit synchronously per PROJ-05, so a reload always
 * shows the last committed state).
 */
import type { Point } from "../geometry/transform";
import type { Shape } from "./polygonState";

export const UNDO_CAP = 20;

export type UndoOp =
  | { kind: "move-vertex"; shapeId: number; vertexIndex: number; from: Point }
  | { kind: "insert-vertex"; shapeId: number; vertexIndex: number }
  | { kind: "delete-vertex"; shapeId: number; vertexIndex: number; point: Point }
  | { kind: "add-shape"; shapeId: number }
  | { kind: "remove-shape"; shape: Shape };

export type UndoIntent =
  | { kind: "move-vertex"; shapeId: number; vertexIndex: number; point: Point }
  | { kind: "delete-vertex"; shapeId: number; vertexIndex: number }
  | { kind: "insert-vertex"; shapeId: number; vertexIndex: number; point: Point }
  | { kind: "delete-shape"; shapeId: number }
  | { kind: "create-shape"; shape: Shape };

export interface UndoStack {
  ops: readonly UndoOp[];
}

export function createUndoStack(): UndoStack {
  return { ops: [] };
}

/** Pushes `op`; when the stack is over `UNDO_CAP` the oldest op is dropped, never the newest refused. */
export function pushOp(stack: UndoStack, op: UndoOp): UndoStack {
  const ops = [...stack.ops, op];
  if (ops.length > UNDO_CAP) {
    ops.shift();
  }
  return { ops };
}

/** Pops the most recently pushed op. On an empty stack, returns `{ op: null }` and the stack unchanged. */
export function popOp(stack: UndoStack): { stack: UndoStack; op: UndoOp | null } {
  if (stack.ops.length === 0) {
    return { stack, op: null };
  }
  const op = stack.ops[stack.ops.length - 1];
  return { stack: { ops: stack.ops.slice(0, -1) }, op };
}

export function clearStack(_stack: UndoStack): UndoStack {
  return { ops: [] };
}

export function stackDepth(stack: UndoStack): number {
  return stack.ops.length;
}

/**
 * Maps each committed op kind to the API intent that undoes it. The result
 * is re-issued as a fresh mutating API call by the caller -- this module
 * performs no I/O itself.
 */
export function invert(op: UndoOp): UndoIntent {
  switch (op.kind) {
    case "move-vertex":
      return { kind: "move-vertex", shapeId: op.shapeId, vertexIndex: op.vertexIndex, point: op.from };
    case "insert-vertex":
      return { kind: "delete-vertex", shapeId: op.shapeId, vertexIndex: op.vertexIndex };
    case "delete-vertex":
      return { kind: "insert-vertex", shapeId: op.shapeId, vertexIndex: op.vertexIndex, point: op.point };
    case "add-shape":
      return { kind: "delete-shape", shapeId: op.shapeId };
    case "remove-shape":
      return { kind: "create-shape", shape: op.shape };
  }
}
