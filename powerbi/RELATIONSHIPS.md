# Star schema wiring

Twelve tables: six dimensions, five facts, and one derived bridge. Every
relationship is **many-to-one, single cross-filter direction, dimension filtering
fact**. There are no bidirectional filters and no fact-to-fact relationships
anywhere in this model.

Build these in Model view before running the measure script — four measures
reference relationships by name and will show an error until they exist.

---

## 1. Active relationships

| # | From (many side) | To (one side) | Cardinality | Cross-filter | Active |
|---|---|---|---|---|---|
| 1 | `fact_bookings[DateKey]` | `dim_date[DateKey]` | Many to one | Single | Yes |
| 2 | `fact_bookings[ServiceKey]` | `dim_service[ServiceKey]` | Many to one | Single | Yes |
| 3 | `fact_bookings[AreaKey]` | `dim_area[AreaKey]` | Many to one | Single | Yes |
| 4 | `fact_bookings[ProKey]` | `dim_professional[ProKey]` | Many to one | Single | Yes |
| 5 | `fact_bookings[CustomerKey]` | `dim_customer[CustomerKey]` | Many to one | Single | Yes |
| 6 | `fact_pro_capacity[DateKey]` | `dim_date[DateKey]` | Many to one | Single | Yes |
| 7 | `fact_pro_capacity[ProKey]` | `dim_professional[ProKey]` | Many to one | Single | Yes |
| 8 | `fact_pro_capacity[AreaKey]` | `dim_area[AreaKey]` | Many to one | Single | Yes |
| 9 | `fact_leads[DateKey]` | `dim_date[DateKey]` | Many to one | Single | Yes |
| 10 | `fact_leads[AreaKey]` | `dim_area[AreaKey]` | Many to one | Single | Yes |
| 11 | `fact_leads[ServiceKey]` | `dim_service[ServiceKey]` | Many to one | Single | Yes |
| 12 | `fact_model_metrics[DateKey]` | `dim_date[DateKey]` | Many to one | Single | Yes |
| 13 | `fact_model_metrics[ModelKey]` | `dim_model[ModelKey]` | Many to one | Single | Yes |
| 14 | `fact_forecast_accuracy[DateKey]` | `dim_date[DateKey]` | Many to one | Single | Yes |
| 15 | `fact_forecast_accuracy[AreaKey]` | `dim_area[AreaKey]` | Many to one | Single | Yes |
| 16 | `fact_forecast_accuracy[ServiceCategory]` | `dim_category[ServiceCategory]` | Many to one | Single | Yes |
| 17 | `dim_service[ServiceCategory]` | `dim_category[ServiceCategory]` | Many to one | Single | Yes |

## 2. Inactive relationships

| # | From (many side) | To (one side) | Cardinality | Cross-filter | Active | Activated by |
|---|---|---|---|---|---|---|
| 18 | `dim_professional[JoinDate]` | `dim_date[Date]` | Many to one | Single | **No** | `[New Pro Onboarding Count]` |
| 19 | `dim_customer[SignupDate]` | `dim_date[Date]` | Many to one | Single | **No** | `[Customer Signups]` |

**Why each one is inactive, in a line:**

- **18** — `dim_professional` already reaches `dim_date` through `fact_bookings` and
  `fact_pro_capacity`; a second active path would be ambiguous, so the join date
  is activated only inside `USERELATIONSHIP` when you specifically want to count
  joiners rather than workers.
- **19** — same shape: `dim_customer` reaches `dim_date` through `fact_bookings`,
  so the signup date is activated only when counting account creations, which
  deliberately lead first bookings by up to 25 days.

## 3. Date table

Mark `dim_date` as the date table: select the table → Table tools → **Mark as
date table** → date column `Date`.

Every time-intelligence measure (`DATEADD`, `DATESINPERIOD`, `DATESYTD`) requires
this. Without it they return blank or, worse, quietly wrong values at year
boundaries.

`dim_date` is contiguous across all 608 days with no gaps, which is the other
requirement time intelligence has and the one people usually miss.

---

## 4. The `dim_category` bridge, and why it exists

`fact_forecast_accuracy` is at **day × area × service category** grain — the
forecaster predicts category-level volume, not individual service volume. Its
`ServiceCategory` column is text.

You cannot relate it directly to `dim_service[ServiceCategory]`, because that
column holds 37 rows across 8 categories and so is not unique. The one side of a
relationship must be unique.

`dim_category` is a one-column table of the 8 distinct categories, built in Power
Query from `dim_service` (see `queries.m`). It sits above both:

```
dim_category ──1:*──> dim_service ──1:*──> fact_bookings
     │                                     fact_leads
     └────────1:*──> fact_forecast_accuracy
```

This keeps the "no fact-to-fact relationships" rule intact while letting one
category slicer filter both booking volume and forecast accuracy at once.

> **Build-guide consequence — this one bites people.**
> Slice category visuals from **`dim_category[ServiceCategory]`**, not from
> `dim_service[ServiceCategory]`. The latter filters bookings and leads but
> leaves the forecast fact wide open, so a "forecast vs actual by category"
> visual would show the same forecast total against every category.
>
> Fix it structurally rather than by remembering: in Model view, select
> `dim_service[ServiceCategory]` → right-click → **Hide in report view**. Now the
> only category field a report author can reach is the correct one.

---

## 5. Relationships you should deliberately *not* create

These are the ones a reviewer will look for, so it is worth knowing why they are
absent rather than forgotten.

| Tempting relationship | Why it is wrong here |
|---|---|
| `dim_customer[AreaKey]` → `dim_area[AreaKey]` | Creates a loop: `dim_area` already reaches `fact_bookings` directly *and* would reach it again through `dim_customer`. Power BI would force one path inactive and the model becomes ambiguous to read. A booking's area is the **job site**; the customer's area is where they live. They agree ~88% of the time, and the fact column is the one that matters for operations. |
| `dim_professional[HomeAreaKey]` → `dim_area[AreaKey]` | Same loop, via `fact_pro_capacity`. `fact_pro_capacity[AreaKey]` already carries the technician's home area at the correct grain, so the dimension-level column is redundant for filtering. |
| Any `fact_*` → `fact_*` | Never. `dim_date`, `dim_area` and `dim_service`/`dim_category` are the conformed bridges; two facts filtered by the same dimension is how they meet. |
| `fact_bookings[DateKey]` → `dim_date[DateKey]` **bidirectional** | Would let a booking filter propagate back up into `dim_date` and then down into `fact_pro_capacity`, silently restricting capacity to days that happened to have bookings. Utilisation would then never show an idle day, which is precisely the number you want to see. |

---

## 6. Verification after wiring

Five quick checks that catch the common mistakes.

1. **Model view** shows exactly 17 solid lines and 2 dotted lines. No table is
   floating unconnected.
2. Every arrow points **from the dimension to the fact** (the `1` is on the
   dimension end, the `*` on the fact end).
3. Card visual with `[Total Bookings]` = **57,973**. Add `dim_date[MonthYear]`
   as a slicer and confirm it moves.
4. Card visual with `[Funnel Bookings]` also = **57,973**. If these two disagree,
   a relationship on `fact_leads` is wrong or missing.
5. Card with `[Slots Booked]` = **57,973** as well. All three facts agree because
   the generator built the funnel and the capacity table backwards from real
   bookings.

If checks 3, 4 and 5 all show the same number, the star is wired correctly.
