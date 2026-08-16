/**
 * The Phase 2 page-editor screen (02-UI-SPEC.md §1): one route, one canvas
 * mount, two sequential tool modes (Panels, Protected) and two sequential
 * confirmation gates, all keyed off `page.stage` -- never off local UI
 * state, exactly as Phase 1's stage strip keys its own states off the same
 * field. Confirming the Panels gate does not navigate: it swaps the active
 * layer in place on the same canvas mount, so the page raster is only ever
 * loaded once and the artist keeps their zoom/pan position between the two
 * edits of one page (02-CONTEXT.md's "highest-leverage part of the
 * contract").
 *
 * Replaces 02-12-PLAN.md's empty placeholder wholesale.
 *
 * T-01-XSS: every server- or artist-supplied string is set via
 * `.textContent`; raw-markup insertion is grep-asserted absent from this
 * file, same control as `swatchCard.ts`.
 */

import { api, ApiError } from "../api/client";
import type {
  GoBackTargetDto,
  PageDto,
  PanelDto,
  PanelListDto,
  PipelineStageName,
  ProtectedMaskDto,
  ProtectedMaskListDto,
  StageConfirmDto,
  VertexDto,
} from "../api/types";
import { openGoBackDialog } from "../components/goBackDialog";
import { showToast } from "../components/toast";
import {
  mountCanvasEditor as mountEditorSurface,
  type CanvasEditorHandle,
  type CanvasEditorOptions,
} from "../editor/canvasEditor";
import type { MaskKind, Shape, Tool, ToolMode } from "../editor/polygonState";
import {
  clearStack,
  createUndoStack,
  invert,
  popOp,
  pushOp,
  stackDepth,
  type UndoOp,
  type UndoStack,
} from "../editor/undoStack";
import type { Point } from "../geometry/transform";
import { navigate } from "../shell/router";
import { getToolbarHandle } from "../shell/toolbar";
// 02-10 built this stylesheet but never wired an import for it anywhere --
// this view is the first real caller of the canvas mount below, so it is
// the first place that gap actually matters (Rule 2: without it the canvas
// surface, zoom pill and cursor states have no layout at all).
import "../styles/editor.css";
import "../styles/pageEditor.css";
// plan 02-14: the dialog goBackLink opens is styled from here.
import "../styles/dialog.css";

// ---- Copywriting Contract (02-UI-SPEC.md) -- every fixed string is
// declared exactly once here and referenced by name everywhere it is
// needed, so the same sentence can never drift into two spellings. ----

const CTA_PANELS_LABEL = "Confirm & Continue to Protected";
const CTA_PROTECTED_LABEL = "Confirm & Continue to Zones";
const DONE_LABEL = "Done";
const EMPTY_PANELS_TOOLTIP = "Draw at least one panel before continuing.";
const VERTEX_DELETE_REFUSED_TOAST = "A panel needs at least 3 points.";
// D-24: this is what keeps the SFX-deferral honest -- it is not a
// dismissible tip, it stays visible for the whole time Protected tool mode
// is active.
const SFX_HELPER_TEXT =
  "Bubbles are proposed automatically. Sound effects aren't yet — check for any and draw them by hand.";
const DETECTION_FAILED_BANNER =
  "Bubble detection failed — you can still draw protected masks by hand.";
const DETECTING_PANELS_TEXT = "Detecting panels…";
const DETECTING_BUBBLES_TEXT = "Detecting speech bubbles…";
// UI-SPEC §7: reading order is a backend parameter this phase, defaulting
// left-to-right and not exposed as a per-project setting -- this readout
// exists purely so the convention is visible, never silently assumed.
const READING_ORDER_TEXT = "Reading order: Left → Right";
const TOOL_CAPTION_SELECT = "Select";
const TOOL_CAPTION_DRAW_PANEL = "Draw panel";
const TOOL_CAPTION_DRAW_MASK = "Draw mask";
const KIND_LABEL_BUBBLE = "Bubble";
const KIND_LABEL_SFX = "SFX";
const BACK_TO_GRID_LABEL = "← Back to page grid";
const GO_BACK_LABEL = "Go back";
const UNDO_ARIA_LABEL = "Undo last edit";
const DELETE_PANEL_ARIA_LABEL = "Delete panel";
const DELETE_PROTECTED_ARIA_LABEL = "Delete protected mask";

// ---- Pure DTO <-> editor-state mapping, kept outside the closure so it is
// independently readable and (if a future plan wants it) testable. ----

function toVertexDto(point: Point): VertexDto {
  return [point.x, point.y];
}

function panelToShape(panel: PanelDto): Shape {
  return {
    id: panel.id,
    polygon: panel.polygon.map(([x, y]) => ({ x, y })),
    // Always the server's value -- `_reading_order()`'s tiering logic is
    // never ported to TypeScript and this client never renumbers locally.
    readingOrder: panel.reading_order,
  };
}

function maskToShape(mask: ProtectedMaskDto): Shape {
  return {
    id: mask.id,
    polygon: mask.polygon.map(([x, y]) => ({ x, y })),
    kind: mask.kind,
    touched: mask.touched,
  };
}

function pointsEqual(a: Point, b: Point): boolean {
  return a.x === b.x && a.y === b.y;
}

/**
 * `onCommitPolygon` fires from exactly two call sites inside
 * `canvasEditor.ts` -- an edge-click vertex insert, or a keyboard vertex
 * delete -- never a general reshape, so the two polygons handed to this
 * view always differ by exactly one vertex. Diffing them back into an
 * insert/delete undo op keeps `canvasEditor.ts`'s already-fixed callback
 * signature (plan 02-10, out of this plan's file list) from needing to
 * widen.
 */
function diffPolygonForUndo(prev: Point[], next: Point[], shapeId: number): UndoOp | null {
  if (next.length === prev.length + 1) {
    let i = 0;
    while (i < prev.length && pointsEqual(prev[i], next[i])) i++;
    return { kind: "insert-vertex", shapeId, vertexIndex: i };
  }
  if (next.length === prev.length - 1) {
    let i = 0;
    while (i < next.length && pointsEqual(prev[i], next[i])) i++;
    return { kind: "delete-vertex", shapeId, vertexIndex: i, point: prev[i] };
  }
  return null;
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Failed to load the page image."));
    img.src = src;
  });
}

function buildSpinner(): { element: HTMLElement; text: HTMLElement } {
  const element = document.createElement("div");
  element.className = "page-editor-spinner";
  element.hidden = true;
  const dot = document.createElement("div");
  dot.className = "page-editor-spinner-dot";
  const text = document.createElement("p");
  text.className = "page-editor-spinner-text";
  element.append(dot, text);
  return { element, text };
}

export function renderPageEditor(mount: HTMLElement, params: { pageId: number }): () => void {
  const { pageId } = params;

  const root = document.createElement("div");
  root.className = "page-editor";
  mount.append(root);

  const canvasMount = document.createElement("div");
  canvasMount.className = "page-editor-canvas-mount";
  root.append(canvasMount);

  const spinner = buildSpinner();
  root.append(spinner.element);

  const helperText = document.createElement("p");
  helperText.className = "page-editor-helper-text";
  helperText.textContent = SFX_HELPER_TEXT;
  helperText.hidden = true;
  root.append(helperText);

  const banner = document.createElement("div");
  banner.className = "page-editor-banner";
  banner.hidden = true;
  root.append(banner);

  // Mount point for the Go-Back dialog (01-UI-SPEC.md §3, 02-UI-SPEC.md
  // §8/§10) -- appended to `root` so teardown() removing `root` also tears
  // down any dialog left open.
  const dialogMount = document.createElement("div");
  dialogMount.className = "page-editor-dialog-mount";
  root.append(dialogMount);

  // ---- Toolbar (02-UI-SPEC.md §10: left to right -- breadcrumb, tool-mode
  // + kind selector + undo, Go-Back link, primary Confirm). ----

  const toolbar = getToolbarHandle();
  toolbar.setTitle("");
  toolbar.slot.replaceChildren();

  const toolbarRow = document.createElement("div");
  toolbarRow.className = "page-editor-toolbar-row";

  const breadcrumb = document.createElement("div");
  breadcrumb.className = "page-editor-breadcrumb";
  const backLink = document.createElement("button");
  backLink.type = "button";
  backLink.className = "page-editor-back";
  backLink.textContent = BACK_TO_GRID_LABEL;
  const titleEl = document.createElement("span");
  titleEl.className = "page-editor-title";
  breadcrumb.append(backLink, titleEl);

  const toolMode = document.createElement("div");
  toolMode.className = "page-editor-tool-mode";
  toolMode.setAttribute("role", "group");
  const selectBtn = document.createElement("button");
  selectBtn.type = "button";
  selectBtn.className = "page-editor-tool-button";
  selectBtn.textContent = TOOL_CAPTION_SELECT;
  const drawBtn = document.createElement("button");
  drawBtn.type = "button";
  drawBtn.className = "page-editor-tool-button";
  toolMode.append(selectBtn, drawBtn);

  const kindSelector = document.createElement("div");
  kindSelector.className = "page-editor-kind-selector";
  kindSelector.hidden = true;
  const bubbleBtn = document.createElement("button");
  bubbleBtn.type = "button";
  bubbleBtn.className = "page-editor-kind-button";
  bubbleBtn.textContent = KIND_LABEL_BUBBLE;
  const sfxBtn = document.createElement("button");
  sfxBtn.type = "button";
  sfxBtn.className = "page-editor-kind-button";
  sfxBtn.textContent = KIND_LABEL_SFX;
  kindSelector.append(bubbleBtn, sfxBtn);

  const readingOrderReadout = document.createElement("span");
  readingOrderReadout.className = "page-editor-reading-order";
  readingOrderReadout.textContent = READING_ORDER_TEXT;

  const undoButton = document.createElement("button");
  undoButton.type = "button";
  undoButton.className = "page-editor-undo";
  undoButton.setAttribute("aria-label", UNDO_ARIA_LABEL);
  undoButton.textContent = "↺";
  // Starts disabled and stays that way until the first `syncToolbar()` call
  // at the end of `boot()` -- otherwise a click landing in the window
  // between DOM construction and boot completion would race `boot()`'s own
  // state-setting tail (Rule 1: both paths write `activeTool`/undo state
  // unconditionally, so whichever finishes last would silently win).
  undoButton.disabled = true;

  const deleteButton = document.createElement("button");
  deleteButton.type = "button";
  deleteButton.className = "page-editor-delete";
  deleteButton.setAttribute("aria-label", DELETE_PANEL_ARIA_LABEL);
  deleteButton.textContent = "🗑";
  deleteButton.disabled = true;

  // UI-SPEC §8: low-emphasis destructive-coloured text link, positioned
  // before (visually subordinate to) the primary Confirm button -- never a
  // filled button, never competing with forward motion. Phase 1's original
  // rationale: forward movement should be the path of least resistance,
  // backward movement should require a conscious reach.
  const goBackLink = document.createElement("a");
  goBackLink.href = "#";
  goBackLink.className = "page-editor-go-back";
  goBackLink.textContent = GO_BACK_LABEL;
  // Hidden until the first `refreshGoBackTargets()` call (boot, and after
  // every gate confirm / Go-Back) proves there is somewhere to go back to
  // -- a Go-Back with nothing behind it is simply not offered.
  goBackLink.hidden = true;

  const confirmButton = document.createElement("button");
  confirmButton.type = "button";
  confirmButton.className = "page-editor-confirm accent";
  // Same race-prevention as the undo/delete buttons above: disabled until
  // boot() completes and the real page/panel-count data decide its state.
  confirmButton.disabled = true;

  toolbarRow.append(
    breadcrumb,
    toolMode,
    kindSelector,
    readingOrderReadout,
    undoButton,
    deleteButton,
    goBackLink,
    confirmButton,
  );
  toolbar.slot.append(toolbarRow);

  // ---- State. One undo stack per tool mode (UI-SPEC §6); shape caches
  // mirror the server's last-known list so a single-object mutation
  // response (protected masks) can be merged without a round trip. ----

  let disposed = false;
  let page: PageDto | null = null;
  let editorHandle: CanvasEditorHandle | null = null;

  let activeTool: ToolMode = "panels";
  let currentTool: Tool = "select";
  let currentDrawKind: MaskKind = "bubble";
  let selectionId: number | null = null;
  let detectionFailed = false;
  let doneMode = false;
  let confirmInFlight = false;

  let panelShapes: Shape[] = [];
  let protectedShapes: Shape[] = [];
  let panelCount = 0;

  let panelUndo: UndoStack = createUndoStack();
  let protectedUndo: UndoStack = createUndoStack();

  // The last-fetched Go-Back targets, refreshed at boot and after every
  // gate confirm / Go-Back, purely to decide the link's visibility -- the
  // link click handler below always re-fetches before opening the dialog,
  // since 01-UI-SPEC.md §3's cost sentence must be "computed from real data
  // at the moment the dialog opens", not from a stale cache.
  let lastGoBackTargets: GoBackTargetDto[] = [];
  let dismissGoBackDialog: (() => void) | null = null;

  // ---- Toolbar/overlay sync -- one place that reconciles every visible
  // control against the state above, called after every mutation. ----

  function updateConfirmButton(): void {
    if (doneMode) {
      confirmButton.hidden = false;
      confirmButton.disabled = false;
      confirmButton.title = "";
      confirmButton.textContent = DONE_LABEL;
      return;
    }
    if (!page) return;
    if (page.stage === "panels") {
      confirmButton.hidden = false;
      confirmButton.textContent = CTA_PANELS_LABEL;
      confirmButton.disabled = panelCount === 0;
      confirmButton.title = confirmButton.disabled ? EMPTY_PANELS_TOOLTIP : "";
    } else if (page.stage === "protected") {
      confirmButton.hidden = false;
      confirmButton.textContent = CTA_PROTECTED_LABEL;
      confirmButton.disabled = false;
      confirmButton.title = "";
    } else {
      confirmButton.hidden = true;
    }
  }

  function syncToolbar(): void {
    selectBtn.classList.toggle("is-active", currentTool === "select");
    drawBtn.classList.toggle("is-active", currentTool === "draw");
    drawBtn.textContent = activeTool === "panels" ? TOOL_CAPTION_DRAW_PANEL : TOOL_CAPTION_DRAW_MASK;
    kindSelector.hidden = !(activeTool === "protected" && currentTool === "draw");
    bubbleBtn.classList.toggle("is-active", currentDrawKind === "bubble");
    sfxBtn.classList.toggle("is-active", currentDrawKind === "sfx");
    deleteButton.setAttribute(
      "aria-label",
      activeTool === "panels" ? DELETE_PANEL_ARIA_LABEL : DELETE_PROTECTED_ARIA_LABEL,
    );
    deleteButton.disabled = selectionId === null;
    undoButton.disabled = stackDepth(activeTool === "panels" ? panelUndo : protectedUndo) === 0;
    helperText.hidden = activeTool !== "protected";
    const showBanner = detectionFailed && activeTool === "protected";
    banner.hidden = !showBanner;
    banner.textContent = showBanner ? DETECTION_FAILED_BANNER : "";
    updateConfirmButton();
  }

  function setDetectionFailed(failed: boolean): void {
    detectionFailed = failed;
    syncToolbar();
  }

  function showSpinner(text: string): void {
    spinner.text.textContent = text;
    spinner.element.hidden = false;
  }

  function hideSpinner(): void {
    spinner.element.hidden = true;
  }

  function reportApiError(err: unknown): void {
    if (err instanceof ApiError) showToast(err.detail);
  }

  // ---- Shape-list bookkeeping -- panels always come back as the whole
  // list (server-recomputed reading order); protected masks come back one
  // object at a time and are merged into the local cache. ----

  function applyPanelList(list: PanelListDto): void {
    panelShapes = list.panels.map(panelToShape);
    panelCount = panelShapes.length;
    editorHandle?.setShapes("panels", panelShapes);
    syncToolbar();
  }

  function replaceProtectedShapes(masks: ProtectedMaskDto[]): void {
    protectedShapes = masks.map(maskToShape);
    editorHandle?.setShapes("protected", protectedShapes);
  }

  function upsertProtectedShape(mask: ProtectedMaskDto): void {
    const shape = maskToShape(mask);
    const index = protectedShapes.findIndex((s) => s.id === shape.id);
    protectedShapes = index >= 0 ? protectedShapes.map((s, i) => (i === index ? shape : s)) : [...protectedShapes, shape];
    editorHandle?.setShapes("protected", protectedShapes);
  }

  function removeProtectedShape(shapeId: number): void {
    protectedShapes = protectedShapes.filter((s) => s.id !== shapeId);
    editorHandle?.setShapes("protected", protectedShapes);
  }

  // ---- Undo. UI-SPEC §6: one stack per tool mode, 20-op cap, undo-only,
  // cleared on tool-mode switch and on gate confirm. ----

  function pushUndo(op: UndoOp): void {
    if (activeTool === "panels") panelUndo = pushOp(panelUndo, op);
    else protectedUndo = pushOp(protectedUndo, op);
    syncToolbar();
  }

  async function handleUndo(): Promise<void> {
    const mode = activeTool;
    const stack = mode === "panels" ? panelUndo : protectedUndo;
    const { stack: nextStack, op } = popOp(stack);
    if (mode === "panels") panelUndo = nextStack;
    else protectedUndo = nextStack;
    syncToolbar();
    if (!op) return;

    // UI-SPEC §6's deliberate simplification: the inverse is replayed as a
    // fresh API call, so a recreated shape may carry a new row id -- only
    // the visible geometry is restored, not the identity. This is exactly
    // what "do not pre-build Phase 3's history model" means in practice.
    const intent = invert(op);
    try {
      switch (intent.kind) {
        case "move-vertex":
          if (mode === "panels") {
            applyPanelList(await api.panels.moveVertex(intent.shapeId, intent.vertexIndex, toVertexDto(intent.point)));
          } else {
            upsertProtectedShape(
              await api.protected.moveVertex(intent.shapeId, intent.vertexIndex, toVertexDto(intent.point)),
            );
          }
          break;
        case "insert-vertex": {
          const shapes = mode === "panels" ? panelShapes : protectedShapes;
          const shape = shapes.find((s) => s.id === intent.shapeId);
          if (!shape) break;
          const polygon = [...shape.polygon];
          polygon.splice(intent.vertexIndex, 0, intent.point);
          if (mode === "panels") applyPanelList(await api.panels.setPolygon(intent.shapeId, polygon.map(toVertexDto)));
          else upsertProtectedShape(await api.protected.setPolygon(intent.shapeId, polygon.map(toVertexDto)));
          break;
        }
        case "delete-vertex": {
          const shapes = mode === "panels" ? panelShapes : protectedShapes;
          const shape = shapes.find((s) => s.id === intent.shapeId);
          if (!shape) break;
          const polygon = shape.polygon.filter((_, i) => i !== intent.vertexIndex);
          if (mode === "panels") applyPanelList(await api.panels.setPolygon(intent.shapeId, polygon.map(toVertexDto)));
          else upsertProtectedShape(await api.protected.setPolygon(intent.shapeId, polygon.map(toVertexDto)));
          break;
        }
        case "delete-shape":
          if (mode === "panels") {
            applyPanelList(await api.panels.remove(intent.shapeId));
          } else {
            await api.protected.remove(intent.shapeId);
            removeProtectedShape(intent.shapeId);
          }
          break;
        case "create-shape": {
          const polygon = intent.shape.polygon.map(toVertexDto);
          if (mode === "panels") {
            applyPanelList(await api.panels.create(pageId, polygon));
          } else {
            upsertProtectedShape(await api.protected.create(pageId, intent.shape.kind ?? "bubble", polygon));
          }
          break;
        }
      }
    } catch (err) {
      reportApiError(err);
    }
  }

  // ---- Canvas commit callbacks -- every editor gesture commits through
  // the typed client, then feeds the server's response back through
  // `handle.setShapes` (panels' reading-order badges renumber from the
  // server's values; this client never renumbers locally). ----

  function onCommitVertexMove(shapeId: number, vertexIndex: number, point: Point, from: Point): void {
    void commitVertexMove(shapeId, vertexIndex, point, from);
  }

  async function commitVertexMove(shapeId: number, vertexIndex: number, point: Point, from: Point): Promise<void> {
    const mode = activeTool;
    try {
      if (mode === "panels") {
        applyPanelList(await api.panels.moveVertex(shapeId, vertexIndex, toVertexDto(point)));
      } else {
        upsertProtectedShape(await api.protected.moveVertex(shapeId, vertexIndex, toVertexDto(point)));
      }
      pushUndo({ kind: "move-vertex", shapeId, vertexIndex, from });
    } catch (err) {
      reportApiError(err);
    }
  }

  function onCommitPolygon(shapeId: number, polygon: Point[]): void {
    void commitPolygon(shapeId, polygon);
  }

  async function commitPolygon(shapeId: number, polygon: Point[]): Promise<void> {
    const mode = activeTool;
    const prevShapes = mode === "panels" ? panelShapes : protectedShapes;
    const prevPolygon = prevShapes.find((s) => s.id === shapeId)?.polygon ?? [];
    const undoOp = diffPolygonForUndo(prevPolygon, polygon, shapeId);
    const vertexPolygon = polygon.map(toVertexDto);
    try {
      if (mode === "panels") {
        applyPanelList(await api.panels.setPolygon(shapeId, vertexPolygon));
      } else {
        upsertProtectedShape(await api.protected.setPolygon(shapeId, vertexPolygon));
      }
      if (undoOp) pushUndo(undoOp);
    } catch (err) {
      reportApiError(err);
    }
  }

  function onCommitDraw(polygon: Point[], kind: MaskKind): void {
    void commitDraw(polygon, kind);
  }

  async function commitDraw(polygon: Point[], kind: MaskKind): Promise<void> {
    const mode = activeTool;
    const vertexPolygon = polygon.map(toVertexDto);
    try {
      if (mode === "panels") {
        const priorIds = new Set(panelShapes.map((s) => s.id));
        const list = await api.panels.create(pageId, vertexPolygon);
        applyPanelList(list);
        const created = list.panels.find((p) => !priorIds.has(p.id));
        if (created) pushUndo({ kind: "add-shape", shapeId: created.id });
      } else {
        const mask = await api.protected.create(pageId, kind, vertexPolygon);
        upsertProtectedShape(mask);
        pushUndo({ kind: "add-shape", shapeId: mask.id });
      }
    } catch (err) {
      reportApiError(err);
    }
  }

  function onCommitDelete(shapeId: number): void {
    void commitDelete(shapeId);
  }

  async function commitDelete(shapeId: number): Promise<void> {
    const mode = activeTool;
    const prevShapes = mode === "panels" ? panelShapes : protectedShapes;
    const removedShape = prevShapes.find((s) => s.id === shapeId);
    try {
      // D-19/UI-SPEC §5: no confirmation prompt anywhere on this path -- the
      // session undo stack above is the safety net. Adding one here would
      // directly contradict the decision and slow down the routine,
      // high-frequency case D-18's deliberate over-proposal creates.
      if (mode === "panels") {
        applyPanelList(await api.panels.remove(shapeId));
      } else {
        await api.protected.remove(shapeId);
        removeProtectedShape(shapeId);
      }
      if (removedShape) pushUndo({ kind: "remove-shape", shape: removedShape });
    } catch (err) {
      reportApiError(err);
    }
  }

  function onSelectionChange(shapeId: number | null): void {
    selectionId = shapeId;
    syncToolbar();
  }

  function onDeleteRefused(): void {
    showToast(VERTEX_DELETE_REFUSED_TOAST);
  }

  // ---- Tool-mode / tool switching. ----

  function switchActiveLayer(mode: ToolMode): void {
    activeTool = mode;
    editorHandle?.setActiveLayer(mode);
    // UI-SPEC §6: the stack resets on a tool-mode switch -- a distinct
    // trigger from the gate-confirm clear in `handleConfirm` below, named
    // separately in the spec, so both call sites clear explicitly.
    if (mode === "panels") panelUndo = clearStack(panelUndo);
    else protectedUndo = clearStack(protectedUndo);
    currentTool = "select";
    editorHandle?.setTool("select");
    syncToolbar();
  }

  function setCurrentTool(next: Tool): void {
    currentTool = next;
    editorHandle?.setTool(next);
    syncToolbar();
  }

  function setDrawKind(kind: MaskKind): void {
    currentDrawKind = kind;
    editorHandle?.setDrawKind(kind);
    syncToolbar();
  }

  // ---- Gates (UI-SPEC §4). ----

  function showDoneAffordance(): void {
    doneMode = true;
    syncToolbar();
  }

  async function handleConfirm(): Promise<void> {
    if (!page || confirmInFlight) return;
    const stage = page.stage;
    if (stage !== "panels" && stage !== "protected") return;

    confirmInFlight = true;
    confirmButton.disabled = true;
    if (stage === "panels") showSpinner(DETECTING_BUBBLES_TEXT);

    try {
      const result: StageConfirmDto = await api.pages.confirmStage(pageId);
      page = result.page;

      if (stage === "panels") {
        editorHandle?.setReadOnly("panels", true);
        // UI-SPEC §6: the stack also clears on gate confirm.
        panelUndo = clearStack(panelUndo);
        const maskList: ProtectedMaskListDto = await api.protected.list(pageId);
        if (disposed) return;
        replaceProtectedShapes(maskList.masks);
        setDetectionFailed(maskList.detection_failed);
        switchActiveLayer("protected");
        hideSpinner();
      } else {
        editorHandle?.setReadOnly("protected", true);
        // UI-SPEC §6: the stack also clears on gate confirm.
        protectedUndo = clearStack(protectedUndo);
        setDetectionFailed(result.detection_failed);
        showDoneAffordance();
      }
      // The set of computable Go-Back targets (and their costs) changes on
      // every gate confirm -- refresh so the link's visibility and the next
      // dialog open both reflect the page's new stage.
      await refreshGoBackTargets();
    } catch (err) {
      hideSpinner();
      reportApiError(err);
    } finally {
      confirmInFlight = false;
      syncToolbar();
    }
  }

  // ---- Go-Back (D-08, 01-UI-SPEC.md §3, 02-UI-SPEC.md §8). ----

  async function refreshGoBackTargets(): Promise<void> {
    if (!page) return;
    try {
      lastGoBackTargets = await api.pages.goBackTargets(pageId);
    } catch (err) {
      reportApiError(err);
      lastGoBackTargets = [];
    }
    if (disposed) return;
    goBackLink.hidden = lastGoBackTargets.length === 0;
  }

  async function handleGoBackConfirm(stage: PipelineStageName): Promise<void> {
    const result = await api.pages.goBack(pageId, stage);
    if (disposed) return;
    page = result.page;
    doneMode = false;

    // Both layers are reloaded from the server rather than patched locally:
    // a Go-Back can delete panels, protected masks, or both, depending on
    // which target was chosen, and the server is the only source of truth
    // for what remains.
    const [panelList, maskList] = await Promise.all([api.panels.list(pageId), api.protected.list(pageId)]);
    if (disposed) return;
    applyPanelList(panelList);
    replaceProtectedShapes(maskList.masks);
    setDetectionFailed(maskList.detection_failed);

    // UI-SPEC §6 scopes the undo stack to a tool-mode session; a Go-Back
    // just deleted the rows every pending undo op references (vertex ids,
    // shape ids), so replaying an inverse against either stack would 404.
    // Both are cleared here, the same rule the tool-mode-switch and
    // gate-confirm paths already apply for their own triggers.
    panelUndo = clearStack(panelUndo);
    protectedUndo = clearStack(protectedUndo);

    // Re-derive active layer and read-only state exactly as boot() does,
    // so the stage being returned to becomes editable again.
    activeTool = page.stage === "protected" ? "protected" : "panels";
    editorHandle?.setActiveLayer(activeTool);
    editorHandle?.setReadOnly("panels", page.stage !== "panels");
    editorHandle?.setReadOnly("protected", page.stage !== "protected");
    currentTool = "select";
    editorHandle?.setTool("select");

    syncToolbar();
    await refreshGoBackTargets();
  }

  function openGoBack(): void {
    void (async () => {
      await refreshGoBackTargets();
      if (disposed || lastGoBackTargets.length === 0) return;
      dismissGoBackDialog?.();
      dismissGoBackDialog = openGoBackDialog(dialogMount, lastGoBackTargets, async (stage) => {
        try {
          await handleGoBackConfirm(stage);
        } catch (err) {
          reportApiError(err);
          throw err;
        }
      });
    })();
  }

  // ---- Wiring. ----

  backLink.addEventListener("click", () => {
    if (page) navigate({ kind: "volume", volumeId: page.volume_id });
  });
  selectBtn.addEventListener("click", () => setCurrentTool("select"));
  drawBtn.addEventListener("click", () => setCurrentTool("draw"));
  bubbleBtn.addEventListener("click", () => setDrawKind("bubble"));
  sfxBtn.addEventListener("click", () => setDrawKind("sfx"));
  undoButton.addEventListener("click", () => void handleUndo());
  // canvasEditor.ts's own Delete/Backspace handling already covers
  // selected-vertex vs. selected-shape, the refusal toast and (per D-19)
  // the no-confirmation-prompt rule -- its fixed API boundary from plan
  // 02-10 has no deleteSelected() method, so a synthetic keydown on its
  // own canvas is the smallest correct bridge from this toolbar button to
  // that logic.
  deleteButton.addEventListener("click", () => {
    const canvasEl = canvasMount.querySelector("canvas");
    canvasEl?.dispatchEvent(new KeyboardEvent("keydown", { key: "Delete", bubbles: true }));
  });
  goBackLink.addEventListener("click", (event) => {
    event.preventDefault();
    openGoBack();
  });
  confirmButton.addEventListener("click", () => {
    if (doneMode) {
      if (page) navigate({ kind: "volume", volumeId: page.volume_id });
      return;
    }
    void handleConfirm();
  });

  function onGlobalKeyDown(event: KeyboardEvent): void {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
      event.preventDefault();
      void handleUndo();
    }
  }
  window.addEventListener("keydown", onGlobalKeyDown);

  // ---- Boot. ----

  async function boot(): Promise<void> {
    let loadedPage: PageDto;
    try {
      loadedPage = await api.pages.get(pageId);
    } catch (err) {
      reportApiError(err);
      return;
    }
    if (disposed) return;
    page = loadedPage;
    titleEl.textContent = page.original_name;

    showSpinner(page.stage === "protected" ? DETECTING_BUBBLES_TEXT : DETECTING_PANELS_TEXT);

    let image: HTMLImageElement;
    try {
      image = await loadImage(api.pages.imageUrl(pageId));
    } catch (err) {
      reportApiError(err);
      hideSpinner();
      return;
    }
    if (disposed) return;

    const options: CanvasEditorOptions = {
      image,
      pageWidth: page.width,
      pageHeight: page.height,
      onCommitVertexMove,
      onCommitPolygon,
      onCommitDraw,
      onCommitDelete,
      onSelectionChange,
      onDeleteRefused,
    };
    editorHandle = mountEditorSurface(canvasMount, options);

    const [panelList, maskList] = await Promise.all([
      api.panels.list(pageId).catch((err: unknown) => {
        reportApiError(err);
        return { panels: [] } as PanelListDto;
      }),
      api.protected.list(pageId).catch((err: unknown) => {
        reportApiError(err);
        return { masks: [], detection_failed: false, detection_message: null } as ProtectedMaskListDto;
      }),
    ]);
    if (disposed) return;

    applyPanelList(panelList);
    replaceProtectedShapes(maskList.masks);
    setDetectionFailed(maskList.detection_failed);

    hideSpinner();

    activeTool = page.stage === "protected" ? "protected" : "panels";
    editorHandle.setActiveLayer(activeTool);
    editorHandle.setReadOnly("panels", page.stage !== "panels");
    editorHandle.setReadOnly("protected", page.stage !== "protected");
    currentTool = "select";
    editorHandle.setTool("select");
    syncToolbar();
    // Non-blocking -- decides the Go-Back link's initial visibility without
    // holding up the rest of boot().
    void refreshGoBackTargets();
  }

  void boot();

  return () => {
    disposed = true;
    window.removeEventListener("keydown", onGlobalKeyDown);
    dismissGoBackDialog?.();
    editorHandle?.destroy();
    root.remove();
    toolbar.setTitle("");
    toolbar.slot.replaceChildren();
  };
}
