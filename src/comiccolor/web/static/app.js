// The seven buttons, and one transform.
//
// Rule 5: exactly one screen <-> image transform, `view`, recomputed on every
// render. Nothing else in this file converts coordinates. Step 6 is the first
// thing here that hit-tests, and it does it the way this comment always said
// it would: `view.toImage` on the click, then the server resolves the point
// off the label map. There is no second copy of the arithmetic and no
// client-side guess at which zone was clicked.

const $ = (id) => document.getElementById(id);
const PANEL = "#6ea8fe";
const BUBBLE = "#f0a35e";
const stage = $("stage");
const ctx = stage.getContext("2d");

let state = null;
// The segment payload from /api/segment — what a click resolved to, and the
// unit of work for step 6. Null means nothing is selected.
let selected = null;
const layers = { page: null, lines: null, zones: null, flats: null, left: null };

// Steps 2 and 3 are editable, and this is everything that takes: which of the
// two layers the pointer is aimed at, the corner being dragged, and the
// polygon being drawn. All page-space; screen space exists only inside the
// hit tests, and only through `view`.
// null means "whichever layer the page is up to" — the furthest one the
// artist has reached. Only pressing a step or the radio pins it, so a reload
// at the balloon stage aims at balloons rather than at the panels underneath
// them, which is how a traced balloon becomes a stray panel.
let layer = null;
let drag = null; // {index, corner, dirty}
let draft = null; // {points: [[x, y], …]} — a new panel or bubble, mid-draw
let cursor = null; // where the pointer is, for the rubber band

// The single transform. `scale` fits the page inside the canvas; `ox`/`oy`
// centre it.
const view = {
  scale: 1, ox: 0, oy: 0,
  toScreen(x, y) { return [x * this.scale + this.ox, y * this.scale + this.oy]; },
  toImage(x, y) { return [(x - this.ox) / this.scale, (y - this.oy) / this.scale]; },
};

// ---- server ---------------------------------------------------------------

function say(message, bad = false) {
  const el = $("status");
  el.textContent = message;
  el.classList.toggle("bad", bad);
}

async function call(path, options = {}) {
  document.body.classList.add("busy");
  try {
    const response = await fetch(path, options);
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || body.detail || response.statusText);
    return body;
  } finally {
    document.body.classList.remove("busy");
  }
}

async function step(label, path, options) {
  say(label + "…");
  try {
    const next = await call(path, options);
    state = next;
    // Re-running any step can invalidate the segments, so a selection made
    // before it is a pointer at something that may no longer exist. The same
    // goes for a half-drawn polygon: the geometry it was being drawn onto is
    // gone.
    selected = null;
    draft = null;
    drag = null;
    await reloadLayers();
    apply();
    say(summary(next, label));
  } catch (error) {
    say(error.message, true);
  }
}

function summary(next, label) {
  if (next.result) {
    const { assigned, segments, colours, snapped, skipped } = next.result;
    if (snapped !== undefined && skipped !== undefined) {
      return `${snapped} segments snapped, ${skipped} left as proposed.`;
    }
    return `${assigned} zones coloured, ${segments} segments, ${colours} palette entries.`;
  }
  return label + " — done.";
}

// Overlays are server-rendered PNGs, cache-busted per load so a re-run never
// shows the previous pass.
function loadImage(url) {
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => resolve(null);
    image.src = url + "?t=" + Date.now();
  });
}

async function reloadLayers() {
  const done = state.done;
  layers.page = done.page ? await loadImage("/api/page.png") : null;
  // Extraction happens inside Segment zones, so this only exists afterwards.
  layers.lines = done.zones ? await loadImage("/api/lines.png") : null;
  layers.zones = done.zones ? await loadImage("/api/zones.png") : null;
  layers.flats = done.flats ? await loadImage("/api/flats.png") : null;
  layers.left = done.flats ? await loadImage("/api/unsnapped.png") : null;
}

// ---- rendering ------------------------------------------------------------

function resize() {
  const ratio = window.devicePixelRatio || 1;
  stage.width = stage.clientWidth * ratio;
  stage.height = stage.clientHeight * ratio;
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  render();
}

function render() {
  const width = stage.clientWidth;
  const height = stage.clientHeight;
  ctx.clearRect(0, 0, width, height);
  if (!state || !state.page) return;

  const page = state.page;
  const margin = 24;
  view.scale = Math.min(
    (width - margin * 2) / page.width,
    (height - margin * 2) / page.height,
  );
  view.ox = (width - page.width * view.scale) / 2;
  view.oy = (height - page.height * view.scale) / 2;

  const box = [view.ox, view.oy, page.width * view.scale, page.height * view.scale];

  ctx.fillStyle = "#fff";
  ctx.fillRect(...box);

  // Colour underneath, ink on top — the order the artist works in, and the
  // order the exported PSD stacks in. Flats drawn *over* the line art wash it
  // out, and a colourist cannot judge a colour without the lines that bound
  // it: the ink is half of what the eye reads as the colour.
  //
  // Flats sit above zones: once the colours exist, the zone map is scaffolding.
  if (layers.zones && $("v-zones").checked) ctx.drawImage(layers.zones, ...box);
  if (layers.flats && $("v-flats").checked) ctx.drawImage(layers.flats, ...box);

  // Multiply is what makes ink over colour behave like ink: black stays
  // black, paper drops out, and grey holds its weight. Over the white
  // background — no flats yet — it is identical to drawing the page plainly,
  // so this needs no branch for "before the colours exist".
  ctx.globalCompositeOperation = "multiply";
  if (layers.page && $("v-page").checked) ctx.drawImage(layers.page, ...box);

  // What segmentation actually saw, so you can compare the structural lines
  // against the artist's ink.
  if (layers.lines && $("v-lines").checked) ctx.drawImage(layers.lines, ...box);
  ctx.globalCompositeOperation = "source-over";

  // Step 6's remaining workload, above the ink: it is a marker, not a layer
  // of the drawing, and it is no use if the linework hides it.
  if (layers.left && $("v-left").checked) ctx.drawImage(layers.left, ...box);

  // The layer being corrected is always drawn, checkbox or not: hiding the
  // shape you are dragging a corner of is not a view option, it is a bug.
  const editing = activeLayer();

  if ($("v-bubbles").checked || editing === "bubbles") {
    ctx.strokeStyle = BUBBLE;
    ctx.lineWidth = 1.5;
    for (const polygon of state.protected) trace(polygon);
  }

  if ($("v-panels").checked || editing === "panels") {
    ctx.strokeStyle = PANEL;
    ctx.lineWidth = 2;
    ctx.font = "600 15px ui-sans-serif, system-ui, sans-serif";
    ctx.fillStyle = PANEL;
    for (const panel of state.panels) {
      trace(panel.polygon);
      const [x, y] = view.toScreen(panel.polygon[0][0], panel.polygon[0][1]);
      ctx.fillText(String(panel.order + 1), x + 6, y + 18);
    }
  }

  drawHandles(editing);
  drawDraft(editing);
  drawSelection();
}

// Every corner of the layer being corrected, as something to aim at. Squares
// rather than dots: a corner is a thing you grab, and it has to read as one
// from across the page.
function drawHandles(editing) {
  if (!editing || draft) return;
  ctx.save();
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = editing === "panels" ? PANEL : BUBBLE;
  ctx.fillStyle = "#14161a";
  for (const polygon of shapes()) {
    for (const [px, py] of polygon) {
      const [x, y] = view.toScreen(px, py);
      ctx.beginPath();
      ctx.rect(x - 4, y - 4, 8, 8);
      ctx.fill();
      ctx.stroke();
    }
  }
  ctx.restore();
}

// The polygon being drawn: what has been placed, a rubber band to the
// pointer, and a ring on the first corner once clicking it would close the
// shape. The ring is the whole instruction — "click here to finish" — said
// without a sentence.
function drawDraft(editing) {
  if (!draft || !editing) return;
  const points = draft.points;
  ctx.save();
  ctx.strokeStyle = editing === "panels" ? PANEL : BUBBLE;
  ctx.lineWidth = 2;

  ctx.beginPath();
  points.forEach(([px, py], index) => {
    const [x, y] = view.toScreen(px, py);
    index === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  if (cursor) {
    const [x, y] = view.toScreen(cursor[0], cursor[1]);
    ctx.lineTo(x, y);
  }
  ctx.stroke();

  ctx.fillStyle = "#14161a";
  for (const [px, py] of points) {
    const [x, y] = view.toScreen(px, py);
    ctx.beginPath();
    ctx.rect(x - 4, y - 4, 8, 8);
    ctx.fill();
    ctx.stroke();
  }

  if (points.length >= 3) {
    const [x, y] = view.toScreen(points[0][0], points[0][1]);
    ctx.beginPath();
    ctx.arc(x, y, 9, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.restore();
}

// The selected segment, as its bounding box and the anchor the server
// resolved. Not the zone's outline: the mask lives on the server, and
// shipping it per click to draw a prettier marquee would be a second copy of
// the segmentation on the client.
function drawSelection() {
  if (!selected) return;
  const [x0, y0, x1, y1] = selected.bounds;
  const [sx, sy] = view.toScreen(x0, y0);
  const [ex, ey] = view.toScreen(x1 + 1, y1 + 1);

  ctx.save();
  ctx.lineWidth = 2;
  ctx.strokeStyle = "#fff";
  ctx.setLineDash([5, 4]);
  ctx.strokeRect(sx, sy, ex - sx, ey - sy);

  const [ax, ay] = view.toScreen(selected.anchor[0], selected.anchor[1]);
  ctx.setLineDash([]);
  ctx.beginPath();
  ctx.arc(ax, ay, 4, 0, Math.PI * 2);
  ctx.fillStyle = "#fff";
  ctx.fill();
  ctx.strokeStyle = "#14161a";
  ctx.lineWidth = 1.5;
  ctx.stroke();
  ctx.restore();
}

function trace(polygon) {
  if (polygon.length < 2) return;
  ctx.beginPath();
  polygon.forEach(([px, py], index) => {
    const [x, y] = view.toScreen(px, py);
    index === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.closePath();
  ctx.stroke();
}

// ---- sidebar --------------------------------------------------------------

const rgb = (colour) => `rgb(${colour.join(",")})`;

function paletteById() {
  return new Map(state.palette.map((entry) => [entry.id, entry]));
}

function apply() {
  const done = state.done;
  $("proposer").textContent = `${state.extractor} → ${state.proposer}`;

  for (const button of document.querySelectorAll("[data-needs]")) {
    button.disabled = !done[button.dataset.needs];
  }

  $("page-note").textContent = state.page
    ? `${state.page.name} — ${state.page.width}×${state.page.height}`
    : "No page loaded.";

  const zones = state.panels.reduce((sum, p) => sum + p.zones, 0);
  $("panels-note").textContent = done.panels
    ? `${state.panels.length} panels` +
      (editable("panels") ? " — correct them below before the zones are cut." : ".")
    : "";
  $("bubbles-note").textContent = done.bubbles
    ? `${state.protected.length} protected areas — never coloured` +
      (editable("bubbles") ? ", and correctable below." : ".")
    : "";
  $("zones-note").textContent = done.zones ? `${zones} zones across the page.` : "";

  const references = state.palette.filter((e) => e.source === "reference");
  const proposed = state.palette.length - references.length;
  $("ref-note").textContent = references.length
    ? `${state.references.length} reference(s), ${references.length} colours — zones snap to these.`
    : "No palette — every zone gets its own colour.";
  $("refs").innerHTML = state.references
    .map(
      (r) => `<figure data-id="${r.id}">
        <img src="/api/reference/${r.id}.png" alt="${r.label}">
        <figcaption>${r.kind}</figcaption>
        <button class="x" data-id="${r.id}" title="Remove ${r.label}">&times;</button>
      </figure>`
    )
    .join("");
  // Only the reference half is shown. The proposed half is one private entry
  // per segment — on a real page that is hundreds of swatches, and none of
  // them is a colour the artist chose.
  $("palette").innerHTML = references
    .map((e) => `<i style="background: ${rgb(e.rgb)}" title="${e.label}"></i>`)
    .join("");

  // A click only means something once there are segments under it.
  stage.classList.toggle("pickable", done.flats);
  applyEditMode();

  applySnapStep(proposed);
  showInspector();
  render();
}

// The "Correct" panel is the whole announcement that geometry is editable:
// it appears when a layer can be corrected, names the gestures, and goes away
// again the moment the zones are cut from the shapes.
function applyEditMode() {
  const which = activeLayer();
  const box = $("edit-mode");
  box.hidden = !which;
  stage.classList.toggle("editing", Boolean(which));
  if (!which) {
    stage.classList.remove("on-corner", "on-edge");
    return;
  }
  $("layer-panels").disabled = !editable("panels");
  $("layer-bubbles").disabled = !editable("bubbles");
  $("layer-panels").checked = which === "panels";
  $("layer-bubbles").checked = which === "bubbles";
  $("edit-note").textContent =
    `Drag a corner to move it. Click an edge to add one. Click empty page to` +
    ` draw a new ${which === "panels" ? "panel" : "bubble"}, and click its first` +
    ` corner to close it. Right-click to delete.`;
}

function applySnapStep(proposed) {
  const segments = state.segments;
  $("flats-note").textContent = state.done.flats
    ? `${segments.count} segments, ${proposed} colours proposed — one per zone.`
    : "";

  const snappable = segments.snappable;
  $("btn-snap-all").disabled = !state.done.flats || !snappable;
  if (!state.done.flats) {
    $("snap-note").textContent = "Nothing to snap until the flats exist.";
  } else if (!snappable) {
    $("snap-note").textContent =
      "No reference colours to snap to — add a character sheet first.";
  } else {
    const left = segments.count - segments.snapped;
    $("snap-note").textContent =
      `${segments.snapped} of ${segments.count} snapped, ${left} still the model's guess.` +
      " Click a zone to decide it yourself.";
  }
  $("snap-threshold").disabled = $("snap-any").checked;
}

// ---- steps 2 and 3: correcting the geometry -------------------------------
//
// The detector proposes panels and balloons; this is how the artist disagrees
// with it. Three gestures and no modes: drag a corner, click an edge to add
// one, click empty page to start drawing a new shape. Right-click is the
// destructive half, and it always names what it is about to destroy.
//
// Every change is sent as the whole polygon. The alternative — "corner 3 of
// panel 2 moved to here" — is a second description of the shape, and the two
// go out of step the first time a corner is inserted mid-drag.

// How near a corner or an edge has to be, in screen pixels: the target stays
// the same size to the hand whatever the page is scaled to.
const HANDLE = 8;
const EDGE = 6;

function editable(which) {
  return Boolean(state && state.editable && state.editable[which]);
}

// Which layer the pointer is aimed at, or null when nothing is correctable.
//
// Follows the step the artist is on — panels until balloons exist, balloons
// after — because that is the order the buttons run in. The radio in the
// sidebar is there for the one case that order does not cover: noticing a bad
// panel *after* detecting the balloons, which otherwise costs a re-detect and
// every correction made so far.
function activeLayer() {
  if (layer && editable(layer)) return layer;
  if (editable("bubbles")) return "bubbles";
  if (editable("panels")) return "panels";
  return null;
}

const noun = () => (activeLayer() === "panels" ? "panel" : "bubble");

// The polygons of the active layer, live — mutating one mutates `state`, which
// is what lets a drag repaint at pointer speed without asking the server.
function shapes() {
  const which = activeLayer();
  if (!which) return [];
  return which === "panels" ? state.panels.map((p) => p.polygon) : state.protected;
}

function shapePath(index) {
  return activeLayer() === "panels"
    ? "/api/panel/" + state.panels[index].order
    : "/api/bubble/" + index;
}

function local(event) {
  const rect = stage.getBoundingClientRect();
  return [event.clientX - rect.left, event.clientY - rect.top];
}

function onPage([x, y]) {
  return [
    Math.max(0, Math.min(state.page.width - 1, Math.round(x))),
    Math.max(0, Math.min(state.page.height - 1, Math.round(y))),
  ];
}

function hitCorner(sx, sy) {
  const polygons = shapes();
  // Last first: the shape drawn on top is the one the artist sees on top.
  for (let index = polygons.length - 1; index >= 0; index--) {
    for (let corner = 0; corner < polygons[index].length; corner++) {
      const [x, y] = view.toScreen(...polygons[index][corner]);
      if (Math.hypot(x - sx, y - sy) <= HANDLE) return { index, corner };
    }
  }
  return null;
}

// The edge under the pointer, and where along it the new corner goes.
function hitEdge(sx, sy) {
  const polygons = shapes();
  for (let index = polygons.length - 1; index >= 0; index--) {
    const polygon = polygons[index];
    for (let corner = 0; corner < polygon.length; corner++) {
      const [ax, ay] = view.toScreen(...polygon[corner]);
      const [bx, by] = view.toScreen(...polygon[(corner + 1) % polygon.length]);
      const dx = bx - ax;
      const dy = by - ay;
      const length = dx * dx + dy * dy;
      if (!length) continue;
      // Clamped to the edge's ends, so the corners keep their own hit test
      // rather than losing it to the edge that ends there.
      const along = Math.max(0, Math.min(1, ((sx - ax) * dx + (sy - ay) * dy) / length));
      const px = ax + along * dx;
      const py = ay + along * dy;
      if (Math.hypot(px - sx, py - sy) <= EDGE) {
        return { index, corner: corner + 1, point: onPage(view.toImage(px, py)) };
      }
    }
  }
  return null;
}

// Which shape contains a screen point — even-odd crossing, in page space.
function shapeAt(sx, sy) {
  const [x, y] = view.toImage(sx, sy);
  const polygons = shapes();
  for (let index = polygons.length - 1; index >= 0; index--) {
    const polygon = polygons[index];
    let inside = false;
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
      const [xi, yi] = polygon[i];
      const [xj, yj] = polygon[j];
      if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
    }
    if (inside) return index;
  }
  return null;
}

async function adopt(next) {
  state = next;
  await reloadLayers();
  apply();
}

async function saveShape(index) {
  const polygon = shapes()[index];
  const label = noun();
  try {
    await adopt(
      await call(shapePath(index), {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ polygon }),
      })
    );
    say(label + " corrected.");
  } catch (error) {
    // The local copy is now a shape the server refused, so re-read it rather
    // than leave the screen describing something that does not exist.
    await adopt(await call("/api/state"));
    say(error.message, true);
  }
}

async function deleteCorner({ index, corner }) {
  if (shapes()[index].length <= 3) {
    say("A " + noun() + " needs at least three corners.", true);
    return;
  }
  shapes()[index].splice(corner, 1);
  await saveShape(index);
}

async function deleteShape(index) {
  const label = noun();
  try {
    await adopt(await call(shapePath(index), { method: "DELETE" }));
    say(label + " deleted.");
  } catch (error) {
    say(error.message, true);
  }
}

function startDraft(point) {
  draft = { points: [point] };
  render();
  say("Drawing a " + noun() + " — click the first corner to close it, right-click to stop.");
}

function discardDraft() {
  draft = null;
  cursor = null;
  render();
  say("Stopped drawing.");
}

async function closeDraft() {
  const polygon = draft.points;
  const which = activeLayer();
  draft = null;
  cursor = null;
  try {
    await adopt(
      await call(which === "panels" ? "/api/panel" : "/api/bubble", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ polygon }),
      })
    );
    say("New " + (which === "panels" ? "panel" : "bubble") + " added.");
  } catch (error) {
    render();
    say(error.message, true);
  }
}

stage.addEventListener("pointerdown", (event) => {
  if (event.button !== 0 || !activeLayer()) return;
  const [sx, sy] = local(event);
  const point = onPage(view.toImage(sx, sy));

  if (draft) {
    const [fx, fy] = view.toScreen(draft.points[0][0], draft.points[0][1]);
    if (draft.points.length >= 3 && Math.hypot(fx - sx, fy - sy) <= HANDLE + 3) {
      closeDraft();
    } else {
      draft.points.push(point);
      render();
    }
    return;
  }

  const corner = hitCorner(sx, sy);
  if (corner) {
    drag = { index: corner.index, corner: corner.corner, dirty: false };
    stage.setPointerCapture(event.pointerId);
    return;
  }

  // Clicking an edge puts a corner there and hands it straight to the drag, so
  // "add a corner" and "put it where I want it" are one gesture.
  const edge = hitEdge(sx, sy);
  if (edge) {
    shapes()[edge.index].splice(edge.corner, 0, edge.point);
    drag = { index: edge.index, corner: edge.corner, dirty: true };
    stage.setPointerCapture(event.pointerId);
    render();
    return;
  }

  startDraft(point);
});

stage.addEventListener("pointermove", (event) => {
  if (!activeLayer()) return;
  const [sx, sy] = local(event);

  if (drag) {
    shapes()[drag.index][drag.corner] = onPage(view.toImage(sx, sy));
    drag.dirty = true;
    render();
    return;
  }
  if (draft) {
    cursor = view.toImage(sx, sy);
    render();
    return;
  }
  const corner = Boolean(hitCorner(sx, sy));
  stage.classList.toggle("on-corner", corner);
  stage.classList.toggle("on-edge", !corner && Boolean(hitEdge(sx, sy)));
});

stage.addEventListener("pointerup", (event) => {
  if (!drag) return;
  const dirty = drag.dirty;
  const index = drag.index;
  drag = null;
  if (stage.hasPointerCapture(event.pointerId)) stage.releasePointerCapture(event.pointerId);
  if (dirty) saveShape(index);
});

// ---- the destructive half -------------------------------------------------

function openMenu(event, items) {
  const menu = $("menu");
  menu.innerHTML = "";
  for (const item of items) {
    const button = document.createElement("button");
    button.textContent = item.label;
    button.addEventListener("click", () => {
      closeMenu();
      item.action();
    });
    menu.append(button);
  }
  const rect = stage.getBoundingClientRect();
  menu.style.left = event.clientX - rect.left + "px";
  menu.style.top = event.clientY - rect.top + "px";
  menu.hidden = false;
}

function closeMenu() {
  $("menu").hidden = true;
}

stage.addEventListener("contextmenu", (event) => {
  if (!activeLayer()) return;
  event.preventDefault();
  const [sx, sy] = local(event);

  if (draft) {
    openMenu(event, [{ label: "Stop drawing this " + noun(), action: discardDraft }]);
    return;
  }
  const corner = hitCorner(sx, sy);
  if (corner) {
    openMenu(event, [{ label: "Delete this corner", action: () => deleteCorner(corner) }]);
    return;
  }
  const index = shapeAt(sx, sy);
  if (index !== null) {
    const label = noun();
    openMenu(event, [
      { label: "Delete this " + label, action: () => deleteShape(index) },
    ]);
  }
});

document.addEventListener("pointerdown", (event) => {
  if (!$("menu").hidden && !$("menu").contains(event.target)) closeMenu();
});

for (const which of ["panels", "bubbles"]) {
  $("layer-" + which).addEventListener("change", () => {
    layer = which;
    draft = null;
    drag = null;
    apply();
    say("Correcting " + which + ".");
  });
}

// ---- step 6: one segment at a time ----------------------------------------

function showInspector() {
  const panel = $("inspector");
  if (!selected || !state.done.flats) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;

  const entries = paletteById();
  const current = entries.get(selected.palette_entry_id);
  const suggestion = selected.suggestion;

  $("ins-title").textContent = `Panel ${selected.panel + 1} · zone ${selected.label}`;
  $("ins-area").textContent =
    `${selected.area.toLocaleString()} px · ` +
    (selected.snapped ? "snapped by you" : "showing what the model proposed");

  $("ins-current").style.background = current ? rgb(current.rgb) : "transparent";
  $("ins-current-label").textContent = current
    ? `${current.label}${current.source === "proposed" ? " (proposed)" : ""}`
    : "no colour";

  // The suggestion is measured against whatever the segment holds *now*, so
  // after a snap it is that same colour at ΔE 0. Saying so is more use than
  // offering the artist a zero.
  const taken = suggestion && suggestion.palette_entry_id === selected.palette_entry_id;
  if (suggestion) {
    $("ins-suggestion-row").hidden = false;
    $("ins-suggestion").style.background = rgb(suggestion.rgb);
    $("ins-suggestion-label").textContent = taken
      ? "the nearest reference colour, and the one it holds"
      : `ΔE ${suggestion.delta} — ` +
        (suggestion.within_threshold
          ? "close enough that snap all would take it"
          : "far from anything on the sheet");
    $("ins-suggestion-row").classList.toggle(
      "far",
      !taken && !suggestion.within_threshold,
    );
  } else {
    $("ins-suggestion-row").hidden = true;
  }

  $("ins-snap").disabled = !suggestion || taken;
  $("ins-snap").textContent = suggestion
    ? "Snap to suggestion"
    : "Nothing to snap to";
  $("ins-unsnap").disabled = !selected.snapped;

  const references = state.palette.filter((e) => e.source === "reference");
  $("ins-pick-note").hidden = !references.length;
  $("ins-palette").innerHTML = references
    .map(
      (e) => `<i data-entry="${e.id}" style="background: ${rgb(e.rgb)}" title="${e.label}"
        class="${e.id === selected.palette_entry_id ? "on" : ""}"></i>`
    )
    .join("");
}

async function pickSegment(x, y) {
  try {
    selected = await call(`/api/segment?x=${Math.round(x)}&y=${Math.round(y)}`);
    say(`Panel ${selected.panel + 1}, zone ${selected.label} — ${selected.area} px.`);
  } catch {
    selected = null;
    say("No zone there — that pixel is line, gutter, or a protected balloon.");
  }
  showInspector();
  render();
}

// A snap changes one row, but the flats raster and the counts are derived
// from it, so both are re-read rather than patched locally.
async function afterSegmentChange(message) {
  state = await call("/api/state");
  layers.flats = await loadImage("/api/flats.png");
  layers.left = await loadImage("/api/unsnapped.png");
  apply();
  say(message);
}

async function snapSelected(entryId) {
  if (!selected) return;
  const { panel, label } = selected;
  const query = entryId === undefined ? "" : `?entry_id=${entryId}`;
  try {
    selected = await call(`/api/segment/${panel}/${label}/snap${query}`, {
      method: "POST",
    });
    await afterSegmentChange(`Zone ${label} snapped.`);
  } catch (error) {
    say(error.message, true);
  }
}

async function unsnapSelected() {
  if (!selected) return;
  const { panel, label } = selected;
  try {
    selected = await call(`/api/segment/${panel}/${label}/unsnap`, { method: "POST" });
    await afterSegmentChange(`Zone ${label} back to what the model proposed.`);
  } catch (error) {
    say(error.message, true);
  }
}

stage.addEventListener("click", (event) => {
  if (!state || !state.done.flats) return;
  const rect = stage.getBoundingClientRect();
  const [x, y] = view.toImage(event.clientX - rect.left, event.clientY - rect.top);
  if (x < 0 || y < 0 || x >= state.page.width || y >= state.page.height) return;
  pickSegment(x, y);
});

$("ins-close").addEventListener("click", () => {
  selected = null;
  showInspector();
  render();
});
$("ins-snap").addEventListener("click", () => snapSelected());
$("ins-unsnap").addEventListener("click", unsnapSelected);
$("ins-palette").addEventListener("click", (event) => {
  const entry = event.target.dataset.entry;
  if (entry) snapSelected(entry);
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (!$("menu").hidden) return closeMenu();
  if (draft) return discardDraft();
  if (selected) {
    selected = null;
    showInspector();
    render();
  }
});

$("snap-any").addEventListener("change", () => {
  $("snap-threshold").disabled = $("snap-any").checked;
});

$("btn-snap-all").addEventListener("click", () => {
  // `inf` is the artist overriding the guard deliberately — the same
  // override `comiccolor flatten --threshold inf` takes.
  const threshold = $("snap-any").checked ? "inf" : $("snap-threshold").value;
  step("Snapping every segment", `/api/snap-all?threshold=${threshold}`, {
    method: "POST",
  });
});

function upload(input, path, label, extra) {
  input.addEventListener("change", async () => {
    if (!input.files.length) return;
    const form = new FormData();
    form.append("file", input.files[0]);
    if (extra) for (const [k, v] of Object.entries(extra())) form.append(k, v);
    await step(label, path, { method: "POST", body: form });
    input.value = "";
  });
}

upload($("page-file"), "/api/page", "Loading page");
upload($("ref-file"), "/api/reference", "Reading colours", () => ({
  kind: $("ref-kind").value,
}));

// Removing a reference removes the colours it contributed, so the flats that
// snapped to them are stale — the server says so and `render` follows.
$("refs").addEventListener("click", (event) => {
  const id = event.target.dataset.id;
  if (!id || event.target.tagName !== "BUTTON") return;
  step("Removing reference", `/api/reference/${id}`, { method: "DELETE" });
});

const buttons = {
  "btn-panels": ["/api/panels", "Detecting panels"],
  "btn-bubbles": ["/api/bubbles", "Detecting bubbles"],
  "btn-zones": ["/api/zones", "Segmenting zones"],
  "btn-flats": ["/api/flats", "Generating flats"],
};

// Re-pressing a step replaces what it produced last time (rule 4) — and now
// that panels and balloons are correctable, the artist's own work is part of
// what gets replaced. These are the presses that destroy something, so these
// are the presses that ask first. A step that has produced nothing yet asks
// nothing: the guard is about losing work, not about clicking.
const warnings = {
  "btn-panels": () =>
    state.done.panels &&
    "Detect panels again?\n\nEvery corner you have moved and every panel you " +
      "have drawn is replaced by what the detector finds.",
  "btn-bubbles": () =>
    state.done.bubbles &&
    "Detect bubbles again?\n\nEvery balloon you have traced or corrected is " +
      "replaced by what the detector finds.",
  "btn-zones": () =>
    state.done.zones &&
    "Segment zones again?\n\nThe flats go with them, and so does everything " +
      "you have snapped on this page.",
  "btn-flats": () =>
    state.done.flats &&
    "Generate flats again?\n\nEvery colour you have snapped on this page goes " +
      "back to what the model proposes.",
};

for (const [id, [path, label]] of Object.entries(buttons)) {
  $(id).addEventListener("click", () => {
    const warning = warnings[id]();
    if (warning && !window.confirm(warning)) return;
    // Pressing a step is what moves the artist onto it, so it is also what
    // aims the pointer at that step's geometry. The radio exists to go back.
    if (id === "btn-panels") layer = "panels";
    if (id === "btn-bubbles") layer = "bubbles";
    step(label, path, { method: "POST" });
  });
}

$("btn-export").addEventListener("click", async () => {
  say("Writing PSD…");
  document.body.classList.add("busy");
  try {
    const response = await fetch("/api/export", { method: "POST" });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.error || body.detail || response.statusText);
    }
    const blob = await response.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = (state.page.name.replace(/\.[^.]+$/, "") || "page") + "_flats.psd";
    link.click();
    URL.revokeObjectURL(link.href);
    say("PSD exported — one group per panel, one layer per colour.");
  } catch (error) {
    say(error.message, true);
  } finally {
    document.body.classList.remove("busy");
  }
});

$("btn-reset").addEventListener("click", () => step("Starting over", "/api/reset", { method: "POST" }));

for (const box of document.querySelectorAll(".view input")) {
  box.addEventListener("change", render);
}

window.addEventListener("resize", resize);

(async () => {
  state = await call("/api/state");
  $("snap-threshold").value = state.segments.threshold;
  await reloadLayers();
  apply();
  resize();
  say("Drop in a page to start.");
})();
