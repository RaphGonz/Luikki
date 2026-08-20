// The five buttons, and one transform.
//
// Rule 5: exactly one screen <-> image transform, `view`, recomputed on every
// render. Nothing else in this file converts coordinates. There is no editing
// in the barebone version, so nothing hit-tests yet -- but when merge and cut
// arrive they go through `view.toImage`, not through a second copy of this
// arithmetic.

const $ = (id) => document.getElementById(id);
const stage = $("stage");
const ctx = stage.getContext("2d");

let state = null;
const layers = { page: null, lines: null, zones: null, flats: null };

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

  if (layers.page && $("v-page").checked) ctx.drawImage(layers.page, ...box);

  // What segmentation actually saw, drawn over the page so you can compare
  // the structural lines against the artist's ink.
  if (layers.lines && $("v-lines").checked) {
    ctx.globalAlpha = 0.9;
    ctx.drawImage(layers.lines, ...box);
    ctx.globalAlpha = 1;
  }

  // Flats sit above zones: once the colours exist, the zone map is scaffolding.
  if (layers.zones && $("v-zones").checked) {
    ctx.globalAlpha = 0.5;
    ctx.drawImage(layers.zones, ...box);
    ctx.globalAlpha = 1;
  }
  if (layers.flats && $("v-flats").checked) {
    ctx.globalAlpha = 0.85;
    ctx.drawImage(layers.flats, ...box);
    ctx.globalAlpha = 1;
  }

  if ($("v-bubbles").checked) {
    ctx.strokeStyle = "#f0a35e";
    ctx.lineWidth = 1.5;
    for (const polygon of state.protected) trace(polygon);
  }

  if ($("v-panels").checked) {
    ctx.strokeStyle = "#6ea8fe";
    ctx.lineWidth = 2;
    ctx.font = "600 15px ui-sans-serif, system-ui, sans-serif";
    ctx.fillStyle = "#6ea8fe";
    for (const panel of state.panels) {
      trace(panel.polygon);
      const [x, y] = view.toScreen(panel.polygon[0][0], panel.polygon[0][1]);
      ctx.fillText(String(panel.order + 1), x + 6, y + 18);
    }
  }
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
    ? `${state.panels.length} panels. Wrong ones get deleted in Photoshop for now.`
    : "";
  $("bubbles-note").textContent = done.bubbles
    ? `${state.protected.length} protected areas — never coloured.`
    : "";
  $("zones-note").textContent = done.zones ? `${zones} zones across the page.` : "";

  $("ref-note").textContent = state.palette.length
    ? `${state.references.length} reference(s), ${state.palette.length} colours — zones snap to these.`
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
  $("palette").innerHTML = state.palette
    .map((e) => `<i style="background: rgb(${e.rgb.join(",")})" title="${e.label}"></i>`)
    .join("");

  render();
}

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
for (const [id, [path, label]] of Object.entries(buttons)) {
  $(id).addEventListener("click", () => step(label, path, { method: "POST" }));
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
  await reloadLayers();
  apply();
  resize();
  say("Drop in a page to start.");
})();
