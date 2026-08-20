-- ============================================================================
-- Seek My Service - source OLTP schema
--
-- The transactional database the analytics layer reads FROM. This is written
-- as PostgreSQL; notes at the bottom cover the MySQL differences.
--
-- This is deliberately normalised and deliberately unfriendly to analysts. It
-- is what a working marketplace backend looks like: booking state lives in an
-- event log rather than a status column, money is split across quotes and
-- payments, and a technician's skills are a many-to-many. Turning this into
-- something Power BI can answer questions from is the entire job of files 02
-- and 03.
--
-- Power BI must never query this database directly. See
-- docs/PRODUCTION_ARCHITECTURE.md for why, and what to do instead.
-- ============================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS app;
SET search_path TO app;

-- ----------------------------------------------------------------------------
-- Enumerations
-- ----------------------------------------------------------------------------
CREATE TYPE booking_state AS ENUM (
    'created', 'assigned', 'accepted', 'en_route', 'in_progress',
    'completed', 'cancelled_by_customer', 'cancelled_by_pro', 'no_show', 'rescheduled'
);

CREATE TYPE payment_method AS ENUM ('upi', 'card', 'cash', 'wallet', 'netbanking');

CREATE TYPE acquisition_channel AS ENUM (
    'organic_search', 'google_ads', 'meta_ads', 'referral',
    'justdial', 'app_store', 'whatsapp_broadcast'
);

CREATE TYPE skill_tier AS ENUM ('bronze', 'silver', 'gold', 'platinum');

CREATE TYPE booking_origin AS ENUM ('app', 'web', 'phone', 'whatsapp');

-- ----------------------------------------------------------------------------
-- Geography
-- ----------------------------------------------------------------------------
CREATE TABLE localities (
    locality_id      SERIAL PRIMARY KEY,
    name             TEXT        NOT NULL UNIQUE,
    zone             TEXT        NOT NULL CHECK (zone IN ('Central','East','North','South','West')),
    pincode          CHAR(6)     NOT NULL,
    latitude         NUMERIC(9,6)  NOT NULL,
    longitude        NUMERIC(9,6)  NOT NULL,
    demand_tier      CHAR(1)     NOT NULL CHECK (demand_tier IN ('A','B','C')),
    income_band      TEXT        NOT NULL,
    is_serviceable   BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON COLUMN localities.pincode IS
    'Char, not integer. Postal codes are identifiers, not quantities.';

-- ----------------------------------------------------------------------------
-- Service catalogue
-- ----------------------------------------------------------------------------
CREATE TABLE service_categories (
    category_id      SERIAL PRIMARY KEY,
    name             TEXT        NOT NULL UNIQUE,
    commission_pct   NUMERIC(5,2) NOT NULL CHECK (commission_pct BETWEEN 0 AND 100),
    sort_order       INT         NOT NULL,
    is_active        BOOLEAN     NOT NULL DEFAULT TRUE
);

CREATE TABLE services (
    service_id         SERIAL PRIMARY KEY,
    category_id        INT          NOT NULL REFERENCES service_categories(category_id),
    name               TEXT         NOT NULL,
    base_price_inr     NUMERIC(10,2) NOT NULL CHECK (base_price_inr > 0),
    avg_duration_mins  INT          NOT NULL CHECK (avg_duration_mins > 0),
    is_emergency       BOOLEAN      NOT NULL DEFAULT FALSE,
    required_tier      skill_tier   NOT NULL DEFAULT 'silver',
    material_cost_pct  NUMERIC(5,2) NOT NULL DEFAULT 0,
    is_active          BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (category_id, name)
);

-- ----------------------------------------------------------------------------
-- Customers
-- ----------------------------------------------------------------------------
CREATE TABLE customers (
    customer_id        BIGSERIAL PRIMARY KEY,
    -- PII lives here and must never leave the OLTP database. The warehouse
    -- receives customer_id and nothing else that identifies a person.
    phone_e164         TEXT        NOT NULL UNIQUE,
    email              TEXT,
    display_name       TEXT,
    signup_at          TIMESTAMPTZ NOT NULL,
    acquisition        acquisition_channel NOT NULL,
    preferred_language TEXT        NOT NULL DEFAULT 'English',
    is_app_user        BOOLEAN     NOT NULL DEFAULT FALSE,
    home_locality_id   INT         REFERENCES localities(locality_id),
    deleted_at         TIMESTAMPTZ
);
CREATE INDEX idx_customers_signup ON customers (signup_at);
CREATE INDEX idx_customers_acquisition ON customers (acquisition);

CREATE TABLE customer_addresses (
    address_id     BIGSERIAL PRIMARY KEY,
    customer_id    BIGINT NOT NULL REFERENCES customers(customer_id),
    locality_id    INT    NOT NULL REFERENCES localities(locality_id),
    line1          TEXT   NOT NULL,
    landmark       TEXT,
    is_default     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_addresses_customer ON customer_addresses (customer_id);

-- ----------------------------------------------------------------------------
-- Supply side
-- ----------------------------------------------------------------------------
CREATE TABLE professionals (
    pro_id                BIGSERIAL PRIMARY KEY,
    full_name             TEXT        NOT NULL,
    phone_e164            TEXT        NOT NULL UNIQUE,
    home_locality_id      INT         NOT NULL REFERENCES localities(locality_id),
    primary_category_id   INT         NOT NULL REFERENCES service_categories(category_id),
    tier                  skill_tier  NOT NULL DEFAULT 'bronze',
    joined_on             DATE        NOT NULL,
    churned_on            DATE,
    background_verified   BOOLEAN     NOT NULL DEFAULT FALSE,
    onboarding_channel    TEXT,
    languages             TEXT[]      NOT NULL DEFAULT '{}',
    CONSTRAINT churn_after_join CHECK (churned_on IS NULL OR churned_on > joined_on)
);
COMMENT ON CONSTRAINT churn_after_join ON professionals IS
    'Enforced here so the warehouse never has to repair it. The synthetic
     generator had this exact bug once; a database constraint is cheaper than
     a validation rule.';

CREATE TABLE professional_skills (
    pro_id      BIGINT NOT NULL REFERENCES professionals(pro_id),
    service_id  INT    NOT NULL REFERENCES services(service_id),
    proficiency SMALLINT NOT NULL DEFAULT 3 CHECK (proficiency BETWEEN 1 AND 5),
    PRIMARY KEY (pro_id, service_id)
);

CREATE TABLE professional_availability (
    availability_id BIGSERIAL PRIMARY KEY,
    pro_id          BIGINT NOT NULL REFERENCES professionals(pro_id),
    on_date         DATE   NOT NULL,
    slots_offered   SMALLINT NOT NULL CHECK (slots_offered >= 0),
    went_online_at  TIMESTAMPTZ,
    went_offline_at TIMESTAMPTZ,
    minutes_logged  INT NOT NULL DEFAULT 0,
    UNIQUE (pro_id, on_date)
);
CREATE INDEX idx_availability_date ON professional_availability (on_date);

-- Every offer the dispatcher made, accepted or not. This is where the
-- acceptance rate comes from; it cannot be derived from bookings alone,
-- because a declined offer never becomes a booking.
CREATE TABLE dispatch_offers (
    offer_id     BIGSERIAL PRIMARY KEY,
    booking_id   BIGINT      NOT NULL,
    pro_id       BIGINT      NOT NULL REFERENCES professionals(pro_id),
    offered_at   TIMESTAMPTZ NOT NULL,
    responded_at TIMESTAMPTZ,
    accepted     BOOLEAN,
    match_score  NUMERIC(6,4),
    rank_position SMALLINT
);
CREATE INDEX idx_offers_booking ON dispatch_offers (booking_id);
CREATE INDEX idx_offers_pro_date ON dispatch_offers (pro_id, offered_at);

-- ----------------------------------------------------------------------------
-- Demand side
-- ----------------------------------------------------------------------------
CREATE TABLE search_events (
    search_id     BIGSERIAL PRIMARY KEY,
    customer_id   BIGINT REFERENCES customers(customer_id),
    session_id    UUID        NOT NULL,
    searched_at   TIMESTAMPTZ NOT NULL,
    locality_id   INT         REFERENCES localities(locality_id),
    service_id    INT         REFERENCES services(service_id),
    became_lead   BOOLEAN     NOT NULL DEFAULT FALSE,
    origin        booking_origin NOT NULL
);
CREATE INDEX idx_search_at ON search_events (searched_at);
CREATE INDEX idx_search_cell ON search_events (locality_id, service_id, searched_at);

CREATE TABLE leads (
    lead_id       BIGSERIAL PRIMARY KEY,
    search_id     BIGINT REFERENCES search_events(search_id),
    customer_id   BIGINT REFERENCES customers(customer_id),
    locality_id   INT    NOT NULL REFERENCES localities(locality_id),
    service_id    INT    NOT NULL REFERENCES services(service_id),
    created_at    TIMESTAMPTZ NOT NULL,
    quality_score NUMERIC(5,4),
    quoted        BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX idx_leads_created ON leads (created_at);

CREATE TABLE bookings (
    booking_id      BIGSERIAL PRIMARY KEY,
    public_ref      TEXT        NOT NULL UNIQUE,   -- the BK0000001 the customer sees
    customer_id     BIGINT      NOT NULL REFERENCES customers(customer_id),
    address_id      BIGINT      REFERENCES customer_addresses(address_id),
    locality_id     INT         NOT NULL REFERENCES localities(locality_id),
    service_id      INT         NOT NULL REFERENCES services(service_id),
    lead_id         BIGINT      REFERENCES leads(lead_id),
    assigned_pro_id BIGINT      REFERENCES professionals(pro_id),
    origin          booking_origin NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL,
    scheduled_for   TIMESTAMPTZ,
    -- Current state is a cache of the latest booking_events row. The event log
    -- is the source of truth; this column exists so the app does not have to
    -- aggregate the log on every read.
    current_state   booking_state NOT NULL DEFAULT 'created',
    commission_pct  NUMERIC(5,2) NOT NULL,
    is_repeat       BOOLEAN     NOT NULL DEFAULT FALSE,
    CONSTRAINT booking_after_signup CHECK (created_at IS NOT NULL)
);
CREATE INDEX idx_bookings_created ON bookings (created_at);
CREATE INDEX idx_bookings_customer ON bookings (customer_id, created_at);
CREATE INDEX idx_bookings_pro ON bookings (assigned_pro_id, created_at);
CREATE INDEX idx_bookings_state ON bookings (current_state);

-- The state machine, append-only. Time-to-assign, response time and actual ETA
-- are all differences between rows in here - they are not stored anywhere as
-- numbers, which is exactly the sort of thing the staging layer exists to fix.
CREATE TABLE booking_events (
    event_id    BIGSERIAL PRIMARY KEY,
    booking_id  BIGINT        NOT NULL REFERENCES bookings(booking_id),
    state       booking_state NOT NULL,
    occurred_at TIMESTAMPTZ   NOT NULL,
    actor       TEXT          NOT NULL,   -- 'customer' | 'pro' | 'system'
    notes       TEXT
);
CREATE INDEX idx_events_booking ON booking_events (booking_id, occurred_at);

CREATE TABLE quotes (
    quote_id      BIGSERIAL PRIMARY KEY,
    booking_id    BIGINT      NOT NULL REFERENCES bookings(booking_id),
    quoted_inr    NUMERIC(12,2) NOT NULL CHECK (quoted_inr >= 0),
    discount_inr  NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (discount_inr >= 0),
    predicted_inr NUMERIC(12,2),
    price_band_low  NUMERIC(12,2),
    price_band_high NUMERIC(12,2),
    issued_at     TIMESTAMPTZ NOT NULL,
    is_current    BOOLEAN     NOT NULL DEFAULT TRUE
);
CREATE INDEX idx_quotes_booking ON quotes (booking_id);

CREATE TABLE invoices (
    invoice_id       BIGSERIAL PRIMARY KEY,
    booking_id       BIGINT      NOT NULL UNIQUE REFERENCES bookings(booking_id),
    final_inr        NUMERIC(12,2) NOT NULL CHECK (final_inr >= 0),
    material_cost_inr NUMERIC(12,2) NOT NULL DEFAULT 0,
    platform_fee_inr NUMERIC(12,2) NOT NULL DEFAULT 0,
    issued_at        TIMESTAMPTZ NOT NULL
);

CREATE TABLE payments (
    payment_id  BIGSERIAL PRIMARY KEY,
    invoice_id  BIGINT      NOT NULL REFERENCES invoices(invoice_id),
    method      payment_method NOT NULL,
    amount_inr  NUMERIC(12,2)  NOT NULL,
    settled_at  TIMESTAMPTZ,
    gateway_ref TEXT
);
CREATE INDEX idx_payments_invoice ON payments (invoice_id);

CREATE TABLE reviews (
    review_id   BIGSERIAL PRIMARY KEY,
    booking_id  BIGINT      NOT NULL UNIQUE REFERENCES bookings(booking_id),
    rating      SMALLINT    NOT NULL CHECK (rating BETWEEN 1 AND 5),
    body        TEXT,
    language    TEXT,
    -- Written back by review_sentiment_indic, not entered by a human.
    sentiment   TEXT CHECK (sentiment IN ('Positive','Neutral','Negative')),
    created_at  TIMESTAMPTZ NOT NULL
);
COMMENT ON TABLE reviews IS
    'A row exists only when the customer actually rated the job. Roughly 38%
     of completed bookings never get one, which is why CustomerRating is blank
     in the warehouse rather than zero.';

CREATE TABLE job_outcomes (
    booking_id        BIGINT PRIMARY KEY REFERENCES bookings(booking_id),
    duration_mins     INT,
    sla_met           BOOLEAN,
    first_time_fix    BOOLEAN,
    reopened_within_7d BOOLEAN,
    actual_eta_mins   INT
);

-- ----------------------------------------------------------------------------
-- ML serving tables
--
-- Predictions are written back here by the FastAPI services. Without this the
-- ML Health page in Power BI is impossible - you cannot report on a model
-- whose outputs were never persisted.
-- ----------------------------------------------------------------------------
CREATE TABLE ml_models (
    model_id       SERIAL PRIMARY KEY,
    name           TEXT NOT NULL UNIQUE,
    model_type     TEXT NOT NULL,
    framework      TEXT NOT NULL,
    algorithm      TEXT NOT NULL,
    primary_metric TEXT NOT NULL,
    metric_goal    NUMERIC(10,4) NOT NULL,
    goal_direction TEXT NOT NULL CHECK (goal_direction IN ('LowerIsBetter','HigherIsBetter')),
    owner_team     TEXT NOT NULL,
    business_critical BOOLEAN NOT NULL DEFAULT FALSE,
    refresh_cadence TEXT
);

CREATE TABLE ml_model_versions (
    version_id     SERIAL PRIMARY KEY,
    model_id       INT  NOT NULL REFERENCES ml_models(model_id),
    version        TEXT NOT NULL,
    deployed_at    TIMESTAMPTZ NOT NULL,
    retired_at     TIMESTAMPTZ,
    training_data_max_date DATE NOT NULL,
    mlflow_run_id  TEXT,
    UNIQUE (model_id, version)
);
COMMENT ON COLUMN ml_model_versions.training_data_max_date IS
    'The freshness signal. TrainingDataAgeDays in the warehouse is
     current_date minus this. It is the column that would have caught the
     March 2026 silent retrain failure four months before anyone noticed.';

CREATE TABLE ml_predictions (
    prediction_id  BIGSERIAL PRIMARY KEY,
    version_id     INT    NOT NULL REFERENCES ml_model_versions(version_id),
    entity_type    TEXT   NOT NULL,   -- 'booking' | 'lead' | 'customer' | 'cell'
    entity_id      TEXT   NOT NULL,
    predicted_at   TIMESTAMPTZ NOT NULL,
    prediction     NUMERIC(14,6) NOT NULL,
    latency_ms     INT,
    feature_null_count SMALLINT DEFAULT 0
);
CREATE INDEX idx_predictions_entity ON ml_predictions (entity_type, entity_id);
CREATE INDEX idx_predictions_at ON ml_predictions (predicted_at);

CREATE TABLE ml_metric_daily (
    metric_date    DATE NOT NULL,
    version_id     INT  NOT NULL REFERENCES ml_model_versions(version_id),
    metric_name    TEXT NOT NULL,
    metric_value   NUMERIC(12,6) NOT NULL,
    psi_drift      NUMERIC(8,5),
    prediction_volume INT,
    p95_latency_ms INT,
    feature_null_pct NUMERIC(6,3),
    PRIMARY KEY (metric_date, version_id, metric_name)
);

COMMIT;

-- ============================================================================
-- Notes for a MySQL deployment
-- ============================================================================
--  * ENUM types: MySQL has an inline ENUM column type. Replace each
--    "CREATE TYPE x AS ENUM (...)" with ENUM(...) on the column itself.
--  * SERIAL / BIGSERIAL   -> INT AUTO_INCREMENT / BIGINT AUTO_INCREMENT.
--  * TIMESTAMPTZ          -> DATETIME. MySQL has no timezone-aware type, so
--                            store UTC and convert in the presentation layer.
--                            Do not store IST and hope.
--  * TEXT[] (languages)   -> a professional_languages child table. A delimited
--                            string is tempting and wrong.
--  * NUMERIC              -> DECIMAL with the same precision. Never FLOAT for
--                            money; 0.1 + 0.2 is a rounding complaint waiting
--                            to be filed by a technician about their payout.
--  * CHECK constraints    -> enforced from MySQL 8.0.16. On older versions use
--                            triggers, or accept that the staging layer has to
--                            do the validating.
-- ============================================================================
