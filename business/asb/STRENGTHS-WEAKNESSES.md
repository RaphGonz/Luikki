# Strengths & Weaknesses — Luikki

Final, 27 September 2026 — 8 attributes: 6 strengths, 4 weaknesses, two
of them both-attributes (S3 = W1, S6 = W4). Every observation is cited,
cut, kept as supporting detail, or parked below.

Distills `OBSERVATIONS.md` (39 observations, 27 September 2026). Luikki:
desktop app that segments comic line art into zones and returns editable
layered flats as a PSD, optional generative colour from character sheets;
solo founder on the side of a job, v0.5.0, three professional testers, no
paying customer yet. Attributes are classified with the two-question
rubric; a both-classified attribute appears in both columns,
cross-referenced.

Best vs worst fit (from the observations' head/tail category): clean,
closed inking and character-focused pages (mangaka, solid artists) run
smoothly; artsy or amateurish inking and very detailed backgrounds bring
many cuts and hundreds of merges [O12, O18]. The tester who asked to keep
the app is the experienced, published one with deadlines [O19]. Format
(franco-belgian, manga, webtoon) makes no difference [O20].

## Strengths

**S1.** The artist flats by clicking pre-cut zones instead of drawing each
zone with the pen: about 30 minutes for a usual page against 4-8 hours by
hand, measured by testers on their own pages.    [O1, O3, O8, O14]
    Rubric: 1b — a tester asked to keep the app for this alone (O1); the
    testers are waiting for the release. Passes the Opposite Test only by
    measured domination (8-16x), so the number stays in the wording.

**S2.** Each zone holds a palette entry, never a raw colour: changing one
palette colour repaints every zone that uses it, across the page, in one
action.    [O2, O15]
    Rubric: 1a — removes repainting by hand, which most colour artists
    would see as a strength; one tester's visible delight (O2). Opposite
    (colour painted as pixels) is what bucket fills, flatters and AI
    colourisers all do.

**S3.** Open line art does not flood the page: Luikki closes most gaps where
bucket fills fail, and one dial per book sets how wide a gap still counts
as a hole in a line.    [O7, O13]
    Rubric: 1b — for artists with somewhat open inking, bucket fills are
    unusable; this alone makes flatting possible for them.
    = W1; deliberately both — see W1.

**S4.** Luikki never alters the line art and never paints the page
directly: every stage is a proposal the artist corrects, and generated
colour lands inside the artist's zones, where it edits like any other
flat.    [O5, O6, O16, O37]
    Rubric: 1b — testers reject every alternative for lacking exactly
    this (AI colourisers change the lines, O5; Colorize's gradients cannot
    be modified, O6). Opposite (take-it-or-leave-it repaint) is how the AI
    colourisers work.

**S5.** Everything runs on the artist's machine and the base mode works
fully offline; only panels sent to generation leave it, and a contract
clause forbids training on the artist's work.    [O33, O38]
    Rubric: 1a — in a community openly hostile to AI training on artists'
    work, more than a third would see this as a strength. 1b not yet
    evidenced: no tester has named it. Opposite (cloud-first, trains on
    uploads) is the norm among big AI and creative platforms.

**S6.** The artist deals directly with the one person who builds Luikki: a
tester's complaint comes back as a fixed release in one evening, and the
app is shaped live over video call with the artist's own page.    [O29, O24]
    Rubric: 1a, founder's call, not yet evidenced by a customer — authors
    who value a maker who answers would see it as a strength; the record
    behind it is the one-evening fix (O29), not an aspiration.
    = W4; deliberately both — see W4.

## Weaknesses

**W1.** The gaps Luikki misses come back as cuts, which pile up on loose,
artsy inking; cutting is the main complaint in sessions.    [O10, O12]
    Rubric: 2a — for loose, artsy inkers the pile of cuts is the main pain.
    = S3; deliberately both — segments disagree: clean inkers barely notice
    it, moderately open inkers love it (S3), very loose inkers pay for it
    in cuts (W1). A strategic choice is pending here.

**W2.** The generative colour (Cobra) gets a character about half right,
even with 10 references; outside manga and American-comics styles, or on
details no reference covers, it produces greys. The model cannot be
retrained or swapped — it is the only one of its kind.    [O9, O21, O35, O36]
    Rubric: 2a — anyone paying for the AI colour sees "half right" as a
    weakness; 2b — on franco-belgian pages that come out grey it is
    unusable. No tester praise names it (O9). O34 (the cloud runs a model
    too heavy for a PC) is supporting detail, not a strength.

**W3.** A page with a very detailed background comes out as hundreds of
tiny zones the artist sweeps and merges by hand; character-focused pages
run smoothly.    [O18]
    Rubric: 2a — background-heavy artists (realistic franco-belgian,
    detailed webtoon settings) would see it as a weakness; a pain, not a
    refusal, since the characters still go fast.

**W4.** Luikki is one person's side project with no public audience yet:
~200 views per video, no tester has spread the word, 12 of 15 authors
contacted never replied, two interested people dropped away, and the
certificates (Apple, Windows signing, domiciliation) are bought one at a
time.    [O4, O22, O23, O24, O28, O30, O31, O32]
    Rubric: 2b for studios and publishers — a solo side project with
    unsigned installers is reason alone to refuse (trust scored 0.1 in
    PROBLEM-SCORE.md A).
    = S6; deliberately both — segments disagree: studios and publishers
    read "one person" as a risk (W4); individual authors may read it as a
    maker who answers in one evening (S6). A strategic choice is pending.

## Cuts (nobody cares — attention stops here)

- Balloon polygons come out too big, so nearly every balloon needs fixing
  — a defect note, not an attribute: fails the mirrored Opposite Test (no
  one strategizes toward it) and is likely fixable without retraining
  (OBSERVATIONS side-list).    [O11]
- Works on any format (franco-belgian, manga, webtoon; open or closed
  panels) — no to both: nobody buys or refuses over it.    [O20]
- The brand (name, orange logo, violet surround) — no to both: customers do
  not buy for it; the founder's pride stays on record in the observations.
  [O17]

Supporting detail, no attribute of its own: O34 (the cloud runs a model too heavy for a
PC), O19-O20 (fit differential, carried in the preamble).

## Notes for downstream steps (parked, not attributes)

- The AI licence (50 €/yr) sells the weakest part of the product (W2),
  while every tester-backed strength (S1, S2, S4) is in the base licence —
  for definition, and for the pricing skills after this method.
- Franco-belgian and other non-manga styles come out grey (W2) — for
  deal-breakers: an anti-market for the AI colour, not for the base app.
- The founder stops if no customer comes within 6 months of going on sale
  (O25); a competitor is a worry, only Flagcat seen, in-house (O26); the
  founder reads the anti-AI backlash as fading (O27) — for definition, as
  context on the stakes and timing.
- Depth detection with artist-made lights and shadows (O39) — for
  inciting events / definition: a possible reason for colourists (not only
  flatters) to buy later.

## Next steps

Refine each strength into keystones — the characteristics, behaviours or
circumstances that make a customer NEED an extreme version of it (who needs
4-8 hours back per page badly enough to buy for that alone? who cannot use
bucket fills at all?) — and name the real market segments that typify each.
Then the mirror work on weaknesses: deal-breakers and the anti-market (loose
inkers, background-heavy pages, anyone buying for the AI colour). That is
`asb-carol-keystones`, and it works directly from this file.
