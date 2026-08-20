# Report build guide

Four pages, built by hand in Power BI Desktop. No Copilot, no Premium capacity,
no custom visuals from AppSource — everything here uses the visuals that ship in
the box.

Written for someone who has used Power BI before but has never seen this model.

**Canvas for every page: 1280 × 720, 4:3 off, page background `#F4F6F8`.**
Set it once per page: click empty canvas → Format pane → Canvas settings → Type
**Custom**, Height 720, Width 1280.

Every visual below gives an exact position. Set it in
Format pane → **General → Properties → Position / Size**, typing the numbers in.
Dragging is fine for a first pass, but a demo where the cards are two pixels out
of line is the sort of thing a prospective client notices without knowing why.

---

## 0. Before the first page

Do these in order. Skipping step 3 is the single most common cause of "all my
time-intelligence measures return blank".

1. **Load the data.** Paste each query from `queries.m` (Home → Get data → Blank
   query → Advanced Editor). Create the `DataFolder` parameter first. Twelve
   queries: eleven tables plus the `dim_category` bridge.
2. **Wire relationships** exactly per `RELATIONSHIPS.md`. 17 active, 2 inactive.
3. **Mark `dim_date` as the date table** on the `Date` column.
   Table tools → Mark as date table.
4. **Apply the theme.** View → Themes → Browse for themes → `THEME.json`.
5. **Create the measures.** External Tools → Tabular Editor → Advanced Scripting
   → paste `measures_tabular_editor.csx` → F5 → Ctrl+S.
   No Tabular Editor? Use `measures.dax` in DAX query view instead — see the
   header of that file.
6. **Sort columns properly.** Without this, months sort alphabetically and
   "Apr 2025" leads the axis.

   | Column | Sort by column |
   |---|---|
   | `dim_date[MonthYear]` | `dim_date[MonthYearSort]` |
   | `dim_date[MonthName]` | `dim_date[MonthNo]` |
   | `dim_date[DayName]` | `dim_date[DayOfWeekNo]` |
   | `dim_area[AreaName]` | `dim_area[AreaSortOrder]` |
   | `dim_service[ServiceName]` | `dim_service[ServiceSortOrder]` |

   Select the column → Column tools → **Sort by column**.
7. **Hide `dim_service[ServiceCategory]`** in report view. Use
   `dim_category[ServiceCategory]` for all category slicing — see
   `RELATIONSHIPS.md` §4 for why this matters.
8. **Hide every key column** from report view: all `*Key` columns on the facts,
   and `DateKey` everywhere. They are join plumbing, not analysis fields, and a
   field list with 31 booking columns in it is hostile to a client who wants to
   self-serve later.

### Sanity check before you build anything

Drop a Card on a blank page with `[Total Bookings]`. It must read **57,973**.
If it does not, stop and fix the model — do not build four pages on a broken star.

---

## Page 1 — Ops Control Room

**The question this page answers:** are we delivering the jobs we take, and where
is it breaking down?

**The story to walk into:** service level sits at 81.1% against a 90% promise,
and the misses are not random — they cluster on days when volume runs ahead of
the trailing average.

### Layout

| ID | Visual | X | Y | W | H |
|---|---|---|---|---|---|
| 1.1 | Card | 16 | 12 | 760 | 40 |
| 1.2 | Slicer — date range | 16 | 60 | 296 | 44 |
| 1.3 | Slicer — Zone | 328 | 60 | 190 | 44 |
| 1.4 | Slicer — Service Category | 534 | 60 | 220 | 44 |
| 1.5 | Slicer — Booking Status | 770 | 60 | 220 | 44 |
| 1.6 | Button — Clear all slicers | 1006 | 60 | 120 | 44 |
| 1.7 | Card ×6 (KPI strip) | see below | 116 | 198 | 88 |
| 1.8 | Line and stacked column chart | 16 | 216 | 820 | 240 |
| 1.9 | Scatter chart | 852 | 216 | 412 | 240 |
| 1.10 | Matrix | 16 | 468 | 620 | 236 |
| 1.11 | Clustered bar chart | 652 | 468 | 300 | 236 |
| 1.12 | Table | 968 | 468 | 296 | 236 |

### 1.1 — Page title

Card visual. Field: `[Ops Page Title]`.
Format → Callout value: font **Segoe UI Semibold 16**, colour `#1F2933`.
Category label: **Off**. Background: **Off**. Border: **Off**.

It renders as `Ops Control Room | All Bengaluru | 01 Jan 2025 to 31 Aug 2026`
and updates as slicers move.

### 1.2–1.5 — Slicers

| ID | Field | Style |
|---|---|---|
| 1.2 | `dim_date[Date]` | Slicer settings → Style **Between** |
| 1.3 | `dim_area[Zone]` | Style **Dropdown**, Selection → Multi-select on |
| 1.4 | `dim_category[ServiceCategory]` | Style **Dropdown**, multi-select on |
| 1.5 | `fact_bookings[BookingStatus]` | Style **Dropdown**, multi-select on |

Set each slicer's Header text to a friendly label (`Zone`, `Category`, `Status`).

### 1.6 — Clear all slicers

Insert → Buttons → **Blank**. Format → Action → Type **Clear all slicers**.
Text: `Reset filters`. Fill `#2A6FB5`, text white (the theme does this already).

### 1.7 — KPI strip

Six Card visuals, `Y = 116`, `W = 198`, `H = 88`.

| X | Measure | Expected (unfiltered) |
|---|---|---|
| 16 | `[Total Bookings]` | 57,973 |
| 226 | `[Completion Rate]` | 80.0% |
| 436 | `[SLA Met Pct]` | 81.1% |
| 646 | `[Avg Time To Assign]` | 13.7 |
| 856 | `[GMV INR]` | 124,526,480 |
| 1066 | `[Platform Revenue INR]` | 22,536,667 |

For each: Callout value font size **20**, Category label **On** (it supplies the
measure name as the caption).

**Conditional formatting on the SLA card (436):**
Format → Callout value → Colour → **fx** → Format style **Rules**,
Field `[SLA Met Pct]`, Summarization *Don't summarize*:

| If value | And | Then |
|---|---|---|
| `>= 0.90` | `<= 1` | `#1B9E77` |
| `>= 0.85` | `< 0.90` | `#E6A700` |
| `>= 0` | `< 0.85` | `#D6455D` |

At 81.1% this card is red on load. That is intentional and it is the first thing
you point at in the demo.

### 1.8 — Volume against service level

**Line and stacked column chart.**

| Well | Field |
|---|---|
| X-axis | `dim_date[MonthYear]` |
| Column y-axis | `[Completed Jobs]`, `[Cancelled Jobs]` |
| Line y-axis | `[SLA Met Pct]` |

Format:
- Line y-axis → Range: Min `0.6`, Max `1`. Without this the SLA line looks flat.
- Add a constant line at `0.9`: Format → **Reference line** (under Analytics for
  the line axis) → colour `#D6455D`, style dashed, label `SLA promise 90%`.
- Title: `Volume delivered against the 90% arrival promise`.

**What it shows:** columns grow from ~900 to ~4,100 completed a month while the
SLA line sits below the dashed target for the whole period and dips hardest in
the monsoon months.

### 1.9 — The capacity story, in one visual

**Scatter chart.** This is the most important visual on the page.

| Well | Field |
|---|---|
| Values (Details) | `dim_date[Date]` |
| X-axis | `[Capacity Strain Index]` |
| Y-axis | `[SLA Breach Pct]` |
| Size | `[Total Bookings]` |

Format:
- X-axis Min `0.5`, Max `2.0`. Y-axis Min `0`, Max `0.6`.
- Analytics pane → **Trend line** → On, colour `#D6455D`, dashed.
- Markers → size 3, transparency 40% (608 points need room to breathe).
- Title: `Every dot is one day. Strain on the left, broken promises going up.`

**What it shows:** an unmistakable upward slope. Breach rate is **14.2%** on
normal days and **32.5%** on the busiest fifth of days — **2.3×**. Average
time-to-assign goes from 11.4 to 19.7 minutes and average rating drops from 4.32
to 4.04 across the same split. This is a correlation that exists in the data,
not a claim on a slide.

### 1.10 — Where it breaks, by zone and month

**Matrix.**

| Well | Field |
|---|---|
| Rows | `dim_area[Zone]` |
| Columns | `dim_date[MonthYear]` |
| Values | `[SLA Breach Pct]` |

Format → Cell elements → **Background colour** → fx → Format style **Rules**,
Summarization *Don't summarize*:

| If value | And | Then |
|---|---|---|
| `>= 0.25` | `<= 1` | `#D6455D` |
| `>= 0.15` | `< 0.25` | `#E6A700` |
| `>= 0` | `< 0.15` | `#1B9E77` |

Turn column subtotals off (Format → Subtotals → Column subtotals **Off**) so the
grid stays readable.

### 1.11 — What went wrong

**Clustered bar chart.**

| Well | Field |
|---|---|
| Y-axis | `fact_bookings[BookingStatus]` |
| X-axis | `[Total Bookings]` |

Filter out `Completed` on this visual (Filters pane → BookingStatus → uncheck
Completed) so the four failure modes are readable rather than a single bar and
four slivers. Title: `Failure modes, completed jobs excluded`.

### 1.12 — Slowest areas to dispatch

**Table.**

| Column | Field |
|---|---|
| Area | `dim_area[AreaName]` |
| Assign | `[Avg Time To Assign]` |
| Response | `[Avg Response Time]` |
| SLA | `[SLA Met Pct]` |

Sort descending by `[Avg Time To Assign]`. Add a data bar on the Assign column
(Cell elements → Data bars → On, positive bar `#E07A3E`).

Filter to Top 8 by `[Avg Time To Assign]` (Filters pane → Area → Top N → 8).

**What it shows:** the tier-C areas (KR Puram, RT Nagar, Vijayanagar, Yelahanka)
sit at the top, because supply density there is roughly half that of the tier-A
core. That is the bridge into the Supply Health page.

---

## Page 2 — Demand Intelligence

**The question this page answers:** where is demand going unserved, and which
acquisition channels are worth the money?

**This page carries the field parameter.**

### Build the field parameter first

Modeling ribbon → **New parameter** → **Fields**.

- Name: `Demand Metric`
- Tick, in this order: `[Total Bookings]`, `[GMV INR]`, `[Search Volume]`,
  `[Search to Booking Pct]`, `[Avg Order Value]`, `[Avg Lead Quality]`
- Leave **Add slicer to this page** ticked.

Power BI creates a calculated table. Reposition its slicer to the coordinates
given for 2.4 below and set Style → **Tile**, Orientation → Horizontal.

### Layout

| ID | Visual | X | Y | W | H |
|---|---|---|---|---|---|
| 2.1 | Card | 16 | 12 | 760 | 40 |
| 2.2 | Slicer — date range | 16 | 60 | 296 | 44 |
| 2.3 | Slicer — Demand Tier | 328 | 60 | 190 | 44 |
| 2.4 | Slicer — Demand Metric (field parameter) | 534 | 60 | 592 | 44 |
| 2.5 | Card ×6 (KPI strip) | see below | 116 | 198 | 88 |
| 2.6 | Funnel chart | 16 | 216 | 380 | 240 |
| 2.7 | Map | 412 | 216 | 424 | 240 |
| 2.8 | Line chart | 852 | 216 | 412 | 240 |
| 2.9 | Matrix | 16 | 468 | 744 | 236 |
| 2.10 | Clustered column chart | 776 | 468 | 488 | 236 |

### 2.1 — Title
Card with `[Demand Page Title]`. Same formatting as 1.1.

### 2.5 — KPI strip

| X | Measure | Expected |
|---|---|---|
| 16 | `[Search Volume]` | 1,149,271 |
| 226 | `[Lead Volume]` | 326,532 |
| 436 | `[Quotes Sent]` | 199,600 |
| 646 | `[Search to Booking Pct]` | 5.0% |
| 856 | `[Quote to Booking Pct]` | 29.0% |
| 1066 | `[Avg Order Value]` | 2,684 |

### 2.6 — The funnel

**Funnel chart.** Funnel visuals take one category well, so build it from the
field parameter trick or, more simply, from four measures:

| Well | Field |
|---|---|
| Category | *(leave empty)* |
| Values | `[Search Volume]`, `[Lead Volume]`, `[Quotes Sent]`, `[Funnel Bookings]` |

Format → Data labels → On, show **Percent of first**.

**What it shows:** 1,149,271 → 326,532 → 199,600 → 57,973. Five percent of
search interest becomes a job.

### 2.7 — Where the demand is

**Map** (the standard bubble map, not Azure Maps — no extra licensing).

| Well | Field |
|---|---|
| Latitude | `dim_area[Latitude]` |
| Longitude | `dim_area[Longitude]` |
| Bubble size | `Demand Metric` (the field parameter) |
| Legend | `dim_area[DemandTier]` |

Set Latitude/Longitude summarization to **Don't summarize**.

If your tenant has maps disabled (some Indian tenants do), substitute a
**Clustered bar chart** with `dim_area[AreaName]` on the Y-axis and
`Demand Metric` on the X-axis. The page still works.

### 2.8 — Seasonality

**Line chart.**

| Well | Field |
|---|---|
| X-axis | `dim_date[MonthYear]` |
| Y-axis | `[Completed Jobs]` |
| Legend | `dim_category[ServiceCategory]` |

Filter the legend to four categories: **Painter, Plumber, AC Service,
Deep Cleaning**. All eight at once is spaghetti; these four tell the story.

Title: `Bengaluru weather is a demand driver`.

**What it shows, and it is worth memorising:**
- AC Service 335 in Feb 2026 → **1,254** in Apr 2026
- Plumber 471 in May 2026 → **1,026** in Aug 2026
- Painter 209 in Apr 2026 → **142** in Jul 2026 (nobody paints in the rain)
- Deep Cleaning 232 in Sep 2025 → **542** in Oct 2025 (Diwali)

### 2.9 — High interest, poor conversion

**Matrix.** The page's payoff visual.

| Well | Field |
|---|---|
| Rows | `dim_area[AreaName]` |
| Columns | `dim_category[ServiceCategory]` |
| Values | `[Search to Booking Pct]` |

Conditional formatting → Background colour → **Gradient**, Summarization
*Don't summarize*: Minimum `#D6455D`, Centre `#E6A700`, Maximum `#1B9E77`.

Add `[Search Volume]` as a second value so a cell that is red *and* busy is
visibly different from a cell that is red and empty.

**What it shows:** the tier-C areas run a red band across every category — real
search interest converting at roughly half the tier-A rate. That is a coverage
problem, not a demand problem, and it is the follow-on scope conversation.

### 2.10 — The acquisition-quality gap

**Clustered column chart.**

| Well | Field |
|---|---|
| X-axis | `dim_customer[AcquisitionChannel]` |
| Y-axis | `[New Customers]` |
| Line y-axis *(switch to a combo chart)* | `[Avg LTV INR]` |

Sort descending by `[Avg LTV INR]`.

**What it shows:** Referral customers are worth **₹7,793** each against Meta Ads
at **₹3,506** — a **2.2× gap** — and they repeat at **79.0%** against Meta's
**39.9%**. Meta Ads delivers the second-largest new-customer count in the
dataset. The channel bringing the most people brings the least value per person.

---

## Page 3 — Supply Health

**The question this page answers:** do we have the right technicians, in the
right places, doing enough work?

**The story:** utilisation is 17% platform-wide. That sounds like massive
oversupply, and in aggregate it is — but it is distributed so unevenly that
specific area-and-category cells run hot while most of the roster sits idle.

### Layout

| ID | Visual | X | Y | W | H |
|---|---|---|---|---|---|
| 3.1 | Card | 16 | 12 | 760 | 40 |
| 3.2 | Slicer — date range | 16 | 60 | 296 | 44 |
| 3.3 | Slicer — Skill Tier | 328 | 60 | 190 | 44 |
| 3.4 | Slicer — Zone | 534 | 60 | 190 | 44 |
| 3.5 | Card ×6 (KPI strip) | see below | 116 | 198 | 88 |
| 3.6 | Line and clustered column chart | 16 | 216 | 620 | 240 |
| 3.7 | Scatter chart | 652 | 216 | 612 | 240 |
| 3.8 | Matrix | 16 | 468 | 620 | 236 |
| 3.9 | Clustered bar chart | 652 | 468 | 300 | 236 |
| 3.10 | Table | 968 | 468 | 296 | 236 |

### 3.5 — KPI strip

| X | Measure | Expected |
|---|---|---|
| 16 | `[Active Pros]` | 833 |
| 226 | `[Pro Utilization Pct]` | 17.0% |
| 436 | `[Jobs per Active Pro]` | 55.7 |
| 646 | `[Pro Acceptance Rate]` | 67.2% |
| 856 | `[Pros At Risk]` | 128 |
| 1066 | `[Churned Pros]` | 91 |

### 3.6 — Capacity opened against capacity used

**Line and clustered column chart.**

| Well | Field |
|---|---|
| X-axis | `dim_date[MonthYear]` |
| Column y-axis | `[Slots Available]`, `[Slots Booked]` |
| Line y-axis | `[Pro Utilization Pct]` |

Line y-axis Min `0`, Max `0.35`.

### 3.7 — The inequality visual

**Scatter chart.** This is the one that makes the point.

| Well | Field |
|---|---|
| Values (Details) | `dim_professional[ProName]` |
| X-axis | `[Slots Available]` |
| Y-axis | `[Completed Jobs]` |
| Size | `[Avg Pro Rating]` |
| Legend | `dim_professional[SkillTier]` |

Title: `833 technicians. A small number of them do most of the work.`

**What it shows:** a dense cloud near the origin and a thin arm of Gold and
Platinum technicians stretching up and right. The ranker concentrates work on
proven technicians, which is good for customers and, at this roster size, means
most of the supply the company recruited is doing very little.

### 3.8 — The supply gap by area

**Matrix.**

| Well | Field |
|---|---|
| Rows | `dim_area[AreaName]` |
| Columns | `dim_date[MonthYear]` |
| Values | `[Supply Demand Gap]` |

Background colour → Gradient, Minimum `#1B9E77`, Maximum `#D6455D`
(high positive gap = unmet demand = red).

> **Do not add a category or service field to this visual.**
> `fact_pro_capacity` has no service key, so slicing by category filters the
> demand half of the measure and leaves the capacity half untouched. The measure
> description says the same thing; this is the one measure in the library with a
> grain restriction and it is worth saying out loud in the demo.

### 3.9 — Where the roster actually lives

**Clustered bar chart.** Y-axis `dim_professional[PrimaryServiceCategory]`,
X-axis `[Roster Size]` and `[Active Pros]`.

### 3.10 — Technicians needing attention

**Table.** Columns: `dim_professional[ProName]`, `[Avg Pro Rating]`,
`[Completed Jobs]`, `[Pro Acceptance Rate]`.
Filter: `[Avg Pro Rating]` is less than `4.0`. Sort ascending by rating.

Because ratings are shrunk towards a tier prior, nobody appears here on the
strength of three bad jobs — a low score means a sustained pattern.

---

## Page 4 — ML Model Health

**The question this page answers:** are the eight models in production still
doing their job, and would we know if one stopped?

**The story is an incident with a beginning, a middle and an end.** Build this
page so the four beats read left to right, top to bottom.

### Layout

| ID | Visual | X | Y | W | H |
|---|---|---|---|---|---|
| 4.1 | Card | 16 | 12 | 760 | 40 |
| 4.2 | Slicer — date range | 16 | 60 | 296 | 44 |
| 4.3 | Slicer — Model Name | 328 | 60 | 296 | 44 |
| 4.4 | Slicer — Business Critical | 640 | 60 | 190 | 44 |
| 4.5 | Card ×6 (KPI strip) | see below | 116 | 198 | 88 |
| 4.6 | Table — model scorecard | 16 | 216 | 620 | 240 |
| 4.7 | Line chart — MAPE | 652 | 216 | 612 | 240 |
| 4.8 | Line chart — PSI drift | 16 | 468 | 405 | 236 |
| 4.9 | Area chart — training data age | 437 | 468 | 405 | 236 |
| 4.10 | Line and clustered column — forecast vs actual | 858 | 468 | 406 | 236 |

### 4.5 — KPI strip

| X | Measure | Expected |
|---|---|---|
| 16 | `[Models In Breach]` | 8 (over the full period; 0–2 in a typical month) |
| 226 | `[Avg PSI Drift]` | 0.066 |
| 436 | `[Forecast MAPE]` | 10.4% |
| 646 | `[Forecast WAPE]` | 37.2% |
| 856 | `[Max Training Data Age]` | 126 |
| 1066 | `[Total Prediction Volume]` | 1,187,540 |

Put `[Forecast MAPE]` and `[Forecast WAPE]` **side by side deliberately.** The
gap between 10.4% and 37.2% is the single most interesting number on the page —
see §4.10.

### 4.6 — Model scorecard

**Table.**

| Column | Field |
|---|---|
| Model | `dim_model[ModelName]` |
| Metric | `dim_model[PrimaryMetric]` |
| Value | `[Metric Value Avg]` |
| Goal | `[Metric Goal Avg]` |
| Status | `[Model KPI Status]` |
| Owner | `dim_model[OwnerTeam]` |

Conditional formatting on **Status** → Background colour → fx → Format style
**Field value** → Field `[KPI Status Colour]`.

That measure returns the hex directly, which is why the colours match `THEME.json`
without anyone maintaining two lists.

> `[Metric Value Avg]` is in each model's own units — 12.0 is percentage points
> of MAPE, 0.82 is an NDCG, 14.0 is minutes. Never total this column. It is
> correct per row and meaningless in aggregate, which is exactly why the status
> measure compares against `MetricGoal` per model rather than against a constant.

### 4.7 — The incident

**Line chart.** The centrepiece.

| Well | Field |
|---|---|
| X-axis | `dim_date[Date]` |
| Y-axis | `[Metric Value Avg]` |

Filter this visual to `dim_model[ModelName]` = `demand_forecaster`.

- Analytics → **Constant line** at `12`, colour `#D6455D`, dashed,
  label `MAPE goal 12%`.
- Y-axis Min `0`, Max `26`.
- Title: `demand_forecaster MAPE — the June 2026 incident`.

**What it shows, and this is the demo:** a flat line around 9% through May 2026,
a climb through early June to a plateau near **19%**, then a sharp fall back to
about 10% within days of 20 July.

*(A monthly view averages June's ramp-up and July's recovery into the plateau,
so monthly reads ~16% and ~17%. Use the daily axis for the demo — the plateau is
genuinely 19% and the daily line is the honest picture.)*

### 4.8 — How it was caught

**Line chart.** X-axis `dim_date[Date]`, Y-axis `[Avg PSI Drift]`, filtered to
`demand_forecaster`.

Constant line at `0.25`, colour `#D6455D`, dashed, label `Drift alert threshold`.

**What it shows:** PSI sits around 0.05 for fifteen months, then crosses 0.25 in
mid-June and stays there until the retrain. This is the monitor that fired.

### 4.9 — The root cause

**Area chart.** X-axis `dim_date[Date]`, Y-axis `[Max Training Data Age]`,
filtered to `demand_forecaster`. Fill `#E07A3E`.

**What it shows, and it is the best beat in the story:** a 7-day sawtooth for a
year — the weekly retrain doing its job — then, from **15 March 2026**, a
straight diagonal climb to **126 days**. The retrain job stopped succeeding four
months before anything looked wrong, and nothing alerted because the model kept
returning predictions the whole time. It only became visible when the monsoon
changed the demand regime and the stale model could no longer cope.

Then it drops to zero on 20 July and the sawtooth resumes.

### 4.10 — Forecast against reality

**Line and clustered column chart.**

| Well | Field |
|---|---|
| X-axis | `dim_date[MonthYear]` |
| Column y-axis | `[Actual Jobs]`, `[Forecasted Jobs]` |
| Line y-axis | `[Forecast Bias Pct]` |

Add a second Card beneath if space allows, or mention it verbally:
`[Phantom Demand Cells]` = **11,004**.

**The point worth making out loud.** MAPE says this model runs at 10.4%. WAPE
says 37.2%. Both are correct. The difference is 11,004 day-area-category cells
where the model forecast demand and **nothing arrived at all** — 14,806 jobs'
worth of phantom demand against 55,654 real ones. MAPE cannot see them, because
a cell with zero actual jobs has no denominator to divide by, so it is excluded
from the average entirely.

Every one of those cells is a technician told to be somewhere that had no work.
A monitoring page that reported only MAPE would have called this model healthy.

---

## Cross-page finishing

1. **Sync the date slicer** across all four pages: select the date slicer →
   View ribbon → **Sync slicers** → tick Sync and Visible for all four pages.
   Do *not* sync the Zone or Category slicers — each page frames a different
   question and forcing one filter across all of them is more annoying than
   helpful.
2. **Page navigation.** Insert → Buttons → Navigator → **Page navigator**.
   Place at X 16, Y 690, W 600, H 26 on every page.
3. **Tab order.** For each page: View → Selection pane → Tab order. Put the
   title first, then slicers, then KPIs, then visuals. Screen readers follow
   this, and so does keyboard navigation in a live demo.
4. **Alt text** on the four story visuals (1.9, 2.9, 4.7, 4.9) — Format →
   General → Alt text. One sentence each.
5. **Turn off** "Modify report to help users find insights" nudges if they clutter
   the canvas: File → Options → Report settings.

## Common mistakes, and what they look like

| Symptom | Cause |
|---|---|
| Every time-intelligence measure is blank | `dim_date` not marked as the date table |
| Months sort Apr, Aug, Dec... | `MonthYear` not sorted by `MonthYearSort` |
| Forecast total is identical for every category | Sliced by `dim_service[ServiceCategory]` instead of `dim_category[ServiceCategory]` |
| `[Supply Demand Gap]` looks absurd | A service or category field is on the visual — see 3.8 |
| Utilisation never shows an idle day | A relationship was set to bidirectional |
| `[New Pro Onboarding Count]` errors | Inactive relationship #18 not created |
| SLA card is green | Conditional formatting rules entered as 90 instead of 0.90 |
| KPI cards show `4.0` where you expect `4` | Format string not applied — re-run the `.csx` |
