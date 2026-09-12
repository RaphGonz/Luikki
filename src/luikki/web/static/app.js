// Luikki — the interface: a rail of seven steps, one canvas, one inspector.
//
// Rule 5: exactly one screen <-> image transform, `view`, recomputed on every
// render. Nothing else in this file converts coordinates. Every hit test goes
// through `view.toImage`, and the server resolves a point off the label map:
// there is no second copy of the arithmetic and no client-side guess at which
// zone was clicked.
//
// The rail controls the canvas and the canvas controls the inspector (UI.md
// R5). Which step is open decides what the canvas shows and what a click on
// it does; what the click lands on decides what the inspector holds.
//
// No word the artist reads is written in this file. Every one is a key into
// `locales/<lang>.json`, looked up through `t`, so a new language is a new
// file and nothing else.

"use strict";

const $ = (id) => document.getElementById(id);

const remembered = {
  get(name) {
    try {
      return localStorage.getItem("luikki:" + name);
    } catch {
      return null;
    }
  },
  set(name, value) {
    try {
      localStorage.setItem("luikki:" + name, value);
    } catch {
      // A browser that refuses storage just forgets the preference.
    }
  },
};

// ---- words ------------------------------------------------------------------
//
// A locale is a flat map of dotted keys. A value is a string with `{name}`
// placeholders, or an object of plural forms named the way `Intl.PluralRules`
// names them — `one`/`other` in English, `other` alone in Japanese, `few` and
// `many` in Polish — so no language has to fit English grammar.
//
// Keys are written out in full wherever they are used, never assembled from
// pieces: `tests/test_locales.py` reads this file for them, and a key built at
// runtime is a key that test cannot see.

const LOCALES = ["en", "fr"];
// Accented and stretched from English at runtime. A string still unaccented
// on screen was written into the code; a row that breaks will break in French.
const PSEUDO = "en-XA";

const words = {
  locale: "en",
  numbers: "en",
  strings: {},
  fallback: {},
  plural: new Intl.PluralRules("en"),
  warned: new Set(),
};

function chooseLocale() {
  const asked = new URLSearchParams(location.search).get("lang");
  if (asked === PSEUDO || LOCALES.includes(asked)) return asked;
  const stored = remembered.get("lang");
  if (LOCALES.includes(stored)) return stored;
  for (const tag of navigator.languages || []) {
    if (LOCALES.includes(tag)) return tag;
    if (LOCALES.includes(tag.split("-")[0])) return tag.split("-")[0];
  }
  return "en";
}

async function loadWords(locale) {
  const read = async (path) => (await fetch(path)).json();
  words.fallback = await read("/locales/en.json");
  if (locale === PSEUDO) words.strings = pseudoLocale(words.fallback);
  else if (locale === "en") words.strings = words.fallback;
  else words.strings = await read(`/locales/${locale}.json`).catch(() => words.fallback);
  words.locale = locale;
  words.numbers = locale === PSEUDO ? "en" : locale;
  words.plural = new Intl.PluralRules(words.numbers);
  document.documentElement.lang = locale;
}

function lookup(key, params = {}) {
  let entry = words.strings[key];
  if (entry === undefined) {
    entry = words.fallback[key];
    if (!words.warned.has(key)) {
      words.warned.add(key);
      console.warn(`luikki: no "${key}" in ${words.locale}`);
    }
  }
  if (entry === undefined) return key;
  if (typeof entry === "object") {
    entry = entry[words.plural.select(params.count ?? 0)] ?? entry.other;
  }
  return entry.replace(/\{(\w+)\}/g, (whole, name) => {
    if (!(name in params)) return whole;
    const value = params[name];
    return typeof value === "number" ? fmt.number(value) : String(value);
  });
}

const t = (key, params) => lookup(key, params);

function pseudoLocale(source) {
  const accents = {
    a: "á", b: "ƀ", c: "ç", d: "ð", e: "é", f: "ƒ", g: "ĝ", h: "ĥ", i: "í",
    j: "ĵ", k: "ķ", l: "ĺ", m: "ɱ", n: "ñ", o: "ö", p: "þ", r: "ŕ", s: "š",
    t: "ţ", u: "ü", w: "ŵ", y: "ý", z: "ž", A: "Á", C: "Ç", D: "Ð", E: "É",
    G: "Ĝ", I: "Í", L: "Ĺ", N: "Ñ", O: "Ö", P: "Þ", R: "Ŕ", S: "Š", T: "Ţ",
    U: "Ü", Z: "Ž",
  };
  const stretch = (text) => {
    // Placeholders pass through untouched: they are code, not words.
    const accented = text
      .split(/(\{\w+\})/)
      .map((part) => (/^\{\w+\}$/.test(part) ? part : part.replace(/[A-Za-z]/g, (c) => accents[c] ?? c)))
      .join("");
    return `[${accented} ${"·".repeat(Math.ceil(text.length * 0.35))}]`;
  };
  const each = (value) =>
    typeof value === "object"
      ? Object.fromEntries(Object.entries(value).map(([form, text]) => [form, stretch(text)]))
      : stretch(value);
  return Object.fromEntries(Object.entries(source).map(([key, value]) => [key, each(value)]));
}

const fmt = {
  number: (value, digits = 0) =>
    new Intl.NumberFormat(words.numbers, {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    }).format(value),
  percent: (value) =>
    new Intl.NumberFormat(words.numbers, { style: "percent", maximumFractionDigits: 0 }).format(
      value / 100,
    ),
  clock: (seconds) =>
    `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`,
};

function applyStaticStrings() {
  for (const el of document.querySelectorAll("[data-i18n]")) {
    el.textContent = lookup(el.dataset.i18n);
  }
  for (const el of document.querySelectorAll("[data-i18n-title]")) {
    el.title = lookup(el.dataset.i18nTitle);
  }
  for (const el of document.querySelectorAll("[data-i18n-aria-label]")) {
    el.setAttribute("aria-label", lookup(el.dataset.i18nAriaLabel));
  }
}

// ---- elements ---------------------------------------------------------------

// Text goes in as text, never as markup: a reference label is a file name,
// and a file name is not HTML.
function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [name, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (name === "class") el.className = value;
    else if (name === "style") Object.assign(el.style, value);
    else if (name.startsWith("on")) el.addEventListener(name.slice(2), value);
    else if (name in el) el[name] = value;
    else el.setAttribute(name, value === true ? "" : value);
  }
  el.append(...children.flat().filter((child) => child !== null && child !== undefined && child !== false));
  return el;
}

// A disabled button keeps its tooltip and its place in the tab order, so the
// reason it is disabled can still be read (§12). `aria-disabled` rather than
// `disabled` is what allows both.
function button(content, { kind = "", key, onclick, disabled = false, why, label, pressed } = {}) {
  return h(
    "button",
    {
      type: "button",
      class: `btn ${kind}`.trim(),
      "data-key": key,
      "aria-disabled": disabled ? "true" : null,
      "aria-label": label,
      "aria-pressed": pressed === undefined ? null : String(pressed),
      title: disabled ? why : label,
      onclick: (event) => {
        if (!disabled) onclick(event);
      },
    },
    content,
  );
}

const ICONS = {
  check: '<path d="M3.5 8.5l3 3 6-7"/>',
  close: '<path d="M4.5 4.5l7 7M11.5 4.5l-7 7"/>',
};

function icon(name) {
  const glyph = document.createElement("span");
  glyph.className = "glyph";
  glyph.setAttribute("aria-hidden", "true");
  glyph.innerHTML = `<svg viewBox="0 0 16 16">${ICONS[name]}</svg>`;
  return glyph;
}

// The check on a taken chip sits on an arbitrary colour, so it is drawn the
// way lines on the artwork are: dark under light.
function tick() {
  const mark = document.createElement("span");
  mark.className = "tick";
  mark.setAttribute("aria-hidden", "true");
  mark.innerHTML =
    '<svg viewBox="0 0 16 16"><path class="under" d="M3.5 8.5l3 3 6-7"/><path class="over" d="M3.5 8.5l3 3 6-7"/></svg>';
  return mark;
}

// Re-rendering a column replaces its buttons. The one holding the keyboard
// focus is found again by its key, so tabbing through the rail survives it.
function keepFocus(draw) {
  const focused = document.activeElement?.dataset?.key;
  draw();
  if (focused && document.activeElement?.dataset?.key !== focused) {
    document.querySelector(`[data-key="${CSS.escape(focused)}"]`)?.focus({ preventScroll: true });
  }
}

// ---- tokens -----------------------------------------------------------------

// Read once. The canvas cannot use a CSS variable, so it uses the value the
// variable holds, and `app.css` stays the only place a colour is written.
const tokens = (() => {
  const style = getComputedStyle(document.documentElement);
  const read = (name) => style.getPropertyValue(name).trim();
  return {
    dark: read("--over-dark"),
    light: read("--over-light"),
    wash: read("--over-wash"),
    panel: read("--over-panel"),
    bubble: read("--over-bubble"),
    ring: read("--action-ring"),
    edge: read("--canvas-edge"),
    chip: read("--bg"),
    chipText: read("--text"),
    font: read("--font"),
    surround: parseFloat(read("--s-6")),
  };
})();

// The paper under the page. Not an interface colour: it is the artwork's own
// white, and multiply needs it to leave the line art exactly as drawn.
const PAPER = "white";

// ---- state ------------------------------------------------------------------

const stage = $("stage");
const ctx = stage.getContext("2d");

let state = null;
// The open step in the rail. Everything on the canvas follows it.
let current = null;
// `references` or `palette` when the inspector shows the book instead of the step.
let shelf = null;
// The rail's one inline confirmation: {id, sentence}.
let asking = null;
const layers = { page: null, lines: null, zones: null, flats: null, left: null };
const controls = {
  gap: 14,
  threshold: 12,
  ignoreGuard: true,
  granularity: "colour",
  refKind: "sheet",
  lines: false,
  neutral: false,
  left: false,
};

// The artist's corrections since each stage last ran in this browser, so a
// confirmation can say what it deletes. null is "unknown": after a reload the
// server still holds the corrections, and this page never saw them made.
let edits = freshEdits();

function freshEdits() {
  return { panels: 0, bubbles: 0, zones: { merges: 0, cuts: 0 } };
}

const bump = (count) => (count === null ? null : count + 1);

// ---- the view ---------------------------------------------------------------

const view = {
  scale: 1,
  ox: 0,
  oy: 0,
  toScreen(x, y) {
    return [x * this.scale + this.ox, y * this.scale + this.oy];
  },
  toImage(x, y) {
    return [(x - this.ox) / this.scale, (y - this.oy) / this.scale];
  },
};

// Zoom and pan sit on top of the fit rather than beside it: `zoom` multiplies
// the scale that fits the page inside its surround, `pan` offsets it from
// centred. `applyView` folds both into `view`, which stays the only converter.
const MAX_ZOOM = 32;
let zoom = 1;
let pan = { x: 0, y: 0 };
let panning = null;
let panned = false;
let spaceHeld = false;

// The surround is `--s-6` at the minimum on every side (§10).
function fitScale() {
  const margin = tokens.surround;
  return Math.min(
    (stage.clientWidth - margin * 2) / state.page.width,
    (stage.clientHeight - margin * 2) / state.page.height,
  );
}

// The one sizing function. The clamp is the safety of zooming: the page cannot
// be flung off screen, and a page smaller than the canvas cannot be panned.
function applyView() {
  const page = state.page;
  zoom = Math.min(MAX_ZOOM, Math.max(1, zoom));
  view.scale = fitScale() * zoom;
  const drawnWidth = page.width * view.scale;
  const drawnHeight = page.height * view.scale;
  const slackX = Math.max(0, (drawnWidth - stage.clientWidth) / 2 + tokens.surround);
  const slackY = Math.max(0, (drawnHeight - stage.clientHeight) / 2 + tokens.surround);
  pan.x = zoom > 1 ? Math.max(-slackX, Math.min(slackX, pan.x)) : 0;
  pan.y = zoom > 1 ? Math.max(-slackY, Math.min(slackY, pan.y)) : 0;
  view.ox = (stage.clientWidth - drawnWidth) / 2 + pan.x;
  view.oy = (stage.clientHeight - drawnHeight) / 2 + pan.y;
}

function fitPage() {
  zoom = 1;
  pan = { x: 0, y: 0 };
  render();
}

// ---- the server -------------------------------------------------------------

// A refusal the server names by code (`StepError`) is worded here, in the
// artist's language. A sentence — a proposer that could not run — shows as
// it came.
function failure(body, fallback) {
  const code = body && body.code ? "error." + body.code : null;
  if (code && (code in words.strings || code in words.fallback)) {
    return new Error(lookup(code, body.params || {}));
  }
  const message = body && body.detail;
  if (typeof message === "string") return new Error(message);
  return new Error(message ? t("error.refused") : fallback || t("error.refused"));
}

async function call(path, options = {}) {
  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new Error(t("error.network"));
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw failure(body, response.statusText);
  return body;
}

// An upload, through XMLHttpRequest because it is the one request a browser
// can measure: the bar shows the bytes really sent.
function send(path, form) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", path);
    request.responseType = "json";
    request.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) return;
      if (event.loaded < event.total) {
        work.percent = (100 * event.loaded) / event.total;
      } else {
        work.percent = null;
        work.label = t("work.reading");
      }
      showWork();
    });
    request.addEventListener("load", () => {
      if (request.status < 300) resolve(request.response);
      else reject(failure(request.response || {}, request.statusText));
    });
    request.addEventListener("error", () => reject(new Error(t("error.network"))));
    request.send(form);
  });
}

// ---- the footer: status and progress ----------------------------------------

function say(message, bad = false) {
  const status = $("status");
  status.textContent = message;
  status.classList.toggle("bad", bad);
}

const work = { timer: null, started: 0, label: "", phase: null, polling: false, pending: false, percent: null };

// A long step, with the bar running. Segmenting and colouring report a real
// percent through `/api/progress`; a step that reports none gets a still track
// and the time it has taken, never an invented percent (§6).
async function working(label, polling, task) {
  Object.assign(work, {
    started: performance.now(),
    label,
    phase: null,
    polling,
    pending: false,
    percent: null,
  });
  document.body.classList.add("busy");
  $("bar").hidden = false;
  showWork();
  work.timer = setInterval(tickWork, 250);
  try {
    return await task();
  } finally {
    clearInterval(work.timer);
    work.timer = null;
    $("bar").hidden = true;
    $("bar-fill").style.width = "0";
    document.body.classList.remove("busy");
  }
}

async function tickWork() {
  if (work.polling && !work.pending) {
    work.pending = true;
    try {
      const progress = await call("/api/progress");
      if (work.timer && progress.running) {
        work.percent = progress.percent;
        work.phase = progressLabel(progress);
      }
    } catch {
      // A missed poll is a bar that waits a tick. The step itself reports errors.
    } finally {
      work.pending = false;
    }
  }
  if (work.timer) showWork();
}

function progressLabel(progress) {
  switch (progress.phase) {
    case "extract":
      return t("progress.extract");
    case "segment":
      return t("progress.segment", { index: progress.index, total: progress.count });
    case "colour":
      return t("progress.colour", { index: progress.index, total: progress.count });
    default:
      return null;
  }
}

function showWork() {
  const bar = $("bar");
  const determinate = work.percent !== null;
  bar.classList.toggle("indeterminate", !determinate);
  if (determinate) {
    $("bar-fill").style.width = `${work.percent}%`;
    bar.setAttribute("aria-valuenow", String(Math.round(work.percent)));
  } else {
    bar.removeAttribute("aria-valuenow");
  }
  const label = work.phase || work.label;
  say(
    determinate
      ? t("progress.percent", { label, percent: fmt.percent(work.percent) })
      : t("progress.elapsed", { label, time: fmt.clock((performance.now() - work.started) / 1000) }),
  );
}

// ---- layers -----------------------------------------------------------------

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

// The server paints what is left to snap in orange, and orange on a comic page
// is skin (§11). Keep its shape, drop its hue.
function luminanceOnly(image) {
  if (!image) return null;
  const canvas = document.createElement("canvas");
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  const paint = canvas.getContext("2d");
  paint.drawImage(image, 0, 0);
  paint.globalCompositeOperation = "source-in";
  paint.fillStyle = tokens.dark;
  paint.fillRect(0, 0, canvas.width, canvas.height);
  return canvas;
}

async function reloadLayers() {
  const done = state.done;
  [layers.page, layers.lines, layers.zones, layers.flats, layers.left] = await Promise.all([
    done.page ? loadImage("/api/page.png") : null,
    // Extraction happens inside Segment zones, so this only exists afterwards.
    done.zones ? loadImage("/api/lines.png") : null,
    done.zones ? loadImage("/api/zones.png") : null,
    done.flats ? loadImage("/api/flats.png") : null,
    done.flats ? loadImage("/api/unsnapped.png").then(luminanceOnly) : null,
  ]);
}

async function adopt(next) {
  state = next;
  await reloadLayers();
  renderAll();
}

// ---- the steps --------------------------------------------------------------

const STEPS = [
  { id: "upload", number: 1, needs: null, done: (d) => d.page },
  { id: "panels", number: 2, needs: "page", done: (d) => d.panels },
  { id: "bubbles", number: 3, needs: "panels", done: (d) => d.bubbles },
  { id: "zones", number: 4, needs: "panels", done: (d) => d.zones },
  { id: "flats", number: 5, needs: "zones", done: (d) => d.flats },
  // Snapping is per segment and never finished; exporting can always happen again.
  { id: "snap", number: 6, needs: "flats", done: () => false },
  { id: "export", number: 7, needs: "flats", done: () => false },
];

// The stages whose geometry the artist corrects, and which the next step closes.
const CORRECTED = ["panels", "bubbles", "zones"];

function stepName(id) {
  switch (id) {
    case "upload": return t("step.upload.name");
    case "panels": return t("step.panels.name");
    case "bubbles": return t("step.bubbles.name");
    case "zones": return t("step.zones.name");
    case "flats": return t("step.flats.name");
    case "snap": return t("step.snap.name");
    default: return t("step.export.name");
  }
}

function lockedReason(needs) {
  switch (needs) {
    case "page": return t("locked.page");
    case "panels": return t("locked.panels");
    case "zones": return t("locked.zones");
    default: return t("locked.flats");
  }
}

function closedReason(id) {
  switch (id) {
    case "panels": return t("closed.panels");
    case "bubbles": return t("closed.bubbles");
    default: return t("closed.zones");
  }
}

function stateName(status) {
  switch (status) {
    case "done": return t("state.done");
    case "current": return t("state.current");
    case "next": return t("state.next");
    case "locked": return t("state.locked");
    default: return t("state.closed");
  }
}

const isLocked = (step) => Boolean(step.needs) && !state.done[step.needs];

// Five states from the server's flags and the open step (§8). The order the
// server enforces is shown before the click, never discovered by it (R6).
function stepState(step) {
  if (isLocked(step)) return "locked";
  if (step.id === current) return "current";
  if (step.done(state.done)) {
    return CORRECTED.includes(step.id) && !state.editable[step.id] ? "closed" : "done";
  }
  return "next";
}

// The furthest step the page has reached — where a reload opens.
function furthest() {
  const done = state.done;
  if (!done.page) return "upload";
  if (!done.panels) return "panels";
  if (!done.zones) return done.bubbles ? "zones" : "bubbles";
  if (!done.flats) return "zones";
  return "snap";
}

function ensureCurrent() {
  const step = STEPS.find((candidate) => candidate.id === current);
  if (!step || isLocked(step)) current = furthest();
}

const zoneCount = (source = state) => source.panels.reduce((sum, panel) => sum + panel.zones, 0);

function stepMeta(id) {
  const done = state.done;
  switch (id) {
    case "panels": return done.panels ? t("meta.panels", { count: state.panels.length }) : "";
    case "bubbles": return done.bubbles ? t("meta.bubbles", { count: state.protected.length }) : "";
    case "zones": return done.zones ? t("meta.zones", { count: zoneCount() }) : "";
    case "flats": return done.flats ? t("meta.segments", { count: state.segments.count }) : "";
    case "snap":
      return done.flats
        ? t("meta.snapped", { snapped: state.segments.snapped, count: state.segments.count })
        : "";
    default: return "";
  }
}

const RUNS = {
  panels: {
    path: () => "/api/panels",
    polling: false,
    label: () => t("work.panels"),
    done: (next) => t("done.panels", { count: next.panels.length }),
  },
  bubbles: {
    path: () => "/api/bubbles",
    polling: false,
    label: () => t("work.bubbles"),
    done: (next) => t("done.bubbles", { count: next.protected.length }),
  },
  zones: {
    // The gap allowance rides along with the press that uses it: turning the
    // dial changes nothing on its own, because the zones on screen were cut
    // with the old one.
    path: () => `/api/zones?gap=${controls.gap / 100}`,
    polling: true,
    label: () => t("work.zones"),
    done: (next) => t("done.zones", { count: zoneCount(next) }),
  },
  flats: {
    path: () => "/api/flats",
    polling: true,
    label: () => t("work.flats"),
    done: (next) => t("done.flats", { count: next.result.segments }),
  },
};

function pressRow(step, status) {
  if (status === "locked" || status === "current") return;
  if (status === "next") {
    if (step.id === "upload") return choosePage();
    // Step 5 that the GPU would refuse opens instead, where it says why.
    if (RUNS[step.id] && !(step.id === "flats" && gpuBlock())) return requestRun(step.id);
    // Export and snap only open: each has a choice to make first (the layers,
    // the guard), and a row click that skipped it hid the choice entirely.
  }
  open(step.id);
}

function open(id) {
  current = id;
  shelf = null;
  asking = null;
  forgetCanvasSelection();
  renderAll();
}

// ---- confirmations ----------------------------------------------------------
//
// Re-running a step replaces what it produced and clears what was built on it
// (rule 4). A press that would delete the artist's own work asks first, in the
// rail, naming what goes (T9). A press that loses nothing asks nothing.

function ownLoss(id) {
  switch (id) {
    case "panels":
      if (!state.done.panels) return null;
      if (edits.panels === null) return t("confirm.panels.unknown");
      return edits.panels ? t("confirm.panels.counted", { count: edits.panels }) : null;
    case "bubbles":
      if (!state.done.bubbles) return null;
      if (edits.bubbles === null) return t("confirm.bubbles.unknown");
      return edits.bubbles ? t("confirm.bubbles.counted", { count: edits.bubbles }) : null;
    case "zones": {
      if (!state.done.zones) return null;
      const zones = edits.zones;
      if (zones === null) return t("confirm.zones.unknown");
      if (!zones.merges && !zones.cuts) return null;
      return t("confirm.zones.counted", {
        merges: t("count.merges", { count: zones.merges }),
        cuts: t("count.cuts", { count: zones.cuts }),
      });
    }
    case "flats":
      return state.done.flats && state.segments.snapped
        ? t("confirm.flats.counted", { count: state.segments.snapped })
        : null;
    default:
      return null;
  }
}

// What the server clears downstream: panels and bubbles both invalidate the
// zones, and with them the flats. The traced balloons survive new panels.
// Whole sentences rather than a list of nouns, so no language has to fit the
// nouns into an English list.
function laterLoss(id) {
  const done = state.done;
  if ((id === "panels" || id === "bubbles") && done.zones) {
    return done.flats ? t("confirm.later.all") : t("confirm.later.zones");
  }
  if (id === "zones" && done.flats) return t("confirm.later.flats");
  return null;
}

function question(id) {
  switch (id) {
    case "panels": return t("confirm.panels.ask");
    case "bubbles": return t("confirm.bubbles.ask");
    default: return t("confirm.zones.ask");
  }
}

function rerunSentence(id) {
  const own = ownLoss(id);
  const later = laterLoss(id);
  if (!own && !later) return null;
  const first = own || question(id);
  return later ? t("confirm.with_later", { first, later }) : first;
}

function askFor(id, sentence) {
  asking = { id, sentence };
  renderRail();
  document.querySelector(`[data-key="ask-${id}"]`)?.focus();
}

function requestRun(id) {
  const sentence = rerunSentence(id);
  if (sentence) return askFor(id, sentence);
  runStep(id);
}

function askLabel(id) {
  switch (id) {
    case "panels": return t("ask.panels");
    case "bubbles": return t("ask.bubbles");
    case "zones": return t("ask.zones");
    case "flats": return t("ask.flats");
    default: return t("ask.delete_page");
  }
}

function confirmAsked(id) {
  asking = null;
  if (id === "delete") return deletePage();
  runStep(id);
}

function askBlock(id) {
  if (!asking || asking.id !== id) return null;
  return h(
    "div",
    { class: "ask", role: "alert" },
    h("p", {}, asking.sentence),
    h(
      "div",
      { class: "row" },
      button(askLabel(id), { kind: "destructive", key: `ask-${id}`, onclick: () => confirmAsked(id) }),
      button(t("ask.keep"), {
        kind: "quiet",
        key: "ask-keep",
        onclick: () => {
          asking = null;
          renderRail();
        },
      }),
    ),
  );
}

// ---- running a step ---------------------------------------------------------

async function runStep(id) {
  asking = null;
  const run = RUNS[id];
  renderRail();
  try {
    const next = await working(run.label(), run.polling, () => call(run.path(), { method: "POST" }));
    forgetCanvasSelection();
    traces.clear();
    if (id === "panels" || id === "bubbles") edits[id] = 0;
    // Flats leave the zones as they were, merges and cuts included.
    if (id !== "flats") edits.zones = { merges: 0, cuts: 0 };
    state = next;
    // A correction stage opens on itself: detecting is what moves the artist
    // onto the geometry. Colours open on snapping, which is what comes next.
    current = id === "flats" ? "snap" : id;
    shelf = null;
    await reloadLayers();
    renderAll();
    say(run.done(next));
  } catch (error) {
    renderAll();
    say(error.message, true);
  }
  // A press of step 5 spends a page or a generation, or was refused for a reason
  // that may have changed: either way the line above the button is stale.
  if (id === "flats") refreshGpu();
}

// Uploading adds a page: the one on screen stays in the project as it was
// left, so there is nothing to confirm.
function choosePage() {
  $("page-file").click();
}

async function uploadFile(input, path, label, extra = {}) {
  if (!input.files.length) return null;
  const form = new FormData();
  form.append("file", input.files[0]);
  for (const [name, value] of Object.entries(extra)) form.append(name, value);
  input.value = "";
  try {
    return await working(label, false, () => send(path, form));
  } catch (error) {
    say(error.message, true);
    return null;
  }
}

// Another page on screen: nothing selected, drawn or zoomed carries over. The
// corrections a reopened page already holds were made in another sitting, so
// they are unknown here and a re-run asks in general terms instead of counting.
async function enterPage(next) {
  forgetCanvasSelection();
  traces.clear();
  state = next;
  edits = {
    panels: state.done.panels ? null : 0,
    bubbles: state.done.bubbles ? null : 0,
    zones: state.done.zones ? null : { merges: 0, cuts: 0 },
  };
  current = furthest();
  shelf = null;
  zoom = 1;
  pan = { x: 0, y: 0 };
  await reloadLayers();
  renderAll();
  // Another page is another count: counted this month or not.
  refreshGpu();
}

$("page-file").addEventListener("change", async () => {
  const next = await uploadFile($("page-file"), "/api/page", t("work.page"));
  if (!next) return;
  await enterPage(next);
  say(t("done.page", { name: next.page.name }));
});

async function openPage(id) {
  try {
    const next = await working(t("work.open_page"), false, () =>
      call(`/api/pages/${id}/open`, { method: "POST" }),
    );
    await enterPage(next);
    say(t("done.page_opened", { name: next.page.name }));
  } catch (error) {
    renderAll();
    say(error.message, true);
  }
}

async function deletePage() {
  try {
    const next = await working(t("work.delete_page"), false, () => call("/api/page", { method: "DELETE" }));
    await enterPage(next);
    say(t("done.page_deleted"));
  } catch (error) {
    renderAll();
    say(error.message, true);
  }
}

async function snapAll() {
  // `inf` is the artist overriding the guard deliberately — the same override
  // `luikki flatten --threshold inf` takes.
  const threshold = controls.ignoreGuard ? "inf" : controls.threshold;
  try {
    const next = await working(t("work.snap_all"), false, () =>
      call(`/api/snap-all?threshold=${threshold}`, { method: "POST" }),
    );
    selected = null;
    await adopt(next);
    say(t("done.snap_all", { snapped: next.result.snapped, skipped: next.result.skipped }));
  } catch (error) {
    say(error.message, true);
  }
}

const exportLayers = () => state.export.layers[controls.granularity] ?? 0;
const heavyExport = () => exportLayers() > state.export.warn_at;

async function exportPsd() {
  const granularity = controls.granularity;
  const count = exportLayers();
  try {
    const blob = await working(t("work.export"), false, async () => {
      const response = await fetch(`/api/export?granularity=${granularity}`, { method: "POST" });
      if (!response.ok) throw failure(await response.json().catch(() => ({})), response.statusText);
      return response.blob();
    });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = (state.page.name.replace(/\.[^.]+$/, "") || "page") + "_flats.psd";
    link.click();
    URL.revokeObjectURL(link.href);
    say(t("done.export", { count }));
  } catch (error) {
    say(error.message, true);
  }
}

// ---- rendering: the header, the rail, the footer ----------------------------

function renderAll() {
  if (!state) return;
  ensureCurrent();
  renderHeader();
  renderRail();
  renderInspector();
  renderFooter();
  applyCanvasMode();
  render();
}

function renderHeader() {
  $("page-name").textContent = state.page ? state.page.name : t("header.no_page");
  document.title = state.page ? t("header.title", { page: state.page.name }) : "Luikki";
}

function renderRail() {
  keepFocus(() => {
    $("steps").replaceChildren(...STEPS.map(stepRow));
    $("books").replaceChildren(bookRow("pages"), bookRow("references"), bookRow("palette"), bookRow("account"));
  });
}

function stepRow(step) {
  const status = stepState(step);
  const head = h(
    "button",
    {
      type: "button",
      class: "step-head",
      "data-key": `step-${step.id}`,
      "aria-expanded": String(status === "current"),
      "aria-disabled": status === "locked" ? "true" : null,
      title: status === "locked" ? lockedReason(step.needs) : status === "closed" ? closedReason(step.id) : null,
      onclick: () => pressRow(step, status),
    },
    h("span", { class: "step-num", "aria-hidden": "true" }, status === "done" ? icon("check") : fmt.number(step.number)),
    h("span", { class: "step-name" }, stepName(step.id)),
    h("span", { class: "sr" }, stateName(status)),
    h("span", { class: "step-meta" }, stepMeta(step.id)),
  );
  return h(
    "li",
    { class: "step", "data-state": status },
    head,
    status === "current" ? h("div", { class: "step-body" }, stepBody(step.id)) : null,
  );
}

const note = (text, attention = false) => h("p", { class: attention ? "note attention" : "note" }, text);

function runButton(id, first, again, blocked = null) {
  const done = state.done[id];
  return h(
    "div",
    { class: "row" },
    button(done ? again : first, {
      kind: done ? "" : "primary",
      key: `run-${id}`,
      onclick: () => requestRun(id),
      disabled: blocked !== null,
      why: blocked,
    }),
  );
}

function stepBody(id) {
  const done = state.done;
  switch (id) {
    case "upload":
      return [
        state.page
          ? note(t("upload.page", { name: state.page.name, width: String(state.page.width), height: String(state.page.height) }))
          : note(t("upload.hint")),
        note(t("upload.engine", { extractor: state.extractor, proposer: state.proposer })),
        askBlock("delete"),
        h(
          "div",
          { class: "row" },
          button(state.page ? t("upload.again") : t("upload.run"), {
            kind: "primary",
            key: "run-upload",
            onclick: choosePage,
          }),
          state.page
            ? button(t("upload.delete"), {
                kind: "destructive",
                key: "delete-page",
                onclick: () => askFor("delete", t("confirm.delete_page")),
              })
            : null,
        ),
      ];
    case "panels":
      return [
        askBlock("panels"),
        note(state.editable.panels ? t("hint.panels") : done.panels ? t("closed.panels") : t("about.panels")),
        runButton("panels", t("run.panels"), t("run.panels.again")),
      ];
    case "bubbles":
      return [
        askBlock("bubbles"),
        note(state.editable.bubbles ? t("hint.bubbles") : done.bubbles ? t("closed.bubbles") : t("about.bubbles")),
        runButton("bubbles", t("run.bubbles"), t("run.bubbles.again")),
      ];
    case "zones":
      return [
        askBlock("zones"),
        h(
          "label",
          { class: "field", title: t("zones.gap_tip") },
          h("span", {}, t("zones.gap")),
          h("input", {
            type: "number",
            min: 0,
            max: 100,
            step: 1,
            value: controls.gap,
            "data-key": "gap",
            oninput: (event) => {
              controls.gap = Number(event.target.value);
            },
          }),
        ),
        note(state.editable.zones ? t("hint.zones") : done.zones ? t("closed.zones") : t("about.zones")),
        runButton("zones", t("run.zones"), t("run.zones.again")),
      ];
    case "flats":
      return [
        askBlock("flats"),
        state.flats_stale ? note(t("flats.stale"), true) : null,
        note(done.flats ? t("flats.done", { count: state.segments.count }) : t("about.flats")),
        ...gpuNotes(),
        runButton("flats", t("run.flats"), t("run.flats.again"), gpuBlock()),
      ];
    case "snap": {
      const snappable = state.segments.snappable;
      return [
        note(snappable ? t("snap.hint") : t("snap.no_palette"), !snappable),
        h(
          "label",
          { class: "check" },
          h("input", {
            type: "checkbox",
            checked: controls.ignoreGuard,
            "data-key": "guard",
            onchange: (event) => {
              controls.ignoreGuard = event.target.checked;
              renderRail();
            },
          }),
          h("span", {}, t("snap.ignore_guard")),
        ),
        h(
          "label",
          { class: "field" },
          h("span", {}, t("snap.threshold")),
          h("input", {
            type: "number",
            min: 0,
            step: 0.5,
            value: controls.threshold,
            disabled: controls.ignoreGuard,
            "data-key": "threshold",
            oninput: (event) => {
              controls.threshold = Number(event.target.value);
            },
          }),
        ),
        h(
          "div",
          { class: "row" },
          button(t("run.snap_all"), {
            kind: "primary",
            key: "run-snap",
            disabled: !snappable,
            why: t("snap.no_palette"),
            onclick: snapAll,
          }),
        ),
      ];
    }
    default: {
      const count = exportLayers();
      const heavy = heavyExport();
      return [
        h(
          "label",
          { class: "field" },
          h("span", {}, t("export.layers")),
          h(
            "select",
            {
              "data-key": "granularity",
              onchange: (event) => {
                controls.granularity = event.target.value;
                renderAll();
              },
            },
            h("option", { value: "colour", selected: controls.granularity === "colour" }, t("export.per_colour")),
            h("option", { value: "panel", selected: controls.granularity === "panel" }, t("export.per_panel")),
          ),
        ),
        heavy ? note(t("export.warning", { count }), true) : note(t("export.count", { count })),
        note(t("export.note")),
        h(
          "div",
          { class: "row" },
          button(heavy ? t("run.export.anyway", { count }) : t("run.export"), {
            kind: "primary",
            key: "run-export",
            onclick: exportPsd,
          }),
        ),
      ];
    }
  }
}

function bookName(which) {
  switch (which) {
    case "pages": return t("book.pages");
    case "references": return t("book.references");
    case "account": return t("book.account");
    default: return t("book.palette");
  }
}

function bookMeta(which) {
  switch (which) {
    case "pages": return t("meta.pages", { count: state.pages.length });
    case "references": return t("meta.references", { count: state.references.length });
    case "account": return state.account.email ?? t("meta.signed_out");
    default: return t("meta.colours", { count: paletteColours().length });
  }
}

function bookRow(which) {
  const pressed = shelf === which;
  return h(
    "li",
    {},
    h(
      "button",
      {
        type: "button",
        class: "book",
        "data-key": `book-${which}`,
        "aria-pressed": String(pressed),
        onclick: () => {
          shelf = pressed ? null : which;
          renderRail();
          renderInspector();
        },
      },
      h("span", {}, bookName(which)),
      h("span", { class: "step-meta" }, bookMeta(which)),
    ),
  );
}

function renderFooter() {
  const lines = $("v-lines");
  lines.checked = controls.lines;
  lines.disabled = !layers.lines;
  lines.parentElement.title = layers.lines ? "" : t("toggle.lines_why");
  $("v-neutral").checked = controls.neutral;
  $("v-left").checked = controls.left;
  $("v-left-label").hidden = !(current === "snap" && state.done.flats);
  $("shell").classList.toggle("neutral", controls.neutral);
}

function showZoom() {
  const readout = $("zoom");
  if (!state || !state.page) {
    readout.textContent = "";
    return;
  }
  readout.textContent = zoom > 1.01 ? t("zoom.zoomed", { percent: fmt.percent(zoom * 100) }) : t("zoom.fit");
}

// ---- the inspector (§9) -----------------------------------------------------

function renderInspector() {
  keepFocus(() => {
    const [body, footer] = inspectorContent();
    $("inspector-body").replaceChildren(...body.filter(Boolean));
    $("inspector-footer").replaceChildren(...footer.filter(Boolean));
  });
}

const heading = (text) => h("h2", { class: "ins-title" }, text);
const rgb = (colour) => `rgb(${colour.join(",")})`;
const hex = (colour) => "#" + colour.map((part) => part.toString(16).padStart(2, "0")).join("");
const paletteById = () => new Map(state.palette.map((entry) => [entry.id, entry]));
// The artist's half of the palette. The other half is one private entry per
// segment — hundreds on a real page, and not one a colour anybody chose.
const paletteColours = () => state.palette.filter((entry) => entry.source === "palette");

function inspectorContent() {
  if (!state) return [[], []];
  if (shelf === "pages") return pagesView();
  if (shelf === "references") return referencesView();
  if (shelf === "palette") return paletteView();
  if (shelf === "account") return accountView();
  switch (current) {
    case "upload": return uploadView();
    case "panels":
    case "bubbles": return shapeView();
    case "zones": return zonesView();
    case "flats": return flatsView();
    case "snap": return snapView();
    default: return exportView();
  }
}

function uploadView() {
  if (!state.page) return [[note(t("inspect.upload.empty"))], []];
  return [
    [
      heading(t("inspect.page")),
      h("div", { class: "ins-row" }, h("span", { class: "label" }, state.page.name)),
      h(
        "div",
        { class: "ins-row num" },
        t("inspect.size", { width: String(state.page.width), height: String(state.page.height) }),
      ),
    ],
    [],
  ];
}

function stageName(stage) {
  switch (stage) {
    case "page": return t("pages.stage.page");
    case "panels": return t("pages.stage.panels");
    case "bubbles": return t("pages.stage.bubbles");
    case "zones": return t("pages.stage.zones");
    default: return t("pages.stage.flats");
  }
}

// Every page of the project. The open one is marked and does nothing; any
// other opens as it was left.
function pagesView() {
  const add = button(t("upload.again"), { kind: "primary", key: "pages-add", onclick: choosePage });
  if (!state.pages.length) return [[heading(t("book.pages")), note(t("pages.empty"))], [add]];
  return [
    [
      heading(t("book.pages")),
      note(t("pages.about")),
      ...state.pages.map((page) => {
        const isOpen = page.id === state.page_id;
        return h(
          "button",
          {
            type: "button",
            class: "book",
            "data-key": `page-${page.id}`,
            "aria-pressed": String(isOpen),
            onclick: isOpen ? null : () => openPage(page.id),
          },
          h("span", {}, page.name),
          h("span", { class: "step-meta" }, isOpen ? t("state.current") : stageName(page.stage)),
        );
      }),
    ],
    [add],
  ];
}

// Signing in, by a code sent to the artist's email. Once per computer: the
// session is kept by the server process, in the system's password store, and
// this page only ever holds what is being typed.
let signingIn = { email: "", sent: false, code: "" };

const onEnter = (action) => (event) => {
  if (event.key === "Enter") action();
};

function accountView() {
  if (state.account.email) {
    return [
      [
        heading(t("book.account")),
        note(t("account.signed_in", { email: state.account.email })),
        note(t("account.stays")),
      ],
      [button(t("account.sign_out"), { key: "account-out", onclick: signOut })],
    ];
  }
  const input = (name, label, props) =>
    h(
      "label",
      { class: "field" },
      h("span", {}, label),
      h("input", {
        "data-key": `account-${name}`,
        value: signingIn[name],
        ...props,
        oninput: (event) => {
          signingIn[name] = event.target.value;
        },
      }),
    );
  if (!signingIn.sent) {
    return [
      [
        heading(t("book.account")),
        note(t("account.why")),
        input("email", t("account.email"), { type: "email", autocomplete: "email", onkeydown: onEnter(sendCode) }),
      ],
      [button(t("account.send"), { kind: "primary", key: "account-send", onclick: sendCode })],
    ];
  }
  return [
    [
      heading(t("book.account")),
      note(t("account.sent", { email: signingIn.email })),
      input("code", t("account.code"), {
        type: "text",
        inputmode: "numeric",
        autocomplete: "one-time-code",
        onkeydown: onEnter(signIn),
      }),
    ],
    [
      button(t("account.sign_in"), { kind: "primary", key: "account-in", onclick: signIn }),
      button(t("account.resend"), { key: "account-resend", onclick: sendCode }),
      button(t("account.other_email"), {
        kind: "quiet",
        key: "account-other",
        onclick: () => {
          signingIn = { email: signingIn.email, sent: false, code: "" };
          renderInspector();
        },
      }),
    ],
  ];
}

function openAccount() {
  shelf = "account";
  renderRail();
  renderInspector();
}

// What step 5 will meet on the GPU server, asked before it is pressed:
// `/api/account/status`. null until known, and unknown is never a refusal —
// an account server that does not answer is no reason to stop an artist
// whose subscription is fine. The GPU server decides at the press either way.
let gpu = null;

async function refreshGpu() {
  if (!state || state.proposer !== "remote") {
    gpu = null;
    return;
  }
  try {
    gpu = await call("/api/account/status");
  } catch {
    gpu = null;
  }
  renderRail();
}

// Why the GPU server would refuse step 5, or null.
function gpuBlock() {
  if (!gpu || !gpu.remote) return null;
  if (gpu.needs_sign_in) return t("flats.sign_in");
  const quota = gpu.quota;
  if (!quota) return null;
  if (!quota.active) return t("flats.no_subscription");
  if (quota.pages_per_month === null) return null;
  if (quota.page_counted) {
    return quota.page_generations >= quota.generations_per_page ? t("flats.page_out") : null;
  }
  return quota.pages_used >= quota.pages_per_month ? t("flats.quota_out") : null;
}

function gpuNotes() {
  if (!gpu || !gpu.remote) return [];
  const blocked = gpuBlock();
  if (blocked) {
    return [
      note(blocked, true),
      gpu.needs_sign_in
        ? h("div", { class: "row" }, button(t("account.sign_in"), { key: "flats-sign-in", onclick: openAccount }))
        : null,
    ];
  }
  const quota = gpu.quota;
  if (gpu.signed_in && !quota) return [note(t("flats.quota_unknown"))];
  if (!quota || quota.pages_per_month === null) return [];
  if (quota.page_counted) {
    return [note(t("flats.page_counted", { count: quota.generations_per_page - quota.page_generations }))];
  }
  return [
    note(t("flats.pages_left", { count: quota.pages_per_month - quota.pages_used, limit: quota.pages_per_month })),
  ];
}

function accountCall(label, path, method, body) {
  return working(label, false, () =>
    call(path, {
      method,
      headers: { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  );
}

async function sendCode() {
  const email = signingIn.email.trim();
  try {
    state = await accountCall(t("work.send_code"), "/api/account/code", "POST", { email });
    signingIn = { email, sent: true, code: "" };
    renderAll();
    say(t("status.code_sent", { email }));
  } catch (error) {
    renderAll();
    say(error.message, true);
  }
}

async function signIn() {
  const body = { email: signingIn.email.trim(), code: signingIn.code.trim() };
  try {
    state = await accountCall(t("work.sign_in"), "/api/account", "POST", body);
    signingIn = { email: "", sent: false, code: "" };
    renderAll();
    say(t("status.signed_in", { email: state.account.email }));
    refreshGpu();
  } catch (error) {
    renderAll();
    say(error.message, true);
  }
}

async function signOut() {
  try {
    state = await accountCall(t("work.sign_out"), "/api/account", "DELETE");
    renderAll();
    say(t("status.signed_out"));
    refreshGpu();
  } catch (error) {
    renderAll();
    say(error.message, true);
  }
}

function shapeView() {
  const panels = current === "panels";
  if (!state.done[current]) {
    return [[note(panels ? t("inspect.panels.not_run") : t("inspect.bubbles.not_run"))], []];
  }
  if (!state.editable[current]) return [[note(closedReason(current))], []];
  const polygons = shapes();
  if (shapeSelected === null || !polygons[shapeSelected]) {
    return [[note(panels ? t("inspect.panels.empty") : t("inspect.bubbles.empty"))], []];
  }
  const index = shapeSelected;
  return [
    [
      heading(
        panels
          ? t("inspect.panel", { number: state.panels[index].order + 1 })
          : t("inspect.bubble", { number: index + 1 }),
      ),
      h("div", { class: "ins-row num" }, t("inspect.corners", { count: polygons[index].length })),
    ],
    [
      button(panels ? t("inspect.panel.delete") : t("inspect.bubble.delete"), {
        kind: "destructive",
        key: "delete-shape",
        onclick: () => deleteShape(index),
      }),
    ],
  ];
}

function zonesView() {
  if (!state.done.zones) return [[note(t("inspect.zones.not_run"))], []];
  if (!state.editable.zones) return [[note(t("closed.zones"))], []];
  if (cutting) {
    return [
      [note(t("inspect.zones.cutting"))],
      [button(t("inspect.zones.stop_cut"), { kind: "quiet", key: "stop-cut", onclick: stopCut })],
    ];
  }
  if (!picked.size) return [[note(t("inspect.zones.empty"))], []];
  const zones = [...picked.values()];
  const measured = zones.every((zone) => zone.trace);
  const area = zones.reduce((sum, zone) => sum + (zone.trace ? zone.trace.area : 0), 0);
  return [
    [
      heading(t("inspect.zones.selected", { count: picked.size })),
      h("div", { class: "ins-row num" }, measured ? t("inspect.area", { count: area }) : t("inspect.area.measuring")),
    ],
    [
      button(t("inspect.zones.merge"), {
        key: "merge",
        disabled: picked.size < 2,
        why: t("inspect.zones.merge_why"),
        onclick: mergePicked,
      }),
      button(t("inspect.zones.cut"), {
        key: "cut",
        disabled: picked.size !== 1,
        why: t("inspect.zones.cut_why"),
        onclick: startCut,
      }),
      button(t("inspect.zones.clear"), { kind: "quiet", key: "clear", onclick: clearPicked }),
    ],
  ];
}

function flatsView() {
  if (!state.done.flats) return [[note(t("inspect.flats.not_run"))], []];
  const { count, snapped } = state.segments;
  return [
    [
      heading(t("inspect.flats.title")),
      h("div", { class: "ins-row num" }, t("inspect.flats.segments", { count })),
      h("div", { class: "ins-row num" }, t("inspect.flats.private", { count: count - snapped })),
    ],
    [],
  ];
}

// Choosing a colour other than the suggestion opens the palette under it.
let choosing = false;

function snapView() {
  if (!state.done.flats) return [[note(t("inspect.flats.not_run"))], []];
  if (!selected) return [[note(t("inspect.snap.empty"))], []];

  const holding = paletteById().get(selected.palette_entry_id);
  const suggestion = selected.suggestion;
  // Measured against what the segment holds now, so after a snap the nearest
  // colour is that same colour at ΔE 0. Saying so beats offering a zero.
  const taken = Boolean(suggestion) && suggestion.palette_entry_id === selected.palette_entry_id;
  const colours = paletteColours();

  const body = [
    // A label is a name, not a quantity: no digit grouping.
    heading(t("inspect.snap.title", { panel: selected.panel + 1, zone: String(selected.label) })),
    h("div", { class: "ins-row num" }, t("inspect.area", { count: selected.area })),
    note(selected.snapped ? t("inspect.snap.by_you") : t("inspect.snap.by_model")),
    h(
      "div",
      { class: "ins-row" },
      h("i", { class: "ins-swatch", style: { background: holding ? rgb(holding.rgb) : "transparent" } }),
      h(
        "span",
        { class: "label" },
        !holding
          ? t("inspect.snap.no_colour")
          : holding.source === "proposed"
            ? t("inspect.snap.proposed")
            : t("inspect.snap.held", { name: holding.label }),
      ),
    ),
  ];

  if (suggestion) {
    const delta = fmt.number(suggestion.delta, 1);
    body.push(
      h(
        "div",
        { class: "ins-row" },
        h("i", { class: "ins-swatch", style: { background: rgb(suggestion.rgb) } }),
        h("span", { class: "label" }, t("inspect.snap.nearest")),
      ),
      // The number the old automatic pass decided on in silence. It orders the
      // artist's attention; it refuses nothing (§9).
      taken
        ? note(t("inspect.snap.taken"))
        : h(
            "p",
            { class: suggestion.within_threshold ? "note num delta" : "note num delta far" },
            suggestion.within_threshold
              ? t("inspect.snap.delta_close", { delta })
              : t("inspect.snap.delta_far", { delta }),
          ),
    );
  } else {
    body.push(note(t("inspect.snap.no_suggestion")));
  }

  if (choosing && colours.length) {
    body.push(
      h(
        "div",
        { class: "swatches" },
        colours.map((entry) =>
          h(
            "button",
            {
              type: "button",
              class: "swatch",
              "data-key": `pick-${entry.id}`,
              "aria-pressed": String(entry.id === selected.palette_entry_id),
              title: entry.label,
              onclick: () => snapSelected(entry.id),
            },
            h("i", { style: { background: rgb(entry.rgb) } }),
            h("span", {}, String(entry.id)),
          ),
        ),
      ),
    );
  }

  return [
    body,
    [
      button(t("inspect.snap.snap"), {
        key: "snap",
        disabled: !suggestion || taken,
        why: taken ? t("inspect.snap.taken") : t("inspect.snap.no_suggestion"),
        onclick: () => snapSelected(),
      }),
      button(t("inspect.snap.pick"), {
        key: "pick",
        disabled: !colours.length,
        why: t("snap.no_palette"),
        pressed: choosing,
        onclick: () => {
          choosing = !choosing;
          renderInspector();
        },
      }),
      button(t("inspect.snap.unsnap"), {
        kind: "quiet",
        key: "unsnap",
        disabled: !selected.snapped,
        why: t("inspect.snap.not_snapped"),
        onclick: unsnapSelected,
      }),
    ],
  ];
}

function exportView() {
  if (!state.done.flats) return [[note(t("inspect.flats.not_run"))], []];
  return [
    [
      heading(t("inspect.export.title")),
      h("div", { class: "ins-row num" }, t("inspect.export.per_colour", { count: state.export.layers.colour ?? 0 })),
      h("div", { class: "ins-row num" }, t("inspect.export.per_panel", { count: state.export.layers.panel ?? 0 })),
    ],
    [],
  ];
}

function kindName(kind) {
  switch (kind) {
    case "sheet": return t("kind.sheet");
    case "page": return t("kind.page");
    case "panel": return t("kind.panel");
    default: return kind;
  }
}

// A reference is an image: the model is shown it, and colours are found in
// it. The palette is the artist's list, and nothing lands in it without a
// click. The chips under a thumbnail are that click.
function referencesView() {
  const body = [heading(t("book.references"))];
  if (!state.references.length) {
    body.push(note(t("refs.empty")));
  } else {
    body.push(
      note(t("refs.about")),
      h(
        "div",
        { class: "refs" },
        state.references.map((reference) =>
          h(
            "figure",
            { class: "ref" },
            h("img", { src: `/api/reference/${reference.id}.png`, alt: reference.label }),
            h(
              "figcaption",
              {},
              h(
                "div",
                { class: "ref-head" },
                h("span", {}, kindName(reference.kind)),
                button(icon("close"), {
                  kind: "quiet icon",
                  key: `remove-ref-${reference.id}`,
                  label: t("refs.remove", { name: reference.label }),
                  onclick: () => removeReference(reference.id, false),
                }),
              ),
              h("div", { class: "ref-name" }, reference.label),
              h("div", { class: "chips" }, reference.candidates.map((candidate) => chip(reference, candidate))),
            ),
          ),
        ),
      ),
    );
  }
  return [
    body,
    [
      h(
        "select",
        {
          "aria-label": t("refs.kind"),
          "data-key": "ref-kind",
          onchange: (event) => {
            controls.refKind = event.target.value;
          },
        },
        h("option", { value: "sheet", selected: controls.refKind === "sheet" }, t("kind.sheet")),
        h("option", { value: "page", selected: controls.refKind === "page" }, t("kind.page")),
        h("option", { value: "panel", selected: controls.refKind === "panel" }, t("kind.panel")),
      ),
      button(t("refs.add"), { key: "add-ref", onclick: () => $("ref-file").click() }),
    ],
  ];
}

function chip(reference, candidate) {
  const taken = candidate.entry_id !== null;
  const label = taken ? t("chip.remove") : t("chip.add");
  return h(
    "button",
    {
      type: "button",
      class: "chip",
      "aria-pressed": String(taken),
      "aria-label": label,
      title: label,
      style: { background: rgb(candidate.rgb) },
      onclick: () => (taken ? dropColour(candidate.entry_id) : takeColour(reference.id, candidate.rgb)),
    },
    taken ? tick() : null,
  );
}

// The id under a swatch never changes, whatever colour it holds — that is what
// makes "change the hair colour everywhere" one row (rule 1), and the
// interface shows it.
let entrySelected = null;

function paletteView() {
  const colours = paletteColours();
  const body = [heading(t("book.palette")), note(colours.length ? t("palette.about") : t("palette.empty"))];
  if (colours.length) {
    body.push(
      h(
        "div",
        { class: "swatches" },
        colours.map((entry) =>
          h(
            "button",
            {
              type: "button",
              class: "swatch",
              "data-key": `swatch-${entry.id}`,
              "aria-pressed": String(entry.id === entrySelected),
              title: entry.label,
              onclick: () => {
                entrySelected = entry.id === entrySelected ? null : entry.id;
                renderInspector();
              },
            },
            h("i", { style: { background: rgb(entry.rgb) } }),
            h("span", {}, String(entry.id)),
          ),
        ),
      ),
    );
  }
  const entry = colours.find((candidate) => candidate.id === entrySelected);
  if (entry) {
    body.push(
      h(
        "div",
        { class: "editor" },
        h(
          "label",
          { class: "field" },
          h("span", {}, t("palette.colour", { id: String(entry.id) })),
          h("input", {
            type: "color",
            value: hex(entry.rgb),
            "data-key": "recolour",
            onchange: (event) => recolour(entry.id, event.target.value),
          }),
        ),
        h(
          "div",
          { class: "row" },
          button(t("palette.remove"), {
            kind: "destructive",
            key: "remove-colour",
            onclick: () => dropColour(entry.id),
          }),
        ),
      ),
    );
  }
  if (state.palettes.length) {
    body.push(
      h("h3", { class: "ins-sub" }, t("palette.images")),
      h(
        "div",
        { class: "refs" },
        state.palettes.map((image) =>
          h(
            "figure",
            { class: "ref strip" },
            h("img", { src: `/api/reference/${image.id}.png`, alt: image.label }),
            h(
              "figcaption",
              {},
              h(
                "div",
                { class: "ref-head" },
                h("span", { class: "num" }, t("palette.image_colours", { count: image.colours.length })),
                button(icon("close"), {
                  kind: "quiet icon",
                  key: `remove-pal-${image.id}`,
                  label: t("palette.image_remove", { name: image.label }),
                  onclick: () => removeReference(image.id, true),
                }),
              ),
              h("div", { class: "ref-name" }, image.label),
            ),
          ),
        ),
      ),
    );
  }
  return [body, [button(t("palette.add_image"), { key: "add-palette", onclick: () => $("pal-file").click() })]];
}

// ---- the palette and the references, over the wire --------------------------

async function takeColour(referenceId, colour) {
  try {
    await adopt(
      await call("/api/palette", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ reference_id: referenceId, rgb: colour }),
      }),
    );
    say(t("status.colour_added"));
  } catch (error) {
    say(error.message, true);
  }
}

async function dropColour(entryId) {
  try {
    if (entrySelected === entryId) entrySelected = null;
    await adopt(await call(`/api/palette/${entryId}`, { method: "DELETE" }));
    say(t("status.colour_removed"));
  } catch (error) {
    say(error.message, true);
  }
}

// Changing a colour here changes it on every zone holding that entry: one row,
// the whole page (rule 1).
async function recolour(entryId, value) {
  const colour = [1, 3, 5].map((at) => parseInt(value.slice(at, at + 2), 16));
  try {
    await adopt(
      await call(`/api/palette/${entryId}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ rgb: colour }),
      }),
    );
    say(t("status.colour_changed"));
  } catch (error) {
    say(error.message, true);
  }
}

// Deleting a reference deletes the image, not the colours taken from it; the
// flats go stale all the same, because they came from an image now gone.
async function removeReference(id, palette) {
  try {
    await adopt(await call(`/api/reference/${id}`, { method: "DELETE" }));
    say(palette ? t("done.palette_removed") : t("done.reference_removed"));
  } catch (error) {
    say(error.message, true);
  }
}

$("ref-file").addEventListener("change", async () => {
  const next = await uploadFile($("ref-file"), "/api/reference", t("work.reference"), {
    kind: controls.refKind,
  });
  if (!next) return;
  shelf = "references";
  await adopt(next);
  // A finished page is kept whole and cut into its panels: one press, several
  // references, and the count is the honest answer.
  say(
    next.result.panels
      ? t("done.reference.page", { count: next.result.panels })
      : t("done.reference", { kind: kindName(next.result.kind) }),
  );
});

$("pal-file").addEventListener("change", async () => {
  const next = await uploadFile($("pal-file"), "/api/palette/image", t("work.palette"));
  if (!next) return;
  shelf = "palette";
  await adopt(next);
  say(t("done.palette"));
});

// ---- the canvas: what each step shows ---------------------------------------

function shows() {
  const colour = current === "flats" || current === "snap" || current === "export";
  return {
    zones: current === "zones" || (current === "flats" && !state.done.flats),
    flats: colour,
    panels: current === "panels" || current === "bubbles" || current === "zones",
    bubbles: current === "bubbles" || current === "zones",
    left: current === "snap" && controls.left,
  };
}

// Which geometry the pointer corrects: the open step's, while it is still open
// to correction. Nothing else on the canvas takes a click.
function activeLayer() {
  if (!state || !state.page) return null;
  return CORRECTED.includes(current) && state.editable[current] ? current : null;
}

const picking = () => Boolean(state && current === "snap" && state.done.flats);

function applyCanvasMode() {
  const editing = Boolean(activeLayer());
  stage.classList.toggle("editing", editing);
  stage.classList.toggle("pickable", picking());
  if (!editing) stage.classList.remove("on-corner", "on-edge");
}

function resize() {
  const ratio = window.devicePixelRatio || 1;
  stage.width = Math.round(stage.clientWidth * ratio);
  stage.height = Math.round(stage.clientHeight * ratio);
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  render();
}

function render() {
  ctx.clearRect(0, 0, stage.clientWidth, stage.clientHeight);
  showZoom();
  if (!state || !state.page) return;

  applyView();
  const page = state.page;
  const box = [view.ox, view.oy, page.width * view.scale, page.height * view.scale];
  const show = shows();

  // Past 1:1 the artist is inspecting ink, and interpolation turns a hard edge
  // into a smear. Magnified, draw the pixels.
  ctx.imageSmoothingEnabled = view.scale <= 1;

  ctx.fillStyle = PAPER;
  ctx.fillRect(...box);

  // Colour underneath, ink on top — the order the artist works in and the
  // order the PSD stacks in. A colourist cannot judge a colour without the
  // lines that bound it.
  if (layers.zones && show.zones) ctx.drawImage(layers.zones, ...box);
  if (layers.flats && show.flats) ctx.drawImage(layers.flats, ...box);

  // Multiply is what makes ink over colour behave like ink: black stays black,
  // paper drops out, grey holds its weight.
  ctx.globalCompositeOperation = "multiply";
  if (layers.page) ctx.drawImage(layers.page, ...box);
  // What segmentation actually saw, against the artist's own ink.
  if (layers.lines && controls.lines) ctx.drawImage(layers.lines, ...box);
  ctx.globalCompositeOperation = "source-over";

  if (layers.left && show.left) ctx.drawImage(layers.left, ...box);

  // The page border: 1px, no shadow, no gradient (§10).
  ctx.save();
  ctx.strokeStyle = tokens.edge;
  ctx.lineWidth = 1;
  ctx.strokeRect(Math.round(box[0]) - 0.5, Math.round(box[1]) - 0.5, Math.round(box[2]) + 1, Math.round(box[3]) + 1);
  ctx.restore();

  const editing = activeLayer();
  if (show.bubbles) {
    state.protected.forEach((polygon, index) =>
      outline(polygon, DASH.protected, editing === "bubbles" && shapeSelected === index, tokens.bubble),
    );
  }
  if (show.panels) {
    state.panels.forEach((panel, index) =>
      outline(panel.polygon, [], editing === "panels" && shapeSelected === index, tokens.panel),
    );
    for (const panel of state.panels) panelNumber(panel);
  }

  drawHandles(editing);
  drawDraft(editing);
  if (editing === "zones") drawPicked();
  if (picking()) drawSegment();
  startMarching();
}

// ---- lines on the artwork (§11) ---------------------------------------------
//
// A coloured line on a comic page competes with the drawing and shifts the
// colour being judged, so every line here carries luminance, not hue: the
// same path twice, dark underneath and light on top, which stays visible on
// white paper and on a spot black alike.

const DASH = { protected: [6, 4], selected: [4, 4], cut: [6, 4] };

function strokeTwice(dash = [], offset = 0, under = 3, over = 1.5, colours = [tokens.dark, tokens.light]) {
  ctx.save();
  ctx.lineJoin = "round";
  ctx.setLineDash(dash);
  ctx.lineDashOffset = offset;
  ctx.strokeStyle = colours[0];
  ctx.lineWidth = under;
  ctx.stroke();
  ctx.strokeStyle = colours[1];
  ctx.lineWidth = over;
  ctx.stroke();
  ctx.restore();
}

function tracePath(points, close) {
  points.forEach(([px, py], index) => {
    const [x, y] = view.toScreen(px, py);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  if (close) ctx.closePath();
}

// A selected shape marches; the rest stand still. Panels and balloons break
// §11 on Raph's call: grey is lost in black-and-white ink, so they draw a deep
// hue over a light halo, which still holds on a spot black.
function outline(polygon, dash, selectedShape, colour) {
  if (polygon.length < 2) return;
  ctx.beginPath();
  tracePath(polygon, true);
  strokeTwice(selectedShape ? DASH.selected : dash, selectedShape ? -marching : 0, 4, 2, [tokens.light, colour]);
}

function panelNumber(panel) {
  const [x, y] = view.toScreen(panel.polygon[0][0], panel.polygon[0][1]);
  const label = fmt.number(panel.order + 1);
  ctx.save();
  ctx.font = `600 12px ${tokens.font}`;
  const width = Math.max(18, ctx.measureText(label).width + 8);
  ctx.globalAlpha = 0.8;
  ctx.fillStyle = tokens.chip;
  ctx.fillRect(x + 4, y + 4, width, 18);
  ctx.globalAlpha = 1;
  ctx.fillStyle = tokens.chipText;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(label, x + 4 + width / 2, y + 13);
  ctx.restore();
}

// A corner is a thing the hand grabs, so it reads as a square. The one under
// the pointer takes the action colour: under 100 square pixels, it cannot
// shift the page, and the artist has to find it (§11's first exception).
function handle(x, y, under) {
  ctx.fillStyle = under ? tokens.ring : tokens.light;
  ctx.fillRect(Math.round(x) - 4, Math.round(y) - 4, 8, 8);
  ctx.strokeStyle = tokens.dark;
  ctx.lineWidth = 1;
  ctx.strokeRect(Math.round(x) - 4.5, Math.round(y) - 4.5, 9, 9);
}

let hover = null; // {index, corner} — the corner under the pointer

function drawHandles(editing) {
  if (!editing || editing === "zones" || draft) return;
  ctx.save();
  shapes().forEach((polygon, index) =>
    polygon.forEach(([px, py], corner) => {
      const [x, y] = view.toScreen(px, py);
      handle(x, y, Boolean(hover) && hover.index === index && hover.corner === corner);
    }),
  );
  ctx.restore();
}

// The polygon being drawn: what has been placed, a rubber band to the pointer,
// and a ring on the first corner once clicking it would close the shape.
function drawDraft(editing) {
  if (!draft || !editing) return;
  const points = cursor ? [...draft.points, cursor] : draft.points;
  ctx.beginPath();
  tracePath(points, false);
  strokeTwice();
  ctx.save();
  for (const [px, py] of draft.points) {
    const [x, y] = view.toScreen(px, py);
    handle(x, y, false);
  }
  ctx.restore();
  if (draft.points.length >= 3) {
    const [x, y] = view.toScreen(draft.points[0][0], draft.points[0][1]);
    ctx.beginPath();
    ctx.arc(x, y, 9, 0, Math.PI * 2);
    strokeTwice();
  }
}

// ---- zone outlines, traced from the masks -----------------------------------
//
// The server sends one zone as a cropped mask (`/api/zone/{panel}/{label}.png`).
// Its outline is traced here along pixel edges, so a selection is drawn as a
// line around the zone rather than a hue over it — the artist is looking at
// that zone's colour (§11). The same pass counts its pixels, which is the
// area the inspector shows.

const key = (panel, label) => `${panel}:${label}`;
const traces = new Map(); // "panel:label" -> Promise<{loops, area} | null>

function traceOf(panel, label) {
  const at = key(panel, label);
  if (!traces.has(at)) {
    traces.set(at, loadImage(`/api/zone/${panel}/${label}.png`).then((image) => image && traceMask(image)));
  }
  return traces.get(at);
}

function traceMask(image) {
  const width = image.naturalWidth;
  const height = image.naturalHeight;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const paint = canvas.getContext("2d", { willReadFrequently: true });
  paint.drawImage(image, 0, 0);
  const alpha = paint.getImageData(0, 0, width, height).data;
  const inside = (x, y) => x >= 0 && y >= 0 && x < width && y < height && alpha[(y * width + x) * 4 + 3] > 0;

  // Every edge between an inside pixel and an outside one, directed clockwise
  // around the inside, keyed by the vertex it starts from.
  const stride = width + 1;
  const edges = new Map();
  const edge = (x0, y0, x1, y1) => {
    const from = y0 * stride + x0;
    const to = y1 * stride + x1;
    const list = edges.get(from);
    if (list) list.push(to);
    else edges.set(from, [to]);
  };
  let area = 0;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (!inside(x, y)) continue;
      area++;
      if (!inside(x, y - 1)) edge(x, y, x + 1, y);
      if (!inside(x + 1, y)) edge(x + 1, y, x + 1, y + 1);
      if (!inside(x, y + 1)) edge(x + 1, y + 1, x, y + 1);
      if (!inside(x - 1, y)) edge(x, y + 1, x, y);
    }
  }

  // Chained into closed loops, keeping only the corners.
  const loops = [];
  for (const start of [...edges.keys()]) {
    while (edges.has(start)) {
      const vertices = [];
      let at = start;
      do {
        const list = edges.get(at);
        const next = list.pop();
        if (!list.length) edges.delete(at);
        vertices.push(at);
        at = next;
      } while (at !== start && edges.has(at));
      loops.push(corners(vertices, stride));
    }
  }
  return { loops, area };
}

function corners(vertices, stride) {
  const points = vertices.map((vertex) => [vertex % stride, Math.floor(vertex / stride)]);
  return points.filter((point, index) => {
    const before = points[(index + points.length - 1) % points.length];
    const after = points[(index + 1) % points.length];
    const straight =
      (before[0] === point[0] && point[0] === after[0]) || (before[1] === point[1] && point[1] === after[1]);
    return !straight;
  });
}

function traceZone(zone) {
  const [left, top] = zone.bounds;
  for (const loop of zone.trace.loops) {
    tracePath(
      loop.map(([x, y]) => [left + x, top + y]),
      true,
    );
  }
}

// ---- marching selection -----------------------------------------------------

const calm = window.matchMedia("(prefers-reduced-motion: reduce)");
let marching = 0;
let frame = null;
let lastMarch = 0;

function selectionShown() {
  const editing = activeLayer();
  if (editing === "zones") return picked.size > 0;
  if (editing === "panels" || editing === "bubbles") return shapeSelected !== null;
  return picking() && Boolean(selected && selected.trace);
}

function march(time) {
  if (calm.matches || !selectionShown()) {
    frame = null;
    return;
  }
  frame = requestAnimationFrame(march);
  if (time - lastMarch > 80) {
    lastMarch = time;
    marching = (marching + 1) % 8;
    render();
  }
}

// The artist started the selection, so it may move (§15); it stops the moment
// there is none, and never moves at all under reduced motion.
function startMarching() {
  if (!frame && !calm.matches && selectionShown()) frame = requestAnimationFrame(march);
}

// ---- steps 2 and 3: correcting the geometry ---------------------------------
//
// The detector proposes panels and balloons; this is how the artist disagrees
// with it. Drag a corner, click an edge to add one, click inside a shape to
// select it, click outside every shape to draw a new one — Shift-click draws
// even inside one. Right-click is the destructive half, and it always names
// what it is about to destroy.
//
// Every change is sent as the whole polygon. "Corner 3 of panel 2 moved here"
// would be a second description of the shape, and the two go out of step the
// first time a corner is inserted mid-drag.

// How near a corner or an edge must be, in screen pixels: the target stays the
// same size to the hand whatever the page is scaled to.
const HANDLE = 8;
const EDGE = 6;

let drag = null; // {index, corner, dirty}
let draft = null; // {points: [[x, y], …]}
let cursor = null; // the pointer, for the rubber band
let shapeSelected = null; // index into shapes()

function shapes() {
  const which = activeLayer();
  if (which === "panels") return state.panels.map((panel) => panel.polygon);
  if (which === "bubbles") return state.protected;
  return [];
}

function shapePath(index) {
  return activeLayer() === "panels" ? `/api/panel/${state.panels[index].order}` : `/api/bubble/${index}`;
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
      // Clamped to the edge's ends, so the corners keep their own hit test.
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

function selectShape(index) {
  if (shapeSelected === index) return;
  shapeSelected = index;
  renderInspector();
  render();
}

function forgetCanvasSelection() {
  draft = null;
  drag = null;
  cursor = null;
  hover = null;
  shapeSelected = null;
  picked.clear();
  sweep = null;
  cutting = null;
  selected = null;
  choosing = false;
  closeMenu();
}

async function saveShape(index) {
  const which = activeLayer();
  const polygon = shapes()[index];
  try {
    await adopt(
      await call(shapePath(index), {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ polygon }),
      }),
    );
    edits[which] = bump(edits[which]);
    say(which === "panels" ? t("status.panel_saved") : t("status.bubble_saved"));
  } catch (error) {
    // The local copy is now a shape the server refused: re-read it rather than
    // leave the screen describing something that does not exist.
    await adopt(await call("/api/state"));
    say(error.message, true);
  }
}

async function deleteCorner({ index, corner }) {
  // A triangle has no smaller shape to become. Taking a corner off it is the
  // artist saying the detection is wrong, so the whole shape goes.
  if (shapes()[index].length <= 3) return deleteShape(index);
  shapes()[index].splice(corner, 1);
  await saveShape(index);
}

async function deleteShape(index) {
  const which = activeLayer();
  try {
    await adopt(await call(shapePath(index), { method: "DELETE" }));
    shapeSelected = null;
    edits[which] = bump(edits[which]);
    renderInspector();
    say(which === "panels" ? t("status.panel_deleted") : t("status.bubble_deleted"));
  } catch (error) {
    say(error.message, true);
  }
}

function startDraft(point) {
  draft = { points: [point] };
  render();
  say(activeLayer() === "panels" ? t("status.drawing_panel") : t("status.drawing_bubble"));
}

function discardDraft() {
  draft = null;
  cursor = null;
  render();
  say(t("status.draw_stopped"));
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
      }),
    );
    edits[which] = bump(edits[which]);
    say(which === "panels" ? t("status.panel_added") : t("status.bubble_added"));
  } catch (error) {
    render();
    say(error.message, true);
  }
}

// ---- step 4: zones the artist corrects --------------------------------------
//
// Trapped-ball leaks a garment into the background wherever the ink is open,
// and returns forty scraps wherever the drawing is busy. Merging and cutting
// are the corrections, and they happen between the cut and the colour because
// they are permanent: there is no unmerge.
//
// One rule runs the selection: a zone is selected while the button is pressed
// over it. A press toggles one; holding and moving adds everything the pointer
// passes over; two zones apart take two presses and nothing in between.

const picked = new Map(); // "panel:label" -> {panel, label, bounds, trace}
let sweep = null; // {points, sent} while the button is down
let cutting = null; // {panel, label, stroke} after "Cut"

function rememberZone(zone) {
  const at = key(zone.panel, zone.label);
  if (picked.has(at)) return;
  const entry = { ...zone, trace: null };
  picked.set(at, entry);
  traceOf(zone.panel, zone.label).then((trace) => {
    entry.trace = trace;
    if (picked.get(at) === entry) {
      renderInspector();
      render();
    }
  });
}

function clearPicked() {
  picked.clear();
  renderInspector();
  render();
}

async function pressZone(x, y) {
  try {
    const zone = await call(`/api/zone?x=${Math.round(x)}&y=${Math.round(y)}`);
    const at = key(zone.panel, zone.label);
    if (picked.has(at)) picked.delete(at);
    else rememberZone(zone);
    say(t("status.zone_selected", { count: picked.size }));
  } catch {
    say(t("status.no_zone"));
  }
  renderInspector();
  render();
}

// The sweep goes to the server as a path rather than as a hit test per mouse
// move: one request knows every zone the stroke crossed, including the ones
// that fell between two samples.
async function sweptZones(points) {
  try {
    const found = await call("/api/zones/along", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ points }),
    });
    for (const zone of found.zones) rememberZone(zone);
    if (found.zones.length) say(t("status.zone_selected", { count: picked.size }));
  } catch (error) {
    say(error.message, true);
  }
  renderInspector();
  render();
}

function drawPicked() {
  const zones = [...picked.values()].filter((zone) => zone.trace);
  if (zones.length) {
    ctx.beginPath();
    for (const zone of zones) traceZone(zone);
    // Several zones also take a white wash, so a sweep reads as one body.
    if (picked.size > 1) {
      ctx.fillStyle = tokens.wash;
      ctx.fill("evenodd");
    }
    strokeTwice(DASH.selected, -marching);
  }
  if (cutting && cutting.stroke.length) {
    ctx.beginPath();
    tracePath(cutting.stroke, false);
    strokeTwice(DASH.cut, 0, 4, 2);
  }
}

async function mergePicked() {
  const zones = [...picked.values()];
  const panel = zones[0].panel;
  if (zones.some((zone) => zone.panel !== panel)) {
    say(t("error.merge_panels"), true);
    return;
  }
  try {
    const next = await call("/api/zones/merge", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ panel, labels: zones.map((zone) => zone.label) }),
    });
    picked.clear();
    traces.clear();
    if (edits.zones) edits.zones.merges++;
    await adopt(next);
    say(t("status.merged", { count: next.result.merged }));
  } catch (error) {
    say(error.message, true);
  }
}

function startCut() {
  const [zone] = [...picked.values()];
  cutting = { panel: zone.panel, label: zone.label, stroke: [] };
  renderInspector();
  say(t("status.cut_draw"));
}

function stopCut() {
  cutting = null;
  renderInspector();
  render();
  say(t("status.cut_stopped"));
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
    traces.clear();
    if (edits.zones) edits.zones.cuts++;
    await adopt(next);
    say(t("status.cut", { count: next.result.pieces }));
  } catch (error) {
    // The zone is untouched, so the selection still means something.
    renderInspector();
    render();
    say(error.message, true);
  }
}

// ---- step 6: one segment at a time ------------------------------------------

let selected = null; // the /api/segment payload, plus its traced outline

async function pickSegment(x, y) {
  choosing = false;
  try {
    selected = await call(`/api/segment?x=${Math.round(x)}&y=${Math.round(y)}`);
    attachTrace(selected);
  } catch {
    selected = null;
    say(t("status.no_zone"));
  }
  renderInspector();
  render();
}

function attachTrace(segment) {
  traceOf(segment.panel, segment.label).then((trace) => {
    segment.trace = trace;
    if (selected === segment) render();
  });
}

function drawSegment() {
  if (!selected || !selected.trace) return;
  ctx.beginPath();
  traceZone(selected);
  strokeTwice(DASH.selected, -marching);
}

// A snap changes one row, but the flats raster and the counts derive from it,
// so both are re-read rather than patched here.
async function afterSegmentChange(message) {
  state = await call("/api/state");
  const [flats, left] = await Promise.all([loadImage("/api/flats.png"), loadImage("/api/unsnapped.png")]);
  layers.flats = flats;
  layers.left = luminanceOnly(left);
  renderAll();
  say(message);
}

async function snapSelected(entryId) {
  if (!selected) return;
  const { panel, label, trace } = selected;
  const query = entryId === undefined ? "" : `?entry_id=${entryId}`;
  try {
    selected = { ...(await call(`/api/segment/${panel}/${label}/snap${query}`, { method: "POST" })), trace };
    choosing = false;
    await afterSegmentChange(t("status.snapped", { zone: String(label) }));
  } catch (error) {
    say(error.message, true);
  }
}

async function unsnapSelected() {
  if (!selected) return;
  const { panel, label, trace } = selected;
  try {
    selected = { ...(await call(`/api/segment/${panel}/${label}/unsnap`, { method: "POST" })), trace };
    await afterSegmentChange(t("status.unsnapped", { zone: String(label) }));
  } catch (error) {
    say(error.message, true);
  }
}

// ---- pointer ----------------------------------------------------------------

stage.addEventListener("pointerdown", (event) => {
  if (event.button !== 0 || !state || !state.page) return;
  closeMenu();
  const which = activeLayer();
  if (!which) return;
  const [sx, sy] = local(event);
  const point = onPage(view.toImage(sx, sy));

  if (which === "zones") {
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
    selectShape(corner.index);
    drag = { index: corner.index, corner: corner.corner, dirty: false };
    stage.setPointerCapture(event.pointerId);
    return;
  }

  // Clicking an edge puts a corner there and hands it straight to the drag, so
  // "add a corner" and "put it where I want it" are one gesture.
  const edge = hitEdge(sx, sy);
  if (edge) {
    selectShape(edge.index);
    shapes()[edge.index].splice(edge.corner, 0, edge.point);
    drag = { index: edge.index, corner: edge.corner, dirty: true };
    stage.setPointerCapture(event.pointerId);
    render();
    return;
  }

  const inside = shapeAt(sx, sy);
  if (inside !== null && !event.shiftKey) {
    selectShape(inside);
    return;
  }
  selectShape(null);
  startDraft(point);
});

stage.addEventListener("pointermove", (event) => {
  const which = activeLayer();
  if (!which) return;
  const [sx, sy] = local(event);

  if (which === "zones") {
    if (cutting && cutting.stroke.length) {
      cutting.stroke.push(onPage(view.toImage(sx, sy)));
      render();
    } else if (sweep) {
      sweep.points.push(onPage(view.toImage(sx, sy)));
      // Sent in flight rather than only on release, so the outline keeps up
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
  const corner = hitCorner(sx, sy);
  const moved = (corner && (!hover || hover.index !== corner.index || hover.corner !== corner.corner)) || (!corner && hover);
  hover = corner;
  stage.classList.toggle("on-corner", Boolean(corner));
  stage.classList.toggle("on-edge", !corner && Boolean(hitEdge(sx, sy)));
  if (moved) render();
});

stage.addEventListener("pointerup", (event) => {
  const which = activeLayer();
  if (stage.hasPointerCapture(event.pointerId)) stage.releasePointerCapture(event.pointerId);
  if (which === "zones") {
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
  const { dirty, index } = drag;
  drag = null;
  if (dirty) saveShape(index);
});

stage.addEventListener("click", (event) => {
  if (panned) {
    panned = false;
    return;
  }
  if (!picking()) return;
  const [x, y] = view.toImage(...local(event));
  if (x < 0 || y < 0 || x >= state.page.width || y >= state.page.height) return;
  pickSegment(x, y);
});

// ---- the right-click menu ---------------------------------------------------

function openMenu(event, items) {
  const menu = $("menu");
  menu.replaceChildren(
    ...items.map((item) =>
      h(
        "button",
        {
          type: "button",
          role: "menuitem",
          onclick: () => {
            closeMenu();
            item.action();
          },
        },
        item.label,
      ),
    ),
  );
  const [x, y] = local(event);
  menu.hidden = false;
  // Kept inside the canvas: a menu clipped by the inspector hides its items.
  const maxX = stage.clientWidth - menu.offsetWidth - 4;
  const maxY = stage.clientHeight - menu.offsetHeight - 4;
  menu.style.left = `${Math.max(4, Math.min(x, maxX))}px`;
  menu.style.top = `${Math.max(4, Math.min(y, maxY))}px`;
  menu.querySelector("button")?.focus({ preventScroll: true });
}

function closeMenu() {
  $("menu").hidden = true;
}

stage.addEventListener("contextmenu", (event) => {
  const which = activeLayer();
  if (!which) return;
  event.preventDefault();
  const [sx, sy] = local(event);

  if (which === "zones") {
    if (cutting) return openMenu(event, [{ label: t("menu.stop_cutting"), action: stopCut }]);
    const items = [];
    if (picked.size >= 2) items.push({ label: t("menu.merge", { count: picked.size }), action: mergePicked });
    // Cutting is one zone's business: with several selected there is no
    // saying which one the stroke belongs to.
    if (picked.size === 1) items.push({ label: t("menu.cut"), action: startCut });
    if (picked.size) items.push({ label: t("menu.clear"), action: clearPicked });
    if (items.length) openMenu(event, items);
    return;
  }

  const panels = which === "panels";
  if (draft) {
    return openMenu(event, [
      { label: panels ? t("menu.stop_panel") : t("menu.stop_bubble"), action: discardDraft },
    ]);
  }
  const corner = hitCorner(sx, sy);
  if (corner) {
    // On a triangle the corner is the shape — say so, so the click that removes
    // the whole detection never comes as a surprise.
    const last = shapes()[corner.index].length <= 3;
    const label = !last ? t("menu.delete_corner") : panels ? t("menu.delete_panel") : t("menu.delete_bubble");
    return openMenu(event, [{ label, action: () => deleteCorner(corner) }]);
  }
  const index = shapeAt(sx, sy);
  if (index !== null) {
    selectShape(index);
    openMenu(event, [
      { label: panels ? t("menu.delete_panel") : t("menu.delete_bubble"), action: () => deleteShape(index) },
    ]);
  }
});

document.addEventListener("pointerdown", (event) => {
  if (!$("menu").hidden && !$("menu").contains(event.target)) closeMenu();
});

// ---- zoom and pan -----------------------------------------------------------
//
// Two gestures: the wheel zooms about the cursor, and the middle button — or
// space with the left, for a pen with no middle button — drags the page. Both
// take the pointer in the capture phase, before the editing handlers above.

stage.addEventListener(
  "wheel",
  (event) => {
    if (!state || !state.page) return;
    event.preventDefault();
    const [sx, sy] = local(event);
    // The page point under the cursor stays under it: a loupe over paper.
    const [ix, iy] = view.toImage(sx, sy);
    const delta = event.deltaY * (event.deltaMode === 1 ? 16 : 1);
    zoom = Math.min(MAX_ZOOM, Math.max(1, zoom * Math.exp(-delta * 0.0015)));
    const scale = fitScale() * zoom;
    pan.x = sx - ix * scale - (stage.clientWidth - state.page.width * scale) / 2;
    pan.y = sy - iy * scale - (stage.clientHeight - state.page.height * scale) / 2;
    render();
  },
  { passive: false },
);

stage.addEventListener(
  "pointerdown",
  (event) => {
    panned = false;
    if (!state || !state.page) return;
    if (event.button !== 1 && !(spaceHeld && event.button === 0)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    panning = local(event);
    stage.setPointerCapture(event.pointerId);
    stage.classList.add("panning");
  },
  true,
);

stage.addEventListener(
  "pointermove",
  (event) => {
    if (!panning) return;
    event.stopImmediatePropagation();
    const [sx, sy] = local(event);
    pan.x += sx - panning[0];
    pan.y += sy - panning[1];
    panning = [sx, sy];
    panned = true;
    render();
  },
  true,
);

const endPan = (event) => {
  if (!panning) return;
  event.stopImmediatePropagation();
  panning = null;
  stage.classList.remove("panning");
};
stage.addEventListener("pointerup", endPan, true);
stage.addEventListener("pointercancel", endPan, true);
// Windows opens its autoscroll ring on a middle click otherwise.
stage.addEventListener("auxclick", (event) => {
  if (event.button === 1) event.preventDefault();
});

// ---- keyboard ---------------------------------------------------------------

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (!$("menu").hidden) return closeMenu();
    if (asking) {
      asking = null;
      return renderRail();
    }
    if (cutting) return stopCut();
    if (draft) return discardDraft();
    if (picked.size) return clearPicked();
    if (selected || shapeSelected !== null) {
      selected = null;
      shapeSelected = null;
      choosing = false;
      renderInspector();
      render();
    }
    return;
  }
  // Space and 0 belong to a focused control when there is one.
  if (event.target.matches("input, textarea, select, button")) return;
  if (event.code === "Space" && !event.repeat) {
    event.preventDefault();
    spaceHeld = true;
    stage.classList.add("grab");
  }
  if (event.key === "0") fitPage();
});

const releaseSpace = () => {
  spaceHeld = false;
  stage.classList.remove("grab");
};
document.addEventListener("keyup", (event) => {
  if (event.code === "Space") releaseSpace();
});
// Alt-tabbing away with space down otherwise leaves the canvas stuck in pan.
window.addEventListener("blur", releaseSpace);

// ---- the header and footer toggles ------------------------------------------

$("toggle-inspector").addEventListener("click", () => {
  const hidden = $("shell").classList.toggle("no-inspector");
  $("toggle-inspector").setAttribute("aria-pressed", String(!hidden));
  remembered.set("inspector", hidden ? "hidden" : "shown");
});

$("v-lines").addEventListener("change", (event) => {
  controls.lines = event.target.checked;
  render();
});

// The escape hatch from the surround's faint hue (§10). Default off.
$("v-neutral").addEventListener("change", (event) => {
  controls.neutral = event.target.checked;
  remembered.set("neutral", controls.neutral ? "on" : "off");
  renderFooter();
});

$("v-left").addEventListener("change", (event) => {
  controls.left = event.target.checked;
  render();
});

function setupLanguages() {
  const select = $("language");
  select.hidden = LOCALES.length < 2;
  if (select.hidden) return;
  // Each language named in itself — "Français", "English" — so an artist who
  // cannot read the current one can still find their own.
  const nativeName = (code) => {
    const name = new Intl.DisplayNames([code], { type: "language" }).of(code);
    return name.charAt(0).toLocaleUpperCase(code) + name.slice(1);
  };
  select.replaceChildren(
    ...LOCALES.map((code) => h("option", { value: code, selected: code === words.locale }, nativeName(code))),
  );
  select.addEventListener("change", async () => {
    remembered.set("lang", select.value);
    await loadWords(select.value);
    applyStaticStrings();
    renderAll();
    if (!work.timer) say(state && state.page ? t("status.ready") : t("status.start"));
  });
}

function restorePreferences() {
  if (remembered.get("inspector") === "hidden") {
    $("shell").classList.add("no-inspector");
    $("toggle-inspector").setAttribute("aria-pressed", "false");
  }
  controls.neutral = remembered.get("neutral") === "on";
  $("shell").classList.toggle("neutral", controls.neutral);
}

new ResizeObserver(resize).observe(stage);

(async () => {
  await loadWords(chooseLocale());
  applyStaticStrings();
  setupLanguages();
  restorePreferences();
  try {
    state = await call("/api/state");
  } catch (error) {
    say(error.message, true);
    return;
  }
  controls.threshold = state.segments.threshold;
  controls.gap = Math.round(state.leak_gap * 100);
  controls.granularity = state.export.granularity || "colour";
  edits = {
    panels: state.done.panels ? null : 0,
    bubbles: state.done.bubbles ? null : 0,
    zones: state.done.zones ? null : { merges: 0, cuts: 0 },
  };
  current = furthest();
  await reloadLayers();
  renderAll();
  say(state.page ? t("status.ready") : t("status.start"));
  refreshGpu();
})();
