# Phase 1: Foundation — Project, Palette & Pipeline Backbone - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-02
**Phase:** 1-Foundation — Project, Palette & Pipeline Backbone
**Areas discussed:** Project model vs Series/Volume, Pipeline stage model, Palette building (swatch + character sheet)

**Areas offered but not selected:** Web shell & how much frontend now (→ Claude's discretion)

---

## Project model vs Series/Volume

| Option | Description | Selected |
|--------|-------------|----------|
| Rename Volume → Project, drop Series | One flat table, palette stays where it is, zero migration of palette scope | |
| Project = Volume, keep Series as-is | Zero schema churn, hidden Series per project, dead concept in the schema | |
| Project = Series, palette moves up | Palette/entity move from volume scope to project scope; biggest change, most literal reading of "palette accumulates" | ✓ |

**User's choice:** Project = Series, palette moves up

---

| Option | Description | Selected |
|--------|-------------|----------|
| Drop it — pages hang off project | Flattest model, one less join, nothing in v1 needs chapters | |
| Keep it, hidden — auto-create one per project | No migration later, but a DB-only layer that confuses later readers | |
| Keep it, visible — artist groups pages into volumes | Honest to how a series is organised; flagged in the option text as the closest thing to scope creep of the three | ✓ |

**User's choice:** Keep it, visible
**Notes:** Cost was stated explicitly before the choice (no v1 requirement asks for it) and the user selected it anyway. Recorded as deliberate.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Folder per project, DB inside it | Portable: copy/move/back up/hand over the folder; needs a recent-projects list | ✓ |
| One app database, projects are rows | Simplest, one Store; nothing portable, all-or-nothing backup | |
| Global index + per-project DB | Recent list without a scan, keeps portability; two Store types and a sync problem | |

**User's choice:** Folder per project, DB inside it

---

| Option | Description | Selected |
|--------|-------------|----------|
| Bind at accept time, not upload | Frictionless upload; name asked when accepting proposals, where it pays for itself | ✓ |
| Name the character on upload | Pre-tagged proposals and clean Cobra grouping; friction on every upload | |
| Untagged, project-level only | Lowest friction, most literal PROJ-03; proposals arrive unnamed | |

**User's choice:** Bind at accept time

---

## Pipeline stage model

| Option | Description | Selected |
|--------|-------------|----------|
| Declarative registry, thin runner | Stages declare name/deps/output/callable; runner walks the chain, stages stay individually triggerable | ✓ |
| Passive — status only | Stage column plus prerequisites; never executes; by Phase 6 nothing knows the whole chain | |
| Active orchestrator | Runs the page end to end; fights "every boundary is inspectable" | |

**User's choice:** Declarative registry, thin runner

---

| Option | Description | Selected |
|--------|-------------|----------|
| Mark stale, artist decides | Downstream flips to stale, nothing destroyed until the artist says so | |
| Stale, scoped to the affected panel | Per-panel provenance so unaffected panels stay valid | |
| Auto re-run downstream | Always consistent; silently destroys corrections and burns GPU minutes | |

**User's choice:** *None — the user rejected the question and reframed it.*
**Notes:** In the user's words: *"Each stage is forward only, you cannot go back. At each stage, the artist is asked whether they confirm or not and you cannot go back, it would be insane. To go back is to rewrite every steps back: it will cost them time and money."* This eliminated the entire premise — no stale state can exist because the model never permits one. The follow-up questions below were reformulated from this.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Possible, with an explicit warning | Reset is allowed, but the app names what it destroys and makes them confirm | ✓ |
| Forbidden — no path back in the app | Start the page over from upload; zero invalidation logic anywhere | |
| Possible, and it re-runs automatically | Fewest clicks; destruction is invisible until finished | |

**User's choice:** Possible, with an explicit warning

---

| Option | Description | Selected |
|--------|-------------|----------|
| Per page | One stage value per page, exactly what PROJ-04 displays | ✓ |
| Per panel, once panels are confirmed | Matches the per-panel data model and per-panel Cobra runs; page stage becomes a rollup | |

**User's choice:** Per page

---

| Option | Description | Selected |
|--------|-------------|----------|
| No — palette sits outside the stage chain | Repaint not recompute; matches spec §213 and PAL-04; no warning, no cost | ✓ |
| No, but warn once past review | Same mechanic plus a warning on reviewed pages | |
| Yes — sends affected pages back to review | Most conservative; fights §213 and makes the palette scary to touch | |

**User's choice:** No — palette sits outside the stage chain

---

| Option | Description | Selected |
|--------|-------------|----------|
| Declare all stages, implement upload only | Full chain declared up front; later phases fill runners against an existing contract | ✓ |
| Declare only what exists, grow it | Nothing guessed; registry shape not pinned until Phase 5, close to the retrofit cost the phase goal warns about | |

**User's choice:** Declare all stages, implement upload only

---

## Palette building (swatch + character sheet)

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-detect chips, artist corrects on the image | Contour detection with click-to-add/remove fallback | |
| Assume separated chips on a plain background | Requires a prepared palette file; no correction UI | |
| Artist clicks every chip | Cannot fail on any input; 40 colours = 40 clicks | |

**User's choice:** *None of the above — free-text reframing.*
**Notes:** In the user's words: *"The palette is built automatically from the image. The user could drop a grid of object, you extract the main colors from it to generate the palette. Then the user will simply modify. If it was already an image with chips or uniform color blob, the script will get the right colors 100% of the time. I'm pretty sure there's a lib doing this exact thing."* This replaced chip/contour detection with whole-image dominant-colour extraction and turned the task into a library integration. A web search confirmed the user's instinct — Pylette, ColorThief, colorgram.py, and Pillow's own `quantize()` all do this; candidates recorded in CONTEXT.md D-13 for the researcher to choose between on licence and maintenance.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Same extractor, sheet-aware pre-pass | Drops near-black ink and near-white paper before extracting on character sheets; everything downstream shared | ✓ |
| One extractor, no special handling | Least code; two garbage proposals on every sheet | |
| Two genuinely separate paths | Best results both sides; two code paths in an already-heavy phase | |

**User's choice:** Same extractor, sheet-aware pre-pass

---

| Option | Description | Selected |
|--------|-------------|----------|
| Sensible default, artist adjusts and re-extracts | ~12 with a slider, re-runs instantly | |
| Adaptive — the extractor decides | Near-perfect on a chip grid; no lever when it misjudges a shaded sheet | ✓ |
| Artist sets it before every extraction | Explicit; they don't know the answer until they've seen the result | |

**User's choice:** Adaptive
**Notes:** The stated cost (no count lever on a shaded sheet) was accepted. CONTEXT.md records PAL-03's manual add/delete as the recovery path and requires it to be reachable from the extraction result.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-placeholder, rename freely | "Colour 1..N", nothing blocks a working palette in seconds | ✓ |
| Auto-name from a colour-name table | "Burnt Sienna" reads better than a number, still no use for identifying Kaito's hair | |
| Prompt for a name on accept | Best palette to work with in Phase 6; ~12 prompts per extraction | |

**User's choice:** Auto-placeholder, rename freely

---

## Claude's Discretion

- **Web shell architecture** — not selected for discussion. CONTEXT.md defers to
  `.planning/research/STACK.md`: FastAPI + Vite/TypeScript, existing `Store` as the
  data layer, no ORM, no NiceGUI/Streamlit/Gradio/Reflex.
- **Coordinate transform ownership** (Python vs TypeScript) — folded into the same
  unselected area. CONTEXT.md directs it to TypeScript with its own unit tests, since
  the consumers are the Phase 2–3 browser editors, and asks the planner to state its
  choice explicitly.

## Deferred Ideas

None — discussion stayed within phase scope.
