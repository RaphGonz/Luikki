# Luikki — Business Plan

Document status: draft 4
Date: 2 October 2026
Language: ASD-STE100 (Simplified Technical English)

Changes from draft 3: one line only, the licence at 10 € each year. Luikki
makes no colours (ROADMAP G). No GPU, no AI line, no packs, no Studio line,
no sales to the studios. The application is local and simple. The founder
sells it on line and does no sales work. The business is small on purpose.

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
| panel | One image frame on a comic page |
| plane | One depth layer of a panel: foreground, middle ground or background |

---

## 1. Summary

Luikki is a desktop application. It cuts a comic page into panels, balloons,
zones and planes. It writes a PSD file that the artist colours in Photoshop
or Clip Studio. The artist keeps control of each step.

Luikki costs 10 € each year. There is one line and no free line.

The founder does not sell. The application sells itself, with videos and word
of mouth. Luikki is a side business with low costs. It is not a company that
must pay a salary.

---

## 2. The product

### 2.1 What the application does

The application has six buttons. The artist pushes each button in order. No
step starts by itself.

1. Upload the page.
2. Find the panels. The artist corrects them.
3. Find the balloons. The artist corrects them.
4. Cut the page into zones. The artist merges and cuts the zones.
5. Put each zone on a plane: foreground, middle ground, background or
   characters. The artist can skip this step.
6. Write a PSD file: one layer for each plane, or one group for each plane
   with one layer for each colour.

The PSD holds fake flat colours. Two zones that touch never have the same
colour. Thus the magic wand selects one zone. The professional puts the real
colours in their own software.

### 2.2 Where the data stays

All the work runs on the computer of the artist. The pages, the zones and the
PSD stay there. Nothing goes to a server.

Only the account and the payment are on line.

Say this on the web site: "Nothing leaves your computer." It is true.

### 2.3 What the customer buys

The source code of the application is public, under the PolyForm Shield
licence. Any person can read it, change it and use it, also for paid work. No
person can use it to supply a product that competes with Luikki.

The licence sells the installer, the updates and the sign-in. A person can
build the application from GitHub and not pay. Accept this risk. GitHub is a
wall for most artists, and 10 € costs less than one hour of that work.

Register the trademark "Luikki". The licence stops a competing product. The
trademark stops a product that uses your name.

---

## 3. The market

### 3.1 What the task costs today

A flatter charges 6 $ to 20 $ for each page. The usual rate is 10 $ to 15 $.

The test users measured the time of one page, with the colour version of
Luikki (before ROADMAP G):

| Page | With Luikki | By hand |
|---|---|---|
| Simple | 10 minutes | — |
| Usual | 30 minutes | 4 to 8 hours |
| Complex | 1 hour | — |

On the usual page, Luikki was 8 to 16 times faster. Measure this again with
the planes and the fake flats.

The 4 to 8 hours are the flats only, done by an author. A professional
flatter is much faster: two pages in one hour. Thus the speed argument has
one audience: **the author who does the flats alone.** 200 pages each year
cost 2 000 $ to 3 000 $ at a flatter. Luikki costs 10 €.

### 3.2 The customers

| Segment | Population, world | Role for Luikki |
|---|---|---|
| Colour authors who do their own flats | 10^4 professionals, 10^5 with the serious amateurs | **The customers** |
| Professional flatters and colourists | 10^3 to 10^4 | Some buy for the comfort. Not a target |
| Webtoon studios | 10^3 | Not a target. They can buy licences like any person |
| Japanese manga | 0 | Black and white. No colour work |

The populations are orders of magnitude. They are not counts. This is the
method of Jason Cohen: a factor of 2 does not change the decision, a factor
of 10 does.

France has approximately 4 000 comic authors. The English market has 1 000
to 3 000 possible customers. Tapas had 75 000 creators. WEBTOON counts 24
million creators, but most of them do not colour for money.

The studios gave the revenue in draft 3. They need demonstrations, quotes and
a Korean web site. This is sales work. The founder does not want it. Thus
draft 4 removes the studios as a target.

### 3.3 The price tier decides the sale

Jason Cohen puts each price in a power of ten:

| Price each month | Customers for 1 M$ each year | How they come |
|---|---|---|
| 1 $ | 83 333 | Word of mouth only |
| 10 $ | 8 333 | Organic growth. No budget for marketing |
| 100 $ | 833 | Demonstrations and sales material |

The licence is 0,83 € each month. It is in the lowest tier. No advertisement
pays for itself at this price. Only the before/after videos and word of mouth
bring the customers. This agrees with a founder who does not sell.

---

## 4. The price and the costs

### 4.1 The price

The licence costs 10 € each year, all included. A second purchase adds one
year. There is no free line.

The customer already pays for one tool. Clip Studio Paint PRO costs 4,49 $
each month, or 63 $ one time. Procreate costs approximately 13 $ one time.
Luikki stays below these tools.

The time saved supports a higher price. Test a higher price during the year:
for some weeks, multiply the price by two. Write down each test and its
sales. The prices are experiments.

### 4.2 The costs

| Item | Cost | When |
|---|---|---|
| Stripe: 3,5 % Managed Payments + approximately 1,5 % card + 0,25 € | 0,75 € on one licence | Each sale |
| Apple Developer | 99 $ (approximately 90 €) | Each year |
| Windows code signature | approximately 10 $ each month (110 € each year) | Each month |
| Trademark "Luikki" at the INPI | approximately 200 € | One time |
| Accounts, payment, e-mail (Supabase, Modal without GPU, Resend) | Free tiers | Each month |
| The time of the founder | Not counted | — |

One licence gives 9,25 € net. The fixed costs are approximately 200 € each
year. **22 licences each year pay the fixed costs.**

Supabase Pro costs 25 $ each month, thus 30 licences each year. Stay on the
free tier. The free project stops after 7 days with no activity. The sign-ins
of the customers keep it active. Change to Pro only if the project stops.

There is no GPU. A customer costs nothing after the sale.

---

## 5. The revenue

### 5.1 The method

This forecast uses the method of Jason Cohen. It takes a population, a rate
of conversion and a rate of loss. Then it gives three scenarios, each ten
times the one before.

| Assumption | Value |
|---|---|
| Population, world | 100 000 (10^5) |
| Conversion each year | 0,1 %, 1 % or 10 % of the population |
| Customers who do not renew | 40 % each year |

The script `reports/business/projections.py` holds each assumption as one
constant. Change one value and run it again.

### 5.2 Three years, three scenarios

| Scenario | Year 1 | Year 2 | Year 3 | Year 3, each month |
|---|---|---|---|---|
| 0,1 %: +100 licences each year | 1 000 € | 1 600 € | 1 960 € | 163 € |
| 1 %: +1 000 licences each year | 10 000 € | 16 000 € | 19 600 € | 1 633 € |
| 10 %: +10 000 licences each year | 100 000 € | 160 000 € | 196 000 € | 16 333 € |

The revenue is gross. The net revenue, after Stripe and the fixed costs, is
approximately 90 % of the gross revenue in the 1 % and 10 % scenarios.

### 5.3 The growth ceiling

Jason Cohen gives one equation:

    maximum number of customers = new customers each year / rate of loss each year

| Scenario | Licences at the ceiling | Revenue each month |
|---|---|---|
| 0,1 % | 250 | 208 € |
| 1 % | 2 500 | 2 083 € |
| 10 % | 25 000 | 20 833 € |

### 5.4 What the business can be

| Target | Licences | New licences each year |
|---|---|---|
| 1 000 € each month | 1 200 | 480 |
| 20 000 € each month | 24 000 | 9 600 |

1 000 € each month is possible with good videos. 20 000 € each month needs a
viral video and most of the world market. **Do not plan on it.**

This is the cost of "no sales work". Accept it, or change the decision. The
decision is open again in these conditions:

- Many customers ask for the same expensive feature.
- Studios ask for invoices and volume.
- The 1 % scenario is reached and the founder wants more.

---

## 6. The risks

| Risk | Effect | What to do |
|---|---|---|
| A free tool does the same task | The price falls to zero | Sell the control and the planes |
| A person builds the application from GitHub | Loss of one licence | Accept it |
| One licence runs on many machines | Loss of revenue | Accept it at 10 € |
| Nobody talks about Luikki | No sales | Make the videos (ROADMAP D) |
| The low price says "low value" | Some professionals do not trust the tool | Test a higher price |
| Supabase or Modal end the free tier | A fixed cost of 25 $ to 30 $ each month | 30 licences pay for it |

### 6.1 The free tools

Clip Studio Assets gives free actions for the flats. Clip Studio Paint has a
colour function. Petalica Paint and Webtoon AI Painter exist on the web.

Research shows why the professionals do not use them. They give no control.
One professional said the tool puts random colours in the image.

Luikki answers this. It proposes no colour. Each step is correctable. The
artist gets planes and zones, and colours them.

**This is the argument to sell. Put it at the top of the web site.**

---

## 7. The next steps

| Step | Status on 2 October 2026 |
|---|---|
| 1. Finish the local application with the planes. | Done (ROADMAP G) |
| 2. Change the payment to one line at 10 €. | Code done. Supabase, Stripe and Modal to change on line |
| 3. Package the application. Sign the Windows build. | Package done. Signature to do |
| 4. Measure the time of one page with the planes. | To do, with the test users |
| 5. Make the web site and the videos. | To do (ROADMAP D) |
| 6. Open the sales. | To do |

---

## 8. Sources

- Jason Cohen, A Smart Bear, "Pricing determines your business model" — the
  price tiers in powers of ten
  (https://longform.asmartbear.com/pricing-determines-your-business-model/)
- Jason Cohen, A Smart Bear, "Max MRR: your growth ceiling" — the growth
  ceiling (https://longform.asmartbear.com/max-mrr/)
- Clip Studio, price pages — the subscription prices and the perpetual prices
- WEBTOON Entertainment, SEC S-1 filing, 2024 — the 24 million creators
- Tapas, 2026 — the 75 000 creators
- États Généraux de la Bande Dessinée, author survey 2025 — the French
  authors
- URSSAF, artist-author data — the French comic artists and colourists
- Public rate lists of the flatters, 2021 to 2026 — the price of each page
- Test users of Luikki, September 2026 — the time of one page
- Stripe, Managed Payments pricing — 3,5 % for each transaction, plus the
  standard processing fees
- Supabase, price page — the Pro plan and the pause of the free projects
