# ComicColor — the interface

This document tells you how to rebuild the interface. `SPEC.md` says what the app
must do. `ARCHITECTURE.md` says where the code is. This document says what the
app must look like, and why.

It changes no rule in the other two documents. It changes no server behaviour.

The text follows ASD-STE100 Simplified Technical English: short sentences, active
voice, one idea for each sentence, and the same word for the same thing.

## 0. How to use this document

Do the tasks in section 12, in order. Each task is small. After each task, open
the app and look at it.

You touch three files only:

    src/comiccolor/web/static/app.css
    src/comiccolor/web/static/index.html
    src/comiccolor/web/static/app.js

Do not change the Python. One exception is in task 3, and it is a read-only
route. `tests/test_web.py` must pass at the end without a change to the test.

## 1. Rules that must hold

**R1 — The colour scheme is three pairs, and each pair is a ramp.** The six
colours are the ends of three ramps. Section 3 gives the ramps. Every colour in
the interface is a step of one of them. Do not add a fourth ramp. Do not replace
an end.

**R2 — Each ramp owns one domain.** The frame ramp is the vertical structure of
the app. The type ramp is text and borders. The action ramp is everything the
artist clicks. A colour never crosses from its domain into another one.

**R3 — Almost no hue touches the artwork.** The area around an image changes how
the eye sees that image, and the artist judges colour in this app. The surround
holds chroma 3. The lines on the page carry luminance. Section 11 gives the two
exceptions.

**R4 — Every colour comes from a token.** After task 1, no CSS rule and no
`app.js` line holds a hex value. The only hex values in the project are in the
`:root` block.

**R5 — The element on the left controls the element on the right. The element on
the top controls the element below it.** The step rail controls the canvas. The
canvas controls the inspector. A control on the right or at the bottom only
transforms the view.

**R6 — The order of the steps is visible.** The server refuses step 3 before step
2. The interface must show that refusal before the artist clicks.

**R7 — Nothing *interrupts* the canvas.** No dialog, and no pop-up that takes
the artist away from what they were doing, except the one confirmation that
rule 4 of `SPEC.md` asks for.

A panel pinned to the object it is about is not one of those, and section 15
already asks for the opposite: the right-click menu and the merge and cut
actions belong on the page, not off it. Step 6's decision — the colour a zone
holds, the nearest one, Snap, Choose another — sits in a window beside the
zone (`.near`, `renderNear`), because the first tester never found those
buttons at the far edge of the screen while their hand was on the zone. It is
placed clear of the zone it describes and never covers it.

**R8 — One gradient.** Section 6 names the only place a gradient appears.

**R9 — No new dependency.** One HTML file, one CSS file, one JS file. No
framework, no build step, no icon package. Icons are inline SVG.

## 2. How the ramps were made

This section exists so that you do not change a value by accident. Do not
recompute the ramps. Do not adjust a step because it looks dark on your screen.

Each ramp goes from the dark end of a pair to the light end, in OKLCh, in 13
steps. Lightness and chroma are linear. Hue is not.

OKLCh, and not CIELAB. Two reasons. Its lightness is uniform, so an equal step
in `L` is an equal step to the eye. And its constant-hue lines stay straight
through the blues, where CIELAB bends toward purple. That second one is not
academic here: CIELAB puts your two blues 11 degrees apart in hue, and OKLCh
puts them 0.9 degrees apart. They are the same blue at two lightnesses, which is
what they look like, and CIELAB was inventing a hue rotation across the whole
action ramp.

    L(t) = L0 + (L1 - L0)·t
    C(t) = C0 + (C1 - C0)·t
    h(t) = h0 + Δh·t + bow·sin(π·t)

`Δh` is the short way round the hue circle. `sin(π·t)` is zero at both ends, so
the six colours land exactly on their steps. It peaks in the middle, where the
ramp is furthest from both ends.

The bow always goes toward violet and magenta. At the same lightness and the same
chroma, the eye sees a violet or a magenta as more colourful than a yellow or an
orange. This is the Helmholtz-Kohlrausch effect. Therefore the bow makes the
middle of a ramp look more saturated, and it does not increase `C*`. The measured
contrast in section 5 stays true.

The ends and the bows:

| Ramp | Dark end | Light end | Bow |
|---|---|---|---|
| Frame | (59,49,63), L 0.330, C 0.028, h 316.3° | (228,162,128), L 0.768, C 0.092, h 48.2° | −26° |
| Type | (114,107,103), L 0.533, C 0.011, h 52.0° | (193,198,209), L 0.826, C 0.016, h 266.3° | −12° |
| Action | (50,87,164), L 0.471, C 0.131, h 263.0° | (133,160,209), L 0.704, C 0.078, h 262.1° | +18° |

After the interpolation, each step goes OKLCh → OKLab → LMS → linear RGB →
sRGB. A step outside the sRGB gamut loses chroma until it returns. No step of
these three ramps needs that.

## 3. The three ramps

Frame, 13 steps:

    #3B313F #46394A #514256 #5E4B61 #6B536C #795C76 #88647E
    #986C85 #A97589 #BA7E8A #CA8988 #D99484 #E4A280

Type, 13 steps:

    #726B67 #7A726F #827878 #897F81 #90868A #978E93 #9D959C
    #A39DA6 #A9A5AF #AFADB8 #B5B5C0 #BBBEC9 #C1C6D1

Action, 13 steps:

    #3257A4 #415BA8 #4E5FAC #5964AF #6369B2 #6B6EB6 #7174B9
    #767BBD #7A82C2 #7D89C6 #8091CA #8298CE #85A0D1

The interface names 20 of these 39 steps. The rest of the frame ramp appears in
the gradient of section 6, and nowhere else.

## 4. The tokens

Paste this block at the top of `app.css`. Do not edit a value.

```css
:root {
  /* ---- Frame ramp. The vertical structure of the app. ---- */
  --bg:             #3B313F;  /* YOUR (59,49,63). App background.   */
  --panel:          #46394A;  /* Rail, inspector, header, footer.   */
  --control:        #514256;  /* Button and field fill.             */
  --control-hover:  #5E4B61;
  --control-press:  #6B536C;  /* Also: pressed, and selected.       */
  --attention:      #E4A280;  /* YOUR (228,162,128). One meaning.   */
  --attention-tint: rgba(228, 162, 128, 0.16);

  /* The whole frame ramp, as one gradient. See section 6. */
  --ramp: linear-gradient(90deg,
    #3B313F, #46394A, #514256, #5E4B61, #6B536C, #795C76, #88647E,
    #986C85, #A97589, #BA7E8A, #CA8988, #D99484, #E4A280);

  /* ---- Type ramp. Text, borders, disabled. Never a fill. ---- */
  --text:      #C1C6D1;  /* YOUR (193,198,209). 6.3:1 on --panel.   */
  --text-dim:  #AFADB8;  /* 4.9:1 on --panel.                       */
  --text-off:  #726B67;  /* YOUR (114,107,103). Disabled only.      */
  --border:    #9D959C;  /* 3.7:1 on --panel. A control boundary.   */
  --separator: #827878;  /* A line between two areas. Decorative.   */

  /* ---- Action ramp. Interactive only. ---- */
  --action:       #3257A4;  /* YOUR (50,87,164). White text = 6.9:1 */
  --action-hover: #6369B2;  /* White text = 5.0:1                   */
  --action-ring:  #85A0D1;  /* YOUR (133,160,209). Ring and accent. */
  --action-tint:  rgba(50, 87, 164, 0.30);   /* A selected row.     */

  /* ---- The surround. The frame hue at chroma 3. ---- */
  --canvas:         #8E8B90;  /* L 0.64, 30% of the frame chroma.   */
  --canvas-neutral: #8C8C8C;  /* L 0.64, C 0. The toggle of task 7. */
  --canvas-edge:    #5F5C61;  /* L 0.48. The page border.           */

  /* ---- On the artwork. Luminance, plus two shapes. See section 11. ---- */
  --over-dark:  rgba(0, 0, 0, 0.62);
  --over-light: rgba(255, 255, 255, 0.90);
  --over-wash:  rgba(255, 255, 255, 0.12);
  --over-panel:  #3257A4;  /* --action.                              */
  --over-bubble: #7B4F37;  /* --attention's hue at the blue's L 0.47. */

  /* ---- Space. A 4px grid. Nothing off it. ---- */
  --s-1: 4px;  --s-2: 8px;  --s-3: 12px; --s-4: 16px;
  --s-5: 20px; --s-6: 24px; --s-8: 32px;

  --r-control: 4px;
  --r-panel:   6px;

  --rail-w:      232px;
  --inspector-w: 300px;
  --header-h:    44px;
  --footer-h:    32px;

  --font: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto,
          "Helvetica Neue", Arial, sans-serif;
  --fs-body:  13px;
  --fs-label: 12px;
  --fs-num:   12px;
}
```

## 5. Measured contrast

Do not lower these.

| Pair | Ratio |
|---|---|
| `--text` on `--bg` | 7.2:1 |
| `--text` on `--panel` | 6.3:1 |
| `--text` on `--control` | 5.4:1 |
| `--text-dim` on `--panel` | 4.9:1 |
| `--border` on `--panel` | 3.7:1 |
| `--attention` on `--panel` | 5.0:1 |
| `--bg` text on `--attention` fill | 5.8:1 |
| white on `--action` | 6.9:1 |
| white on `--action-hover` | 5.0:1 |
| `--action-ring` on `--bg` | 4.7:1 |
| `--action-ring` on `--panel` | **4.1:1** |
| `--text-off` on `--panel` | **2.1:1** |

Two warnings from that table:

- `--action-ring` misses AA for body text on a panel. Use it there for the focus
  ring, for an icon, and for text at 16px or above. Accent text at 13px goes on
  `--bg`, where it gives 4.7:1.
- `--text-off` is a disabled state. It is never live text.

`--attention` is a light colour. A solid fill of it takes `--bg` text, never
white.

## 6. The gradient

The frame ramp appears as a gradient in exactly one place: the progress bar of
the long steps.

Segmentation takes about two minutes. Therefore the bar must show real progress,
and the artist watches it for a long time. The bar starts at the app background
and travels to the attention colour through the plum middle of the ramp. Use
`--ramp` as the background of the full track, and reveal it from the left with a
width in percent. Do not animate a stripe. Do not use the gradient anywhere else.

    <div class="bar"><div class="bar-fill" style="width: 42%"></div></div>

    .bar      { height: 4px; background: var(--control); border-radius: 2px; }
    .bar-fill { height: 4px; background: var(--ramp); background-size: 640px 4px;
                border-radius: 2px; transition: width 200ms linear; }

Fix the background size, so that the colour at a given percent is the same for
every run. A bar that rescales its gradient tells the artist nothing.

If the server gives no percent for a step, show an indeterminate bar of
`--control` and a text status. Do not fake a percent.

## 7. The layout

Three columns and two bars. The canvas takes the space that is left.

    ┌──────────────────────────────────────────────────────────────┐
    │ HEADER 44px   page name                        [⇥ inspector] │
    ├────────────┬────────────────────────────────┬────────────────┤
    │ STEP RAIL  │            CANVAS              │   INSPECTOR    │
    │ 232px      │                                │   300px        │
    │            │      ┌──────────────┐          │                │
    │ 1 Upload   │      │              │          │  What is       │
    │ 2 Panels   │      │   the page   │          │  selected,     │
    │ 3 Bubbles  │      │              │          │  and its       │
    │ 4 Zones    │      │  on --canvas │          │  properties.   │
    │ 5 Flats    │      │              │          │                │
    │ 6 Snap     │      └──────────────┘          │                │
    │ 7 Export   │                                │                │
    │ ───────    │                                │                │
    │ References │                                │                │
    │ Palette    │                                ├────────────────┤
    │            │                                │ panel footer   │
    ├────────────┴────────────────────────────────┴────────────────┤
    │ FOOTER 32px  status + progress bar    ☐ lines   ☐ neutral    │
    └──────────────────────────────────────────────────────────────┘

```css
.shell {
  display: grid;
  grid-template-columns: var(--rail-w) 1fr var(--inspector-w);
  grid-template-rows: var(--header-h) 1fr var(--footer-h);
  height: 100vh;
  background: var(--bg);
}
```

The rail, the inspector, the header and the footer are `--panel`. The app
background `--bg` shows in the 1px gaps between them, which is how the structure
reads without a border.

The header holds the name of the page and one button that hides the inspector. It
holds no logo. A tool that runs every day does not need a logo in its own
interface.

Each column scrolls on its own. The canvas never scrolls the page.

## 8. The step rail

The rail is the flow. It replaces the list of buttons.

Each step is one row: a number, a name, and a state. The current step also shows
its primary button and its own controls. A step that is not current shows its
name only. This keeps all the controls of one small task in one place.

| State | Row fill | Number | Text | Behaviour |
|---|---|---|---|---|
| done | `--panel` | check mark, `--action-ring` | `--text-dim` | Click opens the step again. |
| current | `--action-tint` | white on `--action` | `--text` | Open. Shows its button and controls. |
| next | `--panel` | `--text-dim` | `--text-dim` | Click runs the step. |
| locked | `--bg` | `--text-off` | `--text-off` | No click. Gives the reason on hover. |
| closed | `--panel` | `--text-dim` | `--text-dim` | A correction stage that the next step closed. |

The left border of the row carries the state: 2px `--action` for current,
transparent for the rest. Colour is never the only carrier. The number and the
position also carry the state.

A locked step gives the reason in plain words: `Detect panels first`. A closed
stage gives the way back: `Segment zones again to change the panels. This deletes
your merges and cuts.`

Below the seven steps, and after a `--separator` line, put **Pages**,
**References** and **Palette**. They are not steps. Give each one a summary:
`3 pages`, `4 references`, `11 colours`. Pages lists every page of the project
in the inspector, with how far each has got; clicking one opens it as it was
left.

## 9. The inspector

The inspector shows what is selected on the canvas, and nothing else. If nothing
is selected, it says what to click.

| Step | What the inspector holds |
|---|---|
| 2 Panels | The number of the panel, its corner count, and Delete panel. |
| 3 Bubbles | The same, for the balloon. |
| 4 Zones | The count of selected zones, their area, Merge, Cut and Clear. |
| 5 Flats | The count of segments, and the count that holds a private entry. |
| 6 Snap | The colour of the zone, the nearest palette colour, the distance, and Snap, Pick another colour, Put the proposal back. |
| References | The thumbnail, the kind, and the chips of the candidate colours. |
| Palette | The swatch grid. Click a swatch to edit that colour. |

The distance at step 6 is the number that the old automatic pass used in silence.
Show it in `--fs-num` with `font-variant-numeric: tabular-nums`. Above
`SNAP_MAX_DELTA` it is `--attention`. Below it, it is `--text-dim`. The number
orders the attention of the artist. It does not refuse the instruction of the
artist.

Put the secondary actions of a panel in a panel footer at its bottom.

## 10. The canvas and the surround

The canvas fills its cell with `--canvas`. The page sits in the middle with a 1px
`--canvas-edge` border and no shadow. There is `--s-6` of surround on all four
sides at the minimum.

`--canvas` is the frame hue at 30 % of the chroma of `--bg`, so the surround
belongs to the app and still barely moves the colours the artist judges inside
it.

Give the artist the escape hatch. A `neutral` toggle in the footer swaps
`--canvas` for `--canvas-neutral`, which holds no chroma at all. Default off.

Do not put a gradient between the page and the surround. Do not put a shadow
there. Do not put a chequerboard there.

The canvas element uses `devicePixelRatio`. Set the CSS size and the buffer size
apart, then scale the context one time. All hit tests go through `view.toImage`.
Do not add a second transform.

Zoom and pan are not in this pass. Keep the surround and the page sizing in one
function, so a later scale factor has one place to go.

## 11. Lines drawn on the artwork

A coloured line on a comic page competes with the drawing, and it shifts the
colour that the artist is judging. Therefore the lines on the page carry
luminance, not hue.

Every outline is a double stroke. Draw the same path two times: first
`--over-dark` at 3px, then `--over-light` at 1.5px on top. The pair stays visible
on white paper and on a spot black.

| Thing | Stroke |
|---|---|
| Panel polygon | `--over-light` at 4px, then `--over-panel` (deep blue) at 2px, solid. |
| Protected area | `--over-light` at 4px, then `--over-bubble` (deep brown) at 2px, dashed `[6, 4]`. |
| Selected zone | Double stroke, dashed `[4, 4]`, animated offset. No fill. |
| A sweep of many zones | The same, plus `--over-wash` inside. The wash is white. |
| The cut stroke, while the button is down | Double stroke, 2px, dashed. |
| The panel number | A chip of `--bg` at 80 % alpha, with `--text`. |

Three exceptions, and no more:

- Panel and protected-area outlines carry a deep hue. A grey double stroke
  disappears into black-and-white ink, and these shapes are the ones the
  artist must read across the whole page. The hue is deep and the line is
  thin, and the light halo underneath holds it on a spot black. Zone
  selection and the cut stroke stay luminance only, because they sit on the
  colour that the artist is judging.
- A corner handle is an 8px square with `--over-light` fill and a 1px
  `--over-dark` border. The handle under the pointer fills with `--action-ring`.
  The area is under 100 square pixels, so it cannot shift the perception of the
  page, and the artist must find it.
- The focus ring is `--action-ring`, 2px, offset 2px. Accessibility wins here.

Never fill a zone with a hue to show that it is selected. The artist is looking
at the colour of that zone. `--attention` never touches the page: it is a skin
colour, and a comic page holds skin.

## 12. Controls, type and space

**Button.** Height 28px, radius `--r-control`, padding `0 var(--s-3)`, text
`--fs-body`, sentence case.

| Kind | Rest | Hover | Pressed | Disabled |
|---|---|---|---|---|
| primary | `--action`, white text | `--action-hover` | `--action`, inset | `--control`, `--text-off` |
| default | `--control`, `--text` | `--control-hover` | `--control-press` | `--panel`, `--text-off` |
| quiet | none, `--text-dim` | `--control` | `--control-press` | `--text-off` |
| destructive | none, `--attention` | `--attention-tint` | `--attention-tint` | `--text-off` |

One primary button at a time. It belongs to the current step. A disabled button
keeps a tooltip that says why it is disabled.

**Palette swatch.** 24px square, radius `--r-control`, 1px `--border`. The
selected swatch takes a 2px `--action-ring`. Show the id below in `--fs-num`,
`--text-dim`. The id never changes, and the interface must show that.

**Candidate chip.** Not taken: 60 % alpha, 1px dashed `--separator`. Taken: full
alpha, 1px solid `--border`, and a check mark. The difference is alpha and
border, not hue.

**Toggle.** Three options or fewer: radio buttons or a switch. More: a dropdown.

**Scrollbar.** Style it. There are many of them.

```css
* { scrollbar-width: thin; scrollbar-color: var(--control-press) transparent; }
*::-webkit-scrollbar { width: 10px; height: 10px; }
*::-webkit-scrollbar-thumb {
  background: var(--control-press); border-radius: 5px;
  border: 3px solid transparent; background-clip: padding-box;
}
*::-webkit-scrollbar-thumb:hover { background: var(--border); background-clip: padding-box; }
*::-webkit-scrollbar-track { background: transparent; }
```

**Focus.** `:focus-visible` takes a 2px `--action-ring` outline, 2px offset. Never
remove the outline.

**Motion.** 120ms on a background colour and on an opacity. The progress bar
moves on its width. Nothing else moves. Respect `prefers-reduced-motion: reduce`,
and stop the dashes of a selected zone under it.

**Type.** One family, `--font`. Body 13px / 1.45. Labels 12px, `--text-dim`,
sentence case. Do not use capitals for a label. Numbers take
`font-variant-numeric: tabular-nums`: the snap distance, the zone count, the
panel number, the palette id. A number that changes must not move the text next
to it.

**Space.** Every margin and every padding is a `--s-*` token.

## 13. The tasks, in order

**T1 — Tokens.** Put the `:root` block at the top of `app.css`. Replace every hex
value in `app.css` and in `app.js` with a token. Then check that
`grep -nE '#[0-9a-fA-F]{3,8}' src/comiccolor/web/static/app.{css,js}` returns the
`:root` block and nothing else. For a colour that `app.js` draws on the canvas,
read the token one time at start with `getComputedStyle`, and cache it.

**T2 — The shell.** Build the grid of section 7. Move the existing buttons into
the rail as they are. Do not change their behaviour yet. The app must still work
at the end of this task.

**T3 — The step rail.** Give the browser one `stage` value, and derive the five
states of section 8 from it. Use the responses that the client already receives.
If no response says which steps are done, add one read-only route
`GET /api/state` that returns the flags that `Session` already holds. Add no
other route, and change no behaviour.

**T4 — The canvas.** Apply section 10. `--canvas` surround, 1px page border, no
shadow, `devicePixelRatio`.

**T5 — The overlays.** Apply section 11 to every path that `app.js` draws.

**T6 — The inspector.** Build the right column of section 9. Move the snap
inspector, the palette and the references into it.

**T7 — The footer.** Status text and the progress bar of section 6 on the left.
The toggles on the right: `extracted lines` first, then `neutral surround`.

**T8 — The controls.** Apply section 12 across all three files.

**T9 — The words.** Every button says what happens: `Detect panels`, `Segment
zones`, `Export PSD`. The confirmation names what it deletes: `Segment zones
again? This deletes 14 merges and 2 cuts.` An error says what to do next.

**T10 — The check.** Run section 14.

## 14. Acceptance

- `pytest` passes, and `tests/test_web.py` is not edited.
- Every one of the seven steps is reachable, in order, from the rail.
- The six colours of the scheme are all in the interface, at their exact value.
- `grep` finds no hex value outside the `:root` block.
- The gradient appears in the progress bar, and in no other place.
- No line drawn on the page carries a hue, except a corner handle under the
  pointer.
- The keyboard reaches every control, and the focus ring is visible on all of
  them.
- Every step shows its state before the artist clicks it.
- No pop-up interrupts the page, and the one panel that sits over the artwork
  is pinned beside the object it is about.
- The window works at 1280 x 720 with no horizontal scrollbar.

## 15. Do not do this

- Do not recompute the ramps, and do not adjust a step by eye.
- Do not use a gradient outside the progress bar.
- Do not move a colour out of its domain. The action ramp is never a surface. The
  type ramp is never a fill.
- Do not put `--attention` on the artwork.
- Do not use `--text-off` for live text. It gives 2.1:1.
- Do not use colour as the only carrier of a state.
- Do not add a framework, a build step, or an icon package.
- Do not move the corner handles, the right-click menu, or the merge and cut
  actions off the page. They belong on the object.
- Do not add a second coordinate transform.
- Do not put a logo in the interface.
- Do not animate anything that the artist did not start.
