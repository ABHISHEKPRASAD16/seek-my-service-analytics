"""
Seek My Service - synthetic data generator.

Produces the eleven CSVs in ``data/`` that Power BI imports. One fixed seed
drives everything, so a regeneration is byte-identical.

Pipeline
--------
1.  Dimensions that depend on nothing (date, service, area, model).
2.  Solve the growth trend algebraically so the first and last month land on
    their anchors *after* seasonality, leaving festival months free to outrun
    their own baseline.
3.  Draw booking counts per day and category, expand to booking rows.
4.  Derive capacity strain from realised daily volume, then draw statuses.
5.  Build the professional roster and its capacity calendar, then assign
    bookings into real slots, so fact_pro_capacity reconciles by construction.
6.  Assign customers in chronological order, so signup precedes first booking
    by construction rather than by a later repair pass.
7.  Money, operations and model scores.
8.  Derive dim_customer and dim_professional back out of the facts.
9.  Build the funnel backwards from real bookings; build model telemetry and
    forecast accuracy.

Run with:  python generator/generate.py
"""

from __future__ import annotations

import calendar
import datetime as dt
import os
import sys
import time
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from generator import config, seasonality  # noqa: E402


# ===========================================================================
# CSV formatting
# ===========================================================================
# Every value is rendered to a string *before* it reaches pandas, so the CSVs
# can never contain "nan", "NULL", or an integer written as "4.0".

def s_int(values, mask=None) -> np.ndarray:
    """Format as a bare integer. ``mask`` False -> blank."""
    arr = np.asarray(values, dtype=float)
    out = np.char.mod("%d", np.nan_to_num(arr, nan=0.0).astype(np.int64))
    if mask is not None:
        out = np.where(np.asarray(mask, dtype=bool), out, config.BLANK)
    return out.astype(object)


def s_dec(values, dp: int, mask=None) -> np.ndarray:
    """Format with exactly ``dp`` decimal places. ``mask`` False -> blank."""
    arr = np.asarray(values, dtype=float)
    out = np.char.mod(f"%.{dp}f", np.nan_to_num(arr, nan=0.0))
    if mask is not None:
        out = np.where(np.asarray(mask, dtype=bool), out, config.BLANK)
    return out.astype(object)


def s_txt(values, mask=None) -> np.ndarray:
    """Format as text, mapping None and NaN to the empty string."""
    arr = np.asarray(values, dtype=object)
    out = np.array(
        [config.BLANK if (v is None or (isinstance(v, float) and np.isnan(v))) else str(v)
         for v in arr],
        dtype=object,
    )
    if mask is not None:
        out = np.where(np.asarray(mask, dtype=bool), out, config.BLANK)
    return out.astype(object)


def write_table(name: str, columns: Dict[str, np.ndarray]) -> Tuple[int, int]:
    """Write one CSV. Returns (row_count, byte_size)."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(columns)
    path = config.DATA_DIR / f"{name}.csv"
    frame.to_csv(
        path,
        index=False,
        encoding=config.CSV_ENCODING,
        lineterminator=config.CSV_LINE_TERMINATOR,
    )
    return len(frame), path.stat().st_size


# ===========================================================================
# Small helpers
# ===========================================================================
def date_key(day: dt.date) -> int:
    return day.year * 10000 + day.month * 100 + day.day


def lognormal_factor(rng: np.random.Generator, sigma: float, size) -> np.ndarray:
    """Multiplicative noise with mean 1.0 (median shifted so the mean is 1)."""
    return rng.lognormal(mean=-0.5 * sigma * sigma, sigma=sigma, size=size)


def normalise(weights) -> np.ndarray:
    arr = np.asarray(weights, dtype=float)
    return arr / arr.sum()


def tenure_bounds(join: dt.date, churn, n_days: int) -> Tuple[int, int]:
    """Half-open [start, end) day-index window a professional is available for.

    Defined once and shared by the capacity calendar and the assignment loop.
    The two used to compute this separately, and a professional who churned
    *before* the fact window opened fell through a dictionary lookup default
    and was treated as never having churned - which put six of them on jobs
    after they had left. One helper, one definition, no drift.
    """
    if join > config.DATE_END:
        return 0, 0
    start = max((join - config.DATE_START).days, 0)

    if churn is None:
        end = n_days
    elif churn <= config.DATE_START:
        end = 0
    elif churn > config.DATE_END:
        end = n_days
    else:
        end = (churn - config.DATE_START).days

    return start, max(end, start)


# ===========================================================================
# Stage 1 - dimensions that depend on nothing
# ===========================================================================
def build_dim_date(days: List[dt.date]) -> pd.DataFrame:
    """One contiguous row per day, with the Indian fiscal calendar."""
    records = []
    for day in days:
        records.append({
            "DateKey": date_key(day),
            "Date": day.isoformat(),
            "Year": day.year,
            "Quarter": f"Q{(day.month - 1) // 3 + 1}",
            "MonthNo": day.month,
            "MonthName": calendar.month_name[day.month],
            "MonthYear": f"{calendar.month_abbr[day.month]} {day.year}",
            "MonthYearSort": day.year * 100 + day.month,
            "WeekNo": day.isocalendar().week,
            "DayName": calendar.day_name[day.weekday()],
            "DayOfWeekNo": day.weekday() + 1,
            "IsWeekend": int(seasonality.is_weekend(day)),
            "IsMonsoon": int(seasonality.is_monsoon(day)),
            "IsFestivalWindow": int(seasonality.is_festival_window(day)),
            "FestivalName": seasonality.festival_name(day),
            "IsMonthEnd": int(seasonality.is_month_end(day)),
            "FiscalYear": seasonality.fiscal_year_label(day),
            "FiscalQuarter": seasonality.fiscal_quarter_label(day),
            "IsHoliday": int(seasonality.is_holiday(day)),
            "DaysFromToday": (day - config.TODAY).days,
        })
    return pd.DataFrame.from_records(records)


def build_dim_service() -> pd.DataFrame:
    """The 37-row service catalogue, keyed 1..37 in configuration order."""
    records = []
    per_category_seen: Dict[str, int] = {}
    for idx, (category, name, price, duration, emergency, tier, material) in enumerate(
        config.SERVICES, start=1
    ):
        seen = per_category_seen.get(category, 0)
        per_category_seen[category] = seen + 1
        records.append({
            "ServiceKey": idx,
            "ServiceCategory": category,
            "ServiceName": name,
            "BasePriceINR": price,
            "AvgDurationMins": duration,
            "IsEmergency": emergency,
            "SkillTier": tier,
            "MaterialCostPct": material,
            "CommissionPct": config.COMMISSION_PCT[category],
            "ServiceSortOrder": (config.CATEGORY_ORDER.index(category) + 1) * 100 + seen + 1,
        })
    return pd.DataFrame.from_records(records)


def build_dim_area() -> pd.DataFrame:
    """The 20 Bengaluru localities, sorted for slicers by zone then name."""
    zone_order = ["Central", "East", "North", "South", "West"]
    rows = []
    for idx, (name, zone, pincode, lat, lon, tier, income, weight) in enumerate(
        config.AREAS, start=1
    ):
        rows.append({
            "AreaKey": idx,
            "AreaName": name,
            "Zone": zone,
            "Pincode": pincode,
            "Latitude": lat,
            "Longitude": lon,
            "DemandTier": tier,
            "IncomeBand": income,
            "_zone_rank": zone_order.index(zone),
            "_weight": weight,
        })
    frame = pd.DataFrame.from_records(rows)
    order = frame.sort_values(["_zone_rank", "AreaName"]).index
    sort_lookup = {area_index: position + 1 for position, area_index in enumerate(order)}
    frame["AreaSortOrder"] = [sort_lookup[i] for i in frame.index]
    return frame


def build_dim_model() -> pd.DataFrame:
    """The eight production models."""
    records = []
    for idx, spec in enumerate(config.MODELS, start=1):
        (name, mtype, purpose, framework, algorithm, metric, goal, direction,
         deployed, version, cadence, team, critical) = spec
        records.append({
            "ModelKey": idx,
            "ModelName": name,
            "ModelType": mtype,
            "BusinessPurpose": purpose,
            "Framework": framework,
            "Algorithm": algorithm,
            "PrimaryMetric": metric,
            "MetricGoal": goal,
            "GoalDirection": direction,
            "DeployedDate": deployed.isoformat(),
            "Version": version,
            "RefreshCadence": cadence,
            "OwnerTeam": team,
            "IsBusinessCritical": critical,
        })
    return pd.DataFrame.from_records(records)


# ===========================================================================
# Stage 2 - solve the growth trend
# ===========================================================================
def solve_trend(days: List[dt.date], rng: np.random.Generator):
    """Return per-day, per-category expected *completed* volume.

    The deseasonalised monthly trend is a geometric curve. Its level and growth
    rate are solved so that the realised (seasonal) volume of the first and last
    month land on the anchors from config. Every month in between is free: a
    Diwali month outruns its own baseline instead of being normalised back down
    to it.
    """
    categories = config.CATEGORY_ORDER
    month_keys = sorted({seasonality.month_key(d) for d in days})
    days_by_month: Dict[int, List[dt.date]] = {m: [] for m in month_keys}
    for day in days:
        days_by_month[seasonality.month_key(day)].append(day)

    # Per day and category: seasonal multiplier x normalised day shape.
    shape: Dict[dt.date, Dict[str, float]] = {d: {} for d in days}
    uplift_by_month = np.zeros(len(month_keys))
    for m_index, month in enumerate(month_keys):
        month_days = days_by_month[month]
        month_uplift = 0.0
        for category in categories:
            nds = seasonality.normalised_day_shape(month_days, category)
            seas = [seasonality.category_seasonal_multiplier(d, category) for d in month_days]
            combined = [s * n for s, n in zip(seas, nds)]
            for day, value in zip(month_days, combined):
                shape[day][category] = value
            month_uplift += config.CATEGORY_DEMAND_SHARE[category] * float(np.mean(combined))
        uplift_by_month[m_index] = month_uplift

    n_months = len(month_keys)
    level = config.COMPLETED_ANCHOR_FIRST_MONTH / uplift_by_month[0]
    final_level = config.COMPLETED_ANCHOR_LAST_MONTH / uplift_by_month[-1]
    growth = (final_level / level) ** (1.0 / (n_months - 1))

    noise = lognormal_factor(rng, config.TREND_NOISE_SIGMA, n_months)
    noise[0] = 1.0
    noise[-1] = 1.0

    trend = np.array([level * growth ** i * noise[i] for i in range(n_months)])

    expected = {}
    for m_index, month in enumerate(month_keys):
        month_days = days_by_month[month]
        per_day_level = trend[m_index] / len(month_days)
        for day in month_days:
            expected[day] = {
                c: per_day_level * config.CATEGORY_DEMAND_SHARE[c] * shape[day][c]
                for c in categories
            }
    return expected, month_keys, trend, uplift_by_month


# ===========================================================================
# Stage 3 - booking skeleton
# ===========================================================================
def build_booking_skeleton(days, expected, heavy_rain, rng) -> pd.DataFrame:
    """Draw booking counts, then expand to one row per booking.

    Counts are drawn for *bookings*, not completions, by dividing the expected
    completed volume by that day's expected completion probability. That keeps
    the growth anchors honest once cancellations are applied.
    """
    categories = config.CATEGORY_ORDER
    cancelish = (config.STATUS_BASE["CancelledByCustomer"]
                 + config.STATUS_BASE["CancelledByPro"]
                 + config.STATUS_BASE["NoShow"])

    day_index = {day: i for i, day in enumerate(days)}
    all_day_idx: List[np.ndarray] = []
    all_cat_idx: List[np.ndarray] = []

    for day in days:
        uplift = config.MONSOON_CANCEL_UPLIFT if heavy_rain[day_index[day]] else 0.0
        completion_prob = 1.0 - cancelish * (1.0 + uplift) - config.STATUS_BASE["Rescheduled"]
        for c_index, category in enumerate(categories):
            lam = expected[day][category] / completion_prob
            count = int(rng.poisson(lam))
            if count == 0:
                continue
            all_day_idx.append(np.full(count, day_index[day], dtype=np.int32))
            all_cat_idx.append(np.full(count, c_index, dtype=np.int8))

    day_idx = np.concatenate(all_day_idx)
    cat_idx = np.concatenate(all_cat_idx)
    return pd.DataFrame({"DayIndex": day_idx, "CategoryIndex": cat_idx})


def assign_area_and_service(frame: pd.DataFrame, area_frame: pd.DataFrame, service_frame,
                            rng) -> pd.DataFrame:
    """Choose an area and a service for every booking, one category at a time."""
    categories = config.CATEGORY_ORDER
    area_weight = area_frame["_weight"].to_numpy(dtype=float)
    income_factor = np.array([config.INCOME_BAND_PRICE_FACTOR[b]
                              for b in area_frame["IncomeBand"]])
    area_keys = area_frame["AreaKey"].to_numpy()

    area_out = np.zeros(len(frame), dtype=np.int32)
    service_out = np.zeros(len(frame), dtype=np.int32)

    for c_index, category in enumerate(categories):
        mask = frame["CategoryIndex"].to_numpy() == c_index
        n = int(mask.sum())
        if n == 0:
            continue
        affinity = config.CATEGORY_INCOME_AFFINITY[category]
        weights = normalise(area_weight * income_factor ** affinity)
        area_out[mask] = rng.choice(area_keys, size=n, p=weights)

        cat_services = service_frame[service_frame["ServiceCategory"] == category]
        svc_keys = cat_services["ServiceKey"].to_numpy()
        svc_weights = normalise([config.SERVICE_WEIGHT_WITHIN_CATEGORY[n_]
                                 for n_ in cat_services["ServiceName"]])
        service_out[mask] = rng.choice(svc_keys, size=n, p=svc_weights)

    frame = frame.copy()
    frame["AreaKey"] = area_out
    frame["ServiceKey"] = service_out
    return frame


def assign_timestamps(frame: pd.DataFrame, days: List[dt.date], rng) -> pd.DataFrame:
    """Draw a plausible booking time of day, then sort chronologically."""
    day_idx = frame["DayIndex"].to_numpy()
    day_array = np.array(days, dtype=object)
    is_weekend = np.array([seasonality.is_weekend(d) for d in days])[day_idx]

    hours = np.zeros(len(frame), dtype=np.int16)
    weekday_p = normalise(config.HOUR_WEIGHTS_WEEKDAY)
    weekend_p = normalise(config.HOUR_WEIGHTS_WEEKEND)
    for mask, probs in ((~is_weekend, weekday_p), (is_weekend, weekend_p)):
        n = int(mask.sum())
        if n:
            hours[mask] = rng.choice(24, size=n, p=probs)
    minutes = rng.integers(0, 60, size=len(frame))
    seconds = rng.integers(0, 60, size=len(frame))

    frame = frame.copy()
    frame["Hour"] = hours
    frame["Minute"] = minutes
    frame["Second"] = seconds
    frame = frame.sort_values(
        ["DayIndex", "Hour", "Minute", "Second"], kind="stable"
    ).reset_index(drop=True)

    day_objects = day_array[frame["DayIndex"].to_numpy()]
    frame["Date"] = day_objects
    frame["DateKey"] = [date_key(d) for d in day_objects]
    frame["BookingTimestamp"] = [
        f"{d.isoformat()} {h:02d}:{mi:02d}:{s:02d}"
        for d, h, mi, s in zip(day_objects, frame["Hour"], frame["Minute"], frame["Second"])
    ]
    frame["BookingID"] = [
        f"{config.BOOKING_ID_PREFIX}{i:0{config.BOOKING_ID_WIDTH}d}"
        for i in range(1, len(frame) + 1)
    ]
    return frame


# ===========================================================================
# Stage 4 - capacity strain and booking status
# ===========================================================================
def compute_strain(frame: pd.DataFrame, n_days: int) -> np.ndarray:
    """Daily volume divided by its trailing 30-day mean.

    This is the operational pressure signal. SLA breaches, time-to-assign and
    cancellations all read from it, so the capacity story in the dashboard is
    a genuine correlation rather than an assertion.
    """
    counts = np.bincount(frame["DayIndex"].to_numpy(), minlength=n_days).astype(float)
    series = pd.Series(counts)
    trailing = series.shift(1).rolling(config.STRAIN_TRAILING_DAYS, min_periods=1).mean()
    trailing = trailing.bfill().replace(0.0, np.nan).ffill()
    strain = (series / trailing).fillna(1.0).to_numpy()
    return np.clip(strain, 0.3, 3.0)


def draw_status(frame, heavy_rain, strain, rng) -> np.ndarray:
    """Status per booking, responding to rain and to capacity strain."""
    day_idx = frame["DayIndex"].to_numpy()
    uplift = np.where(heavy_rain[day_idx], config.MONSOON_CANCEL_UPLIFT, 0.0)
    strain_term = np.clip(strain[day_idx] - 1.0, -0.5, 1.5) * config.STRAIN_CANCEL_UPLIFT_PER_UNIT
    total_uplift = 1.0 + uplift + strain_term

    p_cust = config.STATUS_BASE["CancelledByCustomer"] * total_uplift
    p_pro = config.STATUS_BASE["CancelledByPro"] * total_uplift
    p_noshow = config.STATUS_BASE["NoShow"] * total_uplift
    p_resched = np.full(len(frame), config.STATUS_BASE["Rescheduled"])
    p_completed = np.clip(1.0 - p_cust - p_pro - p_noshow - p_resched, 0.05, 1.0)

    stacked = np.vstack([p_completed, p_cust, p_pro, p_noshow, p_resched])
    stacked = stacked / stacked.sum(axis=0)
    cumulative = np.cumsum(stacked, axis=0)
    draw = rng.random(len(frame))
    choice = (draw > cumulative).sum(axis=0)
    labels = np.array(["Completed", "CancelledByCustomer", "CancelledByPro",
                       "NoShow", "Rescheduled"])
    return labels[np.clip(choice, 0, 4)]


# ===========================================================================
# Stage 5 - professionals and their capacity calendar
# ===========================================================================
def _name_pools() -> Dict[str, Dict[str, List[str]]]:
    """Given-name and surname pools reflecting Bengaluru's actual mix."""
    return {
        "Kannada": {
            "male": ["Manjunath", "Basavaraj", "Shivakumar", "Ramesh", "Nagaraj",
                     "Chandrashekar", "Girish", "Lokesh", "Mahadev", "Prakash",
                     "Srinivas", "Venkatesh", "Ravi", "Suresh", "Kiran", "Umesh",
                     "Naveen", "Mallikarjun", "Shankar", "Yogesh", "Harish",
                     "Ganesh", "Vinay", "Santhosh", "Rajanna"],
            "female": ["Lakshmi", "Savitha", "Padma", "Roopa", "Geetha", "Sunitha",
                       "Kavitha", "Shobha", "Mangala", "Rekha", "Bhagya", "Nandini",
                       "Jayanthi", "Vijaya", "Sowmya", "Chaitra"],
            "surnames": ["Gowda", "Hegde", "Shetty", "Naik", "Patil", "Rao",
                         "Murthy", "Bhat", "Kumar", "Swamy", "Achar", "Poojary",
                         "Kulkarni", "Desai", "Gouda"],
        },
        "Tamil": {
            "male": ["Murugan", "Selvam", "Karthik", "Dinesh", "Saravanan", "Arun",
                     "Vignesh", "Prabhu", "Rajesh", "Bala", "Sathish", "Muthu",
                     "Anand", "Senthil", "Ilango"],
            "female": ["Kalaivani", "Meena", "Revathi", "Deepa", "Uma", "Vasanthi",
                       "Bhuvana", "Thenmozhi"],
            "surnames": ["Subramanian", "Raman", "Krishnan", "Pillai", "Nadar",
                         "Chettiar", "Iyer", "Sundaram", "Natarajan", "Velu"],
        },
        "Telugu": {
            "male": ["Srinu", "Ramakrishna", "Sai", "Venkat", "Nagendra", "Bhaskar",
                     "Chandra", "Praveen", "Sudhakar", "Rambabu"],
            "female": ["Swapna", "Sirisha", "Aruna", "Vasavi", "Madhavi", "Sridevi"],
            "surnames": ["Reddy", "Naidu", "Chowdary", "Rao", "Varma", "Prasad",
                         "Yadav"],
        },
        "Hindi": {
            "male": ["Rakesh", "Sunil", "Amit", "Vikas", "Deepak", "Pankaj", "Rohit",
                     "Sandeep", "Manoj", "Ajay", "Rajkumar", "Dharmendra", "Sanjay",
                     "Vijay", "Anil"],
            "female": ["Sunita", "Poonam", "Kiran", "Anjali", "Meera", "Sarita"],
            "surnames": ["Sharma", "Verma", "Singh", "Yadav", "Gupta", "Mishra",
                         "Pandey", "Thakur", "Chauhan", "Joshi"],
        },
        "Urdu": {
            "male": ["Mohammed", "Imran", "Salim", "Rafiq", "Asif", "Nadeem",
                     "Javed", "Firoz", "Shabbir", "Altaf", "Irfan", "Riyaz",
                     "Sameer", "Tanveer", "Wasim"],
            "female": ["Shabana", "Nasreen", "Farida", "Ayesha", "Rukhsana", "Zareena"],
            "surnames": ["Khan", "Ahmed", "Sheikh", "Pasha", "Ansari", "Qureshi",
                         "Hussain", "Baig", "Sait", "Shariff"],
        },
    }


_BACKGROUND_MIX = {
    "Kannada": 0.36, "Tamil": 0.18, "Telugu": 0.16, "Hindi": 0.17, "Urdu": 0.13,
}
_LANGUAGE_EXTRAS = {
    "Kannada": ["Kannada", "English", "Hindi", "Tamil"],
    "Tamil": ["Tamil", "Kannada", "English", "Telugu"],
    "Telugu": ["Telugu", "Kannada", "English", "Hindi"],
    "Hindi": ["Hindi", "English", "Kannada", "Urdu"],
    "Urdu": ["Urdu", "Hindi", "Kannada", "English"],
}


def build_professionals(area_frame: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """The 850-strong roster. Derived columns are filled in after the facts."""
    n = config.N_PROFESSIONALS
    pools = _name_pools()
    backgrounds = list(_BACKGROUND_MIX)
    background_p = normalise([_BACKGROUND_MIX[b] for b in backgrounds])

    categories = config.CATEGORY_ORDER
    cat_p = normalise([config.CATEGORY_DEMAND_SHARE[c] for c in categories])
    pro_category = rng.choice(categories, size=n, p=cat_p)

    # Supply density is deliberately thinner in low demand-tier areas: that is
    # what creates a genuine supply-demand gap for the Supply Health page.
    area_keys = area_frame["AreaKey"].to_numpy()
    supply_weight = normalise(
        area_frame["_weight"].to_numpy(dtype=float)
        * np.array([config.DEMAND_TIER_SUPPLY_DENSITY[t] for t in area_frame["DemandTier"]])
    )
    home_area = rng.choice(area_keys, size=n, p=supply_weight)

    tiers = list(config.PRO_TIER_MIX)
    tier = rng.choice(tiers, size=n, p=normalise([config.PRO_TIER_MIX[t] for t in tiers]))

    # Join dates: a founding cohort before the window opens, then a flow that
    # grows with the marketplace.
    n_early = int(round(n * config.PRO_SHARE_JOINED_BEFORE_WINDOW))
    early_span = (config.DATE_START - config.PRO_JOIN_EARLIEST).days
    early_offsets = rng.integers(0, early_span, size=n_early)
    early_dates = [config.PRO_JOIN_EARLIEST + dt.timedelta(days=int(o)) for o in early_offsets]

    late_span = (config.PRO_JOIN_LATEST - config.DATE_START).days
    late_weights = normalise(np.linspace(1.0, 2.4, late_span + 1))
    late_offsets = rng.choice(late_span + 1, size=n - n_early, p=late_weights)
    late_dates = [config.DATE_START + dt.timedelta(days=int(o)) for o in late_offsets]

    join_dates = early_dates + late_dates
    rng.shuffle(join_dates)

    background = rng.choice(backgrounds, size=n, p=background_p)
    female_prob = np.array([config.PRO_FEMALE_SHARE[c] for c in pro_category])
    is_female = rng.random(n) < female_prob

    names = []
    languages = []
    for i in range(n):
        pool = pools[background[i]]
        given_pool = pool["female"] if is_female[i] else pool["male"]
        given = given_pool[int(rng.integers(0, len(given_pool)))]
        surname = pool["surnames"][int(rng.integers(0, len(pool["surnames"])))]
        names.append(f"{given} {surname}")
        options = _LANGUAGE_EXTRAS[background[i]]
        count = int(rng.integers(2, min(4, len(options)) + 1))
        languages.append("|".join(options[:count]))

    verified = rng.random(n) < np.array([config.PRO_BACKGROUND_VERIFIED_PROB[t] for t in tier])

    churned = rng.random(n) < config.PRO_CHURN_PROB
    tenure = rng.integers(config.PRO_CHURN_MIN_TENURE_DAYS,
                          config.PRO_CHURN_MAX_TENURE_DAYS, size=n)
    churn_dates = []
    for i in range(n):
        if not churned[i]:
            churn_dates.append(None)
            continue
        candidate = join_dates[i] + dt.timedelta(days=int(tenure[i]))
        churn_dates.append(candidate if candidate <= config.DATE_END else None)

    activity = rng.beta(*config.PRO_ACTIVITY_BETA, size=n)
    activity = np.clip(
        activity + np.array([config.PRO_ACTIVITY_TIER_BONUS[t] for t in tier]),
        config.PRO_ACTIVITY_MIN, config.PRO_ACTIVITY_MAX,
    )

    onboarding = rng.choice(config.PRO_ONBOARDING_CHANNELS, size=n,
                            p=normalise(config.PRO_ONBOARDING_MIX))

    return pd.DataFrame({
        "ProKey": np.arange(1, n + 1),
        "ProName": names,
        "PrimaryServiceCategory": pro_category,
        "HomeAreaKey": home_area,
        "JoinDate": join_dates,
        "SkillTier": tier,
        "IsBackgroundVerified": verified.astype(int),
        "LanguagesSpoken": languages,
        "OnboardingChannel": onboarding,
        "ChurnedDate": churn_dates,
        "_activity": activity,
    })


def build_capacity_calendar(pro_frame, days, rng):
    """Boolean online grid and integer slot grid, shaped (n_pros, n_days).

    Built *before* bookings are assigned. Assignment then consumes real slots,
    which is what makes SlotsBooked reconcile exactly instead of approximately.
    """
    n_pros = len(pro_frame)
    n_days = len(days)
    day_index = {day: i for i, day in enumerate(days)}

    online = np.zeros((n_pros, n_days), dtype=bool)
    slots = np.zeros((n_pros, n_days), dtype=np.int16)
    tenure_mask = np.zeros((n_pros, n_days), dtype=bool)

    # Seasonal pull: a plumber opens more slots in July than in February.
    seasonal = np.ones((len(config.CATEGORY_ORDER), n_days))
    for c_index, category in enumerate(config.CATEGORY_ORDER):
        for d_index, day in enumerate(days):
            seasonal[c_index, d_index] = seasonality.category_seasonal_multiplier(day, category)

    cat_index = {c: i for i, c in enumerate(config.CATEGORY_ORDER)}
    activity = pro_frame["_activity"].to_numpy()
    tiers = pro_frame["SkillTier"].to_numpy()
    categories = pro_frame["PrimaryServiceCategory"].to_numpy()
    joins = pro_frame["JoinDate"].tolist()
    churns = pro_frame["ChurnedDate"].tolist()

    for p in range(n_pros):
        start, end = tenure_bounds(joins[p], churns[p], n_days)
        if end <= start:
            continue
        tenure_mask[p, start:end] = True

        pull = seasonal[cat_index[categories[p]], start:end]
        adjusted = np.clip(
            activity[p] * (1.0 + config.PRO_SEASONAL_ONLINE_SENSITIVITY * (pull - 1.0)),
            0.01, 0.99,
        )
        is_online = rng.random(end - start) < adjusted
        online[p, start:end] = is_online

        low, high = config.PRO_SLOTS_BY_TIER[tiers[p]]
        drawn = rng.integers(low, high + 1, size=end - start)
        slots[p, start:end] = np.where(is_online, drawn, 0)

    return online, slots, tenure_mask


def assign_professionals(frame, pro_frame, area_frame, online, slots, days, rng):
    """Pick a professional for every booking, consuming a real capacity slot."""
    n_pros = len(pro_frame)
    remaining = slots.copy()
    booked = np.zeros_like(slots)

    zone_of_area = dict(zip(area_frame["AreaKey"], area_frame["Zone"]))
    pro_home = pro_frame["HomeAreaKey"].to_numpy()
    pro_zone = np.array([zone_of_area[a] for a in pro_home])
    pro_tier_weight = np.array([config.PRO_TIER_ASSIGNMENT_WEIGHT[t]
                                for t in pro_frame["SkillTier"]])
    pro_category = pro_frame["PrimaryServiceCategory"].to_numpy()

    by_category = {c: np.where(pro_category == c)[0] for c in config.CATEGORY_ORDER}
    all_pros = np.arange(n_pros)

    # Which pros exist at all on a given day (join <= day < churn).
    tenure = np.zeros((n_pros, len(days)), dtype=bool)
    joins = pro_frame["JoinDate"].tolist()
    churns = pro_frame["ChurnedDate"].tolist()
    for p in range(n_pros):
        start, end = tenure_bounds(joins[p], churns[p], len(days))
        tenure[p, start:end] = True

    day_idx = frame["DayIndex"].to_numpy()
    cat_idx = frame["CategoryIndex"].to_numpy()
    area_of_booking = frame["AreaKey"].to_numpy()
    categories = config.CATEGORY_ORDER

    assigned = np.zeros(len(frame), dtype=np.int32)
    forced = 0
    cross_category = rng.random(len(frame)) < config.PRO_CROSS_CATEGORY_PROB

    for i in range(len(frame)):
        d = day_idx[i]
        category = categories[cat_idx[i]]
        candidates = all_pros if cross_category[i] else by_category[category]
        available = candidates[(remaining[candidates, d] > 0) & online[candidates, d]]

        if available.size == 0:
            available = all_pros[(remaining[:, d] > 0) & online[:, d]]

        if available.size == 0:
            # Nobody free: pull a tenured pro of the right category on shift.
            fallback = by_category[category][tenure[by_category[category], d]]
            if fallback.size == 0:
                fallback = all_pros[tenure[:, d]]
            if fallback.size == 0:
                fallback = all_pros
            pick = int(rng.choice(fallback))
            online[pick, d] = True
            slots[pick, d] += 1
            remaining[pick, d] += 1
            available = np.array([pick])
            forced += 1

        booking_area = area_of_booking[i]
        booking_zone = zone_of_area[booking_area]
        geo = np.where(
            pro_home[available] == booking_area, config.PRO_SAME_AREA_WEIGHT,
            np.where(pro_zone[available] == booking_zone,
                     config.PRO_SAME_ZONE_WEIGHT, config.PRO_OTHER_ZONE_WEIGHT),
        )
        weights = pro_tier_weight[available] * geo
        weights = weights / weights.sum()
        pick = int(rng.choice(available, p=weights))

        assigned[i] = pick
        remaining[pick, d] -= 1
        booked[pick, d] += 1

    return assigned, booked, forced


# ===========================================================================
# Stage 6 - customers
# ===========================================================================
def assign_customers(frame, area_frame, days, rng):
    """Choose which bookings are first bookings, then fill the repeats.

    Bookings are walked in chronological order. A customer can only be picked
    for a repeat once they have already been activated, so SignupDate precedes
    the first booking by construction - there is no repair pass to get wrong.
    """
    n_bookings = len(frame)
    n_customers = config.N_CUSTOMERS

    day_idx = frame["DayIndex"].to_numpy()
    progress = day_idx / max(len(days) - 1, 1)
    new_share = (config.NEW_CUSTOMER_SHARE_START
                 + (config.NEW_CUSTOMER_SHARE_END - config.NEW_CUSTOMER_SHARE_START) * progress)

    # Gumbel top-k: weighted sampling without replacement in O(n log n).
    keys = np.log(new_share) - np.log(-np.log(rng.random(n_bookings)))
    keys[:config.FIRST_BOOKING_FORCED_HEAD] = np.inf   # the market has to start somewhere
    first_slots = np.sort(np.argsort(-keys, kind="stable")[:n_customers])

    is_first = np.zeros(n_bookings, dtype=bool)
    is_first[first_slots] = True

    channels = list(config.ACQUISITION_CHANNELS)
    channel_p = normalise([config.ACQUISITION_CHANNELS[c][0] for c in channels])
    cust_channel = rng.choice(channels, size=n_customers, p=channel_p)
    propensity = np.array([config.ACQUISITION_CHANNELS[c][1] for c in cust_channel])

    booking_area = frame["AreaKey"].to_numpy()
    cust_area = booking_area[first_slots]
    activation_day = day_idx[first_slots]

    customer_of_booking = np.zeros(n_bookings, dtype=np.int32)
    last_day = np.full(n_customers, -10_000.0)

    area_keys = area_frame["AreaKey"].to_numpy()
    active_by_area: Dict[int, List[int]] = {int(a): [] for a in area_keys}
    active_all: List[int] = []

    next_customer = 0
    cross_area_draw = rng.random(n_bookings) < config.REPEAT_CROSS_AREA_PROB
    halflife = config.REPEAT_RECENCY_HALFLIFE_DAYS

    for i in range(n_bookings):
        d = day_idx[i]
        if is_first[i]:
            cid = next_customer
            next_customer += 1
            customer_of_booking[i] = cid
            active_by_area[int(cust_area[cid])].append(cid)
            active_all.append(cid)
            last_day[cid] = d
            continue

        pool = active_all if cross_area_draw[i] else active_by_area[int(booking_area[i])]
        if not pool:
            pool = active_all
        candidates = np.fromiter(pool, dtype=np.int32, count=len(pool))
        weights = propensity[candidates] * 0.5 ** ((d - last_day[candidates]) / halflife)
        total = weights.sum()
        if not np.isfinite(total) or total <= 0:
            pick = int(candidates[rng.integers(0, candidates.size)])
        else:
            pick = int(rng.choice(candidates, p=weights / total))
        customer_of_booking[i] = pick
        last_day[pick] = d

    day_array = np.array(days, dtype=object)
    first_booking_dates = day_array[activation_day]
    lead = rng.integers(0, config.SIGNUP_LEAD_DAYS_MAX + 1, size=n_customers)
    signup_dates = [
        max(fb - dt.timedelta(days=int(l)), config.CUSTOMER_SIGNUP_EARLIEST)
        for fb, l in zip(first_booking_dates, lead)
    ]

    app_prob = np.array([config.ACQUISITION_CHANNELS[c][2] for c in cust_channel])
    is_app_user = (rng.random(n_customers) < app_prob).astype(int)
    language = rng.choice(config.CUSTOMER_LANGUAGES, size=n_customers,
                          p=normalise(config.CUSTOMER_LANGUAGE_MIX))

    customer_frame = pd.DataFrame({
        "CustomerKey": np.arange(1, n_customers + 1),
        "SignupDate": signup_dates,
        "AreaKey": cust_area,
        "AcquisitionChannel": cust_channel,
        "IsAppUser": is_app_user,
        "PreferredLanguage": language,
        "_propensity": propensity,
    })
    return customer_of_booking + 1, is_first, customer_frame


# ===========================================================================
# Stage 7 - money, operations, model scores
# ===========================================================================
def build_financials_and_ops(frame, service_frame, area_frame, pro_frame,
                             days, heavy_rain, strain, rng):
    """Everything a booking row carries beyond its keys."""
    n = len(frame)
    svc = service_frame.set_index("ServiceKey")
    area = area_frame.set_index("AreaKey")

    service_key = frame["ServiceKey"].to_numpy()
    area_key = frame["AreaKey"].to_numpy()
    day_idx = frame["DayIndex"].to_numpy()
    status = frame["BookingStatus"].to_numpy()
    pro_index = frame["_ProIndex"].to_numpy()

    base_price = svc.loc[service_key, "BasePriceINR"].to_numpy(dtype=float)
    duration = svc.loc[service_key, "AvgDurationMins"].to_numpy(dtype=float)
    is_emergency = svc.loc[service_key, "IsEmergency"].to_numpy(dtype=int)
    material_pct = svc.loc[service_key, "MaterialCostPct"].to_numpy(dtype=float)
    category = svc.loc[service_key, "ServiceCategory"].to_numpy()

    income_band = area.loc[area_key, "IncomeBand"].to_numpy()
    demand_tier = area.loc[area_key, "DemandTier"].to_numpy()
    income_factor = np.array([config.INCOME_BAND_PRICE_FACTOR[b] for b in income_band])
    supply_density = np.array([config.DEMAND_TIER_SUPPLY_DENSITY[t] for t in demand_tier])

    seasonal_mult = np.array([
        seasonality.category_seasonal_multiplier(days[d], c)
        for d, c in zip(day_idx, category)
    ])
    peak = np.where(seasonal_mult > config.PEAK_SEASON_MULTIPLIER_THRESHOLD,
                    config.PEAK_SEASON_PRICE_PREMIUM, 1.0)
    emergency = np.where(is_emergency == 1, config.EMERGENCY_PRICE_PREMIUM, 1.0)

    # ---- quoted, discount, final -----------------------------------------
    quoted = base_price * income_factor * peak * emergency * lognormal_factor(
        rng, config.QUOTE_NOISE_SIGMA, n)
    quoted = np.maximum(np.round(quoted / config.QUOTE_ROUND_TO) * config.QUOTE_ROUND_TO,
                        config.QUOTE_ROUND_TO * 10)

    has_discount = rng.random(n) < config.DISCOUNT_PROB
    discount_pct = rng.uniform(*config.DISCOUNT_PCT_RANGE, size=n)
    discount = np.where(has_discount, quoted * discount_pct, 0.0)
    discount = np.round(discount / config.QUOTE_ROUND_TO) * config.QUOTE_ROUND_TO

    has_addon = rng.random(n) < config.SCOPE_ADDON_PROB
    addon_pct = rng.uniform(*config.SCOPE_ADDON_PCT_RANGE, size=n)
    addon = np.where(has_addon, quoted * addon_pct, 0.0)

    final = np.clip(quoted - discount + addon, 0.0, quoted + discount)
    final = np.round(final / config.QUOTE_ROUND_TO) * config.QUOTE_ROUND_TO
    final = np.minimum(final, quoted + discount)

    is_completed = status == "Completed"
    final = np.where(is_completed, final, 0.0)

    commission = np.array([config.COMMISSION_PCT[c] for c in category])
    promo = rng.random(n) < config.COMMISSION_PROMO_PROB
    commission = np.where(promo, commission - config.COMMISSION_PROMO_REDUCTION_PCT, commission)
    platform_revenue = np.round(final * commission / 100.0, 2)

    material = np.where(
        is_completed,
        final * material_pct / 100.0 * lognormal_factor(rng, config.MATERIAL_COST_NOISE_SIGMA, n),
        0.0,
    )
    material = np.round(material, 2)

    # ---- operations -------------------------------------------------------
    strain_row = strain[day_idx]
    strain_excess = np.clip(strain_row - 1.0, 0.0, 2.0)
    thin_supply = 1.0 / supply_density

    tta = (config.TIME_TO_ASSIGN_BASE_MINS
           * (1.0 + config.TIME_TO_ASSIGN_STRAIN_FACTOR * strain_excess)
           * (1.0 + (config.TIME_TO_ASSIGN_SUPPLY_FACTOR - 1.0) * (thin_supply - 1.0))
           * np.where(is_emergency == 1, config.TIME_TO_ASSIGN_EMERGENCY_FACTOR, 1.0)
           * lognormal_factor(rng, config.TIME_TO_ASSIGN_SIGMA, n))
    time_to_assign = np.maximum(np.round(tta), 1).astype(int)

    rt = (config.RESPONSE_TIME_BASE_MINS
          * (1.0 + config.RESPONSE_TIME_STRAIN_FACTOR * strain_excess)
          * lognormal_factor(rng, config.RESPONSE_TIME_SIGMA, n))
    response_time = np.maximum(np.round(rt), 1).astype(int)

    # ---- SLA and ETA ------------------------------------------------------
    monsoon_day = np.array([seasonality.is_monsoon(days[d]) for d in day_idx])
    p_sla = (config.SLA_BASE_MET_PROB
             - config.SLA_STRAIN_PENALTY * strain_excess
             - config.SLA_THIN_SUPPLY_PENALTY * (thin_supply - 1.0)
             - config.SLA_MONSOON_PENALTY * monsoon_day)
    p_sla = np.clip(p_sla, 0.30, 0.99)
    sla_met = (rng.random(n) < p_sla).astype(int)

    met_eta = np.clip(
        np.round(rng.normal(config.ETA_MET_MEAN_MINS, config.ETA_MET_SD_MINS, n)),
        config.ETA_MET_MIN_MINS, config.ETA_MET_MAX_MINS,
    )
    breach_eta = np.clip(
        np.round(config.ETA_BREACH_MIN_MINS
                 + rng.exponential(config.ETA_BREACH_SCALE_MINS, n)),
        config.ETA_BREACH_MIN_MINS, config.ETA_BREACH_MAX_MINS,
    )
    actual_eta = np.where(sla_met == 1, met_eta, breach_eta)

    predicted_eta = (config.ETA_BASE_MINS
                     + config.ETA_PRED_SHRINK
                     * (actual_eta + rng.normal(0.0, config.ETA_PRED_NOISE_MINS, n)
                        - config.ETA_BASE_MINS))
    predicted_eta = np.clip(np.round(predicted_eta),
                            config.ETA_PRED_MIN_MINS, config.ETA_PRED_MAX_MINS).astype(int)

    job_duration = np.maximum(
        np.round(duration * lognormal_factor(rng, config.JOB_DURATION_SIGMA, n)), 5
    ).astype(int)

    pro_tier = pro_frame["SkillTier"].to_numpy()[pro_index]
    ftf_prob = np.clip(
        config.FIRST_TIME_FIX_BASE
        + np.array([config.FIRST_TIME_FIX_TIER_BONUS[t] for t in pro_tier])
        - 0.06 * (1 - sla_met),
        0.4, 0.99,
    )
    first_time_fix = (rng.random(n) < ftf_prob).astype(int)
    reopen_prob = np.where(first_time_fix == 1, config.REOPEN_BASE_PROB,
                           config.REOPEN_IF_NOT_FIRST_FIX)
    reopened = (rng.random(n) < reopen_prob).astype(int)

    slow_response = response_time > config.RESPONSE_TIME_SLOW_THRESHOLD_MINS
    rating_score = (config.RATING_BASE
                    - config.RATING_SLA_BREACH_PENALTY * (1 - sla_met)
                    - config.RATING_SLOW_RESPONSE_PENALTY * slow_response
                    - config.RATING_REOPEN_PENALTY * reopened
                    + np.array([config.RATING_TIER_BONUS[t] for t in pro_tier])
                    + rng.normal(0.0, config.RATING_NOISE_SIGMA, n))
    rating = np.clip(np.round(rating_score), 1, 5).astype(int)
    has_rating = is_completed & (rng.random(n) < config.RATING_PRESENT_PROB)

    sentiment = np.where(rating >= 4, "Positive", np.where(rating == 3, "Neutral", "Negative"))

    # ---- payment and channel ---------------------------------------------
    progress = day_idx / max(len(days) - 1, 1)
    channel_mix = (np.array(config.BOOKING_CHANNEL_MIX_START)[None, :]
                   + (np.array(config.BOOKING_CHANNEL_MIX_END)
                      - np.array(config.BOOKING_CHANNEL_MIX_START))[None, :]
                   * progress[:, None])
    channel_cum = np.cumsum(channel_mix / channel_mix.sum(axis=1, keepdims=True), axis=1)
    draw = rng.random(n)[:, None]
    channel = np.array(config.BOOKING_CHANNELS)[
        np.clip((draw > channel_cum).sum(axis=1), 0, len(config.BOOKING_CHANNELS) - 1)
    ]

    pay_weights = np.tile(np.array(config.PAYMENT_MODE_MIX), (n, 1)).astype(float)
    cash_col = config.PAYMENT_MODES.index("Cash")
    pay_weights[channel == "Phone", cash_col] *= config.PAYMENT_CASH_UPLIFT_PHONE
    pay_weights[income_band == "Value", cash_col] *= config.PAYMENT_CASH_UPLIFT_VALUE_AREA
    pay_cum = np.cumsum(pay_weights / pay_weights.sum(axis=1, keepdims=True), axis=1)
    draw = rng.random(n)[:, None]
    payment = np.array(config.PAYMENT_MODES)[
        np.clip((draw > pay_cum).sum(axis=1), 0, len(config.PAYMENT_MODES) - 1)
    ]

    # ---- model score columns ---------------------------------------------
    predicted_price = np.maximum(
        np.round(quoted * lognormal_factor(rng, config.PRICE_PREDICTION_SIGMA, n)), 50
    ).astype(int)

    match_score = np.clip(
        config.MATCH_SCORE_BASE
        + np.array([config.MATCH_SCORE_TIER_BONUS[t] for t in pro_tier])
        + rng.normal(0.0, config.MATCH_SCORE_SIGMA, n),
        0.05, 0.999,
    )

    fraud_score = np.abs(rng.normal(config.FRAUD_SCORE_BASE, config.FRAUD_SCORE_SIGMA, n))
    high_risk = rng.random(n) < config.FRAUD_HIGH_RISK_PROB
    fraud_score = np.where(high_risk, rng.uniform(*config.FRAUD_HIGH_RISK_RANGE, size=n),
                           fraud_score)
    fraud_score = np.clip(fraud_score, 0.001, 0.999)

    return {
        "QuotedAmountINR": quoted,
        "FinalAmountINR": final,
        "DiscountINR": discount,
        "CommissionPct": commission,
        "PlatformRevenueINR": platform_revenue,
        "MaterialCostINR": material,
        "PaymentMode": payment,
        "Channel": channel,
        "TimeToAssignMins": time_to_assign,
        "ResponseTimeMins": response_time,
        "JobDurationMins": job_duration,
        "SLAMetFlag": sla_met,
        "CustomerRating": rating,
        "ReviewSentiment": sentiment,
        "HasRating": has_rating,
        "IsCompleted": is_completed,
        "PredictedPriceINR": predicted_price,
        "PredictedETAMins": predicted_eta,
        "ActualETAMins": actual_eta.astype(int),
        "MatchScore": match_score,
        "FraudScore": fraud_score,
        "IsFirstTimeFix": first_time_fix,
        "ReopenedWithin7Days": reopened,
    }


# ===========================================================================
# Stage 9 - downstream facts
# ===========================================================================
def build_leads(bookings, area_frame, service_frame, days, rng) -> pd.DataFrame:
    """The funnel, built backwards from real bookings.

    Bookings in each cell are the truth; quotes, leads and searches are inferred
    upwards from them with tier-dependent conversion. Monotonicity therefore
    holds by construction, and the reconciliation check cannot fail.
    """
    grouped = (bookings.groupby(["DateKey", "AreaKey", "ServiceKey"], sort=True)
               .size().reset_index(name="Bookings"))

    tier_of_area = dict(zip(area_frame["AreaKey"], area_frame["DemandTier"]))
    tier = np.array([tier_of_area[a] for a in grouped["AreaKey"]])
    q2b = np.array([config.DEMAND_TIER_QUOTE_TO_BOOKING[t] for t in tier])
    q2b = np.clip(q2b * lognormal_factor(rng, config.FUNNEL_NOISE_SIGMA, len(grouped)),
                  0.08, 0.90)
    l2q = np.clip(config.FUNNEL_LEAD_TO_QUOTE
                  * lognormal_factor(rng, config.FUNNEL_NOISE_SIGMA, len(grouped)), 0.15, 0.95)
    s2l = np.clip(config.FUNNEL_SEARCH_TO_LEAD
                  * lognormal_factor(rng, config.FUNNEL_NOISE_SIGMA, len(grouped)), 0.08, 0.85)

    bookings_n = grouped["Bookings"].to_numpy()
    quotes = np.ceil(bookings_n / q2b).astype(int)
    leads = np.ceil(quotes / l2q).astype(int)
    searches = np.ceil(leads / s2l).astype(int)

    live = pd.DataFrame({
        "DateKey": grouped["DateKey"].to_numpy(),
        "AreaKey": grouped["AreaKey"].to_numpy(),
        "ServiceKey": grouped["ServiceKey"].to_numpy(),
        "Searches": searches,
        "Leads": leads,
        "QuotesSent": quotes,
        "Bookings": bookings_n,
        "_tier": tier,
    })

    # Cells with genuine search interest that converted to nothing at all.
    n_dead = int(len(grouped) * config.FUNNEL_DEAD_CELL_RATIO)
    area_keys = area_frame["AreaKey"].to_numpy()
    area_p = normalise([config.FUNNEL_DEAD_CELL_TIER_WEIGHT[t]
                        for t in area_frame["DemandTier"]]
                       * area_frame["_weight"].to_numpy(dtype=float))
    svc_keys = service_frame["ServiceKey"].to_numpy()
    svc_p = normalise([config.SERVICE_WEIGHT_WITHIN_CATEGORY[n_]
                       for n_ in service_frame["ServiceName"]])
    day_keys = np.array([date_key(d) for d in days])

    dead = pd.DataFrame({
        "DateKey": rng.choice(day_keys, size=n_dead),
        "AreaKey": rng.choice(area_keys, size=n_dead, p=area_p),
        "ServiceKey": rng.choice(svc_keys, size=n_dead, p=svc_p),
    })
    dead = dead.merge(live[["DateKey", "AreaKey", "ServiceKey"]],
                      on=["DateKey", "AreaKey", "ServiceKey"], how="left", indicator=True)
    dead = dead[dead["_merge"] == "left_only"].drop(columns="_merge")
    dead = dead.drop_duplicates(subset=["DateKey", "AreaKey", "ServiceKey"])

    m = len(dead)
    dead_searches = rng.integers(config.FUNNEL_DEAD_CELL_SEARCH_RANGE[0],
                                 config.FUNNEL_DEAD_CELL_SEARCH_RANGE[1] + 1, size=m)
    dead_s2l = np.clip(config.FUNNEL_SEARCH_TO_LEAD
                       * lognormal_factor(rng, config.FUNNEL_NOISE_SIGMA, m), 0.05, 0.9)
    dead_leads = np.floor(dead_searches * dead_s2l).astype(int)
    dead_l2q = np.clip(config.FUNNEL_LEAD_TO_QUOTE
                       * lognormal_factor(rng, config.FUNNEL_NOISE_SIGMA, m), 0.1, 0.95)
    dead_quotes = np.floor(dead_leads * dead_l2q).astype(int)
    dead["Searches"] = dead_searches
    dead["Leads"] = dead_leads
    dead["QuotesSent"] = dead_quotes
    dead["Bookings"] = 0
    dead["_tier"] = [tier_of_area[a] for a in dead["AreaKey"]]

    combined = pd.concat([live, dead], ignore_index=True)
    combined = combined[combined["Searches"] > 0].copy()

    quality = np.clip(
        config.LEAD_QUALITY_BASE
        + np.array([config.LEAD_QUALITY_TIER_BONUS[t] for t in combined["_tier"]])
        + rng.normal(0.0, config.LEAD_QUALITY_SIGMA, len(combined)),
        0.02, 0.99,
    )
    combined["AvgLeadQualityScore"] = quality
    combined = combined.sort_values(["DateKey", "AreaKey", "ServiceKey"]).reset_index(drop=True)
    return combined


def forecaster_mape(day: dt.date) -> float:
    """The MAPE regime behind the drift incident, as a fraction."""
    deployed = config.MODELS[0][8]
    if day < deployed:
        return config.FORECASTER_MAPE_MATURE

    if day >= config.RETRAIN_FIX_DATE:
        elapsed = (day - config.RETRAIN_FIX_DATE).days
        if elapsed >= config.RETRAIN_RECOVERY_DAYS:
            return config.FORECASTER_MAPE_RECOVERED
        frac = elapsed / config.RETRAIN_RECOVERY_DAYS
        return (config.FORECASTER_MAPE_DRIFTED
                + (config.FORECASTER_MAPE_RECOVERED - config.FORECASTER_MAPE_DRIFTED) * frac)

    if day >= config.DRIFT_FULL_DATE:
        return config.FORECASTER_MAPE_DRIFTED

    if day >= config.DRIFT_ONSET_DATE:
        span = (config.DRIFT_FULL_DATE - config.DRIFT_ONSET_DATE).days
        frac = (day - config.DRIFT_ONSET_DATE).days / span
        return (config.FORECASTER_MAPE_MATURE
                + (config.FORECASTER_MAPE_DRIFTED - config.FORECASTER_MAPE_MATURE) * frac)

    age = (day - deployed).days
    if age >= config.FORECASTER_MAPE_MATURITY_DAYS:
        return config.FORECASTER_MAPE_MATURE
    frac = age / config.FORECASTER_MAPE_MATURITY_DAYS
    return (config.FORECASTER_MAPE_LAUNCH
            + (config.FORECASTER_MAPE_MATURE - config.FORECASTER_MAPE_LAUNCH) * frac)


def forecaster_training_age(day: dt.date) -> int:
    """Days since the model last saw fresh training data.

    Sawtooth under the weekly cadence, then a straight climb from the day the
    retrain job silently stops succeeding, then a reset when the fix lands.
    """
    if day >= config.RETRAIN_FIX_DATE:
        return (day - config.RETRAIN_FIX_DATE).days % config.TRAINING_AGE_SAWTOOTH_DAYS
    if day >= config.RETRAIN_SILENT_FAILURE_DATE:
        return (day - config.RETRAIN_SILENT_FAILURE_DATE).days
    return (day - config.MODELS[0][8]).days % config.TRAINING_AGE_SAWTOOTH_DAYS


def build_model_metrics(model_frame, days, daily_bookings, rng) -> pd.DataFrame:
    """Daily telemetry per model, including the demand_forecaster incident."""
    rows = []
    day_index = {d: i for i, d in enumerate(days)}

    for _, model in model_frame.iterrows():
        name = model["ModelName"]
        deployed = dt.date.fromisoformat(model["DeployedDate"])
        goal = float(model["MetricGoal"])
        direction = model["GoalDirection"]
        metric_name = model["PrimaryMetric"]
        live_days = [d for d in days if d >= deployed]
        if not live_days:
            continue
        span = max(len(live_days) - 1, 1)

        for offset, day in enumerate(live_days):
            progress = offset / span
            volume_factor = config.MODEL_PREDICTION_VOLUME_PER_BOOKING[name]
            volume = daily_bookings[day_index[day]] * volume_factor
            psi_low, psi_high = config.MODEL_PSI_BASELINE_OTHER
            psi = rng.uniform(psi_low, psi_high)
            null_pct = rng.uniform(*config.FEATURE_NULL_PCT_BASELINE)
            version = model["Version"]
            training_age = offset % config.TRAINING_AGE_SAWTOOTH_DAYS

            if name == "demand_forecaster":
                value = forecaster_mape(day) * 100.0
                value *= float(lognormal_factor(rng, config.FORECASTER_MAPE_NOISE_SIGMA, 1)[0])
                in_incident = (config.DRIFT_ONSET_DATE <= day < config.RETRAIN_FIX_DATE)
                if day >= config.PSI_CROSSING_DATE and day < config.RETRAIN_FIX_DATE:
                    psi = rng.uniform(*config.PSI_DRIFTED)
                elif config.DRIFT_ONSET_DATE <= day < config.PSI_CROSSING_DATE:
                    ramp = (day - config.DRIFT_ONSET_DATE).days / max(
                        (config.PSI_CROSSING_DATE - config.DRIFT_ONSET_DATE).days, 1)
                    psi = (config.PSI_BASELINE[1]
                           + (config.PSI_ALERT_THRESHOLD - config.PSI_BASELINE[1]) * ramp)
                else:
                    psi = rng.uniform(*config.PSI_BASELINE)
                if in_incident:
                    null_pct = rng.uniform(*config.FEATURE_NULL_PCT_INCIDENT)
                training_age = forecaster_training_age(day)
                if day >= config.RETRAIN_FIX_DATE:
                    version = config.FORECASTER_VERSION_AFTER_FIX

            elif name == "pro_match_ranker":
                value = (config.MATCH_NDCG_START
                         + (config.MATCH_NDCG_END - config.MATCH_NDCG_START) * progress
                         + rng.normal(0.0, 0.010))

            else:
                start, end, sigma = config.MODEL_HEALTH_ENVELOPE[name]
                value = start + (end - start) * progress + rng.normal(0.0, sigma)
                if name == "fraud_booking_detector" and seasonality.is_festival_window(day):
                    if "Diwali" in seasonality.window_names(day):
                        value -= config.FRAUD_DIWALI_PRECISION_DROP
                        volume *= config.FRAUD_DIWALI_VOLUME_UPLIFT

            if rng.random() < config.MODEL_BLIP_PROB:
                sign = -1.0 if direction == "HigherIsBetter" else 1.0
                value *= (1.0 + sign * config.MODEL_BLIP_MAGNITUDE)

            breach = int(value > goal) if direction == "LowerIsBetter" else int(value < goal)
            latency = (config.MODEL_LATENCY_P95_MS[name]
                       * float(lognormal_factor(rng, config.MODEL_LATENCY_SIGMA, 1)[0]))

            rows.append({
                "DateKey": date_key(day),
                "ModelKey": int(model["ModelKey"]),
                "MetricName": metric_name,
                "MetricValue": value,
                "MetricGoal": goal,
                "IsBreach": breach,
                "PSIDriftScore": psi,
                "PredictionVolume": int(max(round(volume), 0)),
                "P95LatencyMs": int(max(round(latency), 1)),
                "FeatureNullPct": null_pct,
                "TrainingDataAgeDays": int(training_age),
                "ModelVersion": version,
            })

    return pd.DataFrame.from_records(rows).sort_values(
        ["DateKey", "ModelKey"]).reset_index(drop=True)


def build_forecast_accuracy(bookings, area_frame, service_frame, days, rng) -> pd.DataFrame:
    """Per day, area and category: what was forecast against what happened."""
    deployed = config.MODELS[0][8]
    live_days = [d for d in days if d >= deployed]
    live_keys = np.array([date_key(d) for d in live_days])

    category_of_service = dict(zip(service_frame["ServiceKey"],
                                   service_frame["ServiceCategory"]))
    working = bookings[["DateKey", "AreaKey", "ServiceKey"]].copy()
    working["ServiceCategory"] = working["ServiceKey"].map(category_of_service)
    actual = (working[working["DateKey"].isin(set(live_keys))]
              .groupby(["DateKey", "AreaKey", "ServiceCategory"], sort=True)
              .size().reset_index(name="ActualJobs"))

    grid = pd.MultiIndex.from_product(
        [live_keys, area_frame["AreaKey"].to_numpy(), config.CATEGORY_ORDER],
        names=["DateKey", "AreaKey", "ServiceCategory"],
    ).to_frame(index=False)
    merged = grid.merge(actual, on=["DateKey", "AreaKey", "ServiceCategory"], how="left")
    merged["ActualJobs"] = merged["ActualJobs"].fillna(0).astype(int)

    key_to_date = {date_key(d): d for d in live_days}
    mape_target = merged["DateKey"].map(lambda k: forecaster_mape(key_to_date[k])).to_numpy()

    n = len(merged)
    actual_jobs = merged["ActualJobs"].to_numpy(dtype=float)
    # Relative error with the requested mean, signed, plus a small hot bias.
    ape = rng.gamma(shape=1.6, scale=mape_target / 1.6, size=n)
    sign = np.where(rng.random(n) < 0.5 + config.FORECAST_BIAS, 1.0, -1.0)
    forecast = np.maximum(actual_jobs * (1.0 + sign * ape), 0.0)

    zero_mask = actual_jobs == 0
    phantom = rng.random(n) < config.FORECAST_ZERO_ACTUAL_PROB
    forecast = np.where(
        zero_mask,
        np.where(phantom, rng.exponential(config.FORECAST_ZERO_ACTUAL_SCALE, n), 0.0),
        forecast,
    )
    forecast = np.round(forecast, config.FORECAST_ROUND_DP)

    keep = (actual_jobs > 0) | (forecast >= config.FORECAST_EMIT_MIN)
    merged = merged[keep].copy()
    forecast = forecast[keep]
    actual_jobs = actual_jobs[keep]

    abs_error = np.round(np.abs(forecast - actual_jobs), config.FORECAST_ROUND_DP)
    with np.errstate(divide="ignore", invalid="ignore"):
        ape_out = np.where(actual_jobs > 0, abs_error / actual_jobs, np.nan)

    merged["ForecastedJobs"] = forecast
    merged["AbsError"] = abs_error
    merged["APE"] = ape_out
    return merged.sort_values(["DateKey", "AreaKey", "ServiceCategory"]).reset_index(drop=True)


# ===========================================================================
# Orchestration
# ===========================================================================
def main() -> None:
    started = time.time()
    rng = np.random.default_rng(config.SEED)

    print("=" * 78)
    print("Seek My Service - synthetic data generation")
    print(f"seed={config.SEED}  window={config.DATE_START} .. {config.DATE_END}")
    print("=" * 78)

    days = seasonality.date_range(config.DATE_START, config.DATE_END)
    n_days = len(days)

    # ---- dimensions -------------------------------------------------------
    dim_date = build_dim_date(days)
    dim_service = build_dim_service()
    dim_area = build_dim_area()
    dim_model = build_dim_model()
    print(f"[1/9] dimensions built: {n_days} days, {len(dim_service)} services, "
          f"{len(dim_area)} areas, {len(dim_model)} models")

    # ---- demand -----------------------------------------------------------
    heavy_rain = np.array([
        rng.random() < seasonality.heavy_rain_probability(d) for d in days
    ])
    expected, month_keys, trend, uplift = solve_trend(days, rng)
    print(f"[2/9] trend solved: baseline {trend[0]:.0f} -> {trend[-1]:.0f} completed/month, "
          f"seasonal uplift {uplift.min():.2f}..{uplift.max():.2f}")

    bookings = build_booking_skeleton(days, expected, heavy_rain, rng)
    bookings = assign_area_and_service(bookings, dim_area, dim_service, rng)
    bookings = assign_timestamps(bookings, days, rng)
    print(f"[3/9] booking skeleton: {len(bookings):,} rows")

    strain = compute_strain(bookings, n_days)
    bookings["BookingStatus"] = draw_status(bookings, heavy_rain, strain, rng)
    completed_n = int((bookings["BookingStatus"] == "Completed").sum())
    print(f"[4/9] statuses drawn: {completed_n:,} completed "
          f"({completed_n / len(bookings):.1%})")

    # ---- supply -----------------------------------------------------------
    dim_pro = build_professionals(dim_area, rng)
    online, slots, tenure_mask = build_capacity_calendar(dim_pro, days, rng)
    pro_index, booked, forced = assign_professionals(
        bookings, dim_pro, dim_area, online, slots, days, rng)
    bookings["_ProIndex"] = pro_index
    bookings["ProKey"] = pro_index + 1
    print(f"[5/9] supply assigned: {len(dim_pro)} pros, "
          f"{int(online.sum()):,} online pro-days, {forced} surge slots opened")

    # ---- demand side ------------------------------------------------------
    customer_keys, is_first_booking, dim_customer = assign_customers(
        bookings, dim_area, days, rng)
    bookings["CustomerKey"] = customer_keys
    bookings["IsRepeatCustomer"] = (~is_first_booking).astype(int)
    print(f"[6/9] customers assigned: {len(dim_customer):,} customers, "
          f"repeat share {bookings['IsRepeatCustomer'].mean():.1%}")

    # ---- money and operations --------------------------------------------
    ops = build_financials_and_ops(bookings, dim_service, dim_area, dim_pro,
                                   days, heavy_rain, strain, rng)
    for key, value in ops.items():
        bookings[key] = value

    propensity_of_customer = dim_customer["_propensity"].to_numpy()
    churn_score = np.clip(
        config.CHURN_SCORE_BASE
        - config.CHURN_SCORE_PROPENSITY_WEIGHT * propensity_of_customer[customer_keys - 1]
        + rng.normal(0.0, config.CHURN_SCORE_SIGMA, len(bookings)),
        0.01, 0.99,
    )
    bookings["ChurnRiskScore"] = churn_score
    gmv = bookings["FinalAmountINR"].sum()
    print(f"[7/9] financials: GMV {gmv:,.0f} INR, "
          f"platform revenue {bookings['PlatformRevenueINR'].sum():,.0f} INR")

    # ---- derived dimension columns ---------------------------------------
    completed = bookings[bookings["IsCompleted"]]
    rated = bookings[bookings["HasRating"]]

    jobs_per_pro = completed.groupby("ProKey").size()
    rating_sum = rated.groupby("ProKey")["CustomerRating"].sum()
    rating_count = rated.groupby("ProKey")["CustomerRating"].size()
    tier_prior = dim_pro["SkillTier"].map(config.RATING_PRIOR_BY_TIER).to_numpy()
    r_sum = dim_pro["ProKey"].map(rating_sum).fillna(0.0).to_numpy()
    r_n = dim_pro["ProKey"].map(rating_count).fillna(0).to_numpy()
    dim_pro["AvgRating"] = ((r_sum + config.RATING_PRIOR_WEIGHT * tier_prior)
                            / (r_n + config.RATING_PRIOR_WEIGHT))
    dim_pro["LifetimeJobs"] = dim_pro["ProKey"].map(jobs_per_pro).fillna(0).astype(int)
    dim_pro["IsActive"] = [0 if c is not None else 1 for c in dim_pro["ChurnedDate"]]

    per_customer = bookings.groupby("CustomerKey")
    dim_customer["TotalBookings"] = dim_customer["CustomerKey"].map(
        per_customer.size()).fillna(0).astype(int)
    dim_customer["LifetimeValueINR"] = dim_customer["CustomerKey"].map(
        per_customer["FinalAmountINR"].sum()).fillna(0.0)
    first_dates = per_customer["Date"].min()
    last_dates = per_customer["Date"].max()
    dim_customer["FirstBookingDate"] = dim_customer["CustomerKey"].map(first_dates)
    dim_customer["LastBookingDate"] = dim_customer["CustomerKey"].map(last_dates)

    days_since_last = np.array([
        (config.TODAY - d).days for d in dim_customer["LastBookingDate"]
    ])
    total = dim_customer["TotalBookings"].to_numpy()
    segment = np.where(
        days_since_last > config.SEGMENT_DORMANT_DAYS, "Dormant",
        np.where(total >= config.SEGMENT_LOYAL_MIN_BOOKINGS, "Loyal",
                 np.where(total >= config.SEGMENT_REPEAT_MIN_BOOKINGS, "Repeat", "New")),
    )
    dim_customer["Segment"] = segment

    # ---- supply fact ------------------------------------------------------
    cancelled_by_pro = (bookings[bookings["BookingStatus"] == "CancelledByPro"]
                        .groupby(["_ProIndex", "DayIndex"]).size())
    duration_by_pro_day = (completed.groupby(["_ProIndex", "DayIndex"])["JobDurationMins"]
                           .sum())

    pro_idx_grid, day_idx_grid = np.meshgrid(
        np.arange(len(dim_pro)), np.arange(n_days), indexing="ij")
    flat_pro = pro_idx_grid.ravel()
    flat_day = day_idx_grid.ravel()
    flat_tenure = tenure_mask.ravel()
    flat_online = online.ravel()
    flat_slots = slots.ravel()
    flat_booked = booked.ravel()

    keep = flat_tenure
    total_tenured_rows = int(keep.sum())
    if total_tenured_rows > config.PRO_CAPACITY_ROW_CAP:
        keep = keep & (flat_online | (flat_booked > 0))

    flat_pro = flat_pro[keep]
    flat_day = flat_day[keep]
    flat_online = flat_online[keep]
    flat_slots = flat_slots[keep]
    flat_booked = flat_booked[keep]

    duration_lookup = duration_by_pro_day.to_dict()
    cancel_lookup = cancelled_by_pro.to_dict()
    job_minutes = np.array([duration_lookup.get((p, d), 0)
                            for p, d in zip(flat_pro, flat_day)], dtype=float)
    pro_cancels = np.array([cancel_lookup.get((p, d), 0)
                            for p, d in zip(flat_pro, flat_day)], dtype=int)

    n_rows = len(flat_pro)
    travel = flat_booked * rng.integers(*config.PRO_TRAVEL_MINS_PER_JOB, size=n_rows)
    idle = np.where(flat_online,
                    rng.integers(*config.PRO_IDLE_MINS_PER_ONLINE_DAY, size=n_rows), 0)
    hours_logged = (job_minutes + travel + idle).astype(int)
    accepted = (flat_booked - pro_cancels).clip(min=0)
    rejected = (rng.poisson(config.PRO_REJECTED_JOBS_LAMBDA, size=n_rows)
                * flat_online.astype(int)) + pro_cancels

    fact_capacity = pd.DataFrame({
        "DateKey": np.array([date_key(days[d]) for d in flat_day]),
        "ProKey": flat_pro + 1,
        "AreaKey": dim_pro["HomeAreaKey"].to_numpy()[flat_pro],
        "SlotsAvailable": flat_slots,
        "SlotsBooked": flat_booked,
        "IsOnline": flat_online.astype(int),
        "HoursLoggedMins": hours_logged,
        "AcceptedJobs": accepted,
        "RejectedJobs": rejected,
    }).sort_values(["DateKey", "ProKey"]).reset_index(drop=True)
    print(f"[8/9] capacity fact: {len(fact_capacity):,} rows "
          f"(from {total_tenured_rows:,} tenured pro-days)")

    # ---- funnel, telemetry, forecast accuracy ----------------------------
    fact_leads = build_leads(bookings, dim_area, dim_service, days, rng)
    daily_bookings = np.bincount(bookings["DayIndex"].to_numpy(), minlength=n_days)
    fact_metrics = build_model_metrics(dim_model, days, daily_bookings, rng)
    fact_forecast = build_forecast_accuracy(bookings, dim_area, dim_service, days, rng)
    print(f"[9/9] downstream facts: {len(fact_leads):,} lead rows, "
          f"{len(fact_metrics):,} metric rows, {len(fact_forecast):,} forecast rows")

    # ---- write ------------------------------------------------------------
    written = []
    written.append(("dim_date", *write_table("dim_date", {
        "DateKey": s_int(dim_date["DateKey"]),
        "Date": s_txt(dim_date["Date"]),
        "Year": s_int(dim_date["Year"]),
        "Quarter": s_txt(dim_date["Quarter"]),
        "MonthNo": s_int(dim_date["MonthNo"]),
        "MonthName": s_txt(dim_date["MonthName"]),
        "MonthYear": s_txt(dim_date["MonthYear"]),
        "MonthYearSort": s_int(dim_date["MonthYearSort"]),
        "WeekNo": s_int(dim_date["WeekNo"]),
        "DayName": s_txt(dim_date["DayName"]),
        "DayOfWeekNo": s_int(dim_date["DayOfWeekNo"]),
        "IsWeekend": s_int(dim_date["IsWeekend"]),
        "IsMonsoon": s_int(dim_date["IsMonsoon"]),
        "IsFestivalWindow": s_int(dim_date["IsFestivalWindow"]),
        "FestivalName": s_txt(dim_date["FestivalName"]),
        "IsMonthEnd": s_int(dim_date["IsMonthEnd"]),
        "FiscalYear": s_txt(dim_date["FiscalYear"]),
        "FiscalQuarter": s_txt(dim_date["FiscalQuarter"]),
        "IsHoliday": s_int(dim_date["IsHoliday"]),
        "DaysFromToday": s_int(dim_date["DaysFromToday"]),
    })))

    written.append(("dim_service", *write_table("dim_service", {
        "ServiceKey": s_int(dim_service["ServiceKey"]),
        "ServiceCategory": s_txt(dim_service["ServiceCategory"]),
        "ServiceName": s_txt(dim_service["ServiceName"]),
        "BasePriceINR": s_int(dim_service["BasePriceINR"]),
        "AvgDurationMins": s_int(dim_service["AvgDurationMins"]),
        "IsEmergency": s_int(dim_service["IsEmergency"]),
        "SkillTier": s_txt(dim_service["SkillTier"]),
        "MaterialCostPct": s_dec(dim_service["MaterialCostPct"], 1),
        "CommissionPct": s_dec(dim_service["CommissionPct"], 1),
        "ServiceSortOrder": s_int(dim_service["ServiceSortOrder"]),
    })))

    written.append(("dim_area", *write_table("dim_area", {
        "AreaKey": s_int(dim_area["AreaKey"]),
        "AreaName": s_txt(dim_area["AreaName"]),
        "Zone": s_txt(dim_area["Zone"]),
        "Pincode": s_txt(dim_area["Pincode"]),
        "Latitude": s_dec(dim_area["Latitude"], 4),
        "Longitude": s_dec(dim_area["Longitude"], 4),
        "DemandTier": s_txt(dim_area["DemandTier"]),
        "IncomeBand": s_txt(dim_area["IncomeBand"]),
        "AreaSortOrder": s_int(dim_area["AreaSortOrder"]),
    })))

    written.append(("dim_professional", *write_table("dim_professional", {
        "ProKey": s_int(dim_pro["ProKey"]),
        "ProName": s_txt(dim_pro["ProName"]),
        "PrimaryServiceCategory": s_txt(dim_pro["PrimaryServiceCategory"]),
        "HomeAreaKey": s_int(dim_pro["HomeAreaKey"]),
        "JoinDate": s_txt([d.isoformat() for d in dim_pro["JoinDate"]]),
        "SkillTier": s_txt(dim_pro["SkillTier"]),
        "IsBackgroundVerified": s_int(dim_pro["IsBackgroundVerified"]),
        "IsActive": s_int(dim_pro["IsActive"]),
        "AvgRating": s_dec(dim_pro["AvgRating"], 2),
        "LifetimeJobs": s_int(dim_pro["LifetimeJobs"]),
        "LanguagesSpoken": s_txt(dim_pro["LanguagesSpoken"]),
        "OnboardingChannel": s_txt(dim_pro["OnboardingChannel"]),
        "ChurnedDate": s_txt([config.BLANK if c is None else c.isoformat()
                              for c in dim_pro["ChurnedDate"]]),
    })))

    written.append(("dim_customer", *write_table("dim_customer", {
        "CustomerKey": s_int(dim_customer["CustomerKey"]),
        "SignupDate": s_txt([d.isoformat() for d in dim_customer["SignupDate"]]),
        "AreaKey": s_int(dim_customer["AreaKey"]),
        "AcquisitionChannel": s_txt(dim_customer["AcquisitionChannel"]),
        "Segment": s_txt(dim_customer["Segment"]),
        "IsAppUser": s_int(dim_customer["IsAppUser"]),
        "PreferredLanguage": s_txt(dim_customer["PreferredLanguage"]),
        "LifetimeValueINR": s_dec(dim_customer["LifetimeValueINR"], 2),
        "FirstBookingDate": s_txt([d.isoformat() for d in dim_customer["FirstBookingDate"]]),
        "LastBookingDate": s_txt([d.isoformat() for d in dim_customer["LastBookingDate"]]),
        "TotalBookings": s_int(dim_customer["TotalBookings"]),
    })))

    written.append(("dim_model", *write_table("dim_model", {
        "ModelKey": s_int(dim_model["ModelKey"]),
        "ModelName": s_txt(dim_model["ModelName"]),
        "ModelType": s_txt(dim_model["ModelType"]),
        "BusinessPurpose": s_txt(dim_model["BusinessPurpose"]),
        "Framework": s_txt(dim_model["Framework"]),
        "Algorithm": s_txt(dim_model["Algorithm"]),
        "PrimaryMetric": s_txt(dim_model["PrimaryMetric"]),
        "MetricGoal": s_dec(dim_model["MetricGoal"], 2),
        "GoalDirection": s_txt(dim_model["GoalDirection"]),
        "DeployedDate": s_txt(dim_model["DeployedDate"]),
        "Version": s_txt(dim_model["Version"]),
        "RefreshCadence": s_txt(dim_model["RefreshCadence"]),
        "OwnerTeam": s_txt(dim_model["OwnerTeam"]),
        "IsBusinessCritical": s_int(dim_model["IsBusinessCritical"]),
    })))

    completed_mask = bookings["IsCompleted"].to_numpy()
    rating_mask = bookings["HasRating"].to_numpy()
    written.append(("fact_bookings", *write_table("fact_bookings", {
        "BookingID": s_txt(bookings["BookingID"]),
        "DateKey": s_int(bookings["DateKey"]),
        "BookingTimestamp": s_txt(bookings["BookingTimestamp"]),
        "CustomerKey": s_int(bookings["CustomerKey"]),
        "ProKey": s_int(bookings["ProKey"]),
        "ServiceKey": s_int(bookings["ServiceKey"]),
        "AreaKey": s_int(bookings["AreaKey"]),
        "Channel": s_txt(bookings["Channel"]),
        "BookingStatus": s_txt(bookings["BookingStatus"]),
        "QuotedAmountINR": s_dec(bookings["QuotedAmountINR"], 2),
        "FinalAmountINR": s_dec(bookings["FinalAmountINR"], 2),
        "DiscountINR": s_dec(bookings["DiscountINR"], 2),
        "CommissionPct": s_dec(bookings["CommissionPct"], 1),
        "PlatformRevenueINR": s_dec(bookings["PlatformRevenueINR"], 2),
        "MaterialCostINR": s_dec(bookings["MaterialCostINR"], 2),
        "PaymentMode": s_txt(bookings["PaymentMode"]),
        "TimeToAssignMins": s_int(bookings["TimeToAssignMins"]),
        "ResponseTimeMins": s_int(bookings["ResponseTimeMins"]),
        "JobDurationMins": s_int(bookings["JobDurationMins"], mask=completed_mask),
        "SLAMetFlag": s_int(bookings["SLAMetFlag"], mask=completed_mask),
        "CustomerRating": s_int(bookings["CustomerRating"], mask=rating_mask),
        "ReviewSentiment": s_txt(bookings["ReviewSentiment"], mask=rating_mask),
        "IsRepeatCustomer": s_int(bookings["IsRepeatCustomer"]),
        "PredictedPriceINR": s_int(bookings["PredictedPriceINR"]),
        "PredictedETAMins": s_int(bookings["PredictedETAMins"]),
        "ActualETAMins": s_int(bookings["ActualETAMins"], mask=completed_mask),
        "MatchScore": s_dec(bookings["MatchScore"], config.SCORE_ROUND_DP),
        "FraudScore": s_dec(bookings["FraudScore"], config.SCORE_ROUND_DP),
        "ChurnRiskScore": s_dec(bookings["ChurnRiskScore"], config.SCORE_ROUND_DP),
        "IsFirstTimeFix": s_int(bookings["IsFirstTimeFix"], mask=completed_mask),
        "ReopenedWithin7Days": s_int(bookings["ReopenedWithin7Days"], mask=completed_mask),
    })))

    written.append(("fact_pro_capacity", *write_table("fact_pro_capacity", {
        "DateKey": s_int(fact_capacity["DateKey"]),
        "ProKey": s_int(fact_capacity["ProKey"]),
        "AreaKey": s_int(fact_capacity["AreaKey"]),
        "SlotsAvailable": s_int(fact_capacity["SlotsAvailable"]),
        "SlotsBooked": s_int(fact_capacity["SlotsBooked"]),
        "IsOnline": s_int(fact_capacity["IsOnline"]),
        "HoursLoggedMins": s_int(fact_capacity["HoursLoggedMins"]),
        "AcceptedJobs": s_int(fact_capacity["AcceptedJobs"]),
        "RejectedJobs": s_int(fact_capacity["RejectedJobs"]),
    })))

    written.append(("fact_leads", *write_table("fact_leads", {
        "DateKey": s_int(fact_leads["DateKey"]),
        "AreaKey": s_int(fact_leads["AreaKey"]),
        "ServiceKey": s_int(fact_leads["ServiceKey"]),
        "Searches": s_int(fact_leads["Searches"]),
        "Leads": s_int(fact_leads["Leads"]),
        "QuotesSent": s_int(fact_leads["QuotesSent"]),
        "Bookings": s_int(fact_leads["Bookings"]),
        "AvgLeadQualityScore": s_dec(fact_leads["AvgLeadQualityScore"], 3),
    })))

    written.append(("fact_model_metrics", *write_table("fact_model_metrics", {
        "DateKey": s_int(fact_metrics["DateKey"]),
        "ModelKey": s_int(fact_metrics["ModelKey"]),
        "MetricName": s_txt(fact_metrics["MetricName"]),
        "MetricValue": s_dec(fact_metrics["MetricValue"], 4),
        "MetricGoal": s_dec(fact_metrics["MetricGoal"], 2),
        "IsBreach": s_int(fact_metrics["IsBreach"]),
        "PSIDriftScore": s_dec(fact_metrics["PSIDriftScore"], 4),
        "PredictionVolume": s_int(fact_metrics["PredictionVolume"]),
        "P95LatencyMs": s_int(fact_metrics["P95LatencyMs"]),
        "FeatureNullPct": s_dec(fact_metrics["FeatureNullPct"], 3),
        "TrainingDataAgeDays": s_int(fact_metrics["TrainingDataAgeDays"]),
        "ModelVersion": s_txt(fact_metrics["ModelVersion"]),
    })))

    ape_mask = fact_forecast["ActualJobs"].to_numpy() > 0
    written.append(("fact_forecast_accuracy", *write_table("fact_forecast_accuracy", {
        "DateKey": s_int(fact_forecast["DateKey"]),
        "AreaKey": s_int(fact_forecast["AreaKey"]),
        "ServiceCategory": s_txt(fact_forecast["ServiceCategory"]),
        "ForecastedJobs": s_dec(fact_forecast["ForecastedJobs"], config.FORECAST_ROUND_DP),
        "ActualJobs": s_int(fact_forecast["ActualJobs"]),
        "AbsError": s_dec(fact_forecast["AbsError"], config.FORECAST_ROUND_DP),
        "APE": s_dec(fact_forecast["APE"], config.APE_ROUND_DP, mask=ape_mask),
    })))

    print("-" * 78)
    print(f"{'table':<26}{'rows':>12}{'size':>14}")
    print("-" * 78)
    for name, rows, size in written:
        print(f"{name:<26}{rows:>12,}{size / 1024:>12,.0f} KB")
    print("-" * 78)
    print(f"done in {time.time() - started:.1f}s -> {config.DATA_DIR}")


if __name__ == "__main__":
    main()
