# Observations — Luikki

Final, 27 September 2026 — 39 observations, all twelve categories walked
(10 deliberately thin; 10-12 in fast mode at the founder's request).

Luikki is a desktop app that segments comic line art into zones and
returns editable, layered flats as a PSD, with optional generative colour
from character sheets. Solo founder (Raph), version 0.5.0 in September
2026, three professional testers, no paying customer yet. Pre-launch —
no public reviews or press, so no external research section (only the
GitHub repository and its releases are public). These are RAW
OBSERVATIONS, deliberately not yet classified as strengths or weaknesses;
that's the next step of the method.

## 1. Undeniable comparative strength

**O1.** A tester, after a test session, asked if she could keep the app.
What she named: clicking zones instead of holding the pen and drawing each
zone by hand.

**O2.** A second tester singled out applying a palette: she painted a few
zones and was visibly pleased to see every skin tone repaint at once, the
whole background at once, and so on.

**O3.** Testers timed flats on their own pages, doing the work themselves
in Luikki: about 30 minutes for a usual page, against 4-8 hours by hand.

**O5.** Testers hate the AI colourisers they have tried: those tools
change the line art, and give no control.

**O6.** Testers hate Clip Studio's Colorize: it proposes random, ugly
gradients they cannot modify.

**O7.** Bucket-fill tools fail on open line art: one gap and the fill
floods the page. On the open-lined pages tested so far, Luikki closed most
open lines correctly and never flooded the page — observed by eye, not
yet benchmarked.

**O8.** On clean inking, a page needs very few cuts in Luikki, and a lot of
merges. (How many cuts depends on the artist's inking — O12.)

## 2. Consistent complaints

**O10.** Cutting zones is the main complaint seen in sessions; merges are
fine. What makes cuts tedious is their number, and the cause is open line
art: where a line leaves a gap, two zones come out as one and the tester
has to cut them apart.

**O11.** Correcting balloons (step 3) leaves testers a bit unhappy. The
detector finds the balloons, but the polygon it draws is too big, so nearly
every balloon needs fixing by hand — and pages carry a lot of balloons.

## 3. Proud of

**O13.** Open line art — what floods every bucket tool — declared solved on
11 September 2026: a leak audit reads how open a border is, and one dial,
set per book, lets the artist say how wide a gap still counts as a hole in
a line.

**O14.** Seven buttons in one fixed order (upload → panels → balloons →
zones → flats → snap → export); nothing runs by itself; every stage is a
proposal the artist corrects in a click.

**O15.** The way of thinking about the problem: every stage boundary is
inspectable and correctable — that is the product, not a feature of it.
Zones hold a palette id, never an RGB value, so one colour change repaints
everywhere (what the tester saw in O2).

**O16.** Right after generation, the result is immediately workable: the
AI colours arrive inside the zones, snapped to the palette, and the artist
edits them like any other flat.

**O17.** The brand: the name Luikki, the logo in the signature orange, the
dark violet surround of the app. The founder is especially proud of it.

## 4. Head/tail differential

**O12.** How much correcting a page needs depends on the artist's inking:
mangaka and artists with solid, closed lines have no problems; artsier or
more amateurish inking leaves open lines and many more cuts (O10).
*(Spilled from category 2.)*

**O18.** Page content separates good runs from bad ones: a page with a
very detailed background comes out as hundreds of tiny zones the tester
has to sweep and merge by hand, while a comic focused on its characters
runs smoothly.

**O19.** The tester who asked to keep the app (O1) is the experienced one:
published, working to deadlines.

**O20.** Format makes no difference: franco-belgian, manga and webtoon pages
all work, with open or closed panels.

## 5. We wish / say we're great, but we're not

**O21.** The plan says the AI colours from the character sheets ("the skin
is skin, the jacket is the jacket"). In practice Cobra is mostly wrong,
even with 10 references: a character comes out about half right. Outside
manga and American-comics styles, and wherever a scene holds details no
reference covers, it produces greys.

## 6. Customers advocate for

**O9.** No tester praise recorded so far (O1, O2) names the AI colour
(Cobra); it names clicking zones, palette repaint, and speed. The founder
suspects the AI is not the attractor, and that the non-AI parts are.
*(Spilled from category 1; founder's reading recorded as who-said-what,
not as a verdict.)*

**O22.** No tester is known to have told another artist, shown the app to
a colleague or publisher, or posted about it.

**O23.** Two people asked to test Luikki; when asked whether they work on
Windows or Mac, neither answered.

## 7. Clear and present existential threats

**O25.** The founder names the threat plainly: if no customer comes within
6 months of going on sale, they will stop — they will not keep working for
zero people.

**O26.** The founder expects a new competitor to be the other threat. The
only one seen so far is Flagcat, whose proprietary character-colouring
software is in-house, not sold. Below the 70% bar: a worry, not yet an
observed threat.

**O27.** The founder reads the anti-AI backlash as fading: people accept AI
little by little. Recorded as the founder's reading; no incident behind it
yet.

## 8. Organizational capabilities

**O4.** The founder is not an artist, and tests the pipeline alone on comic
pages found online; the artists' view comes only from the three testers,
over video call. *(Spilled from category 1.)*

**O24.** The founder builds Luikki on the side of a job: no runway, no date
by which it must earn. *(Spilled from category 7.)*

**O28.** The founder can put up to 20 hours a week into Luikki.

**O29.** A tester's complaint reaches them as a fixed release in one
evening.

**O30.** Outreach so far: 15 authors contacted → 3 became the testers, the
other 12 gave nothing (see also O23). The founder joined forums, Discord
servers and X to offer flats to authors who need them, as a way to promote
Luikki; the offers start on 28 September 2026, none made yet.

**O31.** One YouTube video explaining the whole app, cut into shorts: about
200 views each.

**O32.** The administrative costs keep getting put off — business
domiciliation, the Apple developer certificate, Windows code signing, and
the like: the founder does not have the money for all of them, so they get
paid one at a time.

## 9. Technical architecture and capabilities

**O33.** The local pipeline (numpy, OpenCV, onnxruntime; no torch, no GPU)
makes shipping, offline use and debugging easy.

**O34.** Running Cobra in the cloud lets an artist use a model that is too
heavy and slow for their own PC.

**O35.** The founder cannot train or swap the colour model: Cobra is the
only model of its kind that exists. The same holds for the balloon
detector: no way to retrain it alone (its oversized polygons, O11, stay as
they are).

**O36.** In the founder's words, the AI makes the product hard to improve:
the parts that depend on a model are the parts they cannot change.

## 10. Envy of / constantly losing sales to competitors

*(Nothing surfaced after prompting — revisit if something emerges.)*

## 11. Philosophy

**O37.** The artist stays in control at every step — held even if it costs
customers or money.

**O38.** No training on the artists' work — held even if it costs customers
or money. (Written as a contract clause in business-plan.md §2.3.)

## 12. Great ideas

**O39.** A recurring idea: detect depth in the line art, and let the artist
do the lights and shadows on top of the flats.

## Side-list (ideas parked during the session — not processed)

- Benchmark open-line closure on real ink pages (O7 is by eye only).
- Decide whether the AI licence should be the headline of the offer (O9).
- Balloons (O11, O35): tighten the detector's box to the balloon's own ink
  contour after detection, deterministically — no retraining needed.
- Planned: a good website, comparisons and benchmarks, blog posts, more videos.

## Next steps

Distill these observations into the few attributes that matter, merging
observations that point at one deep truth (for example O1, O2, O14, O15 on
the click-and-palette workflow; O9, O21, O35, O36 on the AI), then classify
each as a strength, a weakness, or deliberately both. That is the next step
of the method, `asb-carol-strengths`, and it works directly from this file.
