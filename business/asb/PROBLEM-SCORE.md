# Problem Score — Luikki, AI flatting for webtoon studios

Final, 27 September 2026. Three buyer types looked at: A studios (scored),
C colour authors (scored), publishers (rough shape only, from collapsed C2).

## Target market (Scenario A)
Buyer: French/European studios and publisher labels that produce colour
webtoons in-house with their own artist team (named: Flagcat, Ankama /
Allskreen; seen in research: Ellipse Studio Angoulême) · Problem: flatting
and first-pass colour on every episode costs colourist days · Trade-offs:
the artist corrects every stage; layered PSD out, no pipeline integration
beyond it; colours from character sheets (Cobra); pages stay local except
panels sent to generation · Price: 150 €/month (5 000 panels, 3 seats) ·
Ambition: indie, salary-replacing independence; more is welcome, scale is
not the goal · Evidence: two named studios, no conversation yet; Flagcat
already runs proprietary character-colouring automation; tester timings are
from authors, not studios.

Korea dropped from A: no names, no footing; local studios are reachable.
KOMACON, named at first, is the Korean government agency, not a buyer.

## Scores (Scenario A)
| Criterion | Value | Justification | Class |
| :-- | :-- | :-- | :-- |
| Plausible | 100 | Studios/labels colouring webtoons in-house: tens in France, ~100 in Europe. No census exists; Protoon's member list is the nearest. Below the 1k floor of the scale and 3 orders under the ~100k B2B benchmark — niche exception applies only if the other six are strong. Ceiling at 150 €/mo: ~180 k€/yr with every studio signed. User agreed. | [research] |
| Self-Aware | 0.5 | Flatting is a named, paid job; every artist complains about flats; Ankama builds tools so its artists stop running late; Flagcat automates character colouring. Standard practice. User proposed 0.3 (off-scale, refused); their arguments support 0.5. The AI-acceptance question moved to Eager (identity). | [research] |
| Lucrative | $1k | User: Luikki comes from the tool budget line, not the colour/staff budget — it speeds artists up, it does not replace them. A tool line of ~$1k/yr per studio is consistent with what studios pay for software seats (CSP, Photoshop). Gap: the Studio sticker (150 €/mo ≈ $2k/yr) is above the allocation scored; either the tool line stretches or the sale must reach the colour budget (flatting ≈ $20-40k/yr per studio, Fermi). "10x faster" is measured on authors, not studio colourists. | [fermi] |
| Liquid | 0.1 | Workflow changes happen at production start (Ankama plans quarterly cycles of three series); mid-series retraining risks deadlines already late; Flagcat locked into its own tool; studio IT sign-off. Chosen by user as conservative. Note: Luikki is additive (PSD in front of PS/CSP, monthly, nothing to migrate) — if interviews show studios try tools mid-series, 1.0 is arguable and the total rises x10. | [fermi] |
| Eager (identity) | 0.1 | Solo founder, micro-entreprise, 0.x version; AI stigma in the French scene even with generation masked; unreleased panels sent to a cloud GPU may breach publisher NDAs (near-0 for some buyers, unchecked). Partial mitigations: source-available code as escape hatch, contractual no-training, offline base mode, local French founder. Agreed by user. | [fermi] |
| Eager (comparative) | 0.5 | Output is true flats a colourist keeps working on (corrected zones, palette ids, layered PSD), which the uncontrolled AI colourisers do not give. Not proven against 'change nothing' or a home-built tool (Flagcat). User hesitated between 0.5 and 1.0, settled on 0.5. | [fermi] |
| Enduring | 0.5 | Recurring problem (every episode, weekly) on a recurring subscription. No retention data (plan's 3%/mo studio churn is an assumption); studios close (Korean titles -17.9% in a year; Delitoon absorbed into Lezhin); zero switching cost since output is a standard PSD. Agreed by user. | [fermi] |

**Total: 100 × 0.5 × 1 000 × 0.1 × 0.1 × 0.5 × 0.5 = 125 ÷ 625,000 = 0.0002**
— not viable as scored; four orders of magnitude under the indie bar of ~1.
Weak links: Plausible (100 buyers vs the ~100k benchmark) and Lucrative
($1k tool line). Eager (identity) 0.1 is the most fixable.

---

# Scorecard C — colour authors who flat their own pages
(A different buyer type from A: its own scorecard, not a scenario of A.)

## Target market (Scenario C)
Buyer: professional comic/webtoon colour artists in France and the
English-speaking market who do careful flats by hand on their own or others'
pages — authors who colour themselves, and colourists/flatters who work at
that level of care (not the fast commercial 2-pages-an-hour flatting) ·
Problem: 4-8 hours of flats per usual page · Trade-offs: as A · Price: AI
licence 50 €/yr · Ambition: indie · Evidence: 3 professional testers
(franco-belgian to manga; 1 published, 2 unpublished but well known; all
have done flats as a paid job), measured 30 min with Luikki vs 4-8 h by hand
on their real work; user knows more like them.

Correction to business-plan.md §3.1: the testers are former paid flatters
and really take 4-8 h per page (careful flats). "Professional flatters are
not a target" holds only for fast commercial flatting; careful-flats
flatters and colourists are in this buyer.

## Scores (Scenario C)
| Criterion | Value | Justification | Class |
| :-- | :-- | :-- | :-- |
| Plausible | 10k | France ~4 000 comic authors (744 URSSAF-registered artists/colourists); English market 1-3k plausible customers; plan's own 10^4 pros. Serious amateurs (Tapas/Canvas) mostly excluded by 'professional, careful flats'. Three orders under the ~10M consumer benchmark. User agreed. | [research] |
| Self-Aware | 1.0 | Not creative, nobody likes it; some authors stay in black and white to avoid it; one tester abandoned a large crowdfunded project over the flats and refunded every backer. Pain is felt and costly, not tolerated. | [data] |
| Lucrative | $10 | Testers never paid anyone for flats; they pay in hours. Demonstrated spend is on general tools, the user's anchor being Procreate (~13 $ once); CSP PRO ~50 $/yr. Some authors in this buyer pay flatters (10-15 $/page), testers do not. Gap: the AI licence (50 €/yr ≈ 55 $) is above the allocation scored. User agreed. | [fermi] |
| Liquid | 1.0 | Individual purchase: no procurement, no retraining, card and download; additive (PSD into PS/CSP), nothing to migrate; the pain recurs every page; an app next to their tools, no complicated setup. Testers are actively waiting for the app to be finished. | [data] |
| Eager (identity) | 0.5 | Solo founder is not a red flag for individuals at 50 €/yr (source-available as escape hatch); own art, no NDA; no-training clause and artist control are the opposite of what the community hates. One red flag: AI stigma, public identity at stake. User believes testers would endorse publicly if the control is hammered home. Risk noted: framing Cobra as just "machine learning" invites a worse callout if the community finds a diffusion model inside; honest framing is safer. | [fermi] |
| Eager (comparative) | 1.0 | Nothing else gives careful, editable flats at ~30 min/page: by hand is 4-8 h and fails deadlines and ambitions (one tester abandoned a funded project over it); actions/scripts only speed the manual method; a flatter costs ~2 000 $/yr; AI colourisers give no flats and no control. Holds until Clip Studio or a rival ships controllable flats — the score to watch. | [data] |
| Enduring | 0.5 | Recurring problem (every page of every project) on a yearly licence. Hurts: authors work in waves, so between-project renewals lapse; plan's 40%/yr non-renewal is an assumption; standard PSD means zero switching cost. Agreed by user. | [fermi] |

**Total: 10 000 × 1.0 × 10 × 1.0 × 0.5 × 1.0 × 0.5 = 25 000 ÷ 625,000 = 0.04**
— not viable as scored, but 200× Scorecard A. The product-side scores are
near perfect (Self-Aware, Liquid, Comparative all 1.0); the weak links are
the market's shape: Plausible (10k vs the ~10M consumer benchmark) and
Lucrative ($10 demonstrated spend).

## Scenario C2 — authors who pay for flats, ~15 €/month (collapsed)
Proposed: Plausible 1k, Lucrative $1k → 0.4. Collapsed at the name test:
authors do not pay flatters; publishers (éditeurs) hire flatters to back up
their authors. The author has the pain, the publisher has the budget. C2 is
therefore a different buyer type — publishers — and needs its own scorecard,
not a scenario of C. Rough, unscored shape: Plausible ~100-1k publishers
colouring albums in Europe; Lucrative ~$10k (flatter budget); Liquid and
Identity pulled down as for A.

## Verdict & next steps

| Scorecard | Score | Reading |
| :-- | :-- | :-- |
| A — European webtoon studios, 150 €/mo | 0.0002 | Not viable: ~100 buyers, tool budget below the price, trust gap |
| C — colour authors, 50 €/yr | 0.04 | Not viable as priced, but the product scores 1.0 on three criteria backed by data |
| Publishers who hire flatters (unscored) | ~0.004-0.04 | Real flatting budget, few buyers; capped like A |

**No buyer reaches ~1 on its own.** The weak links are all market shape
(Plausible, Lucrative), never the product: where there is data, Luikki wins.

**The finding that matters: the author has the pain, the publisher has the
budget.** The offer to test is not a new market but a new payer — the
publisher buys Luikki licences for its authors instead of paying a flatter
10-15 $ per page.

**Against business-plan.md:** its target (studios, 133 accounts for
20 k€/mo) exceeds the whole European studio market; Korea was the only way
it worked and is out of reach. The authors are not the shop window; they are
the only buyer where the product demonstrably wins.

**What the score does not measure:** reach (good: studios and publishers are
nameable, authors talk to each other), execution, costs, founder time.

**[fermi] scores to convert into evidence by interview:**
- Publishers: would they pay for authors' licences in place of a flatter?
  Whose budget, who signs? (first hypothesis for asb-interview-*)
- Studios: Liquid (would they try a tool mid-series?), Identity (may
  unreleased panels leave the building under their publisher contracts?)
- Authors: Enduring (renewal between projects; the 40 %/yr is a guess),
  Identity (will a known tester endorse publicly?)

## Sources
- Flagcat: https://www.flagcat.studio/en ·
  https://www.vestbee.com/insights/articles/flagcat-secures-2-5-m
- Ankama / Allskreen: https://www.actuabd.com/Ankama-lance-sa-nouvelle-plateforme-de-webtoons
- Ellipse Studio: https://www.ellipseanimation.com/ellipse-animation-expands-its-activities-to-the-production-of-webtoons/
- French webtoon sector, Protoon association:
  https://actualitte.com/article/132060/enquetes/le-webtoon-francais-une-filiere-en-quete-de-reconnaissance
- French platforms 2026: https://casescritiques.fr/webtoon-francais-guide-plateformes/
