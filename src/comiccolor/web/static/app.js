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
    picked.clear();
    cutting = null;
    await reloadLayers();
    apply();
    say(summary(next, label));
  } catch (error) {
    say(error.message, true);
  }
}

function summary(next, label) {
  if (next.result) {
    const { assigned, segments, colours, snapped, skipped, added, kind, panels } = next.result;
    // One file in, several references out: a finished page is stored as the
    // panels it splits into, and the artist pressed one button.
    if (added !== undefined) {
      // A page is kept whole and cut up: the artist pressed one button and
      // got several references, and the count of each is the honest answer.
      // Panels too small for the model to read are not cut out, which is why
      // this number is often lower than the panels they can see.
      return panels
        ? `Page kept whole, plus ${panels} panel${panels > 1 ? "s" : ""} cut from it — ${added} references.`
        : `Reference added as one ${kind}.`;
    }
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
  if (editing === "zones") drawPicked();
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
  $("zones-note").textContent = done.zones
    ? `${zones} zones across the page` +
      (editable("zones") ? " — merge and cut them below, while you still can." : ".")
    : "";

  applyPalette();
  const proposed = state.palette.length - chosen().length;

  // A click only means something once there are segments under it.
  stage.classList.toggle("pickable", done.flats);
  applyEditMode();

  applySnapStep(proposed);
  showInspector();
  render();
}

// ---- step 4b: zones the artist corrects -----------------------------------
//
// Trapped-ball cuts from the ink it can see, so it leaks a garment into the
// background wherever the ink is open, and returns forty scraps wherever the
// drawing is busy. Merging and cutting are the corrections, and they happen
// here — between the cut and the colour — because they are permanent and
// there is no unmerge to fall back on.
//
// One rule runs the selection: a zone is selected while the button is pressed
// over it. A press picks one; holding and moving picks up everything the
// pointer passes over; two zones on opposite sides of the page take two
// presses and drag nothing in between, because the button was up.

// "panel:label" -> {panel, label, bounds, image}. Insertion order is the order
// the artist met them, which is what the menu counts.
const picked = new Map();
let sweep = null; // {points: [[x, y], …], sent: number} while the button is down
let cutting = null; // {panel, label, stroke: [[x, y], …]} after "Cut this zone"

const key = (panel, label) => `${panel}:${label}`;

async function rememberZone(zone) {
  const at = key(zone.panel, zone.label);
  if (picked.has(at)) return;
  picked.set(at, {
    ...zone,
    image: await loadImage(`/api/zone/${zone.panel}/${zone.label}.png`),
  });
}

function clearPicked() {
  picked.clear();
  render();
  applyEditMode();
}

// A press toggles the zone under it; a sweep only ever adds. Otherwise
// wobbling back over a zone mid-sweep would drop it again, and a long sweep
// would be a coin toss.
async function pressZone(x, y) {
  try {
    const zone = await call(`/api/zone?x=${Math.round(x)}&y=${Math.round(y)}`);
    const at = key(zone.panel, zone.label);
    if (picked.has(at)) {
      picked.delete(at);
      say(`Zone ${zone.label} dropped — ${picked.size} selected.`);
    } else {
      await rememberZone(zone);
      say(`Zone ${zone.label} selected — ${picked.size} selected.`);
    }
  } catch {
    say("No zone there — that pixel is line, gutter, or a protected balloon.");
  }
  render();
  applyEditMode();
}

// The sweep goes to the server as a path, once, rather than as a hit test per
// mouse move: one request knows every zone the stroke crossed, including the
// ones that fell between two samples.
async function sweptZones(points) {
  const found = await call("/api/zones/along", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ points }),
  });
  for (const zone of found.zones) await rememberZone(zone);
  if (found.zones.length) say(`${picked.size} zones selected.`);
  render();
  applyEditMode();
}

function drawPicked() {
  for (const zone of picked.values()) {
    if (!zone.image) continue;
    const [left, top, right, bottom] = zone.bounds;
    const [x, y] = view.toScreen(left, top);
    const [ex, ey] = view.toScreen(right + 1, bottom + 1);
    ctx.drawImage(zone.image, x, y, ex - x, ey - y);
  }
  if (cutting) drawCut();
}

// The cut, while it is being drawn: the line the ink was missing.
function drawCut() {
  if (!cutting.stroke.length) return;
  ctx.save();
  ctx.strokeStyle = "#ff5c5c";
  ctx.lineWidth = 2.5;
  ctx.lineCap = "round";
  ctx.beginPath();
  cutting.stroke.forEach(([px, py], index) => {
    const [x, y] = view.toScreen(px, py);
    index === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();
  ctx.restore();
}

async function mergePicked() {
  const zones = [...picked.values()];
  const panel = zones[0].panel;
  if (zones.some((zone) => zone.panel !== panel)) {
    say("Zones merge inside one panel. The same shirt in the next panel is the palette's job.", true);
    return;
  }
  try {
    const next = await call("/api/zones/merge", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ panel, labels: zones.map((zone) => zone.label) }),
    });
    picked.clear();
    await adopt(next);
    say(`${next.result.merged} zones are now one.`);
  } catch (error) {
    say(error.message, true);
  }
}

function startCut() {
  const [zone] = [...picked.values()];
  cutting = { panel: zone.panel, label: zone.label, stroke: [] };
  applyEditMode();
  say("Draw the line the ink was missing: press, drag across the zone, release.");
}

function stopCut() {
  cutting = null;
  applyEditMode();
  render();
}

async function applyCut() {
  const { panel, label, stroke } = cutting;
  cutting = null;
  try {
    const next = await call("/api/zones/cut", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ panel, label, stroke }),
    });
    picked.clear();
    await adopt(next);
    say(`Zone cut into ${next.result.pieces}.`);
  } catch (error) {
    // The zone is untouched, so the selection still means something.
    applyEditMode();
    render();
    say(error.message, true);
  }
}

// ---- the palette, and the references that offer colours to it -------------
//
// Two different things, and the sidebar has to say so. A reference is an
// image: Cobra is shown it, and colours are *found* in it. The palette is the
// artist's list, and nothing lands in it without a click. The chips under a
// thumbnail are that click — every colour the image offers, lit when it has
// been taken.

// The artist's half of the palette. The other half is one private entry per
// segment, which is hundreds of swatches on a real page and not one of them a
// colour anybody chose.
const chosen = () => state.palette.filter((entry) => entry.source === "palette");

const hex = (colour) =>
  "#" + colour.map((part) => part.toString(16).padStart(2, "0")).join("");

function applyPalette() {
  const taken = chosen();
  const offered = state.references.reduce((sum, r) => sum + r.candidates.length, 0);

  $("ref-note").textContent = state.references.length
    ? `${state.references.length} reference(s) shown to the model, ${offered} colours offered — click the ones this book uses.`
    : "Shown to the model. Its colours are offered, not taken.";

  // A palette image has no chips: every colour in it is already in, which is
  // the difference between a decision and a proposal.
  $("pal-note").textContent = state.palettes.length
    ? `${state.palettes.length} palette image(s). Removing one takes its colours out again.`
    : "An image of your swatches. Every colour in it joins the palette.";
  $("palettes").innerHTML = state.palettes
    .map(
      (p) => `<figure data-id="${p.id}">
        <img src="/api/reference/${p.id}.png" alt="${p.label}">
        <figcaption>${p.colours.length} colours</figcaption>
        <button class="x" data-id="${p.id}" title="Remove ${p.label} and its colours">&times;</button>
      </figure>`
    )
    .join("");

  $("refs").innerHTML = state.references
    .map(
      (r) => `<figure data-id="${r.id}">
        <img src="/api/reference/${r.id}.png" alt="${r.label}">
        <figcaption>${r.kind}</figcaption>
        <button class="x" data-id="${r.id}" title="Remove ${r.label}">&times;</button>
        <div class="chips">${r.candidates
          .map(
            (c) => `<i class="${c.entry_id === null ? "" : "on"}"
              style="background: ${rgb(c.rgb)}"
              data-ref="${r.id}" data-rgb="${c.rgb.join(",")}"
              data-entry="${c.entry_id === null ? "" : c.entry_id}"
              title="${c.entry_id === null ? "Add to the palette" : "Take out of the palette"}"></i>`
          )
          .join("")}</div>
      </figure>`
    )
    .join("");

  // A palette swatch is a colour input, because changing a colour here changes
  // it on every zone holding that entry — one row, the whole page (rule 1).
  $("palette").innerHTML = taken
    .map(
      (e) => `<span class="swatch">
        <input type="color" value="${hex(e.rgb)}" data-id="${e.id}" title="${e.label}">
        <button class="x" data-id="${e.id}" title="Remove ${e.label} from the palette">&times;</button>
      </span>`
    )
    .join("");

  $("palette-note").textContent = taken.length
    ? "Click a colour to change it everywhere it is used."
    : offered
      ? "Nothing in the palette yet — a reference's colours are only offered."
      : "";
}

// Chips add and remove; the palette is never a side effect of an upload.
$("refs").addEventListener("click", (event) => {
  const chip = event.target;
  if (chip.tagName !== "I" || !chip.dataset.ref) return;
  if (chip.dataset.entry) {
    dropColour(chip.dataset.entry);
    return;
  }
  takeColour(Number(chip.dataset.ref), chip.dataset.rgb.split(",").map(Number));
});

async function takeColour(reference_id, colour) {
  try {
    await adopt(
      await call("/api/palette", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ reference_id, rgb: colour }),
      })
    );
    say("Colour added to the palette.");
  } catch (error) {
    say(error.message, true);
  }
}

async function dropColour(entryId) {
  try {
    await adopt(await call(`/api/palette/${entryId}`, { method: "DELETE" }));
    say("Colour taken out — zones snapped to it went back to what was proposed.");
  } catch (error) {
    say(error.message, true);
  }
}

$("palette").addEventListener("change", async (event) => {
  const input = event.target;
  if (input.type !== "color") return;
  const value = input.value;
  const colour = [1, 3, 5].map((at) => parseInt(value.slice(at, at + 2), 16));
  try {
    await adopt(
      await call(`/api/palette/${input.dataset.id}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ rgb: colour }),
      })
    );
    say("Colour changed on every zone holding it.");
  } catch (error) {
    say(error.message, true);
  }
});

$("palette").addEventListener("click", (event) => {
  if (event.target.tagName === "BUTTON") dropColour(event.target.dataset.id);
});

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
  for (const name of ["panels", "bubbles", "zones"]) {
    $(`layer-${name}`).disabled = !editable(name);
    $(`layer-${name}`).checked = which === name;
  }

  if (which === "zones") {
    $("edit-note").textContent = cutting
      ? "Draw the line the ink was missing: press, drag across the zone, release. Right-click to stop."
      : `Press a zone to select it, hold and sweep to add more, press again to drop it.` +
        ` Right-click to merge${picked.size === 1 ? ", cut" : ""} or clear.` +
        (picked.size ? ` ${picked.size} selected.` : "");
    return;
  }
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
  // Zones last in the list and first in time: once they exist, the panels and
  // balloons they were cut from are settled, so nothing else is editable.
  if (editable("zones")) return "zones";
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
  // A triangle has no smaller shape to become. Taking a corner off it is the
  // artist saying this detection is wrong, not that it needs one fewer side,
  // so delete the whole thing rather than refuse the click.
  if (shapes()[index].length <= 3) {
    await deleteShape(index);
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

  if (activeLayer() === "zones") {
    stage.setPointerCapture(event.pointerId);
    if (cutting) {
      cutting.stroke = [point];
      render();
      return;
    }
    // The press itself selects; the sweep that may follow only adds.
    sweep = { points: [point], sent: 0 };
    pressZone(point[0], point[1]);
    return;
  }

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

  if (activeLayer() === "zones") {
    if (cutting && cutting.stroke.length) {
      cutting.stroke.push(onPage(view.toImage(sx, sy)));
      render();
    } else if (sweep) {
      sweep.points.push(onPage(view.toImage(sx, sy)));
      // Sent in flight rather than only on release, so the highlight keeps up
      // with the hand. Each request carries the path since the last one.
      if (sweep.points.length - sweep.sent > 12) {
        const path = sweep.points.slice(Math.max(0, sweep.sent - 1));
        sweep.sent = sweep.points.length;
        sweptZones(path);
      }
    }
    return;
  }

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
  if (activeLayer() === "zones") {
    if (stage.hasPointerCapture(event.pointerId)) stage.releasePointerCapture(event.pointerId);
    if (cutting && cutting.stroke.length) {
      applyCut();
      return;
    }
    if (sweep) {
      const path = sweep.points.slice(Math.max(0, sweep.sent - 1));
      sweep = null;
      if (path.length > 1) sweptZones(path);
    }
    return;
  }
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

  if (activeLayer() === "zones") {
    if (cutting) {
      openMenu(event, [{ label: "Stop cutting", action: stopCut }]);
      return;
    }
    const items = [];
    if (picked.size >= 2) {
      items.push({ label: `Merge these ${picked.size} zones`, action: mergePicked });
    }
    // Cutting is one zone's business: with several selected there is no
    // saying which one the stroke belongs to.
    if (picked.size === 1) items.push({ label: "Cut this zone", action: startCut });
    if (picked.size) items.push({ label: "Clear selection", action: clearPicked });
    if (items.length) openMenu(event, items);
    return;
  }

  if (draft) {
    openMenu(event, [{ label: "Stop drawing this " + noun(), action: discardDraft }]);
    return;
  }
  const corner = hitCorner(sx, sy);
  if (corner) {
    // On a triangle the corner *is* the shape — say so, so the click that
    // removes the whole detection never comes as a surprise.
    const last = shapes()[corner.index].length <= 3;
    const label = last ? "Delete this " + noun() : "Delete this corner";
    openMenu(event, [{ label, action: () => deleteCorner(corner) }]);
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

for (const which of ["panels", "bubbles", "zones"]) {
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

  const references = chosen();
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
  if (cutting) return stopCut();
  if (picked.size) return clearPicked();
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
upload($("pal-file"), "/api/palette/image", "Taking the palette");

// Deleting a reference deletes the image, not the colours taken from it: the
// flats are stale all the same, because the proposal came from an image that
// is no longer there.
$("refs").addEventListener("click", (event) => {
  const id = event.target.dataset.id;
  if (!id || event.target.tagName !== "BUTTON") return;
  step("Removing reference", `/api/reference/${id}`, { method: "DELETE" });
});

$("palettes").addEventListener("click", (event) => {
  const id = event.target.dataset.id;
  if (!id || event.target.tagName !== "BUTTON") return;
  step("Removing palette", `/api/reference/${id}`, { method: "DELETE" });
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
    "Segment zones again?\n\nThe page is cut from scratch: every merge, every " +
      "cut, the flats, and everything you have snapped on this page.",
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
