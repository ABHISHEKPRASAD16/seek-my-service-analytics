# Seek My Service — marketplace analytics and ML monitoring

**A Power BI model, three ML services and a monitoring layer for a Bengaluru
home-services marketplace.**

---

> ### Read this first: a sanitised recreation, and why
>
> This is a **rebuild of client work against synthetic data**. Marketplace
> booking data is exactly the kind of thing that cannot leave a client's
> environment, so rather than show nothing, I reconstructed the whole pipeline —
> source schema, transformations, semantic model, dashboards, ML services,
> monitoring — against a dataset generated to have the same shape and the same
> behaviour.
>
> There is no real company called Seek My Service, and **no real customer record
> was used, seen, or inferred.** Every number in this document comes from
> `generator/generate.py` and is reproducible from a fixed seed.
>
> **What is synthetic:** the 57,973 bookings, 24,000 customers and 850
> technicians, and every figure derived from them.
>
> **What is real:** the architecture and every engineering decision in it — plus
> the 20 Bengaluru localities with their actual pincodes, zones and coordinates;
> Bengaluru's two monsoon seasons; the Indian festival calendar; the Indian
> fiscal year; INR price points benchmarked to the city; and a payments mix that
> reflects India's UPI-first reality.
>
> The behaviour is modelled, not invented. Rain suppresses painting because
> nobody paints in the rain. Where I made a judgement call, it is written down
> in the README under Assumptions rather than left for someone to discover.
>
> If you want to discuss the original engagement, ask me directly — I can talk
> through the approach and the decisions without sharing anything that belongs
> to the client.

---

## The problem

A home-services marketplace connects customers with carpenters, painters,
plumbers, electricians, AC technicians, cleaners, pest-control operators and
appliance-repair technicians across Bengaluru. It has grown roughly 4.5× in
twenty months, from about 900 completed jobs in January 2025 to about 4,100 in
August 2026.

Growth of that shape creates a specific and familiar set of problems:

- **Operations runs on yesterday's numbers.** Founders know service level is
  slipping; they cannot say which days, which areas, or why.
- **Marketing optimises for volume.** Cost per acquisition is measured. Value
  per acquisition is not.
- **Supply is recruited, not managed.** The roster grows because recruiting is
  a target, without anyone asking whether the technicians already signed up are
  getting work.
- **Eight ML models are in production and nobody is watching them.** They return
  predictions, so they look fine. A model that has quietly stopped being
  retrained returns predictions too.

There was no analytics layer. Reporting meant someone exporting a CSV from the
production database, which is slow, dangerous, and different every time.

## What I built

| Layer | What it is |
|---|---|
| **Source model** | A normalised OLTP schema in PostgreSQL — the transactional database this data plausibly comes from, including an append-only booking event log and a prediction store |
| **Transformation** | A staging layer and a dbt-shaped dimensional build; 11 tables, star schema, conformed dimensions |
| **Semantic model** | 119 DAX measures across 8 display folders, every one with an explicit format string, deployed in a single click by a Tabular Editor script |
| **Report** | Four Power BI pages: Ops Control Room, Demand Intelligence, Supply Health, ML Model Health |
| **ML services** | Three FastAPI services — demand forecasting, technician matching, dynamic pricing — with real feature engineering, held-out metrics and OpenAPI docs |
| **Monitoring** | Daily telemetry for eight models: primary metric against goal, PSI drift, prediction volume, p95 latency, feature null rate, and training-data age |
| **Governance** | Row-level security by zone, a data dictionary, model cards, and a production architecture with a migration path |

Everything is reproducible from one fixed seed. `make all` rebuilds the entire
dataset, revalidates it against 16 integrity checks, retrains all three models
and runs 95 tests.

---

## What the data revealed

### 1. The monsoon is a supply reallocation problem, not a supply shortage

Bengaluru has two monsoons — the south-west from June to September, and the
north-east from mid-October to late November. Demand does not simply rise in
them. It **moves**.

Technician utilisation, monsoon against dry season:

| Trade | Dry | Monsoon | Change |
|---|---:|---:|---:|
| Pest Control | 11.9% | 18.9% | **+59%** |
| Plumber | 15.6% | 24.5% | **+57%** |
| Electrician | 14.0% | 19.4% | **+38%** |
| Deep Cleaning | 16.9% | 19.1% | +13% |
| Painter | 13.0% | 11.4% | **−12%** |
| AC Service | 20.0% | 14.9% | **−25%** |

Plumbing volume goes from 471 jobs in May 2026 to 1,026 in August. Painting
falls from 209 to 142 across the same months, because nobody paints a Bengaluru
exterior in July.

The company's instinct during monsoon is to recruit more plumbers. The data says
something cheaper: **it already has idle capacity, it is just wearing the wrong
tool belt.** Painters and AC technicians sit at 11–15% utilisation for four
months a year while plumbers strain.

*What it is worth:* cross-training even a fraction of the painting roster in
basic leak and drainage work converts a fixed seasonal cost into seasonal
capacity, and it costs a training programme rather than a recruitment pipeline.

### 2. The channel bringing the most customers brings the least value

Repeat behaviour and lifetime value by acquisition channel, across 24,000
customers:

| Channel | Customers | Repeat rate | Avg LTV |
|---|---:|---:|---:|
| Referral | 3,436 | **79.0%** | **₹7,793** |
| Organic Search | 4,862 | 72.2% | ₹6,628 |
| App Store | 2,339 | 64.3% | ₹5,354 |
| WhatsApp Broadcast | 1,988 | 54.3% | ₹4,344 |
| Google Ads | 4,416 | 50.4% | ₹4,158 |
| JustDial | 2,844 | 47.9% | ₹4,071 |
| Meta Ads | 4,115 | **39.9%** | **₹3,506** |

A referred customer is worth **2.2× a Meta Ads customer** and rebooks twice as
often. Meta Ads is the second-largest source of new customers in the dataset.

Judged on cost per first booking, Meta Ads probably looks like the best channel
on the marketing dashboard. Judged on cost per rupee of lifetime value, it is
the worst by a distance.

*What it is worth:* this changes budget allocation, and it changes it in a
direction that costs nothing to try. A referral programme funded by a 20% cut of
the Meta Ads budget would need to produce very few referrals to come out ahead.

### 3. Service-level failure is a capacity problem, and it is measurable

Overall service level is **81.1%** against a 90% arrival promise. That average
hides the mechanism entirely.

Splitting every completed job by whether its day ran hot — daily volume against
the trailing 30-day average — gives:

| | Jobs | SLA breach | Avg time to assign | Avg rating |
|---|---:|---:|---:|---:|
| Busiest 20% of days | 12,120 | **32.5%** | 19.7 min | 4.04 |
| Everything else | 34,244 | **14.2%** | 11.4 min | 4.32 |

Breach rate more than doubles. Time to assign rises 73%. Customer rating drops
0.28 stars, which flows straight into the reviews the next customer reads.

This is not a technician quality problem and it will not be fixed by
performance management. It is a **dispatch capacity problem on predictable
days** — weekends, festival windows, and the first heavy rain after a dry spell.
All three are known in advance.

*What it is worth:* the forecasting model already exists. Closing the gap
between the busy-day breach rate and the normal-day rate is an operational
scheduling change, not a technology purchase.

---

## Two things I did not expect to find

**Painting is 5% of jobs and 38% of GMV.** It is 3,029 of 57,973 bookings, and
₹4.7 crore of ₹12.45 crore in gross merchandise value. It also carries the
*lowest* commission rate in the catalogue at 15%, which is defensible on ticket
size but means the category driving a third of platform revenue is the one
being optimised least. The monsoon painting dip is therefore not a minor
seasonal wobble — it is the single largest seasonal revenue exposure the
business has.

**The demand forecaster is confidently wrong about 11,004 cells.** Its headline
MAPE is 10.4%, which looks healthy. Its WAPE is 37.2%. The entire difference is
day-area-category cells where the model forecast demand and **nothing arrived at
all** — 14,806 phantom jobs against 55,654 real ones. MAPE structurally cannot
see them, because a cell with zero actual jobs has no denominator and is dropped
from the average.

Every one of those cells is, in principle, a technician told to be somewhere
that had no work. A monitoring page reporting only MAPE would have called this
model healthy for twenty months.

---

## The ML incident

The Model Health page is built around a real failure sequence, because a
monitoring dashboard that only ever shows green teaches people to stop looking
at it.

**15 March 2026.** The scheduled weekly retrain job stops succeeding. Nothing
breaks. The model keeps serving predictions from its last good version, accuracy
stays at 9%, and no alert fires — because nothing was watching training-data
freshness. `TrainingDataAgeDays` begins climbing from its usual 7-day sawtooth.

**1 June 2026.** The monsoon arrives and the demand regime changes. Plumbing
demand nearly doubles; painting collapses. The model's fitted relationship
between the seasonal features and demand is now three months stale.

**Mid-June 2026.** Accuracy degrades from 9% to a plateau of **19%**. Population
stability index crosses the 0.25 alert threshold and stays there. Feature null
rate rises to 2.5%. This is the first point at which anything is visible.

**20 July 2026.** A retrain lands. Version bumps 2.3.0 → 2.4.0,
`TrainingDataAgeDays` resets from **126 days** to zero, and MAPE recovers to
about 10% within four days.

The lesson is in the four-month gap. The model was broken in March and only
looked broken in June. **The metric that would have caught it in March is
training-data age**, which costs nothing to compute and which almost nobody
monitors.

---

## What it would be worth

I have not put a rupee figure on the operational findings, because doing that
honestly needs the client's actual cost base rather than my assumptions. What
the data does support:

| Finding | Quantified as |
|---|---|
| Tier-C conversion gap | Tier C areas convert search to booking at 3.21% against tier A's 5.92%. Closing half that gap is roughly 2,300 additional bookings over twenty months |
| Idle monsoon capacity | Painters and AC technicians at 11–15% utilisation for four months a year, against plumbers at 24.5% |
| Acquisition mix | Referral LTV is 2.2× Meta Ads LTV on comparable acquisition volumes |
| Diwali concentration | The 25-day Diwali window delivers **+40% bookings but +150% GMV** against the preceding 25 days — ₹85.1 lakh against ₹34.0 lakh |
| Silent model failure | Four months of undetected staleness on a business-critical model, visible for free in a column nobody was reporting |

The Diwali number is the one I would lead with in a planning meeting. A window
that delivers one and a half times its normal revenue in 25 days is worth
staffing deliberately, and at present it is being staffed the same way as an
ordinary October.

---

## How it was built

- **Python 3.12**, pandas and NumPy for generation; LightGBM and scikit-learn
  for modelling; FastAPI and Pydantic for serving; pytest for the suite.
- **Deterministic.** One seed. Regeneration is byte-identical, so a number in
  this document can always be traced back to the code that produced it.
- **Validated, not assumed.** `validate.py` runs 16 integrity checks — foreign
  keys, date continuity, money rules, chronology, funnel monotonicity, capacity
  reconciliation — and fails the build if any of them break. It caught a real
  bug during development: six technicians taking jobs after their churn date,
  caused by the same tenure calculation being written twice in slightly
  different ways.
- **Tested.** 95 tests covering the seasonality window logic, the feature
  builders including explicit time-series leakage checks, and a smoke test per
  service. The service tests caught a genuine training-serving skew bug where a
  feature was added to training and not to inference.
- **Honest about the models.** The technician ranker scores NDCG@5 of 0.954,
  and the model card says plainly that this is optimistic because the generator
  assigns jobs using a known function of the same features. The pricing
  service's accept-probability classifier scores AUC 0.527 and the model card
  says it is not fit to ship, with the reason and the fix.

---

## What I would do next

1. **Ingest weather.** The single highest-value feature addition. Booking
   cancellations track rain, and rain is currently unobservable to every model
   in the stack.
2. **Monitor training-data age on every model, with an alert.** It is one column
   and it would have caught the June incident in March.
3. **Report WAPE beside MAPE everywhere**, and count the zero-actual cells
   explicitly. MAPE alone hid an entire failure mode for the whole period.
4. **Instrument the tier-C conversion gap** to distinguish "no technician
   available" from "quoted and declined". Those need opposite fixes and the
   current funnel cannot tell them apart.
5. **Move the whole thing off CSVs** onto a warehouse with scheduled refresh —
   see `PRODUCTION_ARCHITECTURE.md`, which covers what that costs and which
   parts are genuinely worth doing first.
