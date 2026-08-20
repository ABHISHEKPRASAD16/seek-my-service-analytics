# Model cards

One card per production model: purpose, features, training data, metric and
goal, known limitations, failure modes, monitoring plan, and the trigger that
should cause a retrain.

Three of the eight have working reference implementations in this repository
(`ml/forecast_service.py`, `ml/match_service.py`, `ml/pricing_service.py`) and
their metrics below are **measured on a held-out time split**, not asserted. The
other five are registry entries with simulated telemetry; their cards describe
what would be built and are labelled as such.

> **On honest metrics.** Where a number here is unflattering, it is stated with
> the reason. Two of the three implemented models have a significant caveat —
> one is flattered by synthetic data, and one is not fit to ship. Saying so is
> the point of a model card. A card containing only good news is marketing.

---

## 1. `demand_forecaster` — IMPLEMENTED

**Purpose.** Forecast total job volume over the next seven days for each area
and service category, so technician supply can be pre-positioned rather than
reacted to.

**Owner.** Data Science · **Business critical.** Yes · **Cadence.** Weekly

### Model

| | |
|---|---|
| Framework | LightGBM |
| Objective | Poisson, with a **log exposure offset** |
| Target | Total bookings in the seven days following each observation |
| Grain | day × area × service category |
| Training window | 2025-01-29 to 2026-04-30 (73,120 rows) |
| Validation | 2026-05-01 to 2026-08-31 (18,560 rows), strictly forward in time |

**The exposure offset is the design decision worth understanding.** The model
does not predict volume directly. It predicts a *multiplier* on `7 × the recent
daily mean`, passed in as `log(baseline)`.

Gradient-boosted trees cannot extrapolate: a tree can only ever predict a value
it saw in training. Demand here grows about 4.5× across the window, so the first
version of this model — trained to predict absolute volume — came back with a
**−39.6% bias**, systematically under-forecasting the entire validation period
because the validation volumes were simply larger than anything in training.
With the offset, bias falls to **−6.8%** and the problem becomes scale-free,
which is also the question a supply planner actually asks: *is next week going
to be busier than usual, and by how much?*

### Features (29)

- **Lags** of daily volume at 1, 2, 3, 7, 14, 21 and 28 days
- **Rolling** mean and max over 7, 14 and 28 days, plus a 28-day standard
  deviation, all shifted one day so no row sees its own outcome
- **Momentum**: 7-day mean ÷ 28-day mean
- **Calendar**: day of week, weekend, month, ISO week, month-end, holiday
- **Seasonal**: the configured category multiplier for the day, and its mean
  across the seven-day horizon being predicted
- **Structural**: area demand tier, income band, category, area key

Top features by gain: `Roll28Mean`, `Roll28Std`, `HorizonSeasonalMultiplier`,
`WeekOfYear`, `AreaKey`.

The horizon multiplier is legitimate rather than leakage: next week's calendar,
monsoon window and festival window are all known today.

### Held-out performance

| Metric | Value | Reading |
|---|---:|---|
| MAPE, day × area × category | **47.7%** | against a Poisson noise floor of **44.2%** |
| MAPE, area × day | **13.7%** | the grain a planner acts on |
| MAPE, category × day citywide | **14.7%** | |
| WAPE | 35.4% | |
| MAE | 2.45 jobs | mean target 6.9 jobs |
| Bias | −6.8% | |

> **The cell-grain MAPE is not a bad score, and quoting it alone would be
> misleading in both directions.** At day × area × category the mean target is
> under seven jobs, and a count that small is dominated by its own Poisson
> variance. Simulating actuals from a *perfectly calibrated* model gives a MAPE
> floor of 44.2%. The model sits 3.5 points above a bound no model can beat.
>
> The registry goal of 12.0 is stated at a coarser grain than the cell level.
> Judged there, the model is at 13.7%.

### Known limitations

- **No weather feature.** The single largest gap. Cancellations and demand
  spikes both track rainfall, and rainfall is currently unobservable to the
  model. It sees `IsMonsoon`, which is a calendar window, not a forecast.
- **Cannot extrapolate a level shift** it has not seen, even with the offset. A
  step change in marketing spend will be under-forecast until it is inside the
  28-day rolling window.
- **Cold-start blindness.** A new area or a new category has no lag history and
  falls back to the structural features alone.
- **Poisson assumes variance equals mean.** Festival windows are over-dispersed;
  intervals are too narrow there.

### Failure modes

| Mode | What it looks like | Detection |
|---|---|---|
| Stale training data | Accuracy holds, then collapses at the next regime change | `TrainingDataAgeDays` |
| Regime shift | PSI climbs, MAPE follows a week or two later | PSI > 0.25 |
| Phantom demand | Forecasts in cells with no work. **Invisible to MAPE** | WAPE vs MAPE gap; count of zero-actual cells |
| Upstream null spike | Feature nulls rise, predictions drift towards the global mean | `FeatureNullPct` |

### Monitoring plan

| Signal | Threshold | Action |
|---|---|---|
| `TrainingDataAgeDays` | **> 14** | Page the on-call. This is the one that matters |
| PSI drift | > 0.25 for 3 consecutive days | Investigate; schedule retrain |
| MAPE (area grain, 7-day rolling) | > 18% | Investigate |
| WAPE − MAPE gap | > 20 points | Review zero-actual cells |
| `FeatureNullPct` | > 1.5% | Check the upstream pipeline |
| p95 latency | > 500 ms | Capacity review |

### Retraining trigger

Weekly on schedule, **and immediately** on any of: PSI > 0.25 sustained three
days; training data age > 14 days; area-grain MAPE > 18% for a week.

### Post-incident note — June 2026 drift

**Summary.** A silent retrain failure left the model 126 days stale. It was
undetected for four months and only became visible when the monsoon changed the
demand regime.

**Timeline.**

| Date | Event |
|---|---|
| **2026-03-15** | Scheduled weekly retrain stops succeeding. No alert — the model keeps serving. `TrainingDataAgeDays` begins climbing off its 7-day sawtooth |
| 2026-03 to 2026-05 | Accuracy unaffected at ~9%. Latent risk only |
| **2026-06-01** | South-west monsoon begins. Plumbing demand nearly doubles, painting collapses. The stale seasonal relationships no longer hold |
| **2026-06-15** | PSI crosses 0.25. First automated signal |
| **2026-06-18** | MAPE reaches a plateau of ~19%, roughly double baseline. `FeatureNullPct` elevated to ~2.5% |
| **2026-07-20** | Retrain lands. Version 2.3.0 → 2.4.0. `TrainingDataAgeDays` resets from **126** to 0 |
| **2026-07-24** | MAPE recovers to ~10%. PSI back under 0.1 |

**Root cause.** The retrain job failed silently. Nothing monitored whether it
had succeeded — only whether the *service* was up, which it always was.

**Why it took four months to surface.** Model degradation is not caused by
staleness; it is caused by staleness *plus* a change in the world. Between March
and June the world did not change, so a three-month-old model performed exactly
like a one-week-old one. The monsoon was the trigger, not the cause.

**Corrective actions.**

1. **Alert on `TrainingDataAgeDays > 14`.** One column, already collected, would
   have caught this on 29 March. *(Highest priority, lowest cost.)*
2. Make the retrain job fail loudly — alert on absence of success, not on
   presence of failure.
3. Add PSI to the pre-deployment gate, not just post-deployment monitoring.
4. Report WAPE beside MAPE on the dashboard permanently.

**Cost.** Not quantified in rupees, because that needs the client's cost per
misallocated technician-day. The exposure is four months of supply
pre-positioning against degrading forecasts, across the busiest season, on the
most business-critical model in the estate.

---

## 2. `pro_match_ranker` — IMPLEMENTED

**Purpose.** Rank available technicians for an incoming job so dispatch offers
go to the best candidate first.

**Owner.** Marketplace ML · **Business critical.** Yes · **Cadence.** Weekly

### Model

| | |
|---|---|
| Registry (client production) | XGBoost LambdaMART |
| Reference implementation here | LightGBM `lambdarank` — the same LambdaMART algorithm, kept in LightGBM so the project carries one gradient-boosting dependency rather than two |
| Training data | 14,000 sampled jobs × 8 candidates = ~112,000 rows |
| Split | **By query group**, 80/20. Never by row |
| Goal | NDCG@5 ≥ 0.82 |

Candidates are drawn from technicians who were genuinely online with a free slot
that day — the set dispatch would actually have chosen from — so the negatives
are plausible rather than absurd. Splitting by group rather than by row matters:
putting a job's winner in train and its losers in validation makes the task
trivial and the metric meaningless.

### Features (13)

Distance (haversine, home area to job site), same-area flag, same-zone flag,
category match, skill tier ordinal, shrunk historical rating, background
verification, lifetime jobs, current-day load ratio, 28-day rolling acceptance
rate, 28-day rolling job count, slots available, emergency flag.

Top by gain: `CategoryMatch`, `LoadRatio`, `SameZone`, `DistanceKm`,
`SkillTierOrd`.

### Held-out performance

| Metric | Value |
|---|---:|
| NDCG@5 | **0.954** |
| NDCG@1 | 0.883 |
| Chosen technician ranked first | 88.3% |
| Chosen technician in top 5 | 100% |
| Random baseline NDCG@5 | ~0.369 |

> ### This score is optimistic and should never be quoted without the caveat
>
> The data generator assigns each job using a **known deterministic function** of
> tier weight, geographic proximity and category match — the same features this
> model receives. The ranker is therefore recovering a process it has been handed
> the ingredients of, not learning a messy human dispatch behaviour.
>
> **Recall@5 of 100% is close to meaningless** when there are only 8 candidates:
> picking the right one within the top 5 of 8 is not a hard problem. NDCG@1 at
> 0.883 is the number worth reading, and even that is flattered.
>
> On production data expect materially worse. The registry goal of 0.82 reflects
> what is realistic when real dispatchers override, technicians decline for
> reasons not in the feature set, and the "right" answer is genuinely ambiguous.

### Known limitations

- **Rich-get-richer.** The model concentrates work on proven technicians: the
  top 10% of the roster take 43% of jobs and Platinum technicians run at 2.4×
  Bronze utilisation. Good for immediate customer experience, corrosive for
  supply retention — a Bronze technician who never gets work churns.
- **No explicit fairness constraint.** There should be one. An exploration floor
  (reserve a small share of offers for under-utilised, adequately-rated
  technicians) is the standard remedy and is not implemented.
- **Distance is a straight line**, not travel time. In Bengaluru traffic that is
  a meaningful approximation error, and it is worst in exactly the peak hours
  where dispatch decisions matter most.
- **No customer-side preference** — no history of which technician a repeat
  customer liked.

### Failure modes

| Mode | Detection |
|---|---|
| Supply pool grows, ranking gets harder | Slow NDCG decay — visible in this dataset, 0.862 → 0.801 by mid-2026 |
| Feedback loop starves new technicians | Utilisation Gini; share of jobs to bottom quartile |
| Distance proxy fails under traffic | ETA prediction error correlated with distance |
| Category taxonomy change | Sharp `CategoryMatch` distribution shift |

### Monitoring and retraining

NDCG@5 daily against 0.82; acceptance rate of top-ranked offers; utilisation
distribution across tiers. Retrain weekly; immediately if NDCG@5 < 0.80 for
three days or the roster grows more than 15% in a month.

---

## 3. `dynamic_price_engine` — IMPLEMENTED

**Purpose.** Produce the low / mid / high price band shown to the customer, plus
an estimated probability the quote is accepted.

**Owner.** Pricing · **Business critical.** Yes · **Cadence.** Weekly

### Model

Four boosters: three LightGBM quantile regressors at α = 0.10, 0.50, 0.90 for
the band, and one binary classifier for accept probability. Trained on 30,945
completed bookings; validated on 15,449 forward in time.

Quantiles are fitted independently and can therefore cross. The three
predictions are **sorted at inference**, which is the standard honest repair; a
monotone model costs more than the problem is worth at this scale. In practice
crossings were zero on the validation set.

### Features

**Price band (18):** service key, category, base price and its log, average
duration, emergency flag, material cost percentage, area key, demand tier,
income band, seasonal multiplier, weekend, monsoon, festival window, month-end,
month, day of week, booking hour.

The quoted amount is **deliberately excluded** — predicting the final price from
the quote would be circular, since the quote is the thing this model exists to
produce.

**Accept probability** adds quote-to-base ratio, discount percentage, and two
area load features (7-day volume, and 7-day against 28-day strain).

### Held-out performance

| Metric | Value | Reading |
|---|---:|---|
| Median price MAPE | **14.5%** | across tickets from ₹450 to ₹45,000 |
| Median price MAE | ₹361 | |
| 10–90 band coverage | **78.2%** | against an 80% target — well calibrated |
| Mean band width | 44.8% of mid | |
| Quantile crossings | 0 | |
| Accept probability AUC | **0.527** | see below |

**The price band is sound.** Coverage within two points of target with no
crossings, on a catalogue spanning two orders of magnitude of ticket size, is a
usable model.

> ### The accept-probability classifier is NOT fit to ship
>
> AUC 0.527 against a 79.4% base rate is barely better than a coin flip.
>
> I added operational load features specifically to improve it. **AUC moved from
> 0.530 to 0.527** — that is, not at all. That result is informative rather than
> disappointing: it rules out the hypothesis rather than leaving it open.
>
> **The diagnosis.** In this dataset, whether a booking completes is driven
> mainly by a per-day heavy-rain draw and by capacity strain, not by price. The
> rain variable is not in the feature set at all, and no available feature
> proxies it. There is genuinely little price-related signal to find.
>
> **The fix is a weather feed, not more tuning.** Until then: quote the band and
> ignore the acceptance number. Do not put it in front of a customer-facing
> decision, and do not let a stakeholder see the number without this paragraph.
>
> Note this also means the registry's `QuoteAcceptRate` goal of 0.62 is
> currently being measured by simulated telemetry, not by this classifier.

### Known limitations

- No competitor pricing. Real price elasticity is relative, and this model has
  no view of what anyone else is charging.
- No customer price sensitivity — no per-customer history of accepting or
  declining.
- Trained on **accepted** prices only, so it learns the distribution of prices
  customers agreed to, not the counterfactual.
- Band width is wide (44.8% of mid) on large tickets, where the underlying
  variance is genuinely large. Correct, but not always commercially useful.

### Monitoring and retraining

Band coverage against 80%; median MAPE; quantile crossing rate; realised accept
rate by predicted decile (which is what would expose the classifier's weakness
in production). Retrain weekly; immediately if coverage leaves 72–88% or median
MAPE exceeds 20%.

---

## 4. `eta_sla_predictor` — REGISTRY ENTRY

**Purpose.** Predict the technician arrival window behind the 90-minute SLA
promise.

**Owner.** Marketplace ML · Critical: No · Cadence: Fortnightly
**Metric.** RMSE in minutes, goal ≤ 14.0. Observed in the dataset: **11.5**.

**Features to build.** Distance and routed travel time, time of day, day of
week, current technician load, area traffic index, weather, job complexity,
technician historical punctuality.

**Known limitations.** Straight-line distance is a poor proxy for Bengaluru
travel time. No live traffic. No weather. Predictions are made at dispatch and
never updated en route, so a technician stuck at Silk Board carries a stale ETA
all the way to the customer's phone.

**Failure modes.** Systematic under-prediction in peak hours; degradation during
monsoon; poor calibration on long-tail journeys across zones.

**Monitoring.** RMSE and mean bias daily; error decomposed by hour of day and by
zone pair; calibration of the promise interval. **Retrain** fortnightly, or
immediately if RMSE exceeds 14 minutes for three consecutive days.

---

## 5. `customer_churn` — REGISTRY ENTRY

**Purpose.** Flag customers unlikely to rebook within 90 days, for retention
targeting.

**Owner.** Growth Analytics · Critical: No · Cadence: Monthly
**Metric.** AUC, goal ≥ 0.79.

**Features to build.** Recency, frequency, monetary value; acquisition channel;
category mix; average rating given; any SLA breach experienced; discount
dependence; app usage; area.

**Known limitations.** Acquisition channel is likely to dominate — Referral and
Organic customers repeat at roughly twice the rate of paid social — which makes
the model good at prediction and weak at *intervention*, because you cannot
change how a customer was acquired. A churn model that mostly rediscovers the
acquisition mix tells the retention team nothing they can act on.

**Failure modes.** Label leakage through recency features; concept drift after
any pricing or policy change; the intervention paradox — a successful retention
campaign makes the model look wrong.

**Monitoring.** AUC and lift at decile 1; PSI on the feature distribution;
realised 90-day rebooking rate by predicted decile. **Retrain** monthly, or on
PSI > 0.25.

---

## 6. `fraud_booking_detector` — REGISTRY ENTRY

**Purpose.** Catch fake, duplicate and abusive bookings before dispatch.

**Owner.** Trust and Safety · **Critical: Yes** · Cadence: Weekly
**Metric.** Precision, goal ≥ 0.71. Reviews trigger above a score of 0.6.

**Approach.** IsolationForest over behavioural features, plus deterministic
rules. The rules exist because some fraud patterns are known and should not wait
for a model to rediscover them; the model exists because the unknown patterns
change faster than rules can be written.

**Known limitations.** Precision is the goal metric, which means recall is
deliberately unmeasured — the cost of a false positive (a real customer
blocked) is treated as higher than a false negative. That trade-off is a
business decision and should be revisited explicitly, not inherited.
Unsupervised anomaly detection has no ground truth, so "precision" here means
precision against analyst review, which is itself a noisy label.

**Documented seasonal behaviour.** Prediction volume spikes and precision drops
across the Diwali window — fraud follows the money, and the attack mix changes
when transaction volume rises 40% and GMV rises 150%. The dataset shows a
precision dip of ~0.13 across that window. This is expected, and the on-call
should not treat it as a regression.

**Monitoring.** Precision against analyst review, weekly; flag rate; value of
flagged bookings; false-positive complaints. **Retrain** weekly; immediately on
a flag-rate change beyond ±50% week over week.

---

## 7. `review_sentiment_indic` — REGISTRY ENTRY

**Purpose.** Classify review sentiment in English, Kannada, Hindi and code-mixed
Kanglish.

**Owner.** Data Science · Critical: No · Cadence: Quarterly
**Metric.** Macro-F1, goal ≥ 0.85.

**Approach.** Fine-tuned **MuRIL** (Multilingual Representations for Indian
Languages). This is the one place in the stack where a transformer is the right
tool rather than the fashionable one — see `PRODUCTION_ARCHITECTURE.md`.

**Why not a generic English model.** A real Bengaluru review reads like
*"work ok tha but bahut late aaya, 2 ghante wait kiya"* — Hindi and English
interleaved, Latin script, no consistent transliteration. An English sentiment
model scores that as mildly positive because it recognises "ok" and nothing
else. MuRIL and IndicBERT are pre-trained on exactly this, including
transliterated text.

**Known limitations.** Macro-F1 hides per-language performance; Kannada and
code-mixed classes are almost certainly weaker than English and must be reported
separately. Sarcasm and politeness conventions differ across languages. Class
imbalance is severe — most reviews are positive.

**Failure modes.** Silent degradation on one language while the macro average
holds; new slang; script drift as more users type in Devanagari or Kannada
script rather than Latin.

**Monitoring.** Macro-F1 **and per-language F1** — the per-language breakdown is
the one that matters. Human agreement rate on a weekly sample. Class
distribution drift. **Retrain** quarterly, or on any per-language F1 falling
below 0.75.

---

## 8. `lead_quality_scorer` — REGISTRY ENTRY

**Purpose.** Score inbound leads so the sales team calls the ones worth calling.

**Owner.** Growth Analytics · Critical: No · Cadence: Monthly
**Metric.** AUC, goal ≥ 0.74.

**Features to build.** Source channel, service category and expected ticket
size, area demand tier, time of day, device and channel, completeness of the
enquiry, repeat-customer flag, local supply availability.

**Known limitations.** The strongest and most awkward feature is **supply
availability**: a lead in a poorly-covered tier-C area converts worse regardless
of its own quality. The model therefore learns to deprioritise exactly the areas
with a coverage problem, which entrenches it. Tier-C areas already convert at
3.21% against tier A's 5.92%, and a scorer trained on that gap will widen it.

That is a genuine feedback loop and it should be handled by scoring *lead
quality* separately from *serviceability*, and routing on both — not by pretending
one number captures both.

**Monitoring.** AUC; realised conversion by predicted decile; conversion by area
tier **within** each predicted decile, which is what exposes the feedback loop.
**Retrain** monthly, or after any material change in area coverage.

---

## Cross-cutting notes

**Why gradient boosting almost everywhere.** Seven of these eight problems are
tabular, with modest row counts and heterogeneous features. Gradient-boosted
trees beat deep learning on this shape of problem, train in seconds rather than
hours, need no GPU, and produce feature importances a non-specialist can argue
with. The eighth is text, which is the one place a transformer earns its cost.

**What is missing from all eight.** No model here has a documented fairness
review, and two of them (`pro_match_ranker`, `lead_quality_scorer`) have
plausible feedback loops that concentrate opportunity — one among technicians,
one among neighbourhoods. Neither is malicious and both are the default outcome
of optimising a single metric. They are noted here rather than solved, because
solving them is a scoping conversation with the client, not a modelling change I
should make unilaterally.

**The monitoring gap that matters most.** Six of the eight models had no
training-data-freshness alert before the June 2026 incident. That is one column,
already collected, on every model. It should be the first thing wired up.
