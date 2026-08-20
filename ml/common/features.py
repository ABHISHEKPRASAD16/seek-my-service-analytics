"""
Shared feature engineering for the three services.

Calendar features come from ``generator.seasonality`` rather than being
re-derived here. That matters: the monsoon and festival flags the forecaster
trains on are then literally the same definition that shaped the data, so when
the June 2026 regime shift breaks the model it breaks for an honest reason -
the relationship between those features and demand changed - rather than
because two modules disagreed about when the monsoon starts.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from generator import config, seasonality  # noqa: E402
from ml.common import io  # noqa: E402

# Lags and rolling windows for the demand panel, in days.
FORECAST_LAGS = (1, 2, 3, 7, 14, 21, 28)
FORECAST_ROLLING = (7, 14, 28)
FORECAST_HORIZON = 7

SKILL_TIER_ORDER = {"Bronze": 0, "Silver": 1, "Gold": 2, "Platinum": 3}
DEMAND_TIER_ORDER = {"C": 0, "B": 1, "A": 2}
INCOME_BAND_ORDER = {"Value": 0, "Mid": 1, "Upper-Mid": 2, "Premium": 3}


# ===========================================================================
# Calendar
# ===========================================================================
def calendar_frame(dates: Sequence[dt.date]) -> pd.DataFrame:
    """Per-date calendar features, independent of any category."""
    records = []
    for day in dates:
        records.append({
            "Date": pd.Timestamp(day),
            "DayOfWeek": day.weekday(),
            "IsWeekend": int(seasonality.is_weekend(day)),
            "MonthNo": day.month,
            "WeekOfYear": day.isocalendar().week,
            "IsMonsoon": int(seasonality.is_monsoon(day)),
            "IsFestivalWindow": int(seasonality.is_festival_window(day)),
            "IsMonthEnd": int(seasonality.is_month_end(day)),
            "IsHoliday": int(seasonality.is_holiday(day)),
        })
    return pd.DataFrame.from_records(records)


def seasonal_multiplier_column(dates: Sequence[pd.Timestamp],
                               categories: Sequence[str]) -> np.ndarray:
    """The configured seasonal multiplier for each (date, category) pair.

    This is the single most important feature in the forecaster and the one the
    drift incident is about: when the retrain stops, the model keeps using
    coefficients fitted against last season's relationship between this feature
    and demand.
    """
    cache: Dict[Tuple[dt.date, str], float] = {}
    out = np.empty(len(dates), dtype=float)
    for i, (stamp, category) in enumerate(zip(dates, categories)):
        day = pd.Timestamp(stamp).date()
        key = (day, category)
        value = cache.get(key)
        if value is None:
            value = seasonality.category_seasonal_multiplier(day, category)
            cache[key] = value
        out[i] = value
    return out


# ===========================================================================
# Forecasting: daily demand panel
# ===========================================================================
def build_demand_panel(bookings: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Dense day x area x category panel of booking counts.

    Dense matters. If only days with bookings are kept, a lag of 7 silently
    means "seven rows ago" instead of "seven days ago", and every lag feature
    becomes wrong in exactly the cells where demand is thin.
    """
    if bookings is None:
        bookings = io.load_bookings()

    counts = (bookings.groupby(["BookingDate", "AreaKey", "ServiceCategory"])
              .size().rename("Jobs").reset_index())

    all_dates = pd.date_range(config.DATE_START, config.DATE_END, freq="D")
    areas = io.load_table("dim_area")["AreaKey"].to_numpy()
    categories = config.CATEGORY_ORDER

    grid = pd.MultiIndex.from_product(
        [all_dates, areas, categories],
        names=["BookingDate", "AreaKey", "ServiceCategory"],
    ).to_frame(index=False)

    panel = grid.merge(counts, on=["BookingDate", "AreaKey", "ServiceCategory"],
                       how="left")
    panel["Jobs"] = panel["Jobs"].fillna(0).astype(int)
    return panel.sort_values(["AreaKey", "ServiceCategory", "BookingDate"]).reset_index(drop=True)


def add_forecast_features(panel: pd.DataFrame,
                          horizon: int = FORECAST_HORIZON) -> pd.DataFrame:
    """Lag, rolling and calendar features, plus the forward-looking target.

    The target is the total jobs over the next ``horizon`` days, which is the
    question supply planning actually asks: how many technicians should be in
    Whitefield next week.

    Every lag and rolling feature is shifted by one day before use, so no row
    can see its own outcome. Leakage in a time-series model is the mistake that
    makes an offline metric look wonderful and a production model useless.
    """
    frame = panel.copy()
    group = frame.groupby(["AreaKey", "ServiceCategory"], sort=False)["Jobs"]

    for lag in FORECAST_LAGS:
        frame[f"Lag{lag}"] = group.shift(lag)

    shifted = group.shift(1)
    frame["_shifted"] = shifted
    by_cell = frame.groupby(["AreaKey", "ServiceCategory"], sort=False)["_shifted"]
    for window in FORECAST_ROLLING:
        frame[f"Roll{window}Mean"] = by_cell.transform(
            lambda s, w=window: s.rolling(w, min_periods=1).mean())
        frame[f"Roll{window}Max"] = by_cell.transform(
            lambda s, w=window: s.rolling(w, min_periods=1).max())
    frame["Roll28Std"] = by_cell.transform(
        lambda s: s.rolling(28, min_periods=2).std())
    frame = frame.drop(columns="_shifted")

    # Momentum: is this cell running hotter than its own recent normal?
    frame["TrendRatio"] = np.where(
        frame["Roll28Mean"] > 0, frame["Roll7Mean"] / frame["Roll28Mean"], 1.0)

    # Target: total demand over the next `horizon` days.
    reversed_sum = (frame[::-1]
                    .groupby(["AreaKey", "ServiceCategory"], sort=False)["Jobs"]
                    .transform(lambda s: s.shift(1).rolling(horizon, min_periods=horizon).sum()))
    frame["TargetNext7"] = reversed_sum[::-1]

    calendar = calendar_frame(
        [d.date() for d in pd.to_datetime(frame["BookingDate"].unique())])
    frame = frame.merge(calendar, left_on="BookingDate", right_on="Date", how="left")
    frame = frame.drop(columns="Date")

    frame["SeasonalMultiplier"] = seasonal_multiplier_column(
        frame["BookingDate"].to_numpy(), frame["ServiceCategory"].to_numpy())

    # The seasonal multiplier averaged across the horizon we are predicting.
    # The calendar for next week is known today, so this is legitimate.
    horizon_mult = np.zeros(len(frame))
    unique_pairs = frame[["BookingDate", "ServiceCategory"]].drop_duplicates()
    lookup: Dict[Tuple[pd.Timestamp, str], float] = {}
    for stamp, category in unique_pairs.itertuples(index=False):
        base = pd.Timestamp(stamp).date()
        values = [
            seasonality.category_seasonal_multiplier(base + dt.timedelta(days=k), category)
            for k in range(1, horizon + 1)
        ]
        lookup[(stamp, category)] = float(np.mean(values))
    for i, (stamp, category) in enumerate(
            zip(frame["BookingDate"], frame["ServiceCategory"])):
        horizon_mult[i] = lookup[(stamp, category)]
    frame["HorizonSeasonalMultiplier"] = horizon_mult

    areas = io.load_table("dim_area")[["AreaKey", "DemandTier", "IncomeBand", "Zone"]]
    frame = frame.merge(areas, on="AreaKey", how="left")
    frame["DemandTierOrd"] = frame["DemandTier"].map(DEMAND_TIER_ORDER)
    frame["IncomeBandOrd"] = frame["IncomeBand"].map(INCOME_BAND_ORDER)
    frame["CategoryCode"] = frame["ServiceCategory"].map(
        {c: i for i, c in enumerate(config.CATEGORY_ORDER)})

    return frame


def forecast_feature_columns() -> List[str]:
    """Feature order, fixed. Training and inference must agree exactly."""
    columns = [f"Lag{lag}" for lag in FORECAST_LAGS]
    for window in FORECAST_ROLLING:
        columns += [f"Roll{window}Mean", f"Roll{window}Max"]
    columns += [
        "Roll28Std", "TrendRatio",
        "DayOfWeek", "IsWeekend", "MonthNo", "WeekOfYear",
        "IsMonsoon", "IsFestivalWindow", "IsMonthEnd", "IsHoliday",
        "SeasonalMultiplier", "HorizonSeasonalMultiplier",
        "DemandTierOrd", "IncomeBandOrd", "CategoryCode", "AreaKey",
    ]
    return columns


# ===========================================================================
# Matching: candidate technicians for a job
# ===========================================================================
def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km. Vectorised over numpy arrays."""
    radius = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return radius * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def build_pro_day_state() -> pd.DataFrame:
    """Per technician per day: load, acceptance and rolling recent behaviour.

    These are the features a matching service genuinely has at dispatch time.
    """
    capacity = io.load_capacity()
    capacity = capacity.sort_values(["ProKey", "Date"])
    grouped = capacity.groupby("ProKey", sort=False)

    capacity["LoadRatio"] = np.where(
        capacity["SlotsAvailable"] > 0,
        capacity["SlotsBooked"] / capacity["SlotsAvailable"], 0.0)
    offered = capacity["AcceptedJobs"] + capacity["RejectedJobs"]
    capacity["DayAcceptRate"] = np.where(offered > 0,
                                         capacity["AcceptedJobs"] / offered, np.nan)

    # Shift by one day: at dispatch time you know yesterday, not today.
    capacity["RecentAcceptRate"] = (
        grouped["DayAcceptRate"].transform(
            lambda s: s.shift(1).rolling(28, min_periods=1).mean()))
    capacity["RecentJobs28"] = (
        grouped["SlotsBooked"].transform(
            lambda s: s.shift(1).rolling(28, min_periods=1).sum()))
    capacity["RecentAcceptRate"] = capacity["RecentAcceptRate"].fillna(0.5)
    capacity["RecentJobs28"] = capacity["RecentJobs28"].fillna(0.0)

    return capacity[["ProKey", "Date", "DateKey", "SlotsAvailable", "SlotsBooked",
                     "LoadRatio", "RecentAcceptRate", "RecentJobs28", "IsOnline"]]


def build_match_dataset(n_bookings: int = 12_000,
                        n_candidates: int = 8,
                        seed: int = config.SEED) -> pd.DataFrame:
    """One row per (booking, candidate technician), labelled 1 for the chosen one.

    A learning-to-rank dataset needs negatives, and the fact table only records
    who won. Candidates are drawn from technicians who were genuinely online
    with a free slot that day - the set dispatch would actually have chosen
    from - so the negatives are plausible rather than absurd.
    """
    rng = np.random.default_rng(seed)

    bookings = io.load_bookings()
    pros = io.load_professionals()
    areas = io.load_table("dim_area").set_index("AreaKey")
    pro_state = build_pro_day_state()

    sample = bookings.sample(n=min(n_bookings, len(bookings)), random_state=seed)
    sample = sample.sort_values("BookingTimestamp")

    online = pro_state[pro_state["IsOnline"] == 1]
    by_date: Dict[int, np.ndarray] = {
        key: group["ProKey"].to_numpy()
        for key, group in online.groupby("DateKey", sort=False)
    }
    # A plain dict keyed by (pro, day). A MultiIndex .loc here would be correct
    # and about a hundred times slower across ~100k candidate lookups.
    state_map: Dict[Tuple[int, int], Tuple[float, float, float, int]] = {
        (int(row.ProKey), int(row.DateKey)):
            (float(row.LoadRatio), float(row.RecentAcceptRate),
             float(row.RecentJobs28), int(row.SlotsAvailable))
        for row in pro_state.itertuples(index=False)
    }

    pro_lookup = pros.set_index("ProKey")
    pro_area = pro_lookup["HomeAreaKey"].to_dict()
    pro_tier = pro_lookup["SkillTier"].to_dict()
    pro_rating = pro_lookup["AvgRating"].to_dict()
    pro_category = pro_lookup["PrimaryServiceCategory"].to_dict()
    pro_verified = pro_lookup["IsBackgroundVerified"].to_dict()
    pro_jobs = pro_lookup["LifetimeJobs"].to_dict()

    area_lat = areas["Latitude"].to_dict()
    area_lon = areas["Longitude"].to_dict()
    area_zone = areas["Zone"].to_dict()

    rows = []
    for group_id, booking in enumerate(sample.itertuples(index=False)):
        date_key = booking.DateKey
        pool = by_date.get(date_key)
        if pool is None or len(pool) <= 1:
            continue
        chosen = booking.ProKey
        others = pool[pool != chosen]
        if len(others) == 0:
            continue
        take = min(n_candidates - 1, len(others))
        negatives = rng.choice(others, size=take, replace=False)
        candidates = np.concatenate([[chosen], negatives])

        for pro_key in candidates:
            pro_key = int(pro_key)
            state = state_map.get((pro_key, int(date_key)))
            if state is None:
                continue
            load_ratio, recent_accept, recent_jobs, slots_available = state
            home = pro_area[pro_key]
            rows.append({
                "GroupId": group_id,
                "ProKey": pro_key,
                "Label": int(pro_key == chosen),
                "DistanceKm": float(haversine_km(
                    area_lat[home], area_lon[home],
                    area_lat[booking.AreaKey], area_lon[booking.AreaKey])),
                "SameArea": int(home == booking.AreaKey),
                "SameZone": int(area_zone[home] == area_zone[booking.AreaKey]),
                "CategoryMatch": int(pro_category[pro_key] == booking.ServiceCategory),
                "SkillTierOrd": SKILL_TIER_ORDER[pro_tier[pro_key]],
                "ProRating": float(pro_rating[pro_key]),
                "IsVerified": int(pro_verified[pro_key]),
                "LifetimeJobs": int(pro_jobs[pro_key]),
                "LoadRatio": load_ratio,
                "RecentAcceptRate": recent_accept,
                "RecentJobs28": recent_jobs,
                "SlotsAvailable": slots_available,
                "IsEmergency": int(booking.IsEmergency),
            })

    return pd.DataFrame.from_records(rows)


def match_feature_columns() -> List[str]:
    return [
        "DistanceKm", "SameArea", "SameZone", "CategoryMatch", "SkillTierOrd",
        "ProRating", "IsVerified", "LifetimeJobs", "LoadRatio",
        "RecentAcceptRate", "RecentJobs28", "SlotsAvailable", "IsEmergency",
    ]


# ===========================================================================
# Pricing
# ===========================================================================
def build_pricing_dataset(bookings: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Per-booking features for the quantile price model and the accept model.

    Both targets live on the same frame: ``FinalAmountINR`` for the price band
    and whether the booking completed for the accept probability.
    """
    if bookings is None:
        bookings = io.load_bookings()

    frame = bookings.copy()
    frame["SeasonalMultiplier"] = seasonal_multiplier_column(
        frame["BookingDate"].to_numpy(), frame["ServiceCategory"].to_numpy())

    calendar = calendar_frame(
        [d.date() for d in pd.to_datetime(frame["BookingDate"].unique())])
    frame = frame.merge(calendar, left_on="BookingDate", right_on="Date", how="left")
    frame = frame.drop(columns="Date")

    frame["DemandTierOrd"] = frame["DemandTier"].map(DEMAND_TIER_ORDER)
    frame["IncomeBandOrd"] = frame["IncomeBand"].map(INCOME_BAND_ORDER)
    frame["CategoryCode"] = frame["ServiceCategory"].map(
        {c: i for i, c in enumerate(config.CATEGORY_ORDER)})
    frame["LogBasePrice"] = np.log1p(frame["BasePriceINR"])
    frame["QuoteToBaseRatio"] = np.where(
        frame["BasePriceINR"] > 0,
        frame["QuotedAmountINR"] / frame["BasePriceINR"], 1.0)
    frame["DiscountPct"] = np.where(
        frame["QuotedAmountINR"] > 0,
        frame["DiscountINR"] / frame["QuotedAmountINR"], 0.0)
    frame["Accepted"] = (frame["BookingStatus"] == "Completed").astype(int)
    frame["BookingHour"] = frame["BookingTimestamp"].dt.hour
    frame = frame.merge(area_load_features(frame), on=["AreaKey", "BookingDate"],
                        how="left")
    frame["AreaStrain"] = frame["AreaStrain"].fillna(1.0)
    frame["AreaVolume7"] = frame["AreaVolume7"].fillna(0.0)

    return frame


def area_load_features(bookings: pd.DataFrame) -> pd.DataFrame:
    """Per area per day: recent booking load, and load relative to its own norm.

    Cancellations and no-shows in this marketplace track operational pressure,
    not price, so an accept-probability model with no load feature is blind to
    most of what actually drives its target.

    Both windows are shifted a day before use. At quote time you know how busy
    last week was; you do not know how busy today will turn out.
    """
    daily = (bookings.groupby(["AreaKey", "BookingDate"]).size()
             .rename("Volume").reset_index()
             .sort_values(["AreaKey", "BookingDate"]))
    grouped = daily.groupby("AreaKey", sort=False)["Volume"]
    shifted = grouped.shift(1)
    daily["_shifted"] = shifted
    by_area = daily.groupby("AreaKey", sort=False)["_shifted"]
    daily["AreaVolume7"] = by_area.transform(
        lambda s: s.rolling(7, min_periods=1).mean())
    daily["AreaVolume28"] = by_area.transform(
        lambda s: s.rolling(28, min_periods=1).mean())
    daily["AreaStrain"] = np.where(
        daily["AreaVolume28"] > 0, daily["AreaVolume7"] / daily["AreaVolume28"], 1.0)
    return daily[["AreaKey", "BookingDate", "AreaVolume7", "AreaStrain"]]


def pricing_feature_columns() -> List[str]:
    """Features for the price band. Deliberately excludes the quote itself."""
    return [
        "ServiceKey", "CategoryCode", "BasePriceINR", "LogBasePrice",
        "AvgDurationMins", "IsEmergency", "MaterialCostPct",
        "AreaKey", "DemandTierOrd", "IncomeBandOrd",
        "SeasonalMultiplier", "IsWeekend", "IsMonsoon", "IsFestivalWindow",
        "IsMonthEnd", "MonthNo", "DayOfWeek", "BookingHour",
    ]


def accept_feature_columns() -> List[str]:
    """Features for accept probability.

    Here the quote IS the point, and so is operational load: a job booked into
    an area already running hot is measurably likelier to fall over.
    """
    return pricing_feature_columns() + [
        "QuoteToBaseRatio", "DiscountPct", "AreaStrain", "AreaVolume7",
    ]
