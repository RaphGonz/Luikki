/**
 * The hand-rolled 2D render surface D-26 chose over any third-party canvas
 * library: one mount, two geometry layers (panels, protected masks),
 * pointer interaction for select/drag/insert/delete/draw, and pan/zoom.
 * D-26 rejected a HIGH-confidence library recommendation on one specific
 * ground -- that library's own stage scale/position model would fork
 * `../geometry/transform.ts`, the transform Phase 1 built and unit-tested
 * at 64x and 0.05x precisely because success criterion 2 ("corrections hold
 * at every zoom level") is stated in terms of it. Every coordinate
 * conversion in this file therefore delegates to
 * `screenToLabelMap`/`labelMapToScreen` -- no third-party canvas library of
 * any kind, no ad-hoc screen-to-page arithmetic outside the two viewport
 * constructors named below.
 *
 * Module boundary: this file owns rendering and raw pointer events only.
 * Every decision -- what was hit, what the new state is, what to undo --
 * belongs to `./hitTest.ts`, `./polygonState.ts` and `./undoStack.ts`
 * (undo is wired by the owning view, not here), because
 * 02-RESEARCH.md Pitfall 3 makes anything touching a 2D context untestable
 * and the logic worth testing must therefore live outside it. This module
 * raises events (`onCommit*`), the view performs the actual API writes.
 */
import {
  labelMapToScreen,
  screenToLabelMap,
  type Point,
  type Viewport,
} from "../geometry/transform";
import {
  hitTestEdge,
  hitTestShape,
  hitTestVertex,
  isWithinSnapClose,
  SNAP_CLOSE_RADIUS_SCREEN,
} from "./hitTest";
import {
  appendDraftPoint,
  beginDraft,
  cancelDraft,
  closeDraft,
  createEditorState,
  deleteVertex,
  insertVertex,
  moveVertex,
  removeShape,
  replaceShapes,
  selectShape,
  selectVertex,
  setDrawKind as setDraftKind,
  type EditorState,
  type MaskKind,
  type Shape,
  type Tool,
  type ToolMode,
} from "./polygonState";

// UI convenience clamp, not a transform limitation -- transform.ts is
// unit-tested at 64x and 0.05x; the pill simply need not expose those.
const ZOOM_MIN = 0.1;
const ZOOM_MAX = 16;
const ZOOM_STEP_FACTOR = 1.25;

const BADGE_DIAMETER_SCREEN = 24; // --space-lg
const HANDLE_VISIBLE_RADIUS_SCREEN = 4; // 8px visible diameter
const HANDLE_RING_WIDTH = 1;
const ACCENT_LINE_WIDTH = 2;
const EDGE_GHOST_RADIUS_SCREEN = 3; // 6px diameter ghost
const HATCH_TILE_SIZE = 8;
const DASH_PATTERN: number[] = [6, 4];

export interface CanvasEditorOptions {
  image: HTMLImageElement;
  pageWidth: number;
  pageHeight: number;
  onCommitVertexMove(shapeId: number, vertexIndex: number, point: Point, from: Point): void;
  onCommitPolygon(shapeId: number, polygon: Point[]): void;
  onCommitDraw(polygon: Point[], kind: MaskKind): void;
  onCommitDelete(shapeId: number): void;
  onSelectionChange(shapeId: number | null): void;
  onDeleteRefused(): void;
}

export interface CanvasEditorHandle {
  setActiveLayer(mode: ToolMode): void;
  setTool(tool: Tool): void;
  setShapes(mode: ToolMode, shapes: Shape[]): void;
  setDrawKind(kind: MaskKind): void;
  setReadOnly(mode: ToolMode, readOnly: boolean): void;
  zoomIn(): void;
  zoomOut(): void;
  fitToScreen(): void;
  getViewport(): Viewport;
  getSelection(): number | null;
  destroy(): void;
}

interface DragState {
  shapeId: number;
  vertexIndex: number;
  from: Point;
}

interface PanState {
  startClientX: number;
  startClientY: number;
  startPanX: number;
  startPanY: number;
}

interface HoveredEdge {
  shapeId: number;
  edgeIndex: number;
  point: Point;
}

interface ZoomPill {
  element: HTMLElement;
  zoomInBtn: HTMLButtonElement;
  zoomOutBtn: HTMLButtonElement;
  fitBtn: HTMLButtonElement;
}

function buildZoomPill(): ZoomPill {
  const element = document.createElement("div");
  element.className = "canvas-editor__zoom-pill";

  const zoomInBtn = document.createElement("button");
  zoomInBtn.type = "button";
  zoomInBtn.className = "canvas-editor__zoom-button";
  zoomInBtn.setAttribute("aria-label", "Zoom in");
  zoomInBtn.textContent = "+";

  const zoomOutBtn = document.createElement("button");
  zoomOutBtn.type = "button";
  zoomOutBtn.className = "canvas-editor__zoom-button";
  zoomOutBtn.setAttribute("aria-label", "Zoom out");
  zoomOutBtn.textContent = "−";

  const fitBtn = document.createElement("button");
  fitBtn.type = "button";
  fitBtn.className = "canvas-editor__zoom-button";
  fitBtn.setAttribute("aria-label", "Fit to screen");
  fitBtn.title = "Fit to screen";
  fitBtn.textContent = "⤢";

  element.append(zoomInBtn, zoomOutBtn, fitBtn);
  return { element, zoomInBtn, zoomOutBtn, fitBtn };
}

/**
 * Builds one canvas mount: a `<canvas>` filling `mount`, plus a sibling
 * floating zoom-pill `<div>`. `panelOffset` is always `{ x: 0, y: 0 }` here
 * and must stay that way: panels and protected masks are stored in
 * page-pixel space (02-RESEARCH.md Pitfall 4), and only Phase 3's zone
 * editor works in panel-local label-map space where `panelOffset` becomes
 * non-zero.
 */
export function mountCanvasEditor(mount: HTMLElement, options: CanvasEditorOptions): CanvasEditorHandle {
  mount.classList.add("canvas-editor");

  const canvas = document.createElement("canvas");
  canvas.className = "canvas-editor__surface tool-select";
  canvas.tabIndex = 0;
  mount.append(canvas);

  const pill = buildZoomPill();
  mount.append(pill.element);

  const ctx = canvas.getContext("2d");

  // Colours and typography come from the computed style of `mount`, never
  // a hex literal in TypeScript, so tokens.css stays the single source of
  // truth for every value this module paints with.
  const computed = getComputedStyle(mount);
  const tokens = {
    accent: computed.getPropertyValue("--color-accent").trim(),
    border: computed.getPropertyValue("--color-border").trim(),
    surfaceDominant: computed.getPropertyValue("--color-surface-dominant").trim(),
    textMuted: computed.getPropertyValue("--color-text-muted").trim(),
    fontFamily: computed.getPropertyValue("--font-family").trim(),
    labelFontSize: computed.getPropertyValue("--font-size-label").trim(),
  };

  let hatchPattern: CanvasPattern | null = null;
  function buildHatchPattern(): void {
    if (!ctx) return;
    const offscreen = document.createElement("canvas");
    offscreen.width = HATCH_TILE_SIZE;
    offscreen.height = HATCH_TILE_SIZE;
    const octx = offscreen.getContext("2d");
    if (!octx) return;
    octx.strokeStyle = tokens.textMuted;
    octx.globalAlpha = 0.25;
    octx.lineWidth = 1;
    octx.beginPath();
    octx.moveTo(0, HATCH_TILE_SIZE);
    octx.lineTo(HATCH_TILE_SIZE, 0);
    octx.stroke();
    hatchPattern = ctx.createPattern(offscreen, "repeat");
  }
  buildHatchPattern();

  const states: Record<ToolMode, EditorState> = {
    panels: createEditorState(),
    protected: createEditorState(),
  };
  const readOnly: Record<ToolMode, boolean> = { panels: false, protected: false };

  let activeLayer: ToolMode = "panels";
  let tool: Tool = "select";
  let viewport: Viewport = {
    zoom: 1,
    panX: 0,
    panY: 0,
    devicePixelRatio: window.devicePixelRatio || 1,
    panelOffset: { x: 0, y: 0 },
  };

  let drag: DragState | null = null;
  let panDrag: PanState | null = null;
  // False until the editor has been fitted against a mount that actually had a
  // laid-out box. See the ResizeObserver below.
  let hasFitted = false;
  let spaceHeld = false;
  let hoveredEdge: HoveredEdge | null = null;
  let draftCursor: Point | null = null;
  let rafHandle: number | null = null;
  // Tracks "a frame is pending" independently of `rafHandle`'s assignment,
  // because a synchronous `requestAnimationFrame` stub (as jsdom tests use)
  // runs the callback before `requestAnimationFrame(...)` itself returns --
  // the callback's `rafHandle = null` would otherwise be clobbered by the
  // outer `rafHandle = requestAnimationFrame(...)` assignment completing
  // afterward, permanently blocking every later redraw.
  let rafScheduled = false;

  function scheduleRedraw(): void {
    if (rafScheduled) return;
    rafScheduled = true;
    rafHandle = requestAnimationFrame(() => {
      rafScheduled = false;
      rafHandle = null;
      draw();
    });
  }

  function resizeCanvas(): void {
    const rect = mount.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.round(rect.width * dpr));
    canvas.height = Math.max(1, Math.round(rect.height * dpr));
    viewport = { ...viewport, devicePixelRatio: dpr };
  }

  function toBackingPoint(clientX: number, clientY: number): Point {
    const rect = mount.getBoundingClientRect();
    const dpr = viewport.devicePixelRatio;
    return { x: (clientX - rect.left) * dpr, y: (clientY - rect.top) * dpr };
  }

  // ---- Viewport constructors (the two places ad-hoc zoom/pan arithmetic
  // is expected -- everywhere else routes through screenToLabelMap /
  // labelMapToScreen). ----

  function fitToScreen(): void {
    resizeCanvas();
    const dpr = viewport.devicePixelRatio;
    const backingWidth = canvas.width;
    const backingHeight = canvas.height;
    const fitZoom = Math.min(
      backingWidth / (options.pageWidth * dpr),
      backingHeight / (options.pageHeight * dpr),
    );
    const zoom = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, fitZoom));
    const scaledWidth = options.pageWidth * zoom * dpr;
    const scaledHeight = options.pageHeight * zoom * dpr;
    viewport = {
      zoom,
      panX: (backingWidth - scaledWidth) / 2,
      panY: (backingHeight - scaledHeight) / 2,
      devicePixelRatio: dpr,
      panelOffset: { x: 0, y: 0 },
    };
    scheduleRedraw();
  }

  /** Zoom-step viewport constructor: steps `viewport.zoom` by `factor` while holding `centreBacking` fixed on screen. */
  function applyZoomStep(centreBacking: Point, factor: number): void {
    const centrePage = screenToLabelMap(centreBacking, viewport);
    const nextZoom = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, viewport.zoom * factor));
    const nextViewport: Viewport = { ...viewport, zoom: nextZoom };
    const centreScreenAfter = labelMapToScreen(centrePage, nextViewport);
    viewport = {
      ...nextViewport,
      panX: nextViewport.panX + (centreBacking.x - centreScreenAfter.x),
      panY: nextViewport.panY + (centreBacking.y - centreScreenAfter.y),
    };
    scheduleRedraw();
  }

  function zoomIn(): void {
    applyZoomStep({ x: canvas.width / 2, y: canvas.height / 2 }, ZOOM_STEP_FACTOR);
  }

  function zoomOut(): void {
    applyZoomStep({ x: canvas.width / 2, y: canvas.height / 2 }, 1 / ZOOM_STEP_FACTOR);
  }

  // ---- Draw loop. Scheduled via requestAnimationFrame, never drawn once
  // per pointermove event directly. ----

  function draw(): void {
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    drawImage();
    const inactiveMode: ToolMode = activeLayer === "panels" ? "protected" : "panels";
    drawLayer(inactiveMode, 0.4, false);
    drawLayer(activeLayer, 1, true);
    if (tool === "select" && hoveredEdge) drawEdgeGhost(hoveredEdge);
    drawDraft();
    drawPanelBadges();
  }

  function drawImage(): void {
    if (!ctx) return;
    const topLeft = labelMapToScreen({ x: 0, y: 0 }, viewport);
    const bottomRight = labelMapToScreen({ x: options.pageWidth, y: options.pageHeight }, viewport);
    ctx.drawImage(options.image, topLeft.x, topLeft.y, bottomRight.x - topLeft.x, bottomRight.y - topLeft.y);
  }

  function drawLayer(mode: ToolMode, alpha: number, isActive: boolean): void {
    if (!ctx) return;
    const state = states[mode];
    ctx.save();
    ctx.globalAlpha = alpha;
    for (const shape of state.shapes) {
      const selected = isActive && state.selectedShapeId === shape.id;
      drawShape(shape, mode, selected);
    }
    ctx.restore();
  }

  function drawShape(shape: Shape, mode: ToolMode, selected: boolean): void {
    if (!ctx) return;
    const points = shape.polygon.map((v) => labelMapToScreen(v, viewport));

    ctx.beginPath();
    points.forEach((p, i) => (i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
    ctx.closePath();

    if (mode === "protected") {
      ctx.fillStyle = hatchPattern ?? tokens.textMuted;
      ctx.fill();
      ctx.setLineDash(shape.touched ? [] : DASH_PATTERN);
      ctx.strokeStyle = tokens.border;
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.setLineDash([]);
    } else {
      ctx.strokeStyle = tokens.border;
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    if (selected) {
      ctx.beginPath();
      points.forEach((p, i) => (i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
      ctx.closePath();
      ctx.strokeStyle = tokens.accent;
      ctx.lineWidth = ACCENT_LINE_WIDTH;
      ctx.stroke();
      for (const p of points) drawHandle(p);
    }
  }

  function drawHandle(p: Point): void {
    if (!ctx) return;
    ctx.beginPath();
    ctx.arc(p.x, p.y, HANDLE_VISIBLE_RADIUS_SCREEN, 0, Math.PI * 2);
    ctx.fillStyle = tokens.accent;
    ctx.fill();
    ctx.lineWidth = HANDLE_RING_WIDTH;
    ctx.strokeStyle = tokens.surfaceDominant;
    ctx.stroke();
  }

  function drawEdgeGhost(edge: HoveredEdge): void {
    if (!ctx) return;
    const p = labelMapToScreen(edge.point, viewport);
    ctx.save();
    ctx.globalAlpha = 0.5;
    ctx.beginPath();
    ctx.arc(p.x, p.y, EDGE_GHOST_RADIUS_SCREEN, 0, Math.PI * 2);
    ctx.fillStyle = tokens.accent;
    ctx.fill();
    ctx.restore();
  }

  function drawDraft(): void {
    if (!ctx) return;
    const state = states[activeLayer];
    const draft = state.draft;
    if (!draft || draft.length === 0) return;

    const points = draft.map((v) => labelMapToScreen(v, viewport));
    ctx.beginPath();
    points.forEach((p, i) => (i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
    if (draftCursor) {
      const cursorScreen = labelMapToScreen(draftCursor, viewport);
      ctx.lineTo(cursorScreen.x, cursorScreen.y);
    }
    ctx.strokeStyle = tokens.accent;
    ctx.lineWidth = ACCENT_LINE_WIDTH;
    ctx.stroke();

    if (draftCursor) {
      const cursorScreen = labelMapToScreen(draftCursor, viewport);
      if (isWithinSnapClose(cursorScreen, draft[0], viewport)) {
        const first = labelMapToScreen(draft[0], viewport);
        ctx.save();
        ctx.globalAlpha = 0.5;
        ctx.beginPath();
        ctx.arc(first.x, first.y, SNAP_CLOSE_RADIUS_SCREEN, 0, Math.PI * 2);
        ctx.strokeStyle = tokens.accent;
        ctx.stroke();
        ctx.restore();
      }
    }
  }

  /** In panels mode, each panel's reading-order badge -- drawn last, on top of everything else. */
  function drawPanelBadges(): void {
    if (!ctx) return;
    ctx.save();
    ctx.globalAlpha = activeLayer === "panels" ? 1 : 0.4;
    ctx.font = `600 ${tokens.labelFontSize} ${tokens.fontFamily}`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (const shape of states.panels.shapes) {
      if (shape.readingOrder === undefined || shape.polygon.length === 0) continue;
      const points = shape.polygon.map((v) => labelMapToScreen(v, viewport));
      const minX = Math.min(...points.map((p) => p.x));
      const minY = Math.min(...points.map((p) => p.y));
      const cx = minX + BADGE_DIAMETER_SCREEN / 2;
      const cy = minY + BADGE_DIAMETER_SCREEN / 2;
      ctx.beginPath();
      ctx.arc(cx, cy, BADGE_DIAMETER_SCREEN / 2, 0, Math.PI * 2);
      ctx.fillStyle = tokens.accent;
      ctx.fill();
      ctx.fillStyle = tokens.surfaceDominant;
      ctx.fillText(String(shape.readingOrder), cx, cy);
    }
    ctx.restore();
  }

  // ---- Pointer interaction. Pointer Events, not mouse events, with
  // setPointerCapture during a drag, so stylus and mouse behave identically
  // (02-RESEARCH.md recommends this explicitly; a stylus-using colourist is
  // the literal target user). ----

  function selectVertexAndShape(shapeId: number, vertexIndex: number | null): void {
    const state = states[activeLayer];
    const vertex = vertexIndex === null ? null : { shapeId, vertexIndex };
    states[activeLayer] = selectVertex(selectShape(state, shapeId), vertex);
    options.onSelectionChange(shapeId);
    scheduleRedraw();
  }

  function handleDrawPointerDown(backing: Point): void {
    const state = states[activeLayer];
    const pagePoint = screenToLabelMap(backing, viewport);

    if (!state.draft) {
      states[activeLayer] = appendDraftPoint(beginDraft(state), pagePoint);
      scheduleRedraw();
      return;
    }

    if (state.draft.length > 0 && isWithinSnapClose(backing, state.draft[0], viewport)) {
      closeActiveDraft();
      return;
    }

    states[activeLayer] = appendDraftPoint(state, pagePoint);
    scheduleRedraw();
  }

  function closeActiveDraft(): void {
    const state = states[activeLayer];
    const { state: nextState, polygon } = closeDraft(state);
    states[activeLayer] = nextState;
    if (polygon) {
      options.onCommitDraw(polygon, nextState.drawKind);
      draftCursor = null;
    }
    scheduleRedraw();
  }

  function onPointerDown(event: PointerEvent): void {
    canvas.focus();

    if (event.button === 1 || (spaceHeld && event.button === 0)) {
      panDrag = {
        startClientX: event.clientX,
        startClientY: event.clientY,
        startPanX: viewport.panX,
        startPanY: viewport.panY,
      };
      canvas.classList.add("is-panning");
      if (typeof canvas.setPointerCapture === "function") canvas.setPointerCapture(event.pointerId);
      event.preventDefault();
      return;
    }

    const backing = toBackingPoint(event.clientX, event.clientY);

    if (tool === "draw") {
      if (!readOnly[activeLayer]) handleDrawPointerDown(backing);
      return;
    }

    const state = states[activeLayer];

    const vertexHit = hitTestVertex(backing, state.shapes, viewport);
    if (vertexHit) {
      selectVertexAndShape(vertexHit.shapeId, vertexHit.vertexIndex);
      if (!readOnly[activeLayer]) {
        const shape = state.shapes.find((s) => s.id === vertexHit.shapeId);
        if (shape) {
          drag = { shapeId: vertexHit.shapeId, vertexIndex: vertexHit.vertexIndex, from: shape.polygon[vertexHit.vertexIndex] };
          if (typeof canvas.setPointerCapture === "function") canvas.setPointerCapture(event.pointerId);
        }
      }
      return;
    }

    const edgeHit = readOnly[activeLayer] ? null : hitTestEdge(backing, state.shapes, viewport);
    if (edgeHit) {
      states[activeLayer] = insertVertex(state, edgeHit.shapeId, edgeHit.edgeIndex, edgeHit.point);
      const shape = states[activeLayer].shapes.find((s) => s.id === edgeHit.shapeId);
      if (shape) options.onCommitPolygon(edgeHit.shapeId, shape.polygon);
      scheduleRedraw();
      return;
    }

    const shapeHit = hitTestShape(backing, state.shapes, viewport);
    if (shapeHit !== null) {
      selectVertexAndShape(shapeHit, null);
    } else {
      states[activeLayer] = selectVertex(selectShape(state, null), null);
      options.onSelectionChange(null);
      scheduleRedraw();
    }
  }

  function onPointerMove(event: PointerEvent): void {
    if (panDrag) {
      const dpr = viewport.devicePixelRatio;
      viewport = {
        ...viewport,
        panX: panDrag.startPanX + (event.clientX - panDrag.startClientX) * dpr,
        panY: panDrag.startPanY + (event.clientY - panDrag.startClientY) * dpr,
      };
      scheduleRedraw();
      return;
    }

    const backing = toBackingPoint(event.clientX, event.clientY);

    if (drag) {
      // T-01-FLOOD / swatchCard.ts's input-updates-visual, change-commits
      // split: a drag mutates local state and schedules a redraw only. No
      // fetch, no onCommit* call happens here -- that is pointerup's job,
      // and only when the vertex actually moved.
      const point = screenToLabelMap(backing, viewport);
      states[activeLayer] = moveVertex(states[activeLayer], drag.shapeId, drag.vertexIndex, point);
      scheduleRedraw();
      return;
    }

    if (tool === "draw") {
      draftCursor = screenToLabelMap(backing, viewport);
      scheduleRedraw();
      return;
    }

    // Inactive-layer shapes are never hit-tested: UI-SPEC's 40% dimming is
    // "for spatial context only, non-interactive", so passing them to
    // hitTest would let a click land on a shape the artist cannot see well
    // and is not editing.
    const state = states[activeLayer];
    const edgeHit = readOnly[activeLayer] ? null : hitTestEdge(backing, state.shapes, viewport);
    hoveredEdge = edgeHit ? { shapeId: edgeHit.shapeId, edgeIndex: edgeHit.edgeIndex, point: edgeHit.point } : null;
    scheduleRedraw();
  }

  function onPointerUp(event: PointerEvent): void {
    if (panDrag) {
      panDrag = null;
      canvas.classList.remove("is-panning");
      if (typeof canvas.releasePointerCapture === "function") canvas.releasePointerCapture(event.pointerId);
      return;
    }

    if (drag) {
      const backing = toBackingPoint(event.clientX, event.clientY);
      const point = screenToLabelMap(backing, viewport);
      const { shapeId, vertexIndex, from } = drag;
      drag = null;
      if (typeof canvas.releasePointerCapture === "function") canvas.releasePointerCapture(event.pointerId);
      // Zero-distance drag commits nothing -- mirrors swatchCard.ts's
      // lastCommittedHex no-op guard so a click that moved nothing writes
      // nothing.
      if (point.x !== from.x || point.y !== from.y) {
        options.onCommitVertexMove(shapeId, vertexIndex, point, from);
      }
      scheduleRedraw();
    }
  }

  function onPointerCancel(event: PointerEvent): void {
    if (panDrag) {
      panDrag = null;
      canvas.classList.remove("is-panning");
    }
    if (drag) {
      states[activeLayer] = moveVertex(states[activeLayer], drag.shapeId, drag.vertexIndex, drag.from);
      drag = null;
    }
    if (typeof canvas.releasePointerCapture === "function") {
      try {
        canvas.releasePointerCapture(event.pointerId);
      } catch {
        // Never had capture -- nothing to release.
      }
    }
    scheduleRedraw();
  }

  function onWheel(event: WheelEvent): void {
    event.preventDefault();
    const backing = toBackingPoint(event.clientX, event.clientY);
    applyZoomStep(backing, event.deltaY < 0 ? ZOOM_STEP_FACTOR : 1 / ZOOM_STEP_FACTOR);
  }

  function onKeyDown(event: KeyboardEvent): void {
    if (event.code === "Space") {
      spaceHeld = true;
      return;
    }
    if (event.key === "+" || event.key === "=") {
      zoomIn();
      return;
    }
    if (event.key === "-") {
      zoomOut();
      return;
    }
    if (event.key === "0") {
      fitToScreen();
      return;
    }
    if (event.key === "Escape") {
      if (states[activeLayer].draft) {
        states[activeLayer] = cancelDraft(states[activeLayer]);
        draftCursor = null;
        scheduleRedraw();
      }
      return;
    }
    if (event.key === "Enter") {
      if (states[activeLayer].draft) closeActiveDraft();
      return;
    }
    if (event.key === "Delete" || event.key === "Backspace") {
      if (readOnly[activeLayer]) return;
      const state = states[activeLayer];
      if (state.selectedVertex) {
        const { shapeId, vertexIndex } = state.selectedVertex;
        const { state: nextState, refused } = deleteVertex(state, shapeId, vertexIndex);
        if (refused) {
          // Refusal changes nothing -- this is what produces "A panel
          // needs at least 3 points." in the view.
          options.onDeleteRefused();
          return;
        }
        states[activeLayer] = nextState;
        const shape = nextState.shapes.find((s) => s.id === shapeId);
        if (shape) options.onCommitPolygon(shapeId, shape.polygon);
        scheduleRedraw();
        return;
      }
      if (state.selectedShapeId !== null) {
        // D-19/UI-SPEC §5: no dialog, no intermediate confirmation.
        const shapeId = state.selectedShapeId;
        states[activeLayer] = removeShape(state, shapeId);
        options.onCommitDelete(shapeId);
        scheduleRedraw();
      }
    }
  }

  function onKeyUp(event: KeyboardEvent): void {
    if (event.code === "Space") spaceHeld = false;
  }

  canvas.addEventListener("pointerdown", onPointerDown);
  canvas.addEventListener("pointermove", onPointerMove);
  canvas.addEventListener("pointerup", onPointerUp);
  canvas.addEventListener("pointercancel", onPointerCancel);
  canvas.addEventListener("wheel", onWheel, { passive: false });
  canvas.addEventListener("keydown", onKeyDown);
  canvas.addEventListener("keyup", onKeyUp);
  pill.zoomInBtn.addEventListener("click", zoomIn);
  pill.zoomOutBtn.addEventListener("click", zoomOut);
  pill.fitBtn.addEventListener("click", fitToScreen);
  window.addEventListener("resize", handleResize);

  function handleResize(): void {
    resizeCanvas();
    scheduleRedraw();
  }

  // The mount's box is not laid out yet when `fitToScreen()` runs below, so
  // the first `resizeCanvas()` can size the backing store from a stale rect.
  // CSS then stretches that wrong-aspect bitmap into the real box and the page
  // renders distorted. `window.resize` alone does not catch this -- no window
  // resize happens -- and it also misses every other reflow that changes the
  // editor's box without changing the window's (sidebar collapse, gate banner
  // appearing, the toolbar wrapping). Observe the mount itself, and treat the
  // first observation with a real box as the true initial fit.
  //
  // The size check is not an optimisation, it is what stops the observer
  // feeding itself: reacting writes `canvas.width/height`, which relayouts
  // the mount, which fires the observer again. Only act when the box really
  // changed. jsdom has no ResizeObserver, so no test can cover this path --
  // it is browser-only by construction.
  let observedWidth = -1;
  let observedHeight = -1;
  const resizeObserver =
    typeof ResizeObserver === "undefined"
      ? null
      : new ResizeObserver(() => {
          const rect = mount.getBoundingClientRect();
          const width = Math.round(rect.width);
          const height = Math.round(rect.height);
          if (width < 1 || height < 1) return;
          if (width === observedWidth && height === observedHeight) return;
          observedWidth = width;
          observedHeight = height;
          if (!hasFitted) {
            hasFitted = true;
            fitToScreen();
            return;
          }
          handleResize();
        });
  resizeObserver?.observe(mount);

  // ---- Handle methods ----

  function setActiveLayer(mode: ToolMode): void {
    activeLayer = mode;
    hoveredEdge = null;
    scheduleRedraw();
  }

  function setTool(nextTool: Tool): void {
    tool = nextTool;
    hoveredEdge = null;
    canvas.classList.toggle("tool-draw", tool === "draw");
    canvas.classList.toggle("tool-select", tool === "select");
    if (tool !== "draw" && states[activeLayer].draft) {
      states[activeLayer] = cancelDraft(states[activeLayer]);
      draftCursor = null;
    }
    scheduleRedraw();
  }

  function setShapes(mode: ToolMode, shapes: Shape[]): void {
    states[mode] = replaceShapes(states[mode], shapes);
    scheduleRedraw();
  }

  function setDrawKind(kind: MaskKind): void {
    states[activeLayer] = setDraftKind(states[activeLayer], kind);
  }

  function setReadOnly(mode: ToolMode, value: boolean): void {
    readOnly[mode] = value;
  }

  function getViewport(): Viewport {
    return viewport;
  }

  function getSelection(): number | null {
    return states[activeLayer].selectedShapeId;
  }

  function destroy(): void {
    if (rafHandle !== null && typeof cancelAnimationFrame === "function") {
      cancelAnimationFrame(rafHandle);
    }
    rafHandle = null;
    rafScheduled = false;
    canvas.removeEventListener("pointerdown", onPointerDown);
    canvas.removeEventListener("pointermove", onPointerMove);
    canvas.removeEventListener("pointerup", onPointerUp);
    canvas.removeEventListener("pointercancel", onPointerCancel);
    canvas.removeEventListener("wheel", onWheel);
    canvas.removeEventListener("keydown", onKeyDown);
    canvas.removeEventListener("keyup", onKeyUp);
    pill.zoomInBtn.removeEventListener("click", zoomIn);
    pill.zoomOutBtn.removeEventListener("click", zoomOut);
    pill.fitBtn.removeEventListener("click", fitToScreen);
    window.removeEventListener("resize", handleResize);
    resizeObserver?.disconnect();
    canvas.remove();
    pill.element.remove();
    mount.classList.remove("canvas-editor");
  }

  fitToScreen();
  // Only trust this fit if the mount actually had a box when it ran; otherwise
  // the ResizeObserver above owns the real initial fit.
  {
    const rect = mount.getBoundingClientRect();
    hasFitted = rect.width >= 1 && rect.height >= 1;
    if (hasFitted) {
      observedWidth = Math.round(rect.width);
      observedHeight = Math.round(rect.height);
    }
  }

  return {
    setActiveLayer,
    setTool,
    setShapes,
    setDrawKind,
    setReadOnly,
    zoomIn,
    zoomOut,
    fitToScreen,
    getViewport,
    getSelection,
    destroy,
  };
}
