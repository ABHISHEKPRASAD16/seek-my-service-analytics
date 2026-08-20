"""
Seek My Service - central configuration.

Every tunable constant in the synthetic data generator lives here. No magic
numbers are permitted anywhere else in the ``generator`` package: if a value
shapes the data, it is declared in this module and imported.

Currency is INR throughout. Amounts never carry a symbol inside the data.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
# One seed drives the entire build. Regenerating produces byte-identical CSVs.
SEED = 20260819

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
MODEL_DIR = PROJECT_ROOT / "ml" / "models"

# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------
DATE_START = _dt.date(2025, 1, 1)
DATE_END = _dt.date(2026, 8, 31)
# "Today" for the purposes of DaysFromToday and all recency logic.
TODAY = _dt.date(2026, 8, 31)

# Professionals may have joined before the fact window opens.
PRO_JOIN_EARLIEST = _dt.date(2024, 6, 1)
PRO_JOIN_LATEST = _dt.date(2026, 7, 31)
# Customers may have signed up shortly before the fact window opens.
CUSTOMER_SIGNUP_EARLIEST = _dt.date(2024, 10, 1)
# A customer signs up between 0 and N days before their first booking.
SIGNUP_LEAD_DAYS_MAX = 25

CSV_ENCODING = "utf-8"          # deliberately *without* BOM
CSV_LINE_TERMINATOR = "\n"
BLANK = ""                      # the only representation of "no value" in a CSV

# ---------------------------------------------------------------------------
# Volumes
# ---------------------------------------------------------------------------
N_PROFESSIONALS = 850
N_CUSTOMERS = 24_000

# Completed-booking anchors for the first and last month of the window. The
# growth trend is solved so these two months land on target *after* seasonality
# is applied; every month in between is free to outrun or undershoot its trend.
COMPLETED_ANCHOR_FIRST_MONTH = 900      # Jan 2025
COMPLETED_ANCHOR_LAST_MONTH = 4_200     # Aug 2026

# Lognormal month-over-month noise on the growth trend, so the curve is lumpy
# rather than a clean exponential. The two anchor months carry no noise.
TREND_NOISE_SIGMA = 0.055

# Row-count guard for the daily supply table. Above this, pro-days with no
# jobs and no online time are dropped.
PRO_CAPACITY_ROW_CAP = 350_000

# ---------------------------------------------------------------------------
# Booking status mix
# ---------------------------------------------------------------------------
# Baseline probabilities; monsoon and capacity strain shift these at runtime.
# These are the *base* rates before rain and strain uplift. Realised completion
# lands near 80%, which is what makes total booking volume land near 58,000
# against the completed-volume anchors above: total = completed / completion.
STATUS_BASE = {
    "Completed": 0.8200,
    "CancelledByCustomer": 0.0600,
    "CancelledByPro": 0.0338,
    "NoShow": 0.0262,
    "Rescheduled": 0.0600,
}
# Statuses that produce no money. A Rescheduled booking is superseded by a new
# booking record, so it too carries zero financials.
NON_REVENUE_STATUSES = ("CancelledByCustomer", "CancelledByPro", "NoShow", "Rescheduled")

# Heavy-rain days push customers to cancel and pros to drop jobs.
MONSOON_CANCEL_UPLIFT = 0.55        # relative uplift applied to cancel probabilities
HEAVY_RAIN_DAY_PROB = 0.34          # share of monsoon days that are genuinely heavy
# Capacity strain (today's volume vs the trailing 30-day mean) also lifts them.
STRAIN_CANCEL_UPLIFT_PER_UNIT = 0.45

# ---------------------------------------------------------------------------
# Channels, payments, languages
# ---------------------------------------------------------------------------
BOOKING_CHANNELS = ["App", "Web", "Phone", "WhatsApp"]
# Mix at the start and at the end of the window; interpolated linearly in time.
BOOKING_CHANNEL_MIX_START = [0.42, 0.27, 0.16, 0.15]
BOOKING_CHANNEL_MIX_END = [0.61, 0.18, 0.05, 0.16]

# India is a UPI-first market. This mix is checked by validate.py.
PAYMENT_MODES = ["UPI", "Cash", "Card", "Wallet", "NetBanking"]
PAYMENT_MODE_MIX = [0.58, 0.16, 0.12, 0.08, 0.06]
# Cash skews to phone bookings and to value areas; UPI skews to app users.
PAYMENT_CASH_UPLIFT_PHONE = 2.1
PAYMENT_CASH_UPLIFT_VALUE_AREA = 1.6

CUSTOMER_LANGUAGES = ["Kannada", "English", "Hindi", "Tamil", "Telugu", "Malayalam", "Urdu"]
CUSTOMER_LANGUAGE_MIX = [0.28, 0.30, 0.16, 0.10, 0.09, 0.04, 0.03]

# ---------------------------------------------------------------------------
# Customer acquisition
# ---------------------------------------------------------------------------
# repeat_propensity drives how often a customer is re-drawn for a later booking.
# Referral and Organic must demonstrably out-repeat paid social: that gap is one
# of the three headline findings, so it is built in rather than asserted.
ACQUISITION_CHANNELS = {
    #  name                  share   repeat_propensity  app_user_prob
    "Organic Search":       (0.205,  1.55,              0.62),
    "Google Ads":           (0.185,  0.82,              0.55),
    "Meta Ads":             (0.170,  0.55,              0.49),
    "Referral":             (0.145,  1.95,              0.71),
    "JustDial":             (0.120,  0.70,              0.31),
    "App Store":            (0.095,  1.20,              0.96),
    "WhatsApp Broadcast":   (0.080,  0.88,              0.44),
}

# Share of bookings that are a customer's first, at the start and end of the
# window. New-customer share falls as the base matures.
NEW_CUSTOMER_SHARE_START = 0.88
NEW_CUSTOMER_SHARE_END = 0.24

# Repeat-customer selection weights.
REPEAT_RECENCY_HALFLIFE_DAYS = 115.0
REPEAT_CROSS_AREA_PROB = 0.12     # a booking placed outside the customer's home area

# Segment thresholds, applied after fact_bookings exists.
SEGMENT_DORMANT_DAYS = 120
SEGMENT_LOYAL_MIN_BOOKINGS = 4
SEGMENT_REPEAT_MIN_BOOKINGS = 2

# ---------------------------------------------------------------------------
# Service catalogue
# ---------------------------------------------------------------------------
# (Category, ServiceName, BasePriceINR, AvgDurationMins, IsEmergency, SkillTier,
#  MaterialCostPct)
SERVICES = [
    # --- Carpenter -------------------------------------------------------
    ("Carpenter", "Furniture Repair", 750, 90, 0, "Silver", 22.0),
    ("Carpenter", "Modular Kitchen Install", 45000, 600, 0, "Platinum", 55.0),
    ("Carpenter", "Door and Window Fix", 900, 100, 0, "Silver", 25.0),
    ("Carpenter", "Custom Woodwork", 12000, 420, 0, "Gold", 45.0),
    ("Carpenter", "Bed and Sofa Assembly", 800, 90, 0, "Bronze", 12.0),
    # --- Painter ---------------------------------------------------------
    ("Painter", "Interior Painting", 26000, 1440, 0, "Gold", 48.0),
    ("Painter", "Exterior Painting", 38000, 1800, 0, "Gold", 52.0),
    ("Painter", "Wall Texture", 9500, 480, 0, "Gold", 42.0),
    ("Painter", "Waterproofing", 16000, 600, 0, "Platinum", 50.0),
    ("Painter", "Wood Polish", 5500, 360, 0, "Silver", 38.0),
    # --- Plumber ---------------------------------------------------------
    ("Plumber", "Leak Repair", 700, 60, 1, "Silver", 20.0),
    ("Plumber", "Tap and Mixer Install", 450, 45, 0, "Bronze", 18.0),
    ("Plumber", "Bathroom Fitting", 3200, 240, 0, "Gold", 40.0),
    ("Plumber", "Drain Unclogging", 850, 70, 1, "Silver", 12.0),
    ("Plumber", "Water Tank Cleaning", 1400, 120, 0, "Bronze", 10.0),
    # --- Electrician -----------------------------------------------------
    ("Electrician", "Wiring Repair", 900, 90, 1, "Gold", 25.0),
    ("Electrician", "Switchboard Install", 1200, 110, 0, "Silver", 35.0),
    ("Electrician", "Fan and Light Install", 550, 55, 0, "Bronze", 15.0),
    ("Electrician", "Inverter Setup", 2400, 180, 0, "Gold", 30.0),
    ("Electrician", "MCB and Fuse Repair", 650, 60, 1, "Silver", 22.0),
    # --- AC Service ------------------------------------------------------
    ("AC Service", "AC Servicing", 650, 60, 0, "Silver", 12.0),
    ("AC Service", "AC Install and Uninstall", 1800, 150, 0, "Gold", 25.0),
    ("AC Service", "Gas Refill", 2600, 90, 0, "Gold", 45.0),
    ("AC Service", "AC Repair", 1500, 100, 1, "Gold", 32.0),
    # --- Deep Cleaning ---------------------------------------------------
    ("Deep Cleaning", "Full Home Cleaning", 5200, 360, 0, "Silver", 15.0),
    ("Deep Cleaning", "Bathroom Deep Clean", 1200, 120, 0, "Bronze", 12.0),
    ("Deep Cleaning", "Kitchen Deep Clean", 1900, 180, 0, "Silver", 14.0),
    ("Deep Cleaning", "Sofa and Carpet Shampoo", 1600, 150, 0, "Silver", 16.0),
    # --- Pest Control ----------------------------------------------------
    ("Pest Control", "General Pest Treatment", 1600, 90, 0, "Silver", 30.0),
    ("Pest Control", "Termite Treatment", 6500, 300, 0, "Gold", 42.0),
    ("Pest Control", "Cockroach and Ant Control", 1300, 75, 0, "Bronze", 28.0),
    ("Pest Control", "Bed Bug Treatment", 3200, 150, 0, "Gold", 38.0),
    # --- Appliance Repair ------------------------------------------------
    ("Appliance Repair", "Washing Machine Repair", 1100, 90, 0, "Silver", 34.0),
    ("Appliance Repair", "Refrigerator Repair", 1300, 100, 0, "Gold", 36.0),
    ("Appliance Repair", "Microwave Repair", 850, 70, 0, "Silver", 32.0),
    ("Appliance Repair", "Geyser Repair", 1050, 80, 1, "Silver", 30.0),
    ("Appliance Repair", "Chimney Service", 1400, 110, 0, "Silver", 20.0),
]

# Take rate by category. Cleaning and plumbing carry the highest rate; painting
# the lowest, because ticket sizes there are an order of magnitude larger.
COMMISSION_PCT = {
    "Deep Cleaning": 22.0,
    "Plumber": 22.0,
    "Pest Control": 21.0,
    "Electrician": 20.0,
    "Appliance Repair": 20.0,
    "AC Service": 19.0,
    "Carpenter": 18.0,
    "Painter": 15.0,
}

# Display / slicer ordering for the eight categories.
CATEGORY_ORDER = [
    "AC Service",
    "Appliance Repair",
    "Carpenter",
    "Deep Cleaning",
    "Electrician",
    "Painter",
    "Pest Control",
    "Plumber",
]

# Share of total booking volume, averaged across the whole window. Painter is
# small by volume and large by value, which is exactly the point.
CATEGORY_DEMAND_SHARE = {
    "Plumber": 0.16,
    "AC Service": 0.15,
    "Deep Cleaning": 0.15,
    "Appliance Repair": 0.14,
    "Electrician": 0.13,
    "Carpenter": 0.11,
    "Pest Control": 0.09,
    "Painter": 0.07,
}

# Relative weight of each service inside its category (normalised at load).
SERVICE_WEIGHT_WITHIN_CATEGORY = {
    "Furniture Repair": 3.0,
    "Modular Kitchen Install": 0.35,
    "Door and Window Fix": 2.2,
    "Custom Woodwork": 0.7,
    "Bed and Sofa Assembly": 2.4,
    "Interior Painting": 2.0,
    "Exterior Painting": 0.6,
    "Wall Texture": 0.9,
    "Waterproofing": 1.1,
    "Wood Polish": 1.0,
    "Leak Repair": 3.2,
    "Tap and Mixer Install": 2.4,
    "Bathroom Fitting": 0.9,
    "Drain Unclogging": 2.6,
    "Water Tank Cleaning": 1.3,
    "Wiring Repair": 2.4,
    "Switchboard Install": 1.2,
    "Fan and Light Install": 3.0,
    "Inverter Setup": 0.8,
    "MCB and Fuse Repair": 2.0,
    "AC Servicing": 4.5,
    "AC Install and Uninstall": 1.5,
    "Gas Refill": 1.2,
    "AC Repair": 2.4,
    "Full Home Cleaning": 2.2,
    "Bathroom Deep Clean": 2.6,
    "Kitchen Deep Clean": 2.0,
    "Sofa and Carpet Shampoo": 1.5,
    "General Pest Treatment": 3.2,
    "Termite Treatment": 0.9,
    "Cockroach and Ant Control": 2.6,
    "Bed Bug Treatment": 1.1,
    "Washing Machine Repair": 2.6,
    "Refrigerator Repair": 2.0,
    "Microwave Repair": 1.3,
    "Geyser Repair": 1.9,
    "Chimney Service": 1.5,
}

# ---------------------------------------------------------------------------
# Geography - 20 Bengaluru localities
# ---------------------------------------------------------------------------
# (AreaName, Zone, Pincode, Latitude, Longitude, DemandTier, IncomeBand,
#  demand_weight)
AREAS = [
    ("Koramangala", "South", "560034", 12.9352, 77.6245, "A", "Premium", 1.00),
    ("HSR Layout", "South", "560102", 12.9116, 77.6389, "A", "Premium", 0.96),
    ("Indiranagar", "East", "560038", 12.9784, 77.6408, "A", "Premium", 0.92),
    ("Whitefield", "East", "560066", 12.9698, 77.7500, "A", "Premium", 0.98),
    ("Marathahalli", "East", "560037", 12.9591, 77.6974, "A", "Mid", 0.84),
    ("Bellandur", "East", "560103", 12.9260, 77.6762, "A", "Upper-Mid", 0.81),
    ("Sarjapur Road", "South", "560035", 12.9010, 77.6874, "A", "Upper-Mid", 0.86),
    ("Electronic City", "South", "560100", 12.8452, 77.6602, "B", "Value", 0.62),
    ("BTM Layout", "South", "560076", 12.9166, 77.6101, "B", "Mid", 0.68),
    ("JP Nagar", "South", "560078", 12.9063, 77.5857, "B", "Mid", 0.66),
    ("Jayanagar", "South", "560041", 12.9250, 77.5938, "B", "Upper-Mid", 0.64),
    ("Banashankari", "South", "560070", 12.9255, 77.5468, "B", "Mid", 0.58),
    ("Bannerghatta Road", "South", "560083", 12.8878, 77.5970, "B", "Mid", 0.55),
    ("Hebbal", "North", "560024", 13.0358, 77.5970, "B", "Upper-Mid", 0.57),
    ("Rajajinagar", "West", "560010", 12.9915, 77.5551, "B", "Upper-Mid", 0.52),
    ("Malleshwaram", "Central", "560003", 13.0035, 77.5709, "B", "Premium", 0.54),
    ("Yelahanka", "North", "560064", 13.1007, 77.5963, "C", "Mid", 0.38),
    ("RT Nagar", "North", "560032", 13.0207, 77.5945, "C", "Value", 0.33),
    ("Vijayanagar", "West", "560040", 12.9719, 77.5347, "C", "Value", 0.35),
    ("KR Puram", "East", "560036", 13.0076, 77.6960, "C", "Value", 0.31),
]

# Ticket-size multiplier applied to quoted prices by income band.
INCOME_BAND_PRICE_FACTOR = {
    "Premium": 1.18,
    "Upper-Mid": 1.07,
    "Mid": 1.00,
    "Value": 0.91,
}

# Structural conversion strength by demand tier. Tier C areas generate interest
# but convert poorly - that gap is the Demand Intelligence page's core story.
DEMAND_TIER_QUOTE_TO_BOOKING = {"A": 0.42, "B": 0.34, "C": 0.24}
DEMAND_TIER_SUPPLY_DENSITY = {"A": 1.00, "B": 0.78, "C": 0.52}

# ---------------------------------------------------------------------------
# Pricing behaviour
# ---------------------------------------------------------------------------
QUOTE_NOISE_SIGMA = 0.16            # lognormal spread around the base price
EMERGENCY_PRICE_PREMIUM = 1.22
PEAK_SEASON_PRICE_PREMIUM = 1.09    # applied when the category multiplier > 1.5
PEAK_SEASON_MULTIPLIER_THRESHOLD = 1.5
QUOTE_ROUND_TO = 10                 # INR

DISCOUNT_PROB = 0.55                # share of bookings carrying a coupon
DISCOUNT_PCT_RANGE = (0.05, 0.20)
SCOPE_ADDON_PROB = 0.18             # on-site scope creep
SCOPE_ADDON_PCT_RANGE = (0.05, 0.25)
MATERIAL_COST_NOISE_SIGMA = 0.12
# Occasional promotional take-rate reduction for newly onboarded pros.
COMMISSION_PROMO_PROB = 0.06
COMMISSION_PROMO_REDUCTION_PCT = 3.0

# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------
TIME_TO_ASSIGN_BASE_MINS = 11.0
TIME_TO_ASSIGN_EMERGENCY_FACTOR = 0.55
TIME_TO_ASSIGN_STRAIN_FACTOR = 1.85      # multiplier per unit of strain above 1.0
TIME_TO_ASSIGN_SUPPLY_FACTOR = 1.40      # multiplier for thin-supply areas
TIME_TO_ASSIGN_SIGMA = 0.48

RESPONSE_TIME_BASE_MINS = 26.0
RESPONSE_TIME_STRAIN_FACTOR = 1.55
RESPONSE_TIME_SIGMA = 0.52
RESPONSE_TIME_SLOW_THRESHOLD_MINS = 55.0

ETA_BASE_MINS = 62.0
ETA_SIGMA_BASE_MINS = 13.0               # matches the eta_sla_predictor RMSE goal
ETA_SIGMA_STRAIN_FACTOR = 1.6

SLA_PROMISE_MINS = 90                    # the arrival window promised to customers
SLA_BASE_MET_PROB = 0.912
SLA_STRAIN_PENALTY = 0.42                # probability lost per unit of strain
SLA_THIN_SUPPLY_PENALTY = 0.07
SLA_MONSOON_PENALTY = 0.05

JOB_DURATION_SIGMA = 0.24                # lognormal spread around AvgDurationMins

FIRST_TIME_FIX_BASE = 0.885
FIRST_TIME_FIX_TIER_BONUS = {"Bronze": -0.055, "Silver": 0.0, "Gold": 0.035, "Platinum": 0.055}
REOPEN_BASE_PROB = 0.035
REOPEN_IF_NOT_FIRST_FIX = 0.31

RATING_PRESENT_PROB = 0.62               # 38% of completed jobs go unrated
RATING_BASE = 4.52
RATING_SLA_BREACH_PENALTY = 1.15
RATING_SLOW_RESPONSE_PENALTY = 0.42
RATING_REOPEN_PENALTY = 0.95
RATING_TIER_BONUS = {"Bronze": -0.22, "Silver": 0.0, "Gold": 0.16, "Platinum": 0.28}
RATING_NOISE_SIGMA = 0.62

# Shrink low-volume professionals towards their tier prior so nobody sits at a
# perfect 5.00 off three jobs.
RATING_PRIOR_BY_TIER = {"Bronze": 4.05, "Silver": 4.32, "Gold": 4.55, "Platinum": 4.72}
RATING_PRIOR_WEIGHT = 8.0

# Booking time-of-day. Weights per hour 0..23 for weekdays and weekends.
HOUR_WEIGHTS_WEEKDAY = [
    0.2, 0.1, 0.1, 0.1, 0.2, 0.6, 1.6, 3.4, 6.2, 8.4, 8.8, 7.2,
    5.4, 4.4, 4.2, 4.8, 6.4, 8.6, 9.2, 7.8, 5.6, 3.4, 1.8, 0.8,
]
HOUR_WEIGHTS_WEEKEND = [
    0.3, 0.2, 0.1, 0.1, 0.2, 0.5, 1.2, 2.4, 4.6, 7.4, 9.2, 8.6,
    6.8, 5.6, 5.4, 5.8, 7.0, 8.2, 8.4, 6.8, 4.8, 3.2, 2.0, 1.2,
]

# Trailing window used to define capacity strain.
STRAIN_TRAILING_DAYS = 30

# ---------------------------------------------------------------------------
# Professional supply
# ---------------------------------------------------------------------------
PRO_TIER_MIX = {"Bronze": 0.34, "Silver": 0.38, "Gold": 0.21, "Platinum": 0.07}
# Relative probability of winning an incoming job. The spread is deliberately
# wide: marketplace supply is unequal and the dashboard should say so.
PRO_TIER_ASSIGNMENT_WEIGHT = {"Bronze": 1.0, "Silver": 2.1, "Gold": 4.4, "Platinum": 7.8}
PRO_SAME_AREA_WEIGHT = 6.0
PRO_SAME_ZONE_WEIGHT = 2.2
PRO_OTHER_ZONE_WEIGHT = 0.35
PRO_CROSS_CATEGORY_PROB = 0.05          # a pro occasionally takes adjacent work

PRO_SLOTS_BY_TIER = {"Bronze": (1, 3), "Silver": (2, 4), "Gold": (3, 6), "Platinum": (4, 7)}
# Beta parameters for a pro's roster activity rate (share of days they open a
# calendar at all). Heavily skewed: a long tail of part-time supply.
PRO_ACTIVITY_BETA = (1.5, 4.2)
PRO_ACTIVITY_TIER_BONUS = {"Bronze": -0.06, "Silver": 0.0, "Gold": 0.12, "Platinum": 0.22}
PRO_ACTIVITY_MIN = 0.05
PRO_ACTIVITY_MAX = 0.92
# Pros open more slots when their category is in season.
PRO_SEASONAL_ONLINE_SENSITIVITY = 0.35

PRO_BACKGROUND_VERIFIED_PROB = {"Bronze": 0.72, "Silver": 0.88, "Gold": 0.96, "Platinum": 1.00}
PRO_CHURN_PROB = 0.145
PRO_CHURN_MIN_TENURE_DAYS = 60
PRO_CHURN_MAX_TENURE_DAYS = 520
PRO_SHARE_JOINED_BEFORE_WINDOW = 0.40

PRO_ONBOARDING_CHANNELS = [
    "Field Recruiter", "Referral by Pro", "Walk In",
    "Online Signup", "Partner Agency", "Job Portal",
]
PRO_ONBOARDING_MIX = [0.27, 0.22, 0.09, 0.19, 0.15, 0.08]

# Offers declined per online day. Tuned so blended acceptance lands near 67%:
# a third of offers being turned down is a real marketplace problem worth a
# dashboard tile, whereas a coin-flip 50% just reads as noise.
PRO_REJECTED_JOBS_LAMBDA = 0.25
PRO_IDLE_MINS_PER_ONLINE_DAY = (60, 240)
PRO_TRAVEL_MINS_PER_JOB = (18, 55)

# Share of pros who are women, by category. Deep cleaning crews in Bengaluru
# are substantially women; the wiring trades are not.
PRO_FEMALE_SHARE = {
    "Deep Cleaning": 0.72, "Pest Control": 0.18, "Carpenter": 0.04,
    "Painter": 0.06, "Plumber": 0.03, "Electrician": 0.04,
    "AC Service": 0.05, "Appliance Repair": 0.08,
}

# ---------------------------------------------------------------------------
# Funnel (fact_leads)
# ---------------------------------------------------------------------------
FUNNEL_LEAD_TO_QUOTE = 0.72
FUNNEL_SEARCH_TO_LEAD = 0.31
FUNNEL_NOISE_SIGMA = 0.18
# Share of extra cells with search interest but no booking at all, expressed as
# a ratio to the number of cells that did convert. Weighted towards low-tier
# areas so "high interest, poor conversion" is genuinely in the data.
FUNNEL_DEAD_CELL_RATIO = 0.55
FUNNEL_DEAD_CELL_TIER_WEIGHT = {"A": 0.6, "B": 1.0, "C": 2.4}
FUNNEL_DEAD_CELL_SEARCH_RANGE = (1, 9)
LEAD_QUALITY_BASE = 0.58
LEAD_QUALITY_TIER_BONUS = {"A": 0.09, "B": 0.0, "C": -0.11}
LEAD_QUALITY_SIGMA = 0.06

# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------
# (ModelName, ModelType, BusinessPurpose, Framework, Algorithm, PrimaryMetric,
#  MetricGoal, GoalDirection, DeployedDate, Version, RefreshCadence, OwnerTeam,
#  IsBusinessCritical)
MODELS = [
    ("demand_forecaster", "Time Series Regression",
     "Forecasts next-7-day job volume per area and category so supply can be pre-positioned",
     "LightGBM", "Gradient Boosted Trees", "MAPE", 12.0, "LowerIsBetter",
     _dt.date(2025, 3, 1), "2.3.0", "Weekly", "Data Science", 1),
    ("pro_match_ranker", "Learning to Rank",
     "Ranks available technicians for an incoming job",
     "XGBoost", "LambdaMART", "NDCG@5", 0.82, "HigherIsBetter",
     _dt.date(2025, 2, 15), "3.1.0", "Weekly", "Marketplace ML", 1),
    ("dynamic_price_engine", "Quantile Regression",
     "Produces the quoted price band shown to the customer",
     "LightGBM", "Quantile Gradient Boosting", "QuoteAcceptRate", 0.62, "HigherIsBetter",
     _dt.date(2025, 5, 1), "1.6.0", "Weekly", "Pricing", 1),
    ("eta_sla_predictor", "Regression",
     "Predicts the technician arrival window behind the SLA promise",
     "CatBoost", "Ordered Boosting", "RMSEMins", 14.0, "LowerIsBetter",
     _dt.date(2025, 4, 10), "1.4.0", "Fortnightly", "Marketplace ML", 0),
    ("customer_churn", "Binary Classification",
     "Flags customers unlikely to rebook within the next 90 days",
     "XGBoost", "Gradient Boosted Trees", "AUC", 0.79, "HigherIsBetter",
     _dt.date(2025, 8, 1), "1.2.0", "Monthly", "Growth Analytics", 0),
    ("fraud_booking_detector", "Anomaly Detection",
     "Catches fake, duplicate and abusive bookings before dispatch",
     "scikit-learn", "IsolationForest plus rules", "Precision", 0.71, "HigherIsBetter",
     _dt.date(2025, 6, 15), "2.0.0", "Weekly", "Trust and Safety", 1),
    ("review_sentiment_indic", "NLP Classification",
     "Classifies reviews in English, Kannada, Hindi and code-mixed Kanglish",
     "PyTorch", "Fine-tuned MuRIL", "MacroF1", 0.85, "HigherIsBetter",
     _dt.date(2025, 11, 1), "1.1.0", "Quarterly", "Data Science", 0),
    ("lead_quality_scorer", "Binary Classification",
     "Scores inbound leads so the sales team calls the ones worth calling",
     "LightGBM", "Gradient Boosted Trees", "AUC", 0.74, "HigherIsBetter",
     _dt.date(2026, 1, 15), "1.0.0", "Monthly", "Growth Analytics", 0),
]

# ---------------------------------------------------------------------------
# The demand_forecaster drift incident
# ---------------------------------------------------------------------------
# Beat 1: the scheduled retrain job silently stops succeeding. Nothing breaks.
RETRAIN_SILENT_FAILURE_DATE = _dt.date(2026, 3, 15)
# Beat 2: the monsoon shifts the demand regime and the stale model degrades.
DRIFT_ONSET_DATE = _dt.date(2026, 6, 1)
DRIFT_FULL_DATE = _dt.date(2026, 6, 18)
# Beat 3: PSI crosses the alert threshold and stays there.
PSI_ALERT_THRESHOLD = 0.25
PSI_CROSSING_DATE = _dt.date(2026, 6, 15)
# Beat 4: a retrain lands, the version bumps, the age counter resets.
RETRAIN_FIX_DATE = _dt.date(2026, 7, 20)
RETRAIN_RECOVERY_DAYS = 5
FORECASTER_VERSION_AFTER_FIX = "2.4.0"

# MAPE regime, expressed as a fraction (0.09 == 9%).
FORECASTER_MAPE_LAUNCH = 0.118      # first weeks after deployment
FORECASTER_MAPE_MATURE = 0.090      # steady state through May 2026
FORECASTER_MAPE_DRIFTED = 0.192     # June and July 2026
FORECASTER_MAPE_RECOVERED = 0.100   # after the 2026-07-20 retrain
FORECASTER_MAPE_MATURITY_DAYS = 180  # days from deploy to reach mature accuracy
FORECASTER_MAPE_NOISE_SIGMA = 0.055  # relative day-to-day noise on MAPE

PSI_BASELINE = (0.035, 0.075)
PSI_DRIFTED = (0.26, 0.39)
FEATURE_NULL_PCT_BASELINE = (0.20, 0.85)
FEATURE_NULL_PCT_INCIDENT = (1.60, 3.40)

# Normal weekly retrain cadence produces a sawtooth training-data age.
TRAINING_AGE_SAWTOOTH_DAYS = 7

# fraud_booking_detector: fraud follows the money.
FRAUD_DIWALI_VOLUME_UPLIFT = 2.35
FRAUD_DIWALI_PRECISION_DROP = 0.13

# pro_match_ranker: ranking gets harder as the supply pool grows.
MATCH_NDCG_START = 0.862
MATCH_NDCG_END = 0.801

# Generic health envelopes for the remaining models: (start, end, noise_sigma).
# These sit a clear margin above (or below, for LowerIsBetter) their goals, so a
# healthy model reads as healthy. An envelope parked exactly on its goal line
# flips in and out of breach on noise alone, which trains everyone to ignore the
# alert - true of synthetic data and true of production monitoring.
# The two deliberate exceptions are handled elsewhere: demand_forecaster carries
# the June 2026 incident, and pro_match_ranker decays through its goal by design.
MODEL_HEALTH_ENVELOPE = {
    "dynamic_price_engine": (0.648, 0.671, 0.018),
    "eta_sla_predictor": (13.1, 12.4, 0.62),
    "customer_churn": (0.812, 0.828, 0.012),
    "fraud_booking_detector": (0.758, 0.741, 0.021),
    "review_sentiment_indic": (0.872, 0.891, 0.014),
    "lead_quality_scorer": (0.762, 0.783, 0.016),
}
MODEL_BLIP_PROB = 0.012              # single-day operational blip
MODEL_BLIP_MAGNITUDE = 0.09          # relative size of the blip

MODEL_LATENCY_P95_MS = {
    "demand_forecaster": 210, "pro_match_ranker": 48, "dynamic_price_engine": 62,
    "eta_sla_predictor": 39, "customer_churn": 155, "fraud_booking_detector": 71,
    "review_sentiment_indic": 340, "lead_quality_scorer": 44,
}
MODEL_LATENCY_SIGMA = 0.13
MODEL_PREDICTION_VOLUME_PER_BOOKING = {
    "demand_forecaster": 1.4, "pro_match_ranker": 11.5, "dynamic_price_engine": 2.6,
    "eta_sla_predictor": 2.2, "customer_churn": 0.9, "fraud_booking_detector": 1.0,
    "review_sentiment_indic": 0.42, "lead_quality_scorer": 3.1,
}
MODEL_PSI_BASELINE_OTHER = (0.02, 0.11)

# ---------------------------------------------------------------------------
# Forecast accuracy fact
# ---------------------------------------------------------------------------
FORECAST_EMIT_MIN = 0.5             # emit a row when the forecast is at least this
FORECAST_BIAS = 0.03                # the model runs slightly hot on average
FORECAST_ROUND_DP = 1

# ---------------------------------------------------------------------------
# Booking-level model score columns
# ---------------------------------------------------------------------------
PRICE_PREDICTION_SIGMA = 0.115      # relative error of PredictedPriceINR
MATCH_SCORE_BASE = 0.74
MATCH_SCORE_TIER_BONUS = {"Bronze": -0.12, "Silver": -0.02, "Gold": 0.07, "Platinum": 0.13}
MATCH_SCORE_SIGMA = 0.075
FRAUD_SCORE_BASE = 0.055
FRAUD_SCORE_SIGMA = 0.055
FRAUD_HIGH_RISK_PROB = 0.021
FRAUD_HIGH_RISK_RANGE = (0.62, 0.97)
CHURN_SCORE_SIGMA = 0.13
SCORE_ROUND_DP = 3

# ---------------------------------------------------------------------------
# Public holidays (national plus Karnataka)
# ---------------------------------------------------------------------------
PUBLIC_HOLIDAYS = {
    _dt.date(2025, 1, 1): "New Year Day",
    _dt.date(2025, 1, 14): "Makar Sankranti",
    _dt.date(2025, 1, 26): "Republic Day",
    _dt.date(2025, 2, 26): "Maha Shivaratri",
    _dt.date(2025, 3, 30): "Ugadi",
    _dt.date(2025, 3, 31): "Ramzan",
    _dt.date(2025, 4, 6): "Ram Navami",
    _dt.date(2025, 4, 18): "Good Friday",
    _dt.date(2025, 5, 1): "May Day",
    _dt.date(2025, 6, 7): "Bakrid",
    _dt.date(2025, 8, 8): "Varamahalakshmi",
    _dt.date(2025, 8, 15): "Independence Day",
    _dt.date(2025, 8, 27): "Ganesh Chaturthi",
    _dt.date(2025, 10, 1): "Ayudha Puja",
    _dt.date(2025, 10, 2): "Vijayadashami",
    _dt.date(2025, 10, 20): "Deepavali",
    _dt.date(2025, 11, 1): "Kannada Rajyotsava",
    _dt.date(2025, 12, 25): "Christmas",
    _dt.date(2026, 1, 1): "New Year Day",
    _dt.date(2026, 1, 14): "Makar Sankranti",
    _dt.date(2026, 1, 26): "Republic Day",
    _dt.date(2026, 2, 15): "Maha Shivaratri",
    _dt.date(2026, 3, 19): "Ugadi",
    _dt.date(2026, 3, 21): "Ramzan",
    _dt.date(2026, 3, 27): "Ram Navami",
    _dt.date(2026, 4, 3): "Good Friday",
    _dt.date(2026, 5, 1): "May Day",
    _dt.date(2026, 5, 27): "Bakrid",
    _dt.date(2026, 8, 15): "Independence Day",
}

# ---------------------------------------------------------------------------
# Indian fiscal year
# ---------------------------------------------------------------------------
FISCAL_YEAR_START_MONTH = 4

# ---------------------------------------------------------------------------
# Output tables
# ---------------------------------------------------------------------------
TABLES = [
    "dim_date",
    "dim_service",
    "dim_area",
    "dim_professional",
    "dim_customer",
    "dim_model",
    "fact_bookings",
    "fact_pro_capacity",
    "fact_leads",
    "fact_model_metrics",
    "fact_forecast_accuracy",
]

# ---------------------------------------------------------------------------
# Seasonality windows
# ---------------------------------------------------------------------------
# Each window is (month, day) based and recurs every year. Overlapping windows
# MULTIPLY: painting during the Diwali / north-east monsoon overlap therefore
# lands at 2.4 * 0.65 = 1.56 - demand rises for the festival but the rain still
# restrains it. Categories absent from a window are unaffected by it.
#
# "Flags" drives the dim_date IsMonsoon / IsFestivalWindow columns.
SEASON_WINDOWS = [
    {
        "Name": "South West Monsoon",
        "Kind": "Monsoon",
        "Start": (6, 1),
        "End": (9, 30),
        "Multipliers": {
            "Plumber": 1.90,
            "Electrician": 1.40,
            "Pest Control": 1.60,
            "Painter": 0.65,
        },
    },
    {
        "Name": "North East Monsoon",
        "Kind": "Monsoon",
        "Start": (10, 10),
        "End": (11, 20),
        "Multipliers": {
            "Plumber": 1.90,
            "Electrician": 1.40,
            "Pest Control": 1.60,
            "Painter": 0.65,
        },
    },
    {
        "Name": "Summer",
        "Kind": "Season",
        "Start": (3, 1),
        "End": (5, 31),
        "Multipliers": {
            "AC Service": 3.20,
            "Appliance Repair": 1.30,
        },
    },
    {
        "Name": "Diwali",
        "Kind": "Festival",
        "Start": (10, 12),
        "End": (11, 5),
        "Multipliers": {
            "Painter": 2.40,
            "Deep Cleaning": 2.80,
            "Carpenter": 1.50,
        },
    },
    {
        "Name": "Ugadi",
        "Kind": "Festival",
        "Start": (3, 15),
        "End": (4, 5),
        "Multipliers": {
            "Deep Cleaning": 1.80,
            "Painter": 1.40,
        },
    },
    # The windows below carry no demand multiplier. They exist so that
    # dim_date.IsFestivalWindow and FestivalName are honest about the calendar.
    {
        "Name": "Sankranti",
        "Kind": "Festival",
        "Start": (1, 10),
        "End": (1, 17),
        "Multipliers": {},
    },
    {
        "Name": "Ganesh Chaturthi",
        "Kind": "Festival",
        "Start": (8, 24),
        "End": (9, 1),
        "Multipliers": {},
    },
    {
        "Name": "Christmas and New Year",
        "Kind": "Festival",
        "Start": (12, 22),
        "End": (12, 31),
        "Multipliers": {},
    },
]

# Day-shape effects. These redistribute demand *within* a month rather than
# changing the month total, so the growth trend stays readable.
WEEKEND_MULTIPLIER = 1.35
WEEKEND_CATEGORY_EXTRA = {"Deep Cleaning": 1.60}
MONTH_END_DAYS = 5
MONTH_END_MULTIPLIER = 0.85

# ---------------------------------------------------------------------------
# Category x area affinity
# ---------------------------------------------------------------------------
# Exponent applied to INCOME_BAND_PRICE_FACTOR when choosing which area a
# booking lands in. Deep cleaning and AC work skew hard to premium areas;
# a blocked drain does not care how much rent you pay.
CATEGORY_INCOME_AFFINITY = {
    "Deep Cleaning": 1.5,
    "Painter": 1.3,
    "AC Service": 1.2,
    "Carpenter": 1.0,
    "Pest Control": 0.6,
    "Appliance Repair": 0.5,
    "Plumber": 0.2,
    "Electrician": 0.2,
}

# ---------------------------------------------------------------------------
# ETA and SLA mechanics
# ---------------------------------------------------------------------------
# SLAMetFlag is drawn first from a probability that responds to strain, then
# ActualETAMins is drawn from the matching side of the SLA promise. That keeps
# the two columns mechanically consistent - no row can be "SLA met" with a
# 3-hour arrival - while leaving the strain correlation intact.
ETA_MET_MEAN_MINS = 58.0
ETA_MET_SD_MINS = 15.0
ETA_MET_MIN_MINS = 18
ETA_MET_MAX_MINS = 89
ETA_BREACH_MIN_MINS = 91
ETA_BREACH_SCALE_MINS = 38.0
ETA_BREACH_MAX_MINS = 420
# The predictor is good but not clairvoyant: noise plus shrinkage to the mean,
# which is what a real regressor does and what produces an honest RMSE.
ETA_PRED_NOISE_MINS = 12.0
ETA_PRED_SHRINK = 0.85
ETA_PRED_MIN_MINS = 15
ETA_PRED_MAX_MINS = 400

# ---------------------------------------------------------------------------
# Identifiers
# ---------------------------------------------------------------------------
BOOKING_ID_PREFIX = "BK"
BOOKING_ID_WIDTH = 7

# ---------------------------------------------------------------------------
# Customer activation
# ---------------------------------------------------------------------------
# The earliest bookings must belong to brand new customers - there is nobody
# else yet. This many leading bookings are forced to be first bookings.
FIRST_BOOKING_FORCED_HEAD = 40

# ---------------------------------------------------------------------------
# Churn risk scoring
# ---------------------------------------------------------------------------
CHURN_SCORE_BASE = 0.62
CHURN_SCORE_PROPENSITY_WEIGHT = 0.22

# ---------------------------------------------------------------------------
# Forecast accuracy fact
# ---------------------------------------------------------------------------
# Cells where nothing happened but the model still predicted something. This is
# the failure mode worth seeing, so it is generated deliberately.
FORECAST_ZERO_ACTUAL_PROB = 0.35
FORECAST_ZERO_ACTUAL_SCALE = 0.9
APE_ROUND_DP = 4
