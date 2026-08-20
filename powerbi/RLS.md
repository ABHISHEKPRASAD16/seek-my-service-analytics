# Row-level security

Two roles are specified: a **Zone Manager** who sees only their own slice of
Bengaluru, and a **read-all executive**. Both are built in Power BI Desktop under
Modeling → **Manage roles**, then tested with **View as**.

Everything below is Desktop-native. Nothing here needs Premium capacity.

---

## 1. Roles

### 1.1 `Executive` — read all

Create the role and add **no filters at all**. An empty role is not the same as
no role: a user assigned to `Executive` gets an unrestricted model, whereas a
user assigned to no role at all cannot open the report once RLS exists.

| Table | Filter |
|---|---|
| *(none)* | *(none)* |

### 1.2 `Zone Manager - East` — one zone

The pattern below is shown for East. Repeat it for `Central`, `North`, `South`
and `West`, changing only the zone literal.

| Table | DAX filter expression |
|---|---|
| `dim_area` | `[Zone] = "East"` |
| `dim_customer` | `LOOKUPVALUE ( dim_area[Zone], dim_area[AreaKey], dim_customer[AreaKey] ) = "East"` |
| `dim_professional` | `LOOKUPVALUE ( dim_area[Zone], dim_area[AreaKey], dim_professional[HomeAreaKey] ) = "East"` |

**Why three filters and not one.** Filtering `dim_area` propagates down every
active relationship, so `fact_bookings`, `fact_leads`, `fact_pro_capacity` and
`fact_forecast_accuracy` are all correctly restricted by the first line alone.

But `dim_customer` and `dim_professional` deliberately have **no active
relationship to `dim_area`** (see `RELATIONSHIPS.md` §5 — it would create an
ambiguous loop). So without the second and third filters, a Zone Manager sees
correct numbers everywhere, and then drops `dim_professional[ProName]` into a
table and gets the **entire 850-person roster, names and all**. The measures
would read zero against most of them, which makes it look like a display quirk
rather than a data leak. It is a data leak.

`LOOKUPVALUE` does the zone join without a relationship, which is exactly the
situation it exists for.

---

## 2. What RLS deliberately does **not** filter

| Table | Filtered by zone? | Reasoning |
|---|---|---|
| `fact_bookings` | Yes, via `dim_area` | Job site is the operational truth |
| `fact_leads` | Yes, via `dim_area` | Funnel is area-scoped |
| `fact_pro_capacity` | Yes, via `dim_area` | Capacity is area-scoped |
| `fact_forecast_accuracy` | Yes, via `dim_area` | Forecast grain includes area |
| `fact_model_metrics` | **No** | Model telemetry has no area dimension. It is platform-wide by nature — a zone manager seeing that the forecaster drifted is correct, because it drifted for their zone too. |
| `dim_date`, `dim_service`, `dim_category`, `dim_model` | **No** | Conformed dimensions carrying no customer or personnel data. Filtering them would break time intelligence for no security benefit. |

Say this out loud in the demo. "The ML Health page is not zone-filtered, and
that is a decision, not an oversight" is the kind of sentence that separates a
model someone thought about from one someone generated.

---

## 3. The production pattern: dynamic RLS

Five static roles work for five zones. They stop working the day someone manages
two zones, or a sixth zone opens, or a manager leaves.

The production answer is one role driven by the signed-in user. It needs a
security table the current dataset does not contain, which is why the static
roles ship instead — but this is what to build in phase two.

**Step 1** — add a `sec_user_zone` table to the warehouse and the model:

| UserEmail | Zone |
|---|---|
| `priya@seekmyservice.in` | East |
| `priya@seekmyservice.in` | North |
| `rahul@seekmyservice.in` | South |

A user managing two zones simply gets two rows. This is the whole reason the
table exists.

**Step 2** — one role, `Zone Manager`, with this filter on `dim_area`:

```dax
dim_area[Zone]
    IN CALCULATETABLE (
        VALUES ( sec_user_zone[Zone] ),
        sec_user_zone[UserEmail] = USERPRINCIPALNAME ()
    )
```

**Step 3** — hide `sec_user_zone` in report view and leave it unrelated to
anything. It is referenced only inside the RLS expression, so a relationship
would just create another ambiguous path.

**Step 4** — in the Service, assign every zone manager to the single
`Zone Manager` role. Membership changes become a warehouse `UPDATE`, not a
Desktop edit and republish.

---

## 4. Testing with "View as role"

In Power BI Desktop: Modeling ribbon → **View as** → tick a role → OK. A yellow
banner appears across the top showing which role you are viewing as. Click
**Stop viewing** to exit.

Run these four tests. The expected values are from the shipped dataset, so any
deviation means the roles are wired wrong.

| # | View as | Where to look | Expect |
|---|---|---|---|
| 1 | *no role* | `[Total Bookings]` card | **57,973** — the unfiltered baseline |
| 2 | `Executive` | `[Total Bookings]` card | **57,973** — identical to test 1. If it is blank, the role has a filter it should not have |
| 3 | `Zone Manager - East` | `[Total Bookings]` card | A smaller number. Add `dim_area[Zone]` to a table: **only East** should appear |
| 4 | `Zone Manager - East` | Table of `dim_professional[ProName]` + `[Roster Size]` | Only East-based technicians. **If you see all 850, the `dim_professional` filter is missing** — this is the test that catches the leak described in §1.2 |

A fifth check worth doing once: with `Zone Manager - East` active, confirm the
five zone numbers from separate roles sum back to 57,973. If they do not, an
area is assigned to a zone no role covers, or to two.

```
East + West + North + South + Central = 57,973
```

---

## 5. Assigning roles in the Power BI Service

Roles created in Desktop travel with the `.pbix` but have **no members** until
they are assigned in the Service.

1. Publish the report to a workspace.
2. In the workspace, find the **semantic model** (not the report) → **⋯** →
   **Security**.
3. Select a role, add users or a security group, **Add** → **Save**.

Notes that save a support call later:

- **Workspace Admins, Members and Contributors bypass RLS entirely.** Testing
  RLS while sitting in the workspace as an Admin will always show you everything.
  Test with a genuine Viewer account, or use **Test as role** in the Service.
- Viewers need a **Power BI Pro** licence unless the workspace sits on Premium or
  Fabric capacity. See `docs/SOW_AND_PRICING.md` for what the client must buy.
- RLS applies to the semantic model, so it protects every report built on it,
  including any the client builds later themselves.
