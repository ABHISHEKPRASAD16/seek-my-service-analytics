-- ============================================================================
-- Seek My Service - dimensional build
--
-- Produces the eleven tables Power BI imports, from the staging views in 02.
-- This is where business definitions live, and they live here ONCE: "active
-- customer", "repeat", "at risk", "capacity strain" are defined in this file
-- and nowhere else.
--
-- Written as CREATE TABLE AS so it runs standalone against a warehouse. The
-- dbt-shaped equivalent is noted above each block: each becomes one model in
-- marts/, with {{ ref('stg_x') }} in place of the staging.stg_x references and
-- the materialisation set in the config.
--
-- Load order matters: dimensions first, then facts, then the two dimension
-- columns that are derived FROM the facts.
-- ============================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS warehouse;
SET search_path TO warehouse, staging, app;

-- ============================================================================
-- 1. dim_date
--    dbt: models/marts/dim_date.sql, materialized='table'
--
-- Generated rather than sourced. A date dimension built from observed
-- transaction dates has gaps on quiet days, and a gap breaks every DAX
-- time-intelligence function in ways that are maddening to diagnose.
-- ============================================================================
DROP TABLE IF EXISTS dim_date CASCADE;
CREATE TABLE dim_date AS
WITH calendar AS (
    SELECT generate_series(DATE '2025-01-01', DATE '2026-08-31', INTERVAL '1 day')::DATE AS d
),
festivals AS (
    -- Windows, not single days. Diwali demand starts building well before the
    -- day itself, which is the entire point of the deep-cleaning spike.
    SELECT * FROM (VALUES
        ('Diwali',                 10, 12, 11,  5),
        ('Ugadi',                   3, 15,  4,  5),
        ('Sankranti',               1, 10,  1, 17),
        ('Ganesh Chaturthi',        8, 24,  9,  1),
        ('Christmas and New Year', 12, 22, 12, 31)
    ) AS f(name, start_month, start_day, end_month, end_day)
)
SELECT
    TO_CHAR(c.d, 'YYYYMMDD')::INT                              AS "DateKey",
    c.d                                                        AS "Date",
    EXTRACT(YEAR FROM c.d)::INT                                AS "Year",
    'Q' || EXTRACT(QUARTER FROM c.d)::TEXT                     AS "Quarter",
    EXTRACT(MONTH FROM c.d)::INT                               AS "MonthNo",
    TO_CHAR(c.d, 'FMMonth')                                    AS "MonthName",
    TO_CHAR(c.d, 'Mon YYYY')                                   AS "MonthYear",
    (EXTRACT(YEAR FROM c.d) * 100 + EXTRACT(MONTH FROM c.d))::INT AS "MonthYearSort",
    EXTRACT(WEEK FROM c.d)::INT                                AS "WeekNo",
    TO_CHAR(c.d, 'FMDay')                                      AS "DayName",
    EXTRACT(ISODOW FROM c.d)::INT                              AS "DayOfWeekNo",
    (EXTRACT(ISODOW FROM c.d) >= 6)::INT                       AS "IsWeekend",
    -- Bengaluru has two monsoons. Modelling only the south-west one loses the
    -- entire October plumbing surge.
    (
        (c.d BETWEEN MAKE_DATE(EXTRACT(YEAR FROM c.d)::INT, 6, 1)
                 AND MAKE_DATE(EXTRACT(YEAR FROM c.d)::INT, 9, 30))
     OR (c.d BETWEEN MAKE_DATE(EXTRACT(YEAR FROM c.d)::INT, 10, 10)
                 AND MAKE_DATE(EXTRACT(YEAR FROM c.d)::INT, 11, 20))
    )::INT                                                     AS "IsMonsoon",
    (EXISTS (
        SELECT 1 FROM festivals f
        WHERE c.d BETWEEN MAKE_DATE(EXTRACT(YEAR FROM c.d)::INT, f.start_month, f.start_day)
                      AND MAKE_DATE(EXTRACT(YEAR FROM c.d)::INT, f.end_month, f.end_day)
    ))::INT                                                    AS "IsFestivalWindow",
    COALESCE(
        (SELECT h.name FROM warehouse.public_holidays h WHERE h.holiday_date = c.d),
        (SELECT f.name FROM festivals f
         WHERE c.d BETWEEN MAKE_DATE(EXTRACT(YEAR FROM c.d)::INT, f.start_month, f.start_day)
                       AND MAKE_DATE(EXTRACT(YEAR FROM c.d)::INT, f.end_month, f.end_day)
         LIMIT 1),
        ''
    )                                                          AS "FestivalName",
    -- The last five days of the month: the salary-cycle window where
    -- discretionary spend defers. Not "the last day of the month".
    (EXTRACT(DAY FROM c.d)
        > EXTRACT(DAY FROM (DATE_TRUNC('month', c.d) + INTERVAL '1 month - 1 day')) - 5
    )::INT                                                     AS "IsMonthEnd",
    -- Indian fiscal year: April to March.
    'FY' || LPAD(((CASE WHEN EXTRACT(MONTH FROM c.d) >= 4
                        THEN EXTRACT(YEAR FROM c.d)
                        ELSE EXTRACT(YEAR FROM c.d) - 1 END)::INT % 100)::TEXT, 2, '0')
         || '-' || LPAD(((CASE WHEN EXTRACT(MONTH FROM c.d) >= 4
                        THEN EXTRACT(YEAR FROM c.d) + 1
                        ELSE EXTRACT(YEAR FROM c.d) END)::INT % 100)::TEXT, 2, '0')
                                                               AS "FiscalYear",
    'Q' || ((((EXTRACT(MONTH FROM c.d)::INT - 4) % 12 + 12) % 12) / 3 + 1)::TEXT
                                                               AS "FiscalQuarter",
    (EXISTS (SELECT 1 FROM warehouse.public_holidays h
             WHERE h.holiday_date = c.d))::INT                 AS "IsHoliday",
    (c.d - DATE '2026-08-31')                                  AS "DaysFromToday"
FROM calendar c;

ALTER TABLE dim_date ADD PRIMARY KEY ("DateKey");
CREATE UNIQUE INDEX idx_dim_date_date ON dim_date ("Date");

-- ============================================================================
-- 2. Conformed dimensions
--    dbt: models/marts/dim_area.sql, dim_service.sql, dim_category.sql
-- ============================================================================
DROP TABLE IF EXISTS dim_area CASCADE;
CREATE TABLE dim_area AS
SELECT
    s.*,
    ROW_NUMBER() OVER (ORDER BY s."Zone", s."AreaName")::INT AS "AreaSortOrder"
FROM staging.stg_localities s;
ALTER TABLE dim_area ADD PRIMARY KEY ("AreaKey");

DROP TABLE IF EXISTS dim_service CASCADE;
CREATE TABLE dim_service AS SELECT * FROM staging.stg_services;
ALTER TABLE dim_service ADD PRIMARY KEY ("ServiceKey");

-- The bridge. fact_forecast_accuracy is at category grain, and
-- dim_service."ServiceCategory" is not unique, so it cannot be the one side of
-- a relationship. See powerbi/RELATIONSHIPS.md section 4.
DROP TABLE IF EXISTS dim_category CASCADE;
CREATE TABLE dim_category AS
SELECT DISTINCT "ServiceCategory" FROM dim_service ORDER BY 1;
ALTER TABLE dim_category ADD PRIMARY KEY ("ServiceCategory");

-- ============================================================================
-- 3. fact_bookings
--    dbt: models/marts/fact_bookings.sql, materialized='incremental'
--         unique_key='BookingID', incremental on "BookingTimestamp"
--
-- The completion-only blanking is enforced here. A cancelled job has no
-- duration and no SLA outcome, and writing zero instead of null would drag
-- every average in the model downwards while looking perfectly reasonable.
-- ============================================================================
DROP TABLE IF EXISTS fact_bookings CASCADE;
CREATE TABLE fact_bookings AS
SELECT
    b."BookingID",
    b."DateKey",
    b."BookingTimestamp",
    b."CustomerKey",
    b."ProKey",
    b."ServiceKey",
    b."AreaKey",
    b."Channel",
    b."BookingStatus",
    b."QuotedAmountINR",
    b."FinalAmountINR",
    b."DiscountINR",
    b."CommissionPct",
    b."PlatformRevenueINR",
    b."MaterialCostINR",
    b."PaymentMode",
    b."TimeToAssignMins",
    b."ResponseTimeMins",
    CASE WHEN b."BookingStatus" = 'Completed' THEN b."JobDurationMins"       END AS "JobDurationMins",
    CASE WHEN b."BookingStatus" = 'Completed' THEN b."SLAMetFlag"            END AS "SLAMetFlag",
    b."CustomerRating",
    b."ReviewSentiment",
    b."IsRepeatCustomer",
    b."PredictedPriceINR",
    pe.predicted_eta_mins                                                        AS "PredictedETAMins",
    CASE WHEN b."BookingStatus" = 'Completed' THEN b."ActualETAMins"         END AS "ActualETAMins",
    ms.match_score                                                               AS "MatchScore",
    fs.fraud_score                                                               AS "FraudScore",
    cs.churn_score                                                               AS "ChurnRiskScore",
    CASE WHEN b."BookingStatus" = 'Completed' THEN b."IsFirstTimeFix"        END AS "IsFirstTimeFix",
    CASE WHEN b."BookingStatus" = 'Completed' THEN b."ReopenedWithin7Days"   END AS "ReopenedWithin7Days"
FROM staging.stg_bookings b
-- Model scores come from the prediction store, not from the app database.
-- This join is the reason ml_predictions exists: without predictions written
-- back to the warehouse, the ML Health page cannot be built at all.
LEFT JOIN LATERAL (
    SELECT p.prediction AS predicted_eta_mins FROM app.ml_predictions p
    JOIN app.ml_model_versions v ON v.version_id = p.version_id
    JOIN app.ml_models m ON m.model_id = v.model_id AND m.name = 'eta_sla_predictor'
    WHERE p.entity_type = 'booking' AND p.entity_id = b."BookingID" LIMIT 1
) pe ON TRUE
LEFT JOIN LATERAL (
    SELECT p.prediction AS match_score FROM app.ml_predictions p
    JOIN app.ml_model_versions v ON v.version_id = p.version_id
    JOIN app.ml_models m ON m.model_id = v.model_id AND m.name = 'pro_match_ranker'
    WHERE p.entity_type = 'booking' AND p.entity_id = b."BookingID" LIMIT 1
) ms ON TRUE
LEFT JOIN LATERAL (
    SELECT p.prediction AS fraud_score FROM app.ml_predictions p
    JOIN app.ml_model_versions v ON v.version_id = p.version_id
    JOIN app.ml_models m ON m.model_id = v.model_id AND m.name = 'fraud_booking_detector'
    WHERE p.entity_type = 'booking' AND p.entity_id = b."BookingID" LIMIT 1
) fs ON TRUE
LEFT JOIN LATERAL (
    SELECT p.prediction AS churn_score FROM app.ml_predictions p
    JOIN app.ml_model_versions v ON v.version_id = p.version_id
    JOIN app.ml_models m ON m.model_id = v.model_id AND m.name = 'customer_churn'
    WHERE p.entity_type = 'customer' AND p.entity_id = b."CustomerKey"::TEXT LIMIT 1
) cs ON TRUE
WHERE b."BookingStatus" <> 'InFlight';

CREATE INDEX idx_fb_date ON fact_bookings ("DateKey");
CREATE INDEX idx_fb_area ON fact_bookings ("AreaKey");
CREATE INDEX idx_fb_pro  ON fact_bookings ("ProKey");

-- ============================================================================
-- 4. fact_pro_capacity
--    dbt: models/marts/fact_pro_capacity.sql, materialized='incremental'
--
-- Emitted only for days inside a technician's tenure. The row-count guard
-- drops idle offline days once the table would exceed ~350k rows, which keeps
-- an import-mode model comfortable without losing any day that carries work.
-- ============================================================================
DROP TABLE IF EXISTS fact_pro_capacity CASCADE;
CREATE TABLE fact_pro_capacity AS
SELECT c.*
FROM staging.stg_pro_capacity c
JOIN staging.stg_professionals p ON p."ProKey" = c."ProKey"
WHERE TO_DATE(c."DateKey"::TEXT, 'YYYYMMDD') >= p."JoinDate"
  AND (p."ChurnedDate" IS NULL
       OR TO_DATE(c."DateKey"::TEXT, 'YYYYMMDD') < p."ChurnedDate")
  AND (c."IsOnline" = 1 OR c."SlotsBooked" > 0);

CREATE INDEX idx_fpc_date ON fact_pro_capacity ("DateKey");
CREATE INDEX idx_fpc_pro  ON fact_pro_capacity ("ProKey");

-- ============================================================================
-- 5. fact_leads
--    dbt: models/marts/fact_leads.sql
--
-- The GREATEST() cascade enforces monotonicity. In real data a lead can arrive
-- the day after the search that produced it, which puts it in a different daily
-- bucket and makes leads briefly exceed searches. Clamping is the pragmatic
-- fix; the alternative is sessionising across midnight for no analytical gain.
-- ============================================================================
DROP TABLE IF EXISTS fact_leads CASCADE;
CREATE TABLE fact_leads AS
SELECT
    "DateKey", "AreaKey", "ServiceKey",
    GREATEST("Searches", "Leads", "QuotesSent", "Bookings") AS "Searches",
    GREATEST("Leads", "QuotesSent", "Bookings")             AS "Leads",
    GREATEST("QuotesSent", "Bookings")                      AS "QuotesSent",
    "Bookings",
    "AvgLeadQualityScore"
FROM staging.stg_funnel
WHERE "Searches" > 0;

CREATE INDEX idx_fl_date ON fact_leads ("DateKey");

-- ============================================================================
-- 6. fact_model_metrics and fact_forecast_accuracy
--    dbt: models/marts/fact_model_metrics.sql, fact_forecast_accuracy.sql
-- ============================================================================
DROP TABLE IF EXISTS dim_model CASCADE;
CREATE TABLE dim_model AS
SELECT
    m.model_id                                   AS "ModelKey",
    m.name                                       AS "ModelName",
    m.model_type                                 AS "ModelType",
    ''                                           AS "BusinessPurpose",
    m.framework                                  AS "Framework",
    m.algorithm                                  AS "Algorithm",
    m.primary_metric                             AS "PrimaryMetric",
    m.metric_goal                                AS "MetricGoal",
    m.goal_direction                             AS "GoalDirection",
    MIN(v.deployed_at)::DATE                     AS "DeployedDate",
    (ARRAY_AGG(v.version ORDER BY v.deployed_at DESC))[1] AS "Version",
    m.refresh_cadence                            AS "RefreshCadence",
    m.owner_team                                 AS "OwnerTeam",
    m.business_critical::INT                     AS "IsBusinessCritical"
FROM app.ml_models m
JOIN app.ml_model_versions v ON v.model_id = m.model_id
GROUP BY m.model_id, m.name, m.model_type, m.framework, m.algorithm,
         m.primary_metric, m.metric_goal, m.goal_direction, m.refresh_cadence,
         m.owner_team, m.business_critical;
ALTER TABLE dim_model ADD PRIMARY KEY ("ModelKey");

DROP TABLE IF EXISTS fact_model_metrics CASCADE;
CREATE TABLE fact_model_metrics AS SELECT * FROM staging.stg_model_metrics;
CREATE INDEX idx_fmm_date ON fact_model_metrics ("DateKey");

-- Forecast accuracy: the forecaster's own predictions scored against what
-- happened. APE is stored as a FRACTION so a percent format string in Power BI
-- works without arithmetic, and is NULL where nothing happened - dividing by
-- zero is not an error worth inventing a number for.
DROP TABLE IF EXISTS fact_forecast_accuracy CASCADE;
CREATE TABLE fact_forecast_accuracy AS
WITH forecasts AS (
    SELECT
        SPLIT_PART(p.entity_id, '|', 1)::INT           AS area_key,
        SPLIT_PART(p.entity_id, '|', 2)                AS service_category,
        p.predicted_at::DATE                           AS forecast_date,
        SUM(p.prediction)                              AS forecasted_jobs
    FROM app.ml_predictions p
    JOIN app.ml_model_versions v ON v.version_id = p.version_id
    JOIN app.ml_models m ON m.model_id = v.model_id AND m.name = 'demand_forecaster'
    WHERE p.entity_type = 'cell'
    GROUP BY 1, 2, 3
),
actuals AS (
    SELECT
        f."AreaKey"                                    AS area_key,
        s."ServiceCategory"                            AS service_category,
        TO_DATE(f."DateKey"::TEXT, 'YYYYMMDD')         AS actual_date,
        COUNT(*)                                       AS actual_jobs
    FROM fact_bookings f
    JOIN dim_service s ON s."ServiceKey" = f."ServiceKey"
    GROUP BY 1, 2, 3
)
SELECT
    TO_CHAR(COALESCE(fc.forecast_date, ac.actual_date), 'YYYYMMDD')::INT AS "DateKey",
    COALESCE(fc.area_key, ac.area_key)                  AS "AreaKey",
    COALESCE(fc.service_category, ac.service_category)  AS "ServiceCategory",
    ROUND(COALESCE(fc.forecasted_jobs, 0), 1)           AS "ForecastedJobs",
    COALESCE(ac.actual_jobs, 0)                         AS "ActualJobs",
    ROUND(ABS(COALESCE(fc.forecasted_jobs, 0) - COALESCE(ac.actual_jobs, 0)), 1)
                                                        AS "AbsError",
    CASE WHEN COALESCE(ac.actual_jobs, 0) > 0
         THEN ROUND(ABS(COALESCE(fc.forecasted_jobs, 0) - ac.actual_jobs)
                    / ac.actual_jobs::NUMERIC, 4)
    END                                                 AS "APE"
FROM forecasts fc
FULL OUTER JOIN actuals ac
  ON  ac.area_key         = fc.area_key
  AND ac.service_category = fc.service_category
  AND ac.actual_date      = fc.forecast_date
-- Keep the cells where the model predicted work that never arrived. Filtering
-- them out would hide the failure mode most worth seeing: 11,004 of them in
-- this dataset, worth 14,806 phantom jobs.
WHERE COALESCE(ac.actual_jobs, 0) > 0
   OR COALESCE(fc.forecasted_jobs, 0) >= 0.5;

-- ============================================================================
-- 7. Dimensions derived FROM the facts
--    dbt: these are the two models that must depend on fact_bookings, so dbt's
--         DAG orders them last. Do not be tempted to compute them in staging.
--
-- Deriving a technician's rating from their own bookings rather than storing an
-- editable number is what stops the dimension and the fact disagreeing.
-- ============================================================================
DROP TABLE IF EXISTS dim_professional CASCADE;
CREATE TABLE dim_professional AS
WITH job_stats AS (
    SELECT
        "ProKey",
        COUNT(*) FILTER (WHERE "BookingStatus" = 'Completed')  AS lifetime_jobs,
        COUNT("CustomerRating")                                AS rating_count,
        COALESCE(SUM("CustomerRating"), 0)                     AS rating_sum
    FROM fact_bookings
    GROUP BY "ProKey"
)
SELECT
    p."ProKey",
    p."ProName",
    p."PrimaryServiceCategory",
    p."HomeAreaKey",
    p."JoinDate",
    p."SkillTier",
    p."IsBackgroundVerified",
    p."IsActive",
    -- Shrink towards a tier prior with a weight of 8 pseudo-ratings, so a
    -- technician with three five-star jobs does not outrank one with two
    -- hundred good ones. Without this, every "top rated" list is a list of
    -- people who have barely worked.
    ROUND(
        (COALESCE(j.rating_sum, 0) + 8 * CASE p."SkillTier"
            WHEN 'Bronze'   THEN 4.05
            WHEN 'Silver'   THEN 4.32
            WHEN 'Gold'     THEN 4.55
            WHEN 'Platinum' THEN 4.72
            ELSE 4.30 END
        ) / (COALESCE(j.rating_count, 0) + 8), 2)          AS "AvgRating",
    COALESCE(j.lifetime_jobs, 0)                           AS "LifetimeJobs",
    p."LanguagesSpoken",
    p."OnboardingChannel",
    p."ChurnedDate"
FROM staging.stg_professionals p
LEFT JOIN job_stats j ON j."ProKey" = p."ProKey";
ALTER TABLE dim_professional ADD PRIMARY KEY ("ProKey");

DROP TABLE IF EXISTS dim_customer CASCADE;
CREATE TABLE dim_customer AS
WITH booking_stats AS (
    SELECT
        "CustomerKey",
        COUNT(*)                              AS total_bookings,
        SUM("FinalAmountINR")                 AS lifetime_value,
        MIN("BookingTimestamp")::DATE         AS first_booking,
        MAX("BookingTimestamp")::DATE         AS last_booking
    FROM fact_bookings
    GROUP BY "CustomerKey"
)
SELECT
    c."CustomerKey",
    c."SignupDate",
    c."AreaKey",
    c."AcquisitionChannel",
    -- Segment definition, stated once. Dormancy wins over volume: someone who
    -- booked six times and then vanished four months ago is a churn problem,
    -- not a loyal customer, and calling them Loyal hides the very thing the
    -- retention team needs to see.
    CASE
        WHEN b.last_booking IS NULL                          THEN 'New'
        WHEN DATE '2026-08-31' - b.last_booking > 120        THEN 'Dormant'
        WHEN b.total_bookings >= 4                           THEN 'Loyal'
        WHEN b.total_bookings >= 2                           THEN 'Repeat'
        ELSE 'New'
    END                                       AS "Segment",
    c."IsAppUser",
    c."PreferredLanguage",
    ROUND(COALESCE(b.lifetime_value, 0), 2)   AS "LifetimeValueINR",
    b.first_booking                           AS "FirstBookingDate",
    b.last_booking                            AS "LastBookingDate",
    COALESCE(b.total_bookings, 0)             AS "TotalBookings"
FROM staging.stg_customers c
JOIN booking_stats b ON b."CustomerKey" = c."CustomerKey";
ALTER TABLE dim_customer ADD PRIMARY KEY ("CustomerKey");

COMMIT;

-- ============================================================================
-- 8. Post-build assertions
--
-- These mirror validate.py. Run them after every load; a warehouse that only
-- fails at the dashboard has failed too late.
-- dbt equivalent: tests in schema.yml, plus singular tests in tests/.
-- ============================================================================

-- Referential integrity: must return zero rows.
SELECT 'orphan booking area' AS check_name, COUNT(*) AS failures
FROM fact_bookings f LEFT JOIN dim_area a USING ("AreaKey") WHERE a."AreaKey" IS NULL
UNION ALL
SELECT 'orphan booking service', COUNT(*)
FROM fact_bookings f LEFT JOIN dim_service s USING ("ServiceKey") WHERE s."ServiceKey" IS NULL
UNION ALL
SELECT 'orphan booking date', COUNT(*)
FROM fact_bookings f LEFT JOIN dim_date d USING ("DateKey") WHERE d."DateKey" IS NULL
UNION ALL
-- Money rules.
SELECT 'final exceeds quote plus discount', COUNT(*)
FROM fact_bookings WHERE "FinalAmountINR" > "QuotedAmountINR" + "DiscountINR" + 0.01
UNION ALL
SELECT 'revenue not equal to commission of final', COUNT(*)
FROM fact_bookings
WHERE ABS("PlatformRevenueINR" - ROUND("FinalAmountINR" * "CommissionPct" / 100, 2)) > 0.011
UNION ALL
SELECT 'money on a cancelled booking', COUNT(*)
FROM fact_bookings
WHERE "BookingStatus" <> 'Completed' AND ("FinalAmountINR" <> 0 OR "PlatformRevenueINR" <> 0)
UNION ALL
-- Completion-only columns.
SELECT 'completed job with no duration', COUNT(*)
FROM fact_bookings WHERE "BookingStatus" = 'Completed' AND "JobDurationMins" IS NULL
UNION ALL
SELECT 'non-completed job with a duration', COUNT(*)
FROM fact_bookings WHERE "BookingStatus" <> 'Completed' AND "JobDurationMins" IS NOT NULL
UNION ALL
-- Rating and sentiment travel together or not at all.
SELECT 'rating without sentiment', COUNT(*)
FROM fact_bookings
WHERE ("CustomerRating" IS NULL) <> ("ReviewSentiment" IS NULL)
UNION ALL
-- Chronology.
SELECT 'customer booked before signing up', COUNT(*)
FROM dim_customer WHERE "FirstBookingDate" < "SignupDate"
UNION ALL
SELECT 'technician worked before joining', COUNT(*)
FROM fact_bookings f JOIN dim_professional p USING ("ProKey")
WHERE f."BookingTimestamp"::DATE < p."JoinDate"
UNION ALL
SELECT 'technician worked after churning', COUNT(*)
FROM fact_bookings f JOIN dim_professional p USING ("ProKey")
WHERE p."ChurnedDate" IS NOT NULL AND f."BookingTimestamp"::DATE >= p."ChurnedDate"
UNION ALL
-- Funnel.
SELECT 'funnel not monotonic', COUNT(*)
FROM fact_leads
WHERE NOT ("Searches" >= "Leads" AND "Leads" >= "QuotesSent" AND "QuotesSent" >= "Bookings")
UNION ALL
-- Capacity reconciliation.
SELECT 'overbooked technician day', COUNT(*)
FROM fact_pro_capacity WHERE "SlotsBooked" > "SlotsAvailable"
UNION ALL
SELECT 'date dimension gap', (
    SELECT (MAX("Date") - MIN("Date") + 1) - COUNT(*) FROM dim_date
);
