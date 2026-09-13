# Luikki — Business Plan

Document status: draft 2
Date: 13 September 2026
Language: ASD-STE100 (Simplified Technical English)

Changes from draft 1: the unit of sale is the panel, not the page. The Studio
line has a calculated upper limit. Bought panels never expire. The seats stay
on the server, not in a JWT. The payment stays on Stripe.

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
| SLA | A contract that promises a level of service |
| seat | One computer that an account can use |

---

## 1. Summary

Luikki is a desktop application. It makes the flats for a comic page. The
artist keeps control of each step.

The market is small but it is real. The task is dull, and the industry pays
for it today. Luikki does the task 10 times faster.

Luikki sells colours, counted in panels. The first purchase costs 69 € one
time. Then the colours cost 39 € each year. The studios pay 149 € each month.
The individual artists give the reputation. The studios give the revenue.

The realistic target is 20 000 € to 50 000 € each month. The market cannot
give more than this. Plan for a company of one person or two persons.

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

The free mode is `distinct`. It gives a different colour to each zone. This
is the classical result of the flatting. It needs no GPU.

The paid mode is Cobra. It reads the character sheets of the project. Then it
gives the correct colour to each zone. The skin is skin. The jacket is the
jacket.

The artist selects the mode at step 5. The application never changes the
mode without the artist. A customer without colours sees why, and selects
`distinct` or buys.

The frontier between the two modes is clear. The artist sees it in one
screenshot. This makes the sale easy.

### 2.3 Where the data stays

The project stays on the machine of the artist. The pages stay there. The
references stay there. The palette stays there.

The cloud is one authenticated GPU endpoint. It is not a SaaS. It receives
one panel. It returns one raster image. It keeps nothing.

Luikki does not train a model on the artwork of a customer. This is a
contract clause, not a promise. Put this clause on the first screen of the
web site.

### 2.4 What the customer buys

The source code of the application is public, under the PolyForm Shield
licence. Any person can read it, change it and use it, also for paid work. No
person can use it to supply a product that competes with Luikki.

Luikki does not sell a key for the application. Luikki sells the colour
service on the GPU.

The server decides each request. It checks the account, the rights, the
panels left and the seats. The application holds no licence and no secret.

A person can run Cobra on a personal GPU from the source code. The licence
permits this. This person is not the target customer. The price protects
against this person, not the licence.

Register the trademark "Luikki". The licence stops a competing product. The
trademark stops a product that uses your name.

---

## 3. The market

### 3.1 What the task costs today

A flatter charges 6 $ to 20 $ for each page. The usual rate is 10 $ to 15 $.
A good flatter does two pages in one hour.

After the flatter, the colourist takes approximately three hours for each
page. The colourist hires the flatter. The publisher does not hire the
flatter.

A comic page has approximately 5 panels. With a pack, Luikki colours one page
for approximately 0,10 €. The ratio is 100 to 1. The customer does not need a
calculation.

### 3.2 The four segments

| Segment | Pages each year | Possible customers | Note |
|---|---|---|---|
| French comics | 75 000 | 150 to 400 | The home market. It is too small. |
| English comics | 80 000 | 1 000 to 3 000 | Sensitive to the price |
| Webtoon | 300 000 episodes | 2 000 to 10 000 | The volume is here |
| Japanese manga | 0 | 0 | Black and white. No colour work. |

**French comics.** France publishes approximately 5 500 new comic titles each
year. But 3 212 of the 2024 titles were manga. Japan produced those manga.
France did not. The real French production is 2 000 to 2 500 albums.

The URSSAF counts 744 comic artists and colourists in France. It counts 307
writers. The full population is approximately 4 000 authors. More than half
of them earn less than the minimum wage.

**Do not build a business on France alone.** France can give a few thousand
euros each month. It cannot give more.

**Japanese manga is a zero.** Japan is the largest comic market in the world.
Its manga are black and white. They have no flats and no colourist. Do not
translate the web site into Japanese for the manga publishers. Translate it
for the webtoon studios.

**Webtoon has the volume.** Korea registered 18 792 webtoon titles in 2024. A
webtoon series has approximately 150 episodes. A studio team has 6 to 12
persons. One colourist has 5 to 7 days for each episode. That colourist does
the flatting, the shadows and the effects.

One webtoon episode is not one page. It is a vertical strip of 60 to 80
panels. For the GPU, one episode costs as much as 14 comic pages.

But the segment contracts. Korea registered 8 123 titles in the first half of
2025. This is 17,9 % less than one year before. Platforms close. Enter this
market now, but do not expect growth from the market itself.

### 3.3 The check from the top

Clip Studio Paint is the reference tool of this industry. It has 60 million
users. It has more than 1 million subscriptions. Its subscription revenue is
6,18 billion yen each year. This is approximately 35 million euros.

A tool for one step of the colour work takes a small part of this. The
theoretical ceiling for Luikki is 0,5 million to 3 million euros each year.
Luikki reaches this ceiling only as the world standard.

### 3.4 The real limit

The market is not the limit. The rate of the new customers is the limit.

Use this equation:

    maximum MRR = new MRR each month / rate of loss each month

With 25 new customers each month at 30 €, and a loss of 5 %, the maximum MRR
is 15 000 €. To triple this number, triple the rate of the new customers. Do
not look for a larger market.

---

## 4. The price

### 4.1 The anchor

The customer already pays for one tool. Clip Studio Paint PRO costs 4,49 $
each month, or 63 $ one time. Clip Studio Paint EX costs 8,99 $ each month,
or 277 $ one time. Clip Studio Paint reduces these prices four times each
year.

The customer pays approximately 77 $ each year for the tool that does
everything. Do not ask more than this for a tool that does one step.

This industry knows the perpetual licence. It does not like the monthly
subscription. Sell one payment, not a subscription, to the individuals.

### 4.2 The unit: the panel

The GPU colours one panel at a time. Thus the GPU cost follows the panels, not
the pages. A page quota lets one webtoon episode cost 70 times one page.

Luikki counts panels everywhere: on the server, in the application, and in
the conditions. The application also shows the equivalent:

    1 000 panels ≈ 200 comic pages ≈ 14 webtoon episodes

Each generation of a panel counts one panel. A second generation of the same
panel counts one more panel. One panel is one panel.

### 4.3 The lines

| Line | Price | Colours | Panels | Seats |
|---|---|---|---|---|
| Free | 0 € | `distinct` only | — | — |
| **Luikki** | **69 €, one time** | Cobra for 1 year | 1 000 each month | 2 |
| Colour pass | 39 € each year | Cobra for 1 more year | 1 000 each month | 2 |
| Panel pack | 19 € | — | +1 000, never expire | — |
| Studio | 149 € each month | Cobra | 5 000 each month | 3 |
| Founder | 249 €, 100 units | Cobra for 1 year | 1 000 each month, and +5 000 that never expire | 2 |
| Production | Annual quote | Cobra | Volume | SLA |

One sentence says the full model: **69 € one time, then 39 € each year for
the colours.**

If the customer does not buy the colour pass, the application continues to
work. The artist selects `distinct` at step 5. The customer loses no project
and no file.

**Bought panels never expire.** The authors work in waves. An author colours a
full album in one year, stops for some months, then comes back. The panels of
a pack and of a founder licence wait for the author.

The server uses the panels of the month first. Then it uses the bought
panels. The bought panels work without a colour pass.

### 4.4 Why the limits exist

The limit of 1 000 panels is the frontier between one artist and one studio.
A comic album has 46 to 54 pages, thus approximately 250 panels. An artist
never sees the limit. A studio sees it in the first week.

Do not show the limit on the price page. Put it in the conditions. Show it in
the application, at the moment the customer reaches it.

At that moment, give two paths:

- Buy one pack of 1 000 panels for 19 €.
- Move to the Studio line for 149 € each month.

The Studio line costs less than the packs after 8 packs in one month. Thus the
volume alone does not move a customer to Studio. The seats move the customer.
An individual account has 2 seats and generates one panel at a time. A Studio
account has 3 seats that generate at the same time.

### 4.5 The upper limit of the Studio line

The Studio line needs an upper limit. Without it, one webtoon studio makes the
GPU invoice. This is the calculation.

The assumptions:

| Item | Value | Source |
|---|---|---|
| GPU | 0,80 $ each hour for one L4, 1,00 $ with CPU and memory | Modal price list |
| Exchange rate | 1 € = 1,10 $ | Assumption |
| GPU time for one panel | 20 seconds, warm | Assumption. Not measured. Pessimistic |
| One work session | 60 s of cold start and 120 s of idle time | Modal configuration |
| Payment fees | 3,5 % Managed Payments + approximately 1,5 % card + 0,25 € | Stripe |
| GPU budget | 25 % of the net revenue | Decision |

The costs:

- One second of GPU costs 1,00 $ / 3 600 / 1,10 = 0,00025 €.
- One panel costs 20 × 0,00025 = 0,005 €.
- One work session costs 180 × 0,00025 = 0,046 €.

The Studio line:

- Net revenue: 149 € − 5 % − 0,25 € = 141 € each month.
- GPU budget: 25 % of 141 € = 35 € each month.
- Sessions: 3 seats × 2 sessions each day × 22 days = 132 sessions = 6 €.
- Budget for the panels: 35 € − 6 € = 29 €.
- Panels: 29 € / 0,005 € = 5 700 panels. **Round down to 5 000 panels each
  month.**

The check against the real work:

- One webtoon colourist does 4 to 6 episodes each month, thus 280 to 420
  panels. Three seats do 840 to 1 260 panels.
- Three comic colourists do approximately 5 albums each month, thus 3 750
  panels.

5 000 panels is 4 times a normal webtoon team. A normal studio never sees the
limit. At the limit, the studio buys packs or asks for a Production quote.

### 4.6 The condition on the individual lines

The individual lines have a risk. A customer who uses 1 000 panels each month
costs more than the price.

| Line | Net revenue each year | Break-even at 20 s each panel | Break-even at 10 s each panel |
|---|---|---|---|
| Luikki, 69 € | 65 € | 830 panels each month | 1 660 panels each month |
| Colour pass, 39 € | 37 € | 430 panels each month | 860 panels each month |

The calculation removes 24 € each year for the work sessions at 69 €, and
10 € at 39 €.

Most customers do approximately 250 panels each month. Thus the average
customer gives a margin. But a heavy customer on the colour pass costs money.

**Measure the GPU time of one panel before the public sale.** If one panel
takes more than 10 seconds, reduce the monthly panels of the colour pass. The
limit is one row in the database. The change needs no new version of the
application.

### 4.7 The regional price

Many flatters live in Latin America, Indonesia and the Philippines. 69 € is
not the same amount there.

Stripe gives a price for each currency. Set lower prices in the local
currencies of these regions. Start this function on the first day. Do not
reduce the world price to solve a regional problem.

Stay on Stripe. The payment chain works today, with Managed Payments. Stripe
is the merchant of record and pays the VAT. A move to Paddle or Lemon
Squeezy repeats this work.

### 4.8 What this model costs you

This model removes the loss of customers. A one-time payment cannot churn.

But it gives you a different problem. The revenue from the individuals is not
recurrent. Each month starts at zero on that line.

Your MRR comes from the Studio line and the Production line. The individuals
give the cash and the reputation. Accept this. It agrees with section 3.

---

## 5. The revenue

### 5.1 Now: the founder licences

Sell 100 founder licences at 249 €. The cloud exists and works. Start the
sale now.

Each founder licence gives:

- The Luikki line: Cobra for 1 year and 1 000 panels each month.
- 5 000 panels that never expire, approximately 1 000 pages.
- The name of the customer in the credits.

The server counts the founder licences. It stops the sale at 100.

This sale does three things. It tests the payment chain on real money. It
gives approximately 25 000 € for the GPU start. It answers one question: does
a person pay?

**If you sell less than 30 founder licences, stop the price work.** The
problem is the product, not the price.

### 5.2 An example, not a forecast

| | Year 1 | Year 2 |
|---|---|---|
| New Luikki purchases at 69 € | 400 → 27 600 € | 800 → 55 200 € |
| Colour pass at 39 € | 0 € | 250 → 9 750 € |
| Packs at 19 € | 60 → 1 140 € | 150 → 2 850 € |
| Studio at 149 €/month | 8 accounts → 7 200 € | 30 accounts → 53 600 € |
| **Total** | **≈ 36 000 €** | **≈ 121 000 €** |

The Studio line gives 20 % of the revenue in year 1. It gives 44 % in year 2.
This is the direction of the business.

One Studio customer equals 26 individual purchases. The work to find one
Studio customer is not 26 times larger. Put the effort on the studios.

---

## 6. The risks

| Risk | Effect | What to do |
|---|---|---|
| The webtoon market contracts | The volume segment becomes smaller | Enter now. Do not wait. |
| The artists refuse the AI | No sale, whatever the price | Show the no-training clause first |
| A free tool does the same task | The price falls to zero | Sell the control, not the colours |
| One account runs on five machines | Loss of revenue | The server counts the seats at each panel |
| Many jobs start at the same time | A large GPU invoice | One job for each seat, and a limit of GPUs |
| One panel costs more than 0,5 cent | The colour pass loses money | Measure. Reduce the monthly panels in the database |
| Cobra fails on some artwork | The customer asks for the money back | The free mode always works |

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
4. How long does one page take you today?

Two numbers change this full document: the panels each month, and the time
saved for each page. If the tool saves 80 %, the prices here are too low. If
it saves 30 %, 69 € is too much.

### 7.2 Then, in order

| Step | Status on 13 September 2026 |
|---|---|
| 1. Finish the local application. Connect the project store. | Done |
| 2. Package the application. Sign the Windows build. | Package done. Signature to do |
| 3. Open the payment. Start the regional price. | Payment works in test mode. Panels and regional price to do |
| 4. Measure the GPU time of one panel. | To do, before the public sale |
| 5. Sell the 100 founder licences. | To do |
| 6. Measure the real cost on 10 accounts. | To do |
| 7. Publish the Korean web site. | To do |
| 8. Contact 20 webtoon studios. | To do |

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

- Celsys, company announcements, 2025 and 2026 — the Clip Studio Paint users,
  subscriptions and revenue
- Clip Studio, price pages — the subscription prices and the perpetual prices
- KOMACON and KOCCA, distribution statistics 2024 and first half of 2025 —
  the webtoon titles
- KOCCA, webtoon industry survey 2025 — the size of the Korean market
- États Généraux de la Bande Dessinée, author survey 2025 — the French
  authors
- URSSAF, artist-author data — the French comic artists and colourists
- GfK and Livres Hebdo, 2024 — the French comic market
- Public rate lists of the flatters, 2021 to 2026 — the price of each page
- Stripe, Managed Payments pricing — 3,5 % for each transaction, plus the
  standard processing fees
- Stripe, manual currency prices — one price for each currency
- Modal, price list, and the Luikki measurements of 11 September 2026 — the L4
  price, the cold start and the idle time
