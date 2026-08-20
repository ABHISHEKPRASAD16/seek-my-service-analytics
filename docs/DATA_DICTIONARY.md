# Data dictionary

Eleven tables: six dimensions, five facts. Every column, its type, what it
means, a real example value taken from the shipped data, and whether it is
derived from another table.

**Conventions that hold everywhere:**

| Rule | Value |
|---|---|
| Column naming | PascalCase, no spaces, no special characters |
| Dates | ISO `YYYY-MM-DD` |
| Timestamps | `YYYY-MM-DD HH:MM:SS` |
| Encoding | UTF-8, **no BOM** |
| Decimal separator | `.` |
| Currency | INR, never with a symbol inside the data |
| Blank | An empty string in the CSV. Never `nan`, never `NULL`, never `0` standing in for "unknown" |
| Booleans | Integer `1` / `0`, never `TRUE` / `True` / `Y` |
| Integers | Written without a decimal point. `4`, never `4.0` |

**"Derived" means** the column is computed from a fact table rather than
generated independently. Derived columns cannot disagree with the facts,
because they are recomputed from them. This is why `dim_professional.AvgRating`
is trustworthy and why a rating column typed in by an ops team would not be.

---

## dim_date — 608 rows

One row per day from 2025-01-01 to 2026-08-31, contiguous, no gaps. **Mark this
as the model's date table** on `Date`.

| Column | Type | Meaning | Example | Derived |
|---|---|---|---|:---:|
| `DateKey` | int | `YYYYMMDD`. The join key on every fact | `20260516` | |
| `Date` | date | The date itself. Mark-as-date-table uses this | `2026-05-16` | |
| `Year` | int | Calendar year | `2026` | |
| `Quarter` | text | Calendar quarter, `Q1`–`Q4` | `Q2` | |
| `MonthNo` | int | 1–12. Sort `MonthName` by this | `5` | |
| `MonthName` | text | Full month name | `May` | |
| `MonthYear` | text | Short label for axes | `May 2026` | |
| `MonthYearSort` | int | `YYYYMM`. Sort `MonthYear` by this | `202605` | |
| `WeekNo` | int | ISO week number | `20` | |
| `DayName` | text | Full day name. Sort by `DayOfWeekNo` | `Saturday` | |
| `DayOfWeekNo` | int | 1 = Monday … 7 = Sunday | `6` | |
| `IsWeekend` | int | 1 on Saturday and Sunday | `1` | |
| `IsMonsoon` | int | 1 inside **either** monsoon: 1 Jun–30 Sep, or 10 Oct–20 Nov | `0` | |
| `IsFestivalWindow` | int | 1 inside any configured festival window | `0` | |
| `FestivalName` | text | The named holiday if the day is one, else the window name, else blank | `Deepavali` | |
| `IsMonthEnd` | int | **1 on the last five days of the month**, not just the last day | `0` | |
| `FiscalYear` | text | Indian FY, April–March | `FY26-27` | |
| `FiscalQuarter` | text | Q1 = Apr–Jun … Q4 = Jan–Mar | `Q1` | |
| `IsHoliday` | int | 1 on a national or Karnataka public holiday | `0` | |
| `DaysFromToday` | int | Days relative to 2026-08-31. Always ≤ 0 here | `-107` | |

> **`IsMonthEnd` is deliberately not the conventional "last day of month".**
> It flags the five-day salary-cycle window where discretionary spend defers,
> because that is the effect present in the data (a ×0.85 demand multiplier).
> Flagging only the 31st would make that effect invisible to a report author.
> If you need "is the last calendar day", derive it: `Date` equals `EOMONTH`.

> **Both monsoons are modelled.** Most datasets model only the south-west
> monsoon and lose the entire October plumbing surge with it.

---

## dim_service — 37 rows

The service catalogue. Eight categories.

| Column | Type | Meaning | Example | Derived |
|---|---|---|---|:---:|
| `ServiceKey` | int | Primary key, 1–37 | `1` | |
| `ServiceCategory` | text | One of the eight trades | `Carpenter` | |
| `ServiceName` | text | The specific service | `Furniture Repair` | |
| `BasePriceINR` | int | Reference price before area, season and emergency adjustments | `750` | |
| `AvgDurationMins` | int | Typical on-site minutes | `90` | |
| `IsEmergency` | int | 1 for call-outs priced at a premium and dispatched faster | `0` | |
| `SkillTier` | text | Minimum competence: Bronze / Silver / Gold / Platinum | `Silver` | |
| `MaterialCostPct` | decimal(1) | Materials as a percentage of the final amount | `22.0` | |
| `CommissionPct` | decimal(1) | Platform take rate. Set at category level | `18.0` | |
| `ServiceSortOrder` | int | Slicer ordering, grouped by category | `301` | |

> **Do not slice category visuals from `dim_service[ServiceCategory]`.** It is
> not unique (37 services, 8 categories) so it cannot filter
> `fact_forecast_accuracy`. Use `dim_category[ServiceCategory]` and hide this
> column in report view. See `powerbi/RELATIONSHIPS.md` §4.

Commission by category — cleaning and plumbing carry the highest rate, painting
the lowest because ticket sizes there are an order of magnitude larger:

| Category | Commission | Category | Commission |
|---|---:|---|---:|
| Deep Cleaning | 22.0% | Appliance Repair | 20.0% |
| Plumber | 22.0% | AC Service | 19.0% |
| Pest Control | 21.0% | Carpenter | 18.0% |
| Electrician | 20.0% | Painter | 15.0% |

---

## dim_area — 20 rows

Twenty real Bengaluru localities with correct pincodes and approximate
coordinates.

| Column | Type | Meaning | Example | Derived |
|---|---|---|---|:---:|
| `AreaKey` | int | Primary key, 1–20 | `1` | |
| `AreaName` | text | Locality name | `Koramangala` | |
| `Zone` | text | Central / East / North / South / West | `South` | |
| `Pincode` | **text** | Six-digit postal code. Text, not integer | `560034` | |
| `Latitude` | decimal(4) | Approximate locality centroid | `12.9352` | |
| `Longitude` | decimal(4) | Approximate locality centroid | `77.6245` | |
| `DemandTier` | text | `A` (highest) / `B` / `C`. Drives conversion and supply density | `A` | |
| `IncomeBand` | text | Premium / Upper-Mid / Mid / Value. Drives ticket size | `Premium` | |
| `AreaSortOrder` | int | Slicer ordering, grouped by zone then name | `17` | |

`Pincode` is text on purpose. Bengaluru pincodes happen not to start with a
zero, but treating a postal code as a quantity is a habit that breaks the first
time this model meets a dataset that does.

**Zone assignment:** Central (Malleshwaram) · East (Indiranagar, Whitefield,
Marathahalli, Bellandur, KR Puram) · North (Hebbal, Yelahanka, RT Nagar) ·
South (Koramangala, HSR Layout, Sarjapur Road, Electronic City, BTM Layout,
JP Nagar, Jayanagar, Banashankari, Bannerghatta Road) · West (Rajajinagar,
Vijayanagar).

---

## dim_professional — 850 rows

The technician roster.

| Column | Type | Meaning | Example | Derived |
|---|---|---|---|:---:|
| `ProKey` | int | Primary key, 1–850 | `501` | |
| `ProName` | text | Name, reflecting Bengaluru's Kannada, Tamil, Telugu, Hindi and Urdu-speaking mix | `Ramakrishna Varma` | |
| `PrimaryServiceCategory` | text | Their main trade | `Plumber` | |
| `HomeAreaKey` | int | Base locality → `dim_area` | `1` | |
| `JoinDate` | date | Onboarding date. **Always ≤ their first job** | `2024-09-10` | |
| `SkillTier` | text | Bronze / Silver / Gold / Platinum | `Bronze` | |
| `IsBackgroundVerified` | int | 1 if verification passed. Higher tiers verify more often | `0` | |
| `IsActive` | int | 1 if still on the platform. Exactly `ChurnedDate` being blank | `1` | ✔ |
| `AvgRating` | decimal(2) | **Shrunk** mean rating — see below | `4.02` | ✔ |
| `LifetimeJobs` | int | Count of their completed bookings | `16` | ✔ |
| `LanguagesSpoken` | text | Pipe-delimited | `Telugu\|Kannada\|English` | |
| `OnboardingChannel` | text | How they were recruited | `Online Signup` | |
| `ChurnedDate` | date | Date they left. **Blank if still active** | *(blank)* | |

> **`AvgRating` is shrunk towards a tier prior, not a plain average.**
>
> ```
> AvgRating = (sum_of_ratings + 8 × tier_prior) / (rating_count + 8)
> ```
>
> Tier priors: Bronze 4.05, Silver 4.32, Gold 4.55, Platinum 4.72.
>
> Without this, a technician with three five-star jobs sits at a perfect 5.00
> and tops every "best rated" list ahead of someone with two hundred good ones.
> The shrinkage means a low score here reflects a sustained pattern, which is
> what makes the `[Pros At Risk]` measure worth acting on.

`JoinDate` also carries an **inactive** relationship to `dim_date[Date]`,
activated by `[New Pro Onboarding Count]` via `USERELATIONSHIP`.

---

## dim_customer — 24,000 rows

| Column | Type | Meaning | Example | Derived |
|---|---|---|---|:---:|
| `CustomerKey` | int | Primary key, 1–24000, ordered by first booking | `501` | |
| `SignupDate` | date | Account creation. **Always ≤ `FirstBookingDate`** | `2025-01-12` | |
| `AreaKey` | int | Home locality → `dim_area` | `3` | |
| `AcquisitionChannel` | text | One of seven channels | `Meta Ads` | |
| `Segment` | text | New / Repeat / Loyal / Dormant | `Dormant` | ✔ |
| `IsAppUser` | int | 1 if they use the mobile app | `1` | |
| `PreferredLanguage` | text | Language preference | `Hindi` | |
| `LifetimeValueINR` | decimal(2) | Sum of `FinalAmountINR` across all their bookings | `1930.00` | ✔ |
| `FirstBookingDate` | date | Earliest booking | `2025-01-22` | ✔ |
| `LastBookingDate` | date | Most recent booking | `2025-01-22` | ✔ |
| `TotalBookings` | int | Count of all their bookings, any status | `1` | ✔ |

**Segment rules, applied in this order** (relative to 2026-08-31):

1. `LastBookingDate` more than **120 days** ago → **Dormant**
2. else `TotalBookings` ≥ 4 → **Loyal**
3. else `TotalBookings` ≥ 2 → **Repeat**
4. else → **New**

Dormancy deliberately wins over volume. Someone who booked six times and then
vanished five months ago is a retention problem, and labelling them Loyal hides
exactly the thing the retention team needs to see.

No PII. No name, phone or email — the warehouse gets a key and behavioural
attributes only. See `sql/02_staging_views.sql`.

`SignupDate` carries an **inactive** relationship to `dim_date[Date]`, activated
by `[Customer Signups]`.

---

## dim_model — 8 rows

The production model registry.

| Column | Type | Meaning | Example | Derived |
|---|---|---|---|:---:|
| `ModelKey` | int | Primary key, 1–8 | `1` | |
| `ModelName` | text | Registry name | `demand_forecaster` | |
| `ModelType` | text | Problem class | `Time Series Regression` | |
| `BusinessPurpose` | text | What it is for, in one sentence | `Forecasts next-7-day job volume…` | |
| `Framework` | text | Training framework | `LightGBM` | |
| `Algorithm` | text | Specific algorithm | `Gradient Boosted Trees` | |
| `PrimaryMetric` | text | The metric it is judged on | `MAPE` | |
| `MetricGoal` | decimal(2) | Target, **in that metric's own units** | `12.00` | |
| `GoalDirection` | text | `LowerIsBetter` or `HigherIsBetter` | `LowerIsBetter` | |
| `DeployedDate` | date | First production deployment | `2025-03-01` | |
| `Version` | text | Current semantic version | `2.3.0` | |
| `RefreshCadence` | text | Intended retrain frequency | `Weekly` | |
| `OwnerTeam` | text | Accountable team | `Data Science` | |
| `IsBusinessCritical` | int | 1 if an outage materially hurts operations | `1` | |

> **`MetricGoal` is in each model's own units and must never be aggregated
> across models.** `12.00` is twelve percentage points of MAPE. `0.82` is an
> NDCG. `14.00` is minutes. Averaging that column produces a number with no
> meaning, which is exactly why `[Model KPI Status]` compares value to goal per
> model and honours `GoalDirection` rather than applying one threshold to
> everything.

The eight models: `demand_forecaster`, `pro_match_ranker`,
`dynamic_price_engine`, `eta_sla_predictor`, `customer_churn`,
`fraud_booking_detector`, `review_sentiment_indic`, `lead_quality_scorer`.

---

## fact_bookings — 57,973 rows

**Grain: one row per booking.** The central fact.

| Column | Type | Meaning | Example | Derived |
|---|---|---|---|:---:|
| `BookingID` | text | Public reference, `BK` + 7 digits | `BK0000501` | |
| `DateKey` | int | Booking creation date → `dim_date` | `20250114` | |
| `BookingTimestamp` | datetime | When the booking was created | `2025-01-14 10:21:26` | |
| `CustomerKey` | int | → `dim_customer` | `340` | |
| `ProKey` | int | Assigned technician → `dim_professional` | `315` | |
| `ServiceKey` | int | → `dim_service` | `28` | |
| `AreaKey` | int | **Job site**, not the customer's home area | `13` | |
| `Channel` | text | App / Web / Phone / WhatsApp | `WhatsApp` | |
| `BookingStatus` | text | Terminal status — see below | `Completed` | |
| `QuotedAmountINR` | decimal(2) | Price quoted to the customer | `1580.00` | |
| `FinalAmountINR` | decimal(2) | Amount actually charged. **0 unless Completed** | `1580.00` | |
| `DiscountINR` | decimal(2) | Coupon value applied | `0.00` | |
| `CommissionPct` | decimal(1) | Take rate for this booking | `22.0` | |
| `PlatformRevenueINR` | decimal(2) | Exactly `FinalAmountINR × CommissionPct / 100` | `347.60` | ✔ |
| `MaterialCostINR` | decimal(2) | Materials consumed. 0 unless Completed | `263.89` | |
| `PaymentMode` | text | UPI / Card / Cash / Wallet / NetBanking | `UPI` | |
| `TimeToAssignMins` | int | Minutes from creation to a technician accepting | `13` | |
| `ResponseTimeMins` | int | Minutes from assignment to confirmation | `14` | |
| `JobDurationMins` | int | On-site minutes. **Completed only** | `225` | |
| `SLAMetFlag` | int | 1 if arrival was inside the 90-minute promise. **Completed only** | `1` | |
| `CustomerRating` | int | 1–5 stars. **Blank on ~38% of completed jobs and on all others** | `4` | |
| `ReviewSentiment` | text | Positive / Neutral / Negative. **Blank exactly when rating is blank** | `Positive` | ✔ |
| `IsRepeatCustomer` | int | 1 if this is not the customer's first booking | `0` | ✔ |
| `PredictedPriceINR` | int | `dynamic_price_engine` output at quote time | `1339` | |
| `PredictedETAMins` | int | `eta_sla_predictor` output at dispatch | `39` | |
| `ActualETAMins` | int | Realised arrival minutes. **Completed only** | `47` | |
| `MatchScore` | decimal(3) | `pro_match_ranker` confidence in the chosen technician | `0.916` | |
| `FraudScore` | decimal(3) | `fraud_booking_detector` output. > 0.6 goes to review | `0.013` | |
| `ChurnRiskScore` | decimal(3) | `customer_churn` output for this customer | `0.345` | |
| `IsFirstTimeFix` | int | 1 if resolved without a return visit. **Completed only** | `1` | |
| `ReopenedWithin7Days` | int | 1 if reopened within a week. **Completed only** | `0` | |

### Status values and what they imply

| Status | Share | Money | Completion-only columns |
|---|---:|---|---|
| `Completed` | 80.0% | Full | Populated |
| `CancelledByCustomer` | 7.0% | All zero | Blank |
| `Rescheduled` | 5.9% | All zero | Blank |
| `CancelledByPro` | 3.9% | All zero | Blank |
| `NoShow` | 3.1% | All zero | Blank |

> **`Rescheduled` carries zero money by design.** A rescheduled booking is
> superseded by a new booking record which carries the revenue. Counting both
> would double-count GMV. This is a modelling choice, and it is the reason
> `[Completion Rate]` and `[GMV INR]` agree with each other.

### Invariants enforced and tested

These are checked by `validate.py` and will fail the build:

1. `FinalAmountINR ≤ QuotedAmountINR + DiscountINR`, always.
2. `PlatformRevenueINR = FinalAmountINR × CommissionPct / 100`, to 2dp.
3. `JobDurationMins`, `SLAMetFlag`, `IsFirstTimeFix`, `ActualETAMins` and
   `ReopenedWithin7Days` are populated **only** for `Completed`.
4. `CustomerRating` and `ReviewSentiment` are blank together, populated
   together. Sentiment maps: 4–5 Positive, 3 Neutral, 1–2 Negative.
5. A customer's `SignupDate` is on or before their first booking.
6. A technician's `JoinDate` is on or before their first job, and no technician
   appears on a job on or after their `ChurnedDate`.

> **Never replace a blank with zero on import.** `CustomerRating` blank means
> "not rated", not "rated zero". Coercing it to 0 would drag `[Avg CSAT]` from
> 4.25 to about 2.6 while looking entirely plausible.

---

## fact_pro_capacity — 324,435 rows

**Grain: one row per technician per day they were on the roster.** This is the
table that makes utilisation and the supply-demand gap real measures rather
than proxies.

| Column | Type | Meaning | Example | Derived |
|---|---|---|---|:---:|
| `DateKey` | int | → `dim_date` | `20250102` | |
| `ProKey` | int | → `dim_professional` | `441` | |
| `AreaKey` | int | The technician's home area | `3` | |
| `SlotsAvailable` | int | Capacity they opened that day. 0 when offline | `3` | |
| `SlotsBooked` | int | **Bookings actually assigned to them that day, any status** | `0` | ✔ |
| `IsOnline` | int | 1 if they opened a calendar at all | `1` | |
| `HoursLoggedMins` | int | Job time + travel + idle online time, in minutes | `200` | ✔ |
| `AcceptedJobs` | int | Offers accepted | `0` | ✔ |
| `RejectedJobs` | int | Offers declined, plus jobs they later cancelled | `0` | |

Rows exist only for days on or after `JoinDate` and strictly before any
`ChurnedDate`. Because 850 × 608 exceeds the 350,000-row guard, days where the
technician was **both offline and had no jobs** are dropped.

`SlotsBooked` reconciles **exactly** to `fact_bookings` grouped by
`DateKey` × `ProKey` — the generator assigns bookings into real capacity slots
rather than sampling the two independently. `SlotsBooked ≤ SlotsAvailable` on
every row, and no offline day carries a job.

> Note `HoursLoggedMins` is **minutes** despite the name. The name follows the
> source system's column, which is wrong and which everyone at the client already
> calls by that name. `[Hours Logged]` divides by 60.

---

## fact_leads — 74,286 rows

**Grain: day × area × service.** Emitted only where `Searches > 0`.

| Column | Type | Meaning | Example | Derived |
|---|---|---|---|:---:|
| `DateKey` | int | → `dim_date` | `20250107` | |
| `AreaKey` | int | → `dim_area` | `10` | |
| `ServiceKey` | int | → `dim_service` | `6` | |
| `Searches` | int | Searches performed in this cell | `3` | |
| `Leads` | int | Searches that became identified leads | `0` | |
| `QuotesSent` | int | Leads that received a quote | `0` | |
| `Bookings` | int | **Reconciles exactly to `fact_bookings`** | `0` | ✔ |
| `AvgLeadQualityScore` | decimal(3) | Mean `lead_quality_scorer` output | `0.509` | |

**The funnel is monotonic on every row:**
`Searches ≥ Leads ≥ QuotesSent ≥ Bookings`.

This holds by construction: the funnel is built *backwards* from real bookings
using tier-dependent conversion rates, not sampled independently and hoped to
line up. 23,323 rows are cells with genuine search interest and zero bookings —
those are the "high interest, poor conversion" story, weighted towards tier-C
areas.

---

## fact_model_metrics — 3,481 rows

**Grain: day × model**, starting at each model's `DeployedDate`.

| Column | Type | Meaning | Example | Derived |
|---|---|---|---|:---:|
| `DateKey` | int | → `dim_date` | `20250717` | |
| `ModelKey` | int | → `dim_model` | `4` | |
| `MetricName` | text | Which metric this row reports | `RMSEMins` | |
| `MetricValue` | decimal(4) | **In the model's own units** | `12.8619` | |
| `MetricGoal` | decimal(2) | Copied from `dim_model` for convenience | `14.00` | |
| `IsBreach` | int | 1 if the goal was missed, honouring `GoalDirection` | `0` | ✔ |
| `PSIDriftScore` | decimal(4) | Population stability index. Alert threshold 0.25 | `0.0409` | |
| `PredictionVolume` | int | Predictions served that day | `145` | |
| `P95LatencyMs` | int | 95th-percentile serving latency | `46` | |
| `FeatureNullPct` | decimal(3) | Percentage of null feature values entering the model | `0.412` | |
| `TrainingDataAgeDays` | int | **Days since the model last saw fresh training data** | `0` | |
| `ModelVersion` | text | Serving version on that day | `1.4.0` | |

> **`TrainingDataAgeDays` is the most important column in this table** and it is
> the one nobody usually collects. It normally sawtooths 0→7 under a weekly
> cadence. For `demand_forecaster` it climbs in a straight line from
> 2026-03-15 to **126 days**, then resets on 2026-07-20. That climb is the root
> cause of the June 2026 incident, and it was visible four months before any
> accuracy metric moved.

> `MetricValue` for `demand_forecaster` is MAPE **in percentage points** (9.0
> means 9%), to match its `MetricGoal` of 12.0. This differs from
> `fact_forecast_accuracy.APE`, which is a fraction — see the note below.

---

## fact_forecast_accuracy — 47,117 rows

**Grain: day × area × service category**, from the forecaster's deployment
date onward.

| Column | Type | Meaning | Example | Derived |
|---|---|---|---|:---:|
| `DateKey` | int | → `dim_date` | `20250308` | |
| `AreaKey` | int | → `dim_area` | `13` | |
| `ServiceCategory` | text | → **`dim_category`**, not `dim_service` | `Plumber` | |
| `ForecastedJobs` | decimal(1) | What the model predicted | `1.1` | |
| `ActualJobs` | int | What actually happened | `0` | ✔ |
| `AbsError` | decimal(1) | `\|Forecasted − Actual\|` | `1.1` | ✔ |
| `APE` | decimal(4) | **Fraction**, not percent. **Blank when `ActualJobs` = 0** | *(blank)* | ✔ |

A row is emitted where `ActualJobs > 0` **or** `ForecastedJobs ≥ 0.5`. The
second condition is deliberate: **11,004 rows are cells where the model
forecast demand and nothing arrived**, together worth 14,806 phantom jobs
against 55,654 real ones. Filtering them out would hide the failure mode most
worth seeing, and it is the reason `[Forecast WAPE]` (37.2%) is so far above
`[Forecast MAPE]` (10.4%).

> **Why `APE` is a fraction while `fact_model_metrics.MetricValue` is a
> percentage.** `APE` is consumed directly by a Power BI measure with a `0.0%`
> format string, which expects a fraction — storing `9.23` there would display
> as 923%. `MetricValue` is compared against `MetricGoal` in each model's own
> units, and the forecaster's goal is stated as 12.0 percentage points. Each is
> in the right unit for its consumer. It is the one place in the model where
> the same idea is stored two ways, and it is called out here so nobody
> discovers it in a visual.

---

## Referential integrity

Every foreign key resolves. Enforced by `validate.py` check 1 and by the
post-build assertions in `sql/03_star_schema.sql`.

| Fact | Foreign keys |
|---|---|
| `fact_bookings` | `DateKey`, `CustomerKey`, `ProKey`, `ServiceKey`, `AreaKey` |
| `fact_pro_capacity` | `DateKey`, `ProKey`, `AreaKey` |
| `fact_leads` | `DateKey`, `AreaKey`, `ServiceKey` |
| `fact_model_metrics` | `DateKey`, `ModelKey` |
| `fact_forecast_accuracy` | `DateKey`, `AreaKey`, `ServiceCategory` → `dim_category` |

`dim_professional[HomeAreaKey]` and `dim_customer[AreaKey]` also resolve to
`dim_area`, but are deliberately **not** related in the Power BI model — doing
so creates an ambiguous filter path. See `powerbi/RELATIONSHIPS.md` §5.
