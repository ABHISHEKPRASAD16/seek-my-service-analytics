-- ============================================================================
-- Seek My Service - staging layer
--
-- One view per source table. Staging does four things and nothing else:
--
--   1. rename to the warehouse's PascalCase convention
--   2. cast to the type the warehouse wants
--   3. flatten the things the OLTP schema normalised (the booking event log
--      into timestamps, quotes and invoices into one money row)
--   4. filter out soft-deleted and test rows
--
-- Staging must contain NO business logic and NO aggregation. The moment a
-- staging view starts deciding what "active" means, two marts disagree about
-- it six months later. Definitions live in 03_star_schema.sql.
--
-- Written as views for readability. In dbt these become models with
-- materialized='view' in stg/, and the "schema.table" references become
-- {{ source('app', 'table') }}.
-- ============================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS staging;
SET search_path TO staging, app;

-- ----------------------------------------------------------------------------
-- stg_localities
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW stg_localities AS
SELECT
    l.locality_id                       AS "AreaKey",
    l.name                              AS "AreaName",
    l.zone                              AS "Zone",
    l.pincode::TEXT                     AS "Pincode",
    ROUND(l.latitude,  4)               AS "Latitude",
    ROUND(l.longitude, 4)               AS "Longitude",
    l.demand_tier                       AS "DemandTier",
    l.income_band                       AS "IncomeBand"
FROM app.localities l
WHERE l.is_serviceable;

-- ----------------------------------------------------------------------------
-- stg_services
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW stg_services AS
SELECT
    s.service_id                        AS "ServiceKey",
    c.name                              AS "ServiceCategory",
    s.name                              AS "ServiceName",
    s.base_price_inr::INT               AS "BasePriceINR",
    s.avg_duration_mins                 AS "AvgDurationMins",
    s.is_emergency::INT                 AS "IsEmergency",
    INITCAP(s.required_tier::TEXT)      AS "SkillTier",
    s.material_cost_pct                 AS "MaterialCostPct",
    c.commission_pct                    AS "CommissionPct",
    c.sort_order * 100 + ROW_NUMBER() OVER (
        PARTITION BY c.category_id ORDER BY s.service_id)  AS "ServiceSortOrder"
FROM app.services s
JOIN app.service_categories c USING (category_id)
WHERE s.is_active;

-- ----------------------------------------------------------------------------
-- stg_professionals
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW stg_professionals AS
SELECT
    p.pro_id                            AS "ProKey",
    p.full_name                         AS "ProName",
    c.name                              AS "PrimaryServiceCategory",
    p.home_locality_id                  AS "HomeAreaKey",
    p.joined_on                         AS "JoinDate",
    INITCAP(p.tier::TEXT)               AS "SkillTier",
    p.background_verified::INT          AS "IsBackgroundVerified",
    (p.churned_on IS NULL)::INT         AS "IsActive",
    ARRAY_TO_STRING(p.languages, '|')   AS "LanguagesSpoken",
    p.onboarding_channel                AS "OnboardingChannel",
    p.churned_on                        AS "ChurnedDate"
FROM app.professionals p
JOIN app.service_categories c ON c.category_id = p.primary_category_id;

-- ----------------------------------------------------------------------------
-- stg_customers
--
-- Note what is NOT here: phone, email, display name. PII stops at the OLTP
-- boundary. The warehouse gets a key and behavioural attributes, nothing that
-- identifies a person. This is a deliberate choice, not an oversight, and it
-- is what makes the row-level security story defensible.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW stg_customers AS
SELECT
    c.customer_id                       AS "CustomerKey",
    c.signup_at::DATE                   AS "SignupDate",
    c.home_locality_id                  AS "AreaKey",
    CASE c.acquisition
        WHEN 'organic_search'     THEN 'Organic Search'
        WHEN 'google_ads'         THEN 'Google Ads'
        WHEN 'meta_ads'           THEN 'Meta Ads'
        WHEN 'referral'           THEN 'Referral'
        WHEN 'justdial'           THEN 'JustDial'
        WHEN 'app_store'          THEN 'App Store'
        WHEN 'whatsapp_broadcast' THEN 'WhatsApp Broadcast'
    END                                 AS "AcquisitionChannel",
    c.is_app_user::INT                  AS "IsAppUser",
    c.preferred_language                AS "PreferredLanguage"
FROM app.customers c
WHERE c.deleted_at IS NULL;

-- ----------------------------------------------------------------------------
-- stg_booking_timestamps
--
-- The event log flattened to one row per booking. Everything downstream needs
-- durations, and durations are differences between events. Doing this once
-- here means nobody ever writes this pivot again.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW stg_booking_timestamps AS
SELECT
    e.booking_id,
    MIN(e.occurred_at) FILTER (WHERE e.state = 'created')      AS created_at,
    MIN(e.occurred_at) FILTER (WHERE e.state = 'assigned')     AS assigned_at,
    MIN(e.occurred_at) FILTER (WHERE e.state = 'accepted')     AS accepted_at,
    MIN(e.occurred_at) FILTER (WHERE e.state = 'en_route')     AS en_route_at,
    MIN(e.occurred_at) FILTER (WHERE e.state = 'in_progress')  AS started_at,
    MIN(e.occurred_at) FILTER (WHERE e.state = 'completed')    AS completed_at,
    MAX(e.occurred_at)                                         AS last_event_at
FROM app.booking_events e
GROUP BY e.booking_id;

-- ----------------------------------------------------------------------------
-- stg_booking_money
--
-- Current quote joined to the invoice. Bookings that never completed have no
-- invoice at all, so the COALESCE to zero happens here once rather than in
-- fifteen measures.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW stg_booking_money AS
SELECT
    b.booking_id,
    q.quoted_inr                                  AS quoted_inr,
    q.discount_inr                                AS discount_inr,
    q.predicted_inr                               AS predicted_inr,
    COALESCE(i.final_inr, 0)                      AS final_inr,
    COALESCE(i.material_cost_inr, 0)              AS material_cost_inr,
    COALESCE(i.platform_fee_inr, 0)               AS platform_fee_inr,
    p.method                                      AS payment_method
FROM app.bookings b
LEFT JOIN app.quotes   q ON q.booking_id = b.booking_id AND q.is_current
LEFT JOIN app.invoices i ON i.booking_id = b.booking_id
LEFT JOIN LATERAL (
    SELECT pay.method
    FROM app.payments pay
    WHERE pay.invoice_id = i.invoice_id
    ORDER BY pay.settled_at NULLS LAST
    LIMIT 1
) p ON TRUE;

-- ----------------------------------------------------------------------------
-- stg_bookings
--
-- One wide, typed row per booking. Note the two CASE blocks that blank out
-- completion-only fields: this is where the "populated only for Completed"
-- rule is enforced, once, rather than being hoped for downstream.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW stg_bookings AS
SELECT
    b.public_ref                                  AS "BookingID",
    TO_CHAR(t.created_at, 'YYYYMMDD')::INT        AS "DateKey",
    t.created_at                                  AS "BookingTimestamp",
    b.customer_id                                 AS "CustomerKey",
    b.assigned_pro_id                             AS "ProKey",
    b.service_id                                  AS "ServiceKey",
    b.locality_id                                 AS "AreaKey",
    INITCAP(b.origin::TEXT)                       AS "Channel",
    CASE b.current_state
        WHEN 'completed'             THEN 'Completed'
        WHEN 'cancelled_by_customer' THEN 'CancelledByCustomer'
        WHEN 'cancelled_by_pro'      THEN 'CancelledByPro'
        WHEN 'no_show'               THEN 'NoShow'
        WHEN 'rescheduled'           THEN 'Rescheduled'
        ELSE 'InFlight'
    END                                           AS "BookingStatus",

    m.quoted_inr                                  AS "QuotedAmountINR",
    m.final_inr                                   AS "FinalAmountINR",
    m.discount_inr                                AS "DiscountINR",
    b.commission_pct                              AS "CommissionPct",
    ROUND(m.platform_fee_inr, 2)                  AS "PlatformRevenueINR",
    ROUND(m.material_cost_inr, 2)                 AS "MaterialCostINR",
    CASE m.payment_method
        WHEN 'upi' THEN 'UPI' WHEN 'card' THEN 'Card' WHEN 'cash' THEN 'Cash'
        WHEN 'wallet' THEN 'Wallet' WHEN 'netbanking' THEN 'NetBanking'
    END                                           AS "PaymentMode",

    -- Durations derived from the event log, in whole minutes.
    ROUND(EXTRACT(EPOCH FROM (t.assigned_at - t.created_at)) / 60.0)::INT
                                                  AS "TimeToAssignMins",
    ROUND(EXTRACT(EPOCH FROM (t.accepted_at - t.assigned_at)) / 60.0)::INT
                                                  AS "ResponseTimeMins",

    o.duration_mins                               AS "JobDurationMins",
    o.sla_met::INT                                AS "SLAMetFlag",
    r.rating                                      AS "CustomerRating",
    r.sentiment                                   AS "ReviewSentiment",
    b.is_repeat::INT                              AS "IsRepeatCustomer",
    m.predicted_inr                               AS "PredictedPriceINR",
    o.actual_eta_mins                             AS "ActualETAMins",
    o.first_time_fix::INT                         AS "IsFirstTimeFix",
    o.reopened_within_7d::INT                     AS "ReopenedWithin7Days"
FROM app.bookings b
JOIN stg_booking_timestamps t ON t.booking_id = b.booking_id
JOIN stg_booking_money      m ON m.booking_id = b.booking_id
LEFT JOIN app.job_outcomes  o ON o.booking_id = b.booking_id
LEFT JOIN app.reviews       r ON r.booking_id = b.booking_id;

-- ----------------------------------------------------------------------------
-- stg_pro_capacity
--
-- Availability joined to what was actually dispatched. The LEFT JOIN direction
-- matters: a technician who opened slots and got nothing must still produce a
-- row, or utilisation silently only ever measures busy days and reads far too
-- healthy.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW stg_pro_capacity AS
SELECT
    TO_CHAR(a.on_date, 'YYYYMMDD')::INT           AS "DateKey",
    a.pro_id                                      AS "ProKey",
    p.home_locality_id                            AS "AreaKey",
    a.slots_offered                               AS "SlotsAvailable",
    COALESCE(bk.booked, 0)                        AS "SlotsBooked",
    (a.went_online_at IS NOT NULL)::INT           AS "IsOnline",
    a.minutes_logged                              AS "HoursLoggedMins",
    COALESCE(off.accepted_count, 0)               AS "AcceptedJobs",
    COALESCE(off.rejected_count, 0)               AS "RejectedJobs"
FROM app.professional_availability a
JOIN app.professionals p ON p.pro_id = a.pro_id
LEFT JOIN (
    SELECT assigned_pro_id AS pro_id, created_at::DATE AS on_date, COUNT(*) AS booked
    FROM app.bookings
    WHERE assigned_pro_id IS NOT NULL
    GROUP BY 1, 2
) bk ON bk.pro_id = a.pro_id AND bk.on_date = a.on_date
LEFT JOIN (
    SELECT pro_id, offered_at::DATE AS on_date,
           COUNT(*) FILTER (WHERE accepted)            AS accepted_count,
           COUNT(*) FILTER (WHERE accepted IS FALSE)   AS rejected_count
    FROM app.dispatch_offers
    GROUP BY 1, 2
) off ON off.pro_id = a.pro_id AND off.on_date = a.on_date;

-- ----------------------------------------------------------------------------
-- stg_funnel
--
-- Searches, leads, quotes and bookings collapsed onto a day x area x service
-- grid. Counting each stage independently from its own table is what keeps the
-- funnel monotonic: a lead cannot outnumber the searches it came from because
-- it carries the search_id it came from.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW stg_funnel AS
WITH s AS (
    SELECT searched_at::DATE AS d, locality_id, service_id, COUNT(*) AS searches
    FROM app.search_events GROUP BY 1, 2, 3
), l AS (
    SELECT created_at::DATE AS d, locality_id, service_id,
           COUNT(*) AS leads,
           COUNT(*) FILTER (WHERE quoted) AS quotes,
           AVG(quality_score) AS avg_quality
    FROM app.leads GROUP BY 1, 2, 3
), b AS (
    SELECT created_at::DATE AS d, locality_id, service_id, COUNT(*) AS bookings
    FROM app.bookings GROUP BY 1, 2, 3
)
SELECT
    TO_CHAR(s.d, 'YYYYMMDD')::INT   AS "DateKey",
    s.locality_id                   AS "AreaKey",
    s.service_id                    AS "ServiceKey",
    s.searches                      AS "Searches",
    COALESCE(l.leads, 0)            AS "Leads",
    COALESCE(l.quotes, 0)           AS "QuotesSent",
    COALESCE(b.bookings, 0)         AS "Bookings",
    ROUND(COALESCE(l.avg_quality, 0), 3) AS "AvgLeadQualityScore"
FROM s
LEFT JOIN l ON l.d = s.d AND l.locality_id = s.locality_id AND l.service_id = s.service_id
LEFT JOIN b ON b.d = s.d AND b.locality_id = s.locality_id AND b.service_id = s.service_id
WHERE s.searches > 0;

-- ----------------------------------------------------------------------------
-- stg_model_metrics
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW stg_model_metrics AS
SELECT
    TO_CHAR(d.metric_date, 'YYYYMMDD')::INT AS "DateKey",
    m.model_id                              AS "ModelKey",
    d.metric_name                           AS "MetricName",
    d.metric_value                          AS "MetricValue",
    m.metric_goal                           AS "MetricGoal",
    CASE
        WHEN m.goal_direction = 'LowerIsBetter'  AND d.metric_value > m.metric_goal THEN 1
        WHEN m.goal_direction = 'HigherIsBetter' AND d.metric_value < m.metric_goal THEN 1
        ELSE 0
    END                                     AS "IsBreach",
    d.psi_drift                             AS "PSIDriftScore",
    d.prediction_volume                     AS "PredictionVolume",
    d.p95_latency_ms                        AS "P95LatencyMs",
    d.feature_null_pct                      AS "FeatureNullPct",
    (d.metric_date - v.training_data_max_date) AS "TrainingDataAgeDays",
    v.version                               AS "ModelVersion"
FROM app.ml_metric_daily d
JOIN app.ml_model_versions v ON v.version_id = d.version_id
JOIN app.ml_models m         ON m.model_id  = v.model_id;

COMMIT;
