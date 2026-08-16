// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { mountCanvasEditor, type CanvasEditorHandle, type CanvasEditorOptions } from "../../src/editor/canvasEditor";
import type { Shape } from "../../src/editor/polygonState";
import { mountTestRoot, resetTestRoot } from "../domHarness";

/**
 * jsdom's `getContext('2d')` returns null (02-RESEARCH.md Pitfall 3), so
 * every 2D-context method this module calls is stubbed as a `vi.fn()`
 * no-op below. This file asserts *that* a redraw was requested and *that*
 * the right callbacks fired at the right time -- never what was drawn:
 * canvas rendering fidelity is a named manual-UAT check
 * (02-VALIDATION.md), not something the native `canvas` package (rejected
 * by D-26) would let us fake here anyway.
 */

const CTX_METHODS = [
  "clearRect",
  "save",
  "restore",
  "beginPath",
  "moveTo",
  "lineTo",
  "closePath",
  "stroke",
  "fill",
  "arc",
  "setLineDash",
  "drawImage",
  "fillText",
  "translate",
  "scale",
] as const;

function buildContextStub(): Record<string, unknown> {
  const stub: Record<string, unknown> = {};
  for (const method of CTX_METHODS) {
    stub[method] = vi.fn();
  }
  stub.createPattern = vi.fn(() => null);
  return stub;
}

function rect(left: number, top: number, width: number, height: number): DOMRect {
  return {
    left,
    top,
    right: left + width,
    bottom: top + height,
    width,
    height,
    x: left,
    y: top,
    toJSON() {
      return this;
    },
  } as DOMRect;
}

/**
 * jsdom's `PointerEvent` constructor is unavailable in some jsdom versions
 * (02-RESEARCH.md Pitfall 3's neighbourhood) -- fall back to a
 * `MouseEvent`-shaped init with `pointerId` patched on afterward, since
 * `canvasEditor.ts` only ever reads `pointerId` behind a
 * `typeof canvas.setPointerCapture === "function"` guard that jsdom itself
 * fails, so the patched value is never dereferenced in this suite anyway.
 */
function firePointerEvent(
  target: EventTarget,
  type: string,
  init: { clientX: number; clientY: number; button?: number; pointerId?: number },
): void {
  const eventInit = {
    bubbles: true,
    cancelable: true,
    clientX: init.clientX,
    clientY: init.clientY,
    button: init.button ?? 0,
    pointerId: init.pointerId ?? 1,
  };
  let event: Event;
  if (typeof PointerEvent === "function") {
    event = new PointerEvent(type, eventInit);
  } else {
    event = new MouseEvent(type, eventInit);
    Object.defineProperty(event, "pointerId", { value: eventInit.pointerId });
  }
  target.dispatchEvent(event);
}

interface Spies {
  onCommitVertexMove: ReturnType<typeof vi.fn>;
  onCommitPolygon: ReturnType<typeof vi.fn>;
  onCommitDraw: ReturnType<typeof vi.fn>;
  onCommitDelete: ReturnType<typeof vi.fn>;
  onSelectionChange: ReturnType<typeof vi.fn>;
  onDeleteRefused: ReturnType<typeof vi.fn>;
}

function setup(overrides: Partial<CanvasEditorOptions> = {}): {
  mount: HTMLElement;
  canvas: HTMLCanvasElement;
  handle: CanvasEditorHandle;
  spies: Spies;
} {
  const mount = mountTestRoot();
  vi.spyOn(mount, "getBoundingClientRect").mockReturnValue(rect(0, 0, 1000, 1000));

  const spies: Spies = {
    onCommitVertexMove: vi.fn(),
    onCommitPolygon: vi.fn(),
    onCommitDraw: vi.fn(),
    onCommitDelete: vi.fn(),
    onSelectionChange: vi.fn(),
    onDeleteRefused: vi.fn(),
  };

  const options: CanvasEditorOptions = {
    image: document.createElement("img"),
    pageWidth: 1000,
    pageHeight: 1000,
    ...spies,
    ...overrides,
  };

  const handle = mountCanvasEditor(mount, options);
  const canvas = mount.querySelector("canvas");
  if (!canvas) throw new Error("mountCanvasEditor did not create a canvas");

  return { mount, canvas, handle, spies };
}

// A 4-vertex square: a vertex drag here must never accidentally trip the
// polygon's minimum-vertex-count guard.
const square: Shape = {
  id: 1,
  polygon: [
    { x: 100, y: 100 },
    { x: 300, y: 100 },
    { x: 300, y: 300 },
    { x: 100, y: 300 },
  ],
  readingOrder: 1,
};

// A 3-vertex triangle: exactly at MIN_POLYGON_VERTICES, so any vertex
// delete on it must be refused.
const triangle: Shape = {
  id: 2,
  polygon: [
    { x: 500, y: 500 },
    { x: 700, y: 500 },
    { x: 600, y: 700 },
  ],
};

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
    buildContextStub() as unknown as CanvasRenderingContext2D,
  );
  // Runs the scheduled redraw synchronously so it is observable without
  // timers -- see the `rafScheduled` comment in canvasEditor.ts for why
  // this exact synchronous shape matters to that module's own bookkeeping.
  vi.stubGlobal(
    "requestAnimationFrame",
    (cb: FrameRequestCallback): number => {
      cb(0);
      return 1;
    },
  );
  vi.stubGlobal("cancelAnimationFrame", vi.fn());
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  resetTestRoot();
});

describe("mountCanvasEditor structure and ARIA", () => {
  it("creates exactly one canvas and a zoom pill with three correctly-labelled buttons", () => {
    const { mount } = setup();

    expect(mount.querySelectorAll("canvas")).toHaveLength(1);

    const pill = mount.querySelector(".canvas-editor__zoom-pill");
    expect(pill).not.toBeNull();

    const buttons = pill!.querySelectorAll("button");
    expect(buttons).toHaveLength(3);
    const labels = Array.from(buttons).map((button) => button.getAttribute("aria-label"));
    expect(labels).toEqual(["Zoom in", "Zoom out", "Fit to screen"]);
  });
});

describe("vertex drag commit timing (T-01-FLOOD)", () => {
  it("fires onCommitVertexMove exactly once for a multi-move drag, on pointerup", () => {
    const { canvas, handle, spies } = setup();
    handle.setShapes("panels", [square]);

    firePointerEvent(canvas, "pointerdown", { clientX: 100, clientY: 100 });
    firePointerEvent(canvas, "pointermove", { clientX: 120, clientY: 140 });
    firePointerEvent(canvas, "pointermove", { clientX: 150, clientY: 160 });
    firePointerEvent(canvas, "pointermove", { clientX: 180, clientY: 190 });
    expect(spies.onCommitVertexMove).not.toHaveBeenCalled();

    firePointerEvent(canvas, "pointerup", { clientX: 180, clientY: 190 });
    expect(spies.onCommitVertexMove).toHaveBeenCalledTimes(1);
    expect(spies.onCommitVertexMove).toHaveBeenCalledWith(1, 0, { x: 180, y: 190 }, { x: 100, y: 100 });
  });

  it("fires onCommitVertexMove zero times for a zero-distance drag", () => {
    const { canvas, handle, spies } = setup();
    handle.setShapes("panels", [square]);

    firePointerEvent(canvas, "pointerdown", { clientX: 100, clientY: 100 });
    firePointerEvent(canvas, "pointermove", { clientX: 140, clientY: 120 });
    firePointerEvent(canvas, "pointermove", { clientX: 100, clientY: 100 });
    firePointerEvent(canvas, "pointerup", { clientX: 100, clientY: 100 });

    expect(spies.onCommitVertexMove).toHaveBeenCalledTimes(0);
  });

  it("setReadOnly(mode, true) makes a vertex drag fire no commit at all", () => {
    const { canvas, handle, spies } = setup();
    handle.setShapes("panels", [square]);
    handle.setReadOnly("panels", true);

    firePointerEvent(canvas, "pointerdown", { clientX: 100, clientY: 100 });
    firePointerEvent(canvas, "pointermove", { clientX: 150, clientY: 160 });
    firePointerEvent(canvas, "pointerup", { clientX: 150, clientY: 160 });

    expect(spies.onCommitVertexMove).toHaveBeenCalledTimes(0);
  });
});

describe("selection", () => {
  it("pointerdown on a shape body fires onSelectionChange with that shape's id", () => {
    const { canvas, handle, spies } = setup();
    handle.setShapes("panels", [square]);

    // Interior point: far from every vertex (>16px) and every edge
    // (>12px), so this only resolves via hitTestShape.
    firePointerEvent(canvas, "pointerdown", { clientX: 200, clientY: 200 });

    expect(spies.onSelectionChange).toHaveBeenCalledWith(1);
  });
});

describe("vertex delete refusal", () => {
  it("Delete with a vertex selected on a triangle fires onDeleteRefused and never onCommitPolygon", () => {
    const { canvas, handle, spies } = setup();
    handle.setShapes("panels", [triangle]);

    firePointerEvent(canvas, "pointerdown", { clientX: 500, clientY: 500 });
    firePointerEvent(canvas, "pointerup", { clientX: 500, clientY: 500 });

    canvas.dispatchEvent(new KeyboardEvent("keydown", { key: "Delete", bubbles: true }));

    expect(spies.onDeleteRefused).toHaveBeenCalledTimes(1);
    expect(spies.onCommitPolygon).not.toHaveBeenCalled();
  });
});

describe("destroy()", () => {
  it("removes the canvas from the DOM and a subsequent pointerdown on the detached element fires nothing", () => {
    const { canvas, handle, spies } = setup();
    handle.setShapes("panels", [square]);

    handle.destroy();
    expect(canvas.isConnected).toBe(false);

    firePointerEvent(canvas, "pointerdown", { clientX: 100, clientY: 100 });

    expect(spies.onSelectionChange).not.toHaveBeenCalled();
    expect(spies.onCommitVertexMove).not.toHaveBeenCalled();
  });
});
