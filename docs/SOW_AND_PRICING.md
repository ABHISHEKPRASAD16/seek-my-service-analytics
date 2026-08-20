# Scope of work and indicative pricing

**Engagement:** marketplace analytics platform and ML monitoring layer
**Client:** Seek My Service (home-services marketplace, Bengaluru)
**Supplier:** independent AI/ML engineer
**Currency:** INR, exclusive of GST
**Status:** indicative. Superseded by a signed agreement.

---

## 1. Background

The client operates a home-services marketplace across Bengaluru with eight
service categories, a technician roster in the high hundreds, and eight machine
learning models in production. There is currently no analytics layer: reporting
is by ad-hoc export from the transactional database, and no model has automated
monitoring.

This engagement builds the analytics and monitoring layer, pointed at the
client's own data, using the reference implementation already demonstrated.

---

## 2. Scope of work

### In scope

| # | Workstream | Detail |
|---|---|---|
| 1 | **Warehouse foundations** | Read replica configuration; extraction into a raw layer; dbt project with staging and mart models; the star schema built and tested nightly |
| 2 | **Data quality** | Sixteen integrity checks implemented as dbt tests — referential integrity, date continuity, money rules, chronology, funnel monotonicity, capacity reconciliation. A failing test stops the pipeline |
| 3 | **Semantic model** | Power BI import-mode model; ~119 DAX measures with format strings and display folders; relationships, sort orders, hidden keys; deployed by script |
| 4 | **Report** | Four pages — Ops Control Room, Demand Intelligence, Supply Health, ML Model Health — with conditional formatting, a field parameter, and dynamic titles |
| 5 | **Security** | Row-level security by zone plus a read-all executive role; dynamic RLS driven by a warehouse mapping table; documented test procedure |
| 6 | **ML services** | Three FastAPI services (demand forecasting, technician matching, dynamic pricing) containerised, loading from a model registry, with predictions written back to the database |
| 7 | **ML monitoring** | MLflow tracking and registry; daily telemetry for all eight models; alerting on training-data age, drift, and metric breach |
| 8 | **Orchestration** | Scheduled pipeline with failure alerting. Cron initially; Prefect or Airflow if and when complexity justifies it (see §5) |
| 9 | **Handover** | Data dictionary, model cards, runbook, architecture documentation, and two working sessions with the client's team |

### Out of scope

Explicitly excluded. Any of these can be added by change request.

- Migration of historical data older than the agreed window.
- Changes to the client's transactional application or database schema, beyond
  configuring a read replica and adding the prediction write-back tables.
- Building or retraining the five registry-only models (`eta_sla_predictor`,
  `customer_churn`, `fraud_booking_detector`, `review_sentiment_indic`,
  `lead_quality_scorer`). Their monitoring is in scope; their construction is a
  separate engagement.
- Labelling of review data for the Indic sentiment model.
- Power BI licences, cloud infrastructure, or any third-party subscription (§7).
- Mobile or embedded analytics, Power BI Embedded, or white-labelled reporting.
- 24×7 support, on-call rota, or any uptime SLA. Support terms in §8.
- Data migration to a new warehouse platform, if the client later chooses one.
- Training the client's team to write DAX beyond the two handover sessions.

---

## 3. Milestones

Five milestones. Each has a deliverable and an acceptance criterion that can be
objectively verified — no milestone is accepted on the basis of a demo alone.

### M1 — Warehouse foundations · Weeks 1–3

**Deliverables.** Read replica configured. Extraction job. dbt project with
staging and mart layers producing all eleven tables. Sixteen data quality tests.
Scheduled nightly run with failure alerting.

**Acceptance criteria**
1. `dbt build` completes with zero failing tests against production data.
2. All eleven tables materialise with row counts within 5% of the client's own
   figures for the same period.
3. A deliberately corrupted record causes the relevant test to fail and the
   pipeline to stop.
4. The pipeline runs unattended on schedule for five consecutive nights.

### M2 — Semantic model and report · Weeks 3–5

**Deliverables.** Power BI import model on the marts. Measure library deployed.
Four report pages. RLS roles. Scheduled refresh triggered by the pipeline.
Theme applied.

**Acceptance criteria**
1. Every measure returns a non-error value against production data.
2. `[Total Bookings]`, `[Funnel Bookings]` and `[Slots Booked]` agree exactly —
   the three-way check that proves the star is wired correctly.
3. All four pages render in under three seconds on first load.
4. A nominated zone manager, viewing as their role, sees only their zone —
   including in the technician and customer tables.
5. Refresh completes on schedule for five consecutive nights and does **not**
   run when dbt tests fail.

### M3 — ML services in production · Weeks 5–8

**Deliverables.** MLflow tracking and registry. Three services containerised,
deployed, loading from the registry. Predictions written back to the database.
OpenAPI documentation.

**Acceptance criteria**
1. All three services return HTTP 200 on `/health` with `model_loaded: true`.
2. Each service serves a prediction within its agreed latency budget at p95
   under expected load.
3. Predictions appear in `ml_predictions` and are joinable to bookings.
4. A model promoted from `Staging` to `Production` in MLflow is served by the
   API without redeployment.
5. Held-out metrics for each model are recorded in the registry and match the
   model cards.

### M4 — Monitoring and alerting · Week 8

**Deliverables.** Daily telemetry populated for all eight models. ML Health page
fed by real data rather than simulated telemetry. Alerting on training-data age,
PSI drift, and metric breach.

**Acceptance criteria**
1. `fact_model_metrics` populates daily for all eight models.
2. A model with training data older than 14 days triggers an alert to the
   agreed channel **within one day**.
3. A simulated drift event (PSI forced above 0.25) triggers an alert.
4. The ML Health page reflects live telemetry, verified against MLflow.

> Criterion 2 is the one that matters. It is the control that would have caught
> the June 2026 incident in March.

### M5 — Handover and stabilisation · Weeks 8–10

**Deliverables.** Data dictionary, model cards, architecture documentation and
an operational runbook, all against the client's implementation. Two working
sessions. Two weeks of stabilisation support.

**Acceptance criteria**
1. A nominated client engineer, following the runbook alone, can rebuild the
   warehouse from scratch and refresh the report.
2. A nominated client analyst can add a new measure and a new visual unaided.
3. Documentation reviewed and signed off.
4. No severity-1 defects open at the end of the stabilisation period.

---

## 4. Assumptions

The estimate depends on these. If one turns out to be false, §5 applies.

1. The client provides read access to a Postgres or MySQL primary, and can
   stand up a read replica within the first week.
2. The transactional schema is broadly as described in `sql/01_source_schema.sql`
   — that is, booking state is recoverable, and quotes and payments are
   reconcilable to bookings.
3. Historical data covers at least 18 months. Below 12 months the seasonal
   findings are not supportable and the forecasting model has too little signal.
4. The client owns a Power BI tenant, or will procure one before M2.
5. Cloud infrastructure (warehouse, container hosting, MLflow) is provisioned
   and paid for by the client, on their accounts.
6. One client-side technical point of contact is available for up to four hours
   a week for questions and reviews.
7. Business definitions — "active customer", "at risk technician", the SLA
   window — are agreed by the end of week 2. Late changes to a definition are
   change requests, because measures, tests and documentation all follow from it.
8. The client's data does not require anonymisation beyond excluding PII from
   the warehouse, and no additional regulatory review (DPDP Act assessment,
   sectoral compliance) is required within this engagement.
9. Work is performed remotely. On-site days in Bengaluru are available and
   billed separately.

---

## 5. Change requests

Any of the following constitutes a change request:

- A new report page, or more than three additional visuals on an existing page.
- A change to an agreed business definition after the milestone that used it has
  been accepted.
- Building or retraining any of the five registry-only models.
- Migration to a different warehouse platform after M1.
- A source schema materially different from assumption 2 — for example booking
  state that cannot be reconstructed, or payments that cannot be tied to
  bookings.
- Additional data sources not listed in scope (ad platform APIs, call logs,
  weather feeds).
- Any request for real-time or sub-hourly refresh.

**Process.** Change requests are estimated in writing within two working days,
priced at the standard day rate, and require written approval before work
begins. Requests under half a day are absorbed at the supplier's discretion, and
absorbing one does not create a precedent.

**Schedule.** An approved change request extends the affected milestone by the
estimated duration plus any dependency impact.

---

## 6. Indicative fee structure

Rates reflect the Indian market for an independent senior AI/ML engineer with
demonstrable production and BI delivery experience. All figures **exclude GST**.

### Day rate

| Engagement type | Rate per day (8 hours) |
|---|---:|
| Standard delivery | **₹18,000 – ₹25,000** |
| Discovery, architecture, advisory | ₹25,000 – ₹32,000 |
| On-site in Bengaluru | Standard rate + ₹5,000 per day |

### Fixed-price milestones

Recommended for both sides: the scope above is well understood and the client
gets certainty.

| Milestone | Effort | Indicative fee |
|---|---:|---:|
| M1 — Warehouse foundations | 12–15 days | ₹2,40,000 – ₹3,25,000 |
| M2 — Semantic model and report | 9–11 days | ₹1,80,000 – ₹2,40,000 |
| M3 — ML services in production | 13–16 days | ₹2,60,000 – ₹3,50,000 |
| M4 — Monitoring and alerting | 4–5 days | ₹80,000 – ₹1,10,000 |
| M5 — Handover and stabilisation | 5–6 days | ₹1,00,000 – ₹1,30,000 |
| **Total** | **43–53 days** | **₹8,60,000 – ₹11,55,000** |

**A realistic mid-point for the full engagement is around ₹9,50,000 over ten
weeks**, assuming the assumptions in §4 hold.

### Payment schedule

| Trigger | Share |
|---|---:|
| Signature (mobilisation) | 20% |
| M1 accepted | 20% |
| M2 accepted | 20% |
| M3 accepted | 25% |
| M5 accepted | 15% |

Invoices are payable within **15 days**. Work on the next milestone does not
begin while an invoice is more than 30 days overdue.

### Smaller entry points

If the full engagement is more than the client wants to commit to now, either of
these stands alone and produces something useful:

| Option | Scope | Duration | Fee |
|---|---|---:|---:|
| **Discovery sprint** | Schema review, data quality assessment, findings memo, costed roadmap | 5 days | ₹1,10,000 – ₹1,50,000 |
| **Report-only** | M1 and M2 against existing data; no ML workstream | 4 weeks | ₹4,20,000 – ₹5,65,000 |

The discovery sprint is the honest recommendation for a client who is not yet
sure. It is fully credited against the full engagement if they proceed within 60
days.

### Ongoing support (optional, post-handover)

| Tier | Includes | Monthly |
|---|---|---:|
| Light | Pipeline monitoring, up to 2 days of changes | ₹35,000 |
| Standard | Above, plus model retraining oversight and quarterly review, up to 4 days | ₹65,000 |

Response within one business day. No 24×7 cover, no uptime SLA.

---

## 7. Software the client must buy

**None of this is included in the fees above.** These are the client's own
subscriptions, on the client's own accounts.

### Power BI

| Item | Cost | Who needs it |
|---|---|---|
| **Power BI Pro** | approx. **₹1,000 per user per month** | Every person who **views** the report, and every person who publishes. There is no free viewer tier without Premium or Fabric capacity |
| Power BI Desktop | Free | Authoring only |
| Tabular Editor 2 | Free, open source | Deploying the measure library in one run |

For ten viewers and two authors: **twelve Pro licences, roughly ₹12,000 per
month**.

> ### On Copilot in Power BI — read this before budgeting for it
>
> Copilot is **not** available on Pro licences.
>
> It requires paid capacity: **Fabric F2 or higher**, or legacy **Premium P1**.
> **Premium Per User (PPU) alone does not unlock it.** This catches people out
> regularly, because PPU is marketed as the premium individual tier and Copilot
> sounds like a premium individual feature.
>
> Indicative capacity cost: Fabric F2 starts around **₹22,000–₹26,000 per
> month** at pay-as-you-go, considerably more for F8 and above where Copilot
> performance is actually comfortable.
>
> **Nothing in this engagement requires Copilot.** Everything specified is built
> by hand and works on Pro. If the client wants Copilot, treat it as a separate
> budget line with a separate business case — and I would not recommend it
> before the warehouse and the semantic model are in place, because Copilot on
> top of a badly modelled dataset produces confident nonsense faster than a
> human could.

### Infrastructure (indicative, client's cloud account)

| Item | Indicative monthly |
|---|---:|
| Postgres read replica (small instance) | ₹6,000 – ₹12,000 |
| Container hosting for three services (2 replicas) | ₹8,000 – ₹15,000 |
| MLflow server plus artefact storage | ₹4,000 – ₹8,000 |
| Warehouse, if adopted later (BigQuery / Snowflake) | ₹15,000+, usage-dependent |

**Realistic run cost for the first year, excluding a separate warehouse:
₹18,000 – ₹35,000 per month plus Power BI licences.**

---

## 8. Commercial terms

**Intellectual property.** On full payment, the client owns all deliverables
created specifically for them — dbt models, DAX, report definitions, trained
model artefacts, documentation. The supplier retains ownership of pre-existing
generic tooling, patterns and reference implementations, and may reuse them
provided no client data, branding or confidential information is included.

**Confidentiality.** Mutual. The supplier will not disclose client data,
business metrics or trade secrets. **Portfolio use is restricted to synthetic
data only** — the reference implementation demonstrated to the client uses no
real records, and that remains the case.

**Data protection.** The supplier accesses client data only as required for
delivery, does not copy production data to personal devices, and excludes PII
from the warehouse by design. The client remains the data fiduciary under the
Digital Personal Data Protection Act, 2023.

**Warranty.** Defects in delivered work reported within 30 days of milestone
acceptance are corrected at no charge. This covers defects, not changes in
requirements.

**Liability.** Capped at the total fees paid under this engagement. Neither
party is liable for indirect or consequential loss.

**Termination.** Either party may terminate on 14 days' written notice. Work
completed to the date of termination is invoiced and payable; work in progress
is handed over in whatever state it has reached.

**Availability.** Delivery days are Monday to Friday, Indian business hours.
Reasonable-effort response within one business day. This is a professional
services engagement, not an operational support contract.

---

*Prepared as an indicative commercial framework. Figures are estimates for
planning and are not an offer. Final scope, schedule and fees to be confirmed in
a signed agreement following discovery.*
