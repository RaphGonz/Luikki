# Luikki — Business Plan

Document status: draft 3
Date: 25 September 2026
Language: ASD-STE100 (Simplified Technical English)

> **Superseded in part on 1 October 2026 (ROADMAP G).** Luikki no longer
> makes colours: Cobra, the GPU and the panel quota are gone. Luikki cuts the
> page into panels, balloons, zones and depth planes, and exports a PSD with
> fake flat colours. There is one line: the licence, 10 € each year. The
> sections about the AI licence, the packs, the Studio line, the panel as a
> unit, the GPU cost and the revenue forecast (§2.2, §4, §5) describe the old
> offer. Their numbers must be done again.

Changes from draft 2: three lines only. No free line, no founder licence, no
colour pass, no regional price. The individual lines are cheap on purpose.
The studios are the target. The revenue forecast uses Jason Cohen's method:
populations in powers of ten, three conversion rates, and the growth ceiling.

---

## 0. How to read this document

This document uses ASD-STE100. Each sentence gives one idea. Each sentence
uses the active voice. Each sentence is 25 words or less.

Some words in this document are not in the STE dictionary. They are Technical
Names. This document uses them because the industry uses them:

| Technical Name | What it is |
|---|---|
| flatting | The task that puts one flat colour in each closed area of a page |
| flat | One area of flat colour, before the shadows |
| flatter | The person who does the flatting |
| colourist | The person who does the shadows and the light after the flatting |
| webtoon | A comic that you read as one vertical strip on a telephone |
| panel | One image frame on a comic page. The GPU colours one panel at a time |
| character sheet | A reference image that shows the colours of a character |
| MRR | The money that comes in each month from the subscriptions |
| seat | One computer that an account can use |

---

## 1. Summary

Luikki is a desktop application. It makes the flats for a comic page. The
artist keeps control of each step.

The market is small but it is real. The task is dull, and the industry pays
for it today. An author who does the flats alone does them 8 to 16 times
faster with Luikki (§3.1).

Luikki has three lines. The base licence costs 10 € each year. The AI licence
costs 50 € each year. The studios pay 150 € each month.

The individual lines cannot pay for the company. They bring the users and the
reputation. The studios bring the revenue. 20 000 € each month needs
approximately 133 studio accounts (§5).

---

## 2. The product

### 2.1 What the application does

The application has seven buttons. The artist pushes each button in order. No
step starts by itself.

1. Upload the page.
2. Find the panels. The artist corrects them.
3. Find the balloons. The artist corrects them.
4. Cut the page into zones. The artist merges and cuts the zones.
5. Propose a colour for each zone.
6. Snap the colours to the palette of the artist.
7. Write a PSD file.

Each zone holds an identifier of a palette entry. It does not hold an RGB
value. Thus one change to the palette changes the full page.

### 2.2 The two colour modes

The base mode is `distinct`. It gives a different colour to each zone. The
artist then clicks a palette colour on each zone. This is the classical
result of the flatting. It needs no GPU.

The AI mode is Cobra. It reads the character sheets of the project. Then it
gives the correct colour to each zone. The skin is skin. The jacket is the
jacket.

The artist selects the mode at step 5. The application never changes the
mode without the artist. A customer without the AI licence sees why, and
selects `distinct` or buys.

### 2.3 Where the data stays

The project stays on the machine of the artist. The pages stay there. The
palette stays there.

The AI mode is the one exception. For each panel that the artist sends to
generation, the cloud receives the masked panel and the references. It
returns one raster image. It keeps nothing.

Luikki does not train a model on the artwork of a customer. This is a
contract clause, not a promise. Put this clause on the first screen of the
web site.

Say the exception on the web site too. "Nothing leaves your computer" is
false for the AI mode. The correct sentence: "Nothing leaves your computer,
except the panels that you send to generation. We keep none of them. We
train on none of them."

### 2.4 What the customer buys

The source code of the application is public, under the PolyForm Shield
licence. Any person can read it, change it and use it, also for paid work. No
person can use it to supply a product that competes with Luikki.

The base licence sells the installer, the updates and the sign-in. The
application holds no licence check. A person can build the application from
GitHub and not pay. Accept this risk. GitHub is a wall for most artists, and
10 € costs less than one hour of that work.

The AI licence sells the colour service on the GPU. The server decides each
request. It checks the account, the rights, the panels left and the seats.
The application holds no secret.

Register the trademark "Luikki". The licence stops a competing product. The
trademark stops a product that uses your name.

---

## 3. The market

### 3.1 What the task costs today

A flatter charges 6 $ to 20 $ for each page. The usual rate is 10 $ to 15 $.

The test users measured the time of one page:

| Page | With Luikki | By hand |
|---|---|---|
| Simple | 10 minutes | — |
| Usual | 30 minutes | 4 to 8 hours |
| Complex | 1 hour | — |

On the usual page, Luikki is 240 / 30 = 8 to 480 / 30 = 16 times faster. It
saves 87 % to 94 % of the time. Say "approximately 10 times faster", and give
the range.

The 4 to 8 hours are the flats only, done by an author. The task is
mechanical and the author has no motivation for it. A professional flatter is
much faster: the public rate lists say two pages in one hour.

Thus the speed argument has one audience: **the author who does the flats
alone.** For this author, Luikki replaces 4 to 8 hours, or a flatter at 10 $
to 15 $ each page. 200 pages each year cost 2 000 $ to 3 000 $ at a flatter.
The AI licence costs 50 €.

A professional flatter at 30 minutes each page gains little time. Luikki only
removes the manual tracing of the zones. Do not sell speed to the flatters.

The studios are not measured yet. Their colourists are professionals, thus
fast. The argument for a studio is not "10 times faster". It is the AI
colours from the character sheets, and the cost of one episode. Measure one
episode with one studio colourist before the first studio sale.

### 3.2 The segments

| Segment | Population, world | Role for Luikki |
|---|---|---|
| Webtoon and vertical-comic studios | 10^3 | **The target.** They give the revenue |
| Colour authors who do their own flats | 10^4 professionals, 10^5 with the serious amateurs | The users of the individual lines. They give the reputation |
| Professional flatters and colourists | 10^3 to 10^4 | Not a target. They are as fast as Luikki |
| Japanese manga | 0 | Black and white. No colour work |

The populations are orders of magnitude. They are not counts. This is the
method of Jason Cohen: a factor of 2 does not change the decision, a factor
of 10 does.

**The studios.** Korea registered 18 792 webtoon titles in 2024. The
production houses are the largest type of webtoon company in the KOCCA survey.
China (manhua) and Japan (tateyomi) also make vertical colour comics. A studio
team has 6 to 12 persons. One colourist has 5 to 7 days for each episode. One
webtoon episode is a vertical strip of 60 to 80 panels.

The segment contracts. Korea registered 8 123 titles in the first half of
2025. This is 17,9 % less than one year before. Platforms close. Enter this
market now, but do not expect growth from the market itself.

**The individuals.** France has approximately 4 000 comic authors. The
URSSAF counts 744 comic artists and colourists. The English market has 1 000
to 3 000 possible customers. Tapas had 75 000 creators. WEBTOON counts 24
million creators, but most of them are amateurs who do not colour for money.

**The flatters.** Luikki does not replace the flatter. A professional
flatter is as fast as Luikki (§3.1). Some flatters can buy the base licence
for the comfort. They are not a target.

**Do not build a business on France alone.** France can give a few thousand
euros each month. It cannot give more.

### 3.3 The check from the top

Clip Studio Paint is the reference tool of this industry. It has 60 million
users. It has more than 1 million subscriptions. Its subscription revenue is
6,18 billion yen each year. This is approximately 35 million euros.

A tool for one step of the colour work takes a small part of this. The
theoretical ceiling for Luikki is 0,5 million to 3 million euros each year.
Luikki reaches this ceiling only as the world standard.

### 3.4 The price tier decides the sale

Jason Cohen puts each price in a power of ten. Each tier needs a different
number of customers and a different way to find them.

| Price each month | Customers for 1 M$ each year | How they come |
|---|---|---|
| 1 $ | 83 333 | Word of mouth only |
| 10 $ | 8 333 | Organic growth. No budget for marketing |
| 100 $ | 833 | Demonstrations and sales material |
| 1 000 $ | 83 | A real sales force |

The base licence is 0,83 € each month. The AI licence is 4,17 € each month.
Both lines are in the lowest tier. No advertisement pays for itself at this
price. Only the before/after videos and word of mouth bring these customers.

The Studio line is 150 € each month. It is in the 100 $ tier. A studio buys
after a demonstration. Put the sales effort here.

---

## 4. The price

### 4.1 The anchor

The customer already pays for one tool. Clip Studio Paint PRO costs 4,49 $
each month, or 63 $ one time. Procreate costs approximately 13 $ one time.
These tools do much more than Luikki.

The individual lines stay below these tools. This is a decision, and a test.
The fear is simple: an unknown tool at a high price does not sell.

**Know the cost of this decision.** Draft 2 said: "If the tool saves 80 %,
the prices here are too low." The tool saves 87 % to 94 % (§3.1). The time
saved supports a higher price. Test a higher price during the year (§4.7).

### 4.2 The unit: the panel

The GPU colours one panel at a time. Thus the GPU cost follows the panels, not
the pages. A page quota lets one webtoon episode cost 70 times one page.

Luikki counts panels everywhere: on the server, in the application, and in
the conditions. The application also shows the equivalent:

    1 000 panels ≈ 200 comic pages ≈ 14 webtoon episodes

Each generation of a panel counts one panel. A second generation of the same
panel counts one more panel. One panel is one panel.

### 4.3 The three lines

| Line | Price | Colours | Panels | Seats |
|---|---|---|---|---|
| **Base** | **10 € each year** | `distinct` and click-to-colour, no limit | — | — |
| **AI** | **50 € each year** | Base + Cobra | 1 000 each year | 2 |
| **Studio** | **150 € each month** | Base + Cobra | 5 000 each month | 3 |

The AI customer can add packs:

| Pack | Price | Price of one panel |
|---|---|---|
| 100 panels | 5 € | 0,050 € |
| 500 panels | 10 € | 0,020 € |
| 1 000 panels | 20 € | 0,020 € |

**Only an AI customer can buy a pack.** Without this rule, the base licence
and one pack of 1 000 cost 30 €, less than the AI licence. The packs exist
for one reason: the artist at the limit continues to work.

**Bought panels never expire.** The authors work in waves. The server uses
the panels of the licence first. Then it uses the bought panels.

The 1 000-panel pack gives no reduction on the 500-panel pack. Two packs of
500 cost the same. Keep it or remove it: it is one line less to explain.

### 4.4 Why the limits exist

1 000 panels each year is approximately 200 comic pages, or four albums. Most
authors never see the limit. A studio sees it in the first week.

Show the limit in the application, at the moment the customer reaches it. At
that moment, give two paths:

- Buy a pack.
- Move to the Studio line for 150 € each month.

The volume alone does not move a customer to Studio. The seats move the
customer. An individual account has 2 seats and generates one panel at a
time. A Studio account has 3 seats that generate at the same time.

### 4.5 The upper limit of the Studio line

The Studio line needs an upper limit. Without it, one webtoon studio makes the
GPU invoice. This is the calculation, from the measured cost.

The measurement: 13 September 2026, on Modal, with one L4 GPU. Two work
sessions, each on one page of 3 panels, gave the same values.

| Item | Measured value |
|---|---|
| Cold start: the container starts and loads the model | 30 s, one time in each session |
| First panel after a cold start | 15 s |
| Each next panel | 10,4 s on average, from 10,0 s to 11,0 s |
| Idle time before the GPU stops | 120 s, from the Modal configuration |
| Modal invoice for the full day of tests | 0,10 $ |

The invoice agrees with 1,00 $ each hour for the L4, with CPU and memory.

The other values:

| Item | Value | Source |
|---|---|---|
| Exchange rate | 1 € = 1,10 $ | Assumption |
| Payment fees | 3,5 % Managed Payments + approximately 1,5 % card + 0,25 € | Stripe |
| GPU budget | 25 % of the net revenue | Decision |

The costs:

- One second of GPU costs 1,00 $ / 3 600 / 1,10 = 0,00025 €.
- One panel costs 10 × 0,00025 = 0,0025 €.
- One work session costs 150 s of start and idle time, thus 0,04 €.
- One page of 3 panels, alone in its session, costs approximately 0,05 €. The
  start and the idle time cost more than the panels.

The Studio line:

- Net revenue: 150 € − 5 % − 0,25 € = 142,25 € each month.
- GPU budget: 25 % of 142,25 € = 35,50 € each month.
- Sessions: 3 seats × 2 sessions each day × 22 days = 132 sessions = 5,30 €.
- Budget for the panels: 35,50 € − 5,30 € = 30 €.
- Panels: 30 € / 0,0025 € = 12 000 panels each month.

**The limit stays at 5 000 panels each month.** 5 000 panels and the sessions
cost 17,80 €, thus 13 % of the net revenue. Change the limit only after the
measurement on 10 accounts.

The check against the real work:

- One webtoon colourist does 4 to 6 episodes each month, thus 280 to 420
  panels. Three seats do 840 to 1 260 panels.
- Three comic colourists do approximately 5 albums each month, thus 3 750
  panels.

5 000 panels is 4 times a normal webtoon team. A normal studio never sees the
limit. At the limit, the studio buys packs or asks for a quote.

### 4.6 The margin on each line

| Line | Net revenue | GPU | Margin |
|---|---|---|---|
| Base, 10 € | 9,25 € each year | 0 € | 9,25 € each year |
| AI, 50 € | 47,25 € each year | 2,60 € for 250 panels in 50 sessions | 44,65 € each year |
| AI, at the full 1 000 panels | 47,25 € each year | 6,50 € for 1 000 panels in 100 sessions | 40,75 € each year |
| Pack of 100, 5 € | 4,50 € | 0,25 € + approximately 1 € of sessions | ≈ 3,25 € |
| Studio, 150 € | 142,25 € each month | 9 € for a normal studio, 17,80 € at the limit | 124 € to 133 € each month |

The Stripe fees take 10 % of a pack of 100, because of the 0,25 € fixed fee. The GPU is not a
risk on any line. The work time of the founder is the real cost. This table
does not count it.

### 4.7 The price and the cost

The price does not come from the cost. The measured cost is a floor. It is not
a reason to reduce a price. A low price tells the customer that the product
has a low value.

Test the prices during the year. Make promotions. For some weeks, multiply a
price by two. Write down each test and its sales.

The measurements of the cost are the ground truth. The prices are experiments.

### 4.8 The fixed costs

| Item | Cost | When |
|---|---|---|
| Trademark "Luikki" at the INPI | approximately 200 € | One time |
| Apple Developer | 99 $ each year | Each year |
| Windows code signature | approximately 10 $ each month | Each month |
| Hosting, accounts, e-mail (Modal, Supabase, Resend) | Free tiers today | Each month |
| The time of the founder | Not counted | Each day |

---

## 5. The revenue

### 5.1 The method

This forecast uses the method of Jason Cohen. It does not guess a number of
customers. It takes a population, a rate of conversion and a rate of loss.
Then it gives three scenarios, each ten times the one before.

| Assumption | Value |
|---|---|
| Individuals, world | 100 000 (10^5) |
| Studios, world | 1 000 (10^3) |
| Conversion each year | 0,1 %, 1 % or 10 % of the population |
| Individuals who take the AI licence | 30 % |
| AI customers who buy one pack of 500 each year | 20 % |
| Individuals who do not renew | 40 % each year |
| Studios that stop | 3 % each month |

One paying individual gives 22,60 € each year, 20,40 € net. One studio gives
150 € each month, 133 € net.

The script `reports/business/projections.py` holds each assumption as one
constant. Change one value and run it again.

### 5.2 Three years, three scenarios

| Scenario | Year 1 | Year 2 | Year 3 | Year 3, each month |
|---|---|---|---|---|
| 0,1 %: +100 individuals, +1 studio each year | 3 000 € | 5 700 € | 7 400 € | 620 € |
| 1 %: +1 000 individuals, +10 studios each year | 30 300 € | 56 800 € | 73 900 € | 6 200 € |
| 10 %: +10 000 individuals, +100 studios each year | 302 500 € | 567 800 € | 739 100 € | 61 600 € |

The revenue is gross, before the payment fees and the GPU. The net revenue is
approximately 90 % of the gross revenue.

At the end of year 3, the 1 % scenario has 1 960 individuals and 18 studios.
The individuals give 60 % of the revenue. But the individuals are 100 times
more numerous. One studio gives as much as 80 individuals.

The 10 % scenario is not a plan for one person. 100 new studios each year is
8 sales each month, with demonstrations. It needs a sales person.

### 5.3 The growth ceiling

Jason Cohen gives one equation:

    maximum MRR = new MRR each month / rate of loss each month

| Scenario | Individuals | Studios | Total ceiling each month |
|---|---|---|---|
| 0,1 % | 470 € | 420 € | 890 € |
| 1 % | 4 700 € | 4 200 € | 8 900 € |
| 10 % | 47 100 € | 41 700 € | 88 800 € |

The business stops its growth at this ceiling. A larger market does not move
it. Only more new customers or less loss move it.

### 5.4 What 20 000 € each month needs

| Target | From the studios alone | From the individuals alone |
|---|---|---|
| 20 000 € each month | 133 accounts, 4 new each month | 10 600 paying, 4 250 new each year |
| 50 000 € each month | 333 accounts, 10 new each month | 26 500 paying, 10 600 new each year |

4 new studios each month is possible for one person who sells. 4 250 new
individuals each year at 10 € to 50 € is not possible without a viral video.

**Put the effort on the studios.** The individual lines are the shop window.
The studios are the business.

---

## 6. The risks

| Risk | Effect | What to do |
|---|---|---|
| The webtoon market contracts | The volume segment becomes smaller | Enter now. Do not wait. |
| The artists refuse the AI | No sale, whatever the price | Show the no-training clause first |
| A free tool does the same task | The price falls to zero | Sell the control, not the colours |
| A person builds the application from GitHub | Loss of one base licence | Accept it. The AI and the Studio lines stay on the server |
| One account runs on five machines | Loss of revenue | The server counts the seats at each panel |
| Many jobs start at the same time | A large GPU invoice | One job for each seat, and a limit of GPUs |
| The GPU time of one panel increases | Heavy customers cost money | Measure again. Reduce the panels in the database |
| Cobra fails on some artwork | The customer asks for the money back | The base mode always works |
| The low price says "low value" | The studios do not trust the tool | Studio is 150 €, not 15 €. Test higher individual prices |

### 6.1 The free tools

Clip Studio Assets gives free actions for the flats. Clip Studio Paint has a
colour function. Petalica Paint and Webtoon AI Painter exist on the web.

Research shows why the professionals do not use them. They give no control.
One professional said the tool puts random colours in the image.

Luikki answers this. The geometry is correctable. The output of the model is
never visible. Each zone holds a palette identifier.

**This is the argument to sell. Research proves it. Put it at the top of the
web site.**

### 6.2 The technical protection

The monthly limit does not protect the GPU invoice. The peak protects it.

The server already does these things at each panel, before the GPU starts:

1. It checks the session of the account.
2. It checks the rights and the panels left.
3. It counts the seats. A new computer takes a free seat, or the server
   refuses it.
4. It permits one job for each seat. A second job from another address is
   refused and written to the log.
5. It limits the number of GPUs for all the accounts.

Do not put the seats in a JWT. The code of the application is open source. A
person can change a check in the application. A person cannot change a check
on the server.

---

## 7. The next steps

### 7.1 Now, during the user tests

Ask each test user four questions. Write the answers down.

1. How many panels do you colour each month? How many pages?
2. Is your rhythm continuous, or does it come in waves?
3. Who pays: you, a studio, or a publisher?
4. How long does one page take you today? (Answered for the authors: 4 to 8
   hours of flats. To measure with one studio colourist.)

### 7.2 Then, in order

| Step | Status on 25 September 2026 |
|---|---|
| 1. Finish the local application. Connect the project store. | Done |
| 2. Package the application. Sign the Windows build. | Package done. Signature to do |
| 3. Open the payment. | Works in test mode, with the draft 2 lines. Change to the three lines |
| 4. Measure the GPU time of one panel. | First measurement done: 10,4 s each panel, 30 s of cold start, 1 $ each hour (§4.5) |
| 5. Measure the real cost on 10 accounts. | To do |
| 6. Publish the Korean web site. | To do |
| 7. Contact 20 webtoon studios. | To do |

### 7.3 About the Korean web site

The Korean web site is not a translation. It is a different sale.

| | The individual | The studio |
|---|---|---|
| Buys with | A card, on line | An invoice, each year |
| Counts in | Panels, shown as pages | Panels, shown as episodes |
| Wants to hear | The time saved | The cost of each episode |
| Needs | A buy button | A quote form |

The server counts panels for all the customers. The application shows
"1 000 panels ≈ 200 pages" to the comic artists. The web site shows
"5 000 panels ≈ 70 episodes" to the webtoon studios.

---

## 8. Sources

- Jason Cohen, A Smart Bear, "Pricing determines your business model" — the
  price tiers in powers of ten
  (https://longform.asmartbear.com/pricing-determines-your-business-model/)
- Jason Cohen, A Smart Bear, "Max MRR: your growth ceiling" — the growth
  ceiling (https://longform.asmartbear.com/max-mrr/)
- Freemium and trial benchmarks, 2026 — 2 % to 5 % for SaaS, 1 % to 3 % for
  creative tools
- Celsys, company announcements, 2025 and 2026 — the Clip Studio Paint users,
  subscriptions and revenue
- Clip Studio, price pages — the subscription prices and the perpetual prices
- KOMACON and KOCCA, distribution statistics 2024 and first half of 2025 —
  the webtoon titles
- KOCCA, webtoon industry survey 2025 — the size of the Korean market and the
  types of companies
- WEBTOON Entertainment, SEC S-1 filing, 2024 — the 24 million creators
- Tapas, 2026 — the 75 000 creators
- États Généraux de la Bande Dessinée, author survey 2025 — the French
  authors
- URSSAF, artist-author data — the French comic artists and colourists
- Public rate lists of the flatters, 2021 to 2026 — the price of each page
- Test users of Luikki, September 2026 — the time of one page
- Stripe, Managed Payments pricing — 3,5 % for each transaction, plus the
  standard processing fees
- Modal, request logs and invoice of 13 September 2026 — the GPU time of one
  panel, the cold start, and the real cost of one hour of L4
