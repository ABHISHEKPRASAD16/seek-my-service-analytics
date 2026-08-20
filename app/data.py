"""
Data access for the dashboard.

Every load is cached, so the ~24 MB of CSV is read once per session and every
slicer interaction afterwards is a pandas filter rather than a disk read.

The derived frames here mirror the DAX measures in ``powerbi/measures.dax``.
Where a definition exists in both places it is deliberately the same definition
- "capacity strain" means the same thing in this app and in the Power BI model,
because two dashboards disagreeing about a number is worse than either of them
being slightly wrong.
"""

from __future__ import annotations

import datetime as dt
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import streamlit as st

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from generator import config  # noqa: E402

DATA_DIR = config.DATA_DIR
STRAIN_WINDOW = config.STRAIN_TRAILING_DAYS
SLA_TARGET = 0.90
PSI_THRESHOLD = config.PSI_ALERT_THRESHOLD


def data_is_present() -> bool:
    return all((DATA_DIR / f"{t}.csv").exists() for t in config.TABLES)


# Below this share of unique values, a text column is stored as a category.
CATEGORY_MAX_RATIO = 0.5


def compact(frame: pd.DataFrame) -> pd.DataFrame:
    """Shrink a frame in place: narrow integers, categorical text.

    This is not premature optimisation. The capacity frame is 324,435 rows and
    measured 176 MB, of which 141 MB was text - columns like SkillTier (four
    distinct values) and Zone (five) stored as a full Python string on every
    single row. Category dtype stores the distinct values once and an integer
    code per row.

    That matters because the deployment target has roughly 1 GB of memory. At
    603 MB peak the app would probably have survived; "probably" is not a good
    property for the thing a recruiter clicks.

    Floats are deliberately left alone. Downcasting them to float32 would save
    a little and risk money arithmetic: GMV sums to nine significant figures,
    and float32 carries about seven.
    """
    for column in frame.columns:
        values = frame[column]
        if pd.api.types.is_integer_dtype(values):
            frame[column] = pd.to_numeric(values, downcast="integer")
        elif values.dtype == object:
            distinct = values.nunique(dropna=False)
            if distinct and distinct / max(len(values), 1) < CATEGORY_MAX_RATIO:
                frame[column] = values.astype("category")
    return frame


# ---------------------------------------------------------------------------
# Raw tables
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _raw(table: str) -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / f"{table}.csv")


@st.cache_data(show_spinner="Loading marketplace data...")
def bookings() -> pd.DataFrame:
    """fact_bookings joined to the dimensions every page needs inline."""
    b = _raw("fact_bookings").copy()
    b["BookingTimestamp"] = pd.to_datetime(b["BookingTimestamp"])
    b["Date"] = b["BookingTimestamp"].dt.normalize()

    services = _raw("dim_service")[
        ["ServiceKey", "ServiceCategory", "ServiceName", "BasePriceINR", "IsEmergency"]]
    areas = _raw("dim_area")[
        ["AreaKey", "AreaName", "Zone", "DemandTier", "IncomeBand",
         "Latitude", "Longitude"]]
    dates = _raw("dim_date")[
        ["DateKey", "MonthYear", "MonthYearSort", "IsWeekend", "IsMonsoon",
         "IsFestivalWindow", "FiscalYear", "DayName"]]
    pros = _raw("dim_professional")[["ProKey", "SkillTier", "PrimaryServiceCategory"]]
    customers = _raw("dim_customer")[["CustomerKey", "AcquisitionChannel", "Segment"]]

    b = (b.merge(services, on="ServiceKey", how="left")
           .merge(areas, on="AreaKey", how="left")
           .merge(dates, on="DateKey", how="left")
           .merge(pros, on="ProKey", how="left")
           .merge(customers, on="CustomerKey", how="left"))
    b["IsCompleted"] = (b["BookingStatus"] == "Completed").astype(int)
    return compact(b)


@st.cache_data(show_spinner=False)
def daily_strain() -> pd.DataFrame:
    """Daily volume against its own trailing 30-day mean.

    The same definition as the [Capacity Strain Index] measure. Above 1.0 means
    the day is running hotter than its recent norm.
    """
    b = bookings()
    daily = b.groupby("Date").size().rename("Volume").to_frame().sort_index()
    daily["Trailing"] = (daily["Volume"].shift(1)
                         .rolling(STRAIN_WINDOW, min_periods=1).mean())
    daily["Strain"] = (daily["Volume"] / daily["Trailing"]).fillna(1.0).clip(0.3, 3.0)

    completed = b[b["IsCompleted"] == 1]
    sla = completed.groupby("Date")["SLAMetFlag"].mean().rename("SLAMet")
    tta = b.groupby("Date")["TimeToAssignMins"].mean().rename("TimeToAssign")
    rating = completed.groupby("Date")["CustomerRating"].mean().rename("Rating")

    daily = daily.join(sla).join(tta).join(rating)
    daily["SLABreach"] = 1 - daily["SLAMet"]
    return daily.reset_index()


@st.cache_data(show_spinner=False)
def capacity() -> pd.DataFrame:
    """fact_pro_capacity joined to technician and calendar attributes."""
    c = _raw("fact_pro_capacity").copy()
    pros = _raw("dim_professional")[
        ["ProKey", "ProName", "PrimaryServiceCategory", "SkillTier",
         "AvgRating", "IsActive", "LifetimeJobs"]]
    areas = _raw("dim_area")[["AreaKey", "AreaName", "Zone", "DemandTier"]]
    dates = _raw("dim_date")[["DateKey", "Date", "MonthYear", "MonthYearSort", "IsMonsoon"]]
    c = (c.merge(pros, on="ProKey", how="left")
           .merge(areas, on="AreaKey", how="left")
           .merge(dates, on="DateKey", how="left"))
    c["Date"] = pd.to_datetime(c["Date"])
    return compact(c)


@st.cache_data(show_spinner=False)
def leads() -> pd.DataFrame:
    l = _raw("fact_leads").copy()
    services = _raw("dim_service")[["ServiceKey", "ServiceCategory", "ServiceName"]]
    areas = _raw("dim_area")[["AreaKey", "AreaName", "Zone", "DemandTier",
                              "Latitude", "Longitude"]]
    dates = _raw("dim_date")[["DateKey", "Date", "MonthYear", "MonthYearSort"]]
    l = (l.merge(services, on="ServiceKey", how="left")
           .merge(areas, on="AreaKey", how="left")
           .merge(dates, on="DateKey", how="left"))
    l["Date"] = pd.to_datetime(l["Date"])
    return compact(l)


@st.cache_data(show_spinner=False)
def model_metrics() -> pd.DataFrame:
    m = _raw("fact_model_metrics").copy()
    # MetricGoal lives on BOTH tables - the fact carries a copy for convenience.
    # Merging without dropping one produces MetricGoal_x / MetricGoal_y and every
    # downstream reference to MetricGoal fails with a column-not-found error that
    # points nowhere near the join that caused it. Keep the fact's copy.
    models = _raw("dim_model").drop(columns=["MetricGoal"])
    dates = _raw("dim_date")[["DateKey", "Date", "MonthYear", "MonthYearSort"]]
    m = m.merge(models, on="ModelKey", how="left").merge(dates, on="DateKey", how="left")
    m["Date"] = pd.to_datetime(m["Date"])
    return m


@st.cache_data(show_spinner=False)
def forecast_accuracy() -> pd.DataFrame:
    f = _raw("fact_forecast_accuracy").copy()
    areas = _raw("dim_area")[["AreaKey", "AreaName", "Zone", "DemandTier"]]
    dates = _raw("dim_date")[["DateKey", "Date", "MonthYear", "MonthYearSort"]]
    f = f.merge(areas, on="AreaKey", how="left").merge(dates, on="DateKey", how="left")
    f["Date"] = pd.to_datetime(f["Date"])
    return compact(f)


@st.cache_data(show_spinner=False)
def customers() -> pd.DataFrame:
    c = _raw("dim_customer").copy()
    areas = _raw("dim_area")[["AreaKey", "AreaName", "Zone", "DemandTier"]]
    c = c.merge(areas, on="AreaKey", how="left")
    for column in ("SignupDate", "FirstBookingDate", "LastBookingDate"):
        c[column] = pd.to_datetime(c[column])
    return c


@st.cache_data(show_spinner=False)
def professionals() -> pd.DataFrame:
    p = _raw("dim_professional").copy()
    areas = _raw("dim_area")[["AreaKey", "AreaName", "Zone"]].rename(
        columns={"AreaKey": "HomeAreaKey"})
    p = p.merge(areas, on="HomeAreaKey", how="left")
    p["JoinDate"] = pd.to_datetime(p["JoinDate"])
    return p


@st.cache_data(show_spinner=False)
def services() -> pd.DataFrame:
    return _raw("dim_service")


@st.cache_data(show_spinner=False)
def areas() -> pd.DataFrame:
    return _raw("dim_area")


@st.cache_data(show_spinner=False)
def models() -> pd.DataFrame:
    m = _raw("dim_model").copy()
    m["DeployedDate"] = pd.to_datetime(m["DeployedDate"])
    return m


@st.cache_data(show_spinner=False)
def date_bounds() -> tuple:
    d = _raw("dim_date")
    return (pd.to_datetime(d["Date"]).min().date(),
            pd.to_datetime(d["Date"]).max().date())


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------
@dataclass
class Filters:
    """The sidebar selection, passed down to every page."""
    start: dt.date
    end: dt.date
    zones: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    tiers: List[str] = field(default_factory=list)

    @property
    def is_full_range(self) -> bool:
        lo, hi = date_bounds()
        return self.start == lo and self.end == hi

    @property
    def label(self) -> str:
        return (f"{self.start.strftime('%d %b %Y')} to "
                f"{self.end.strftime('%d %b %Y')}")

    @property
    def scope_label(self) -> str:
        bits = []
        bits.append("All Bengaluru" if not self.zones else ", ".join(self.zones))
        if self.categories:
            bits.append(", ".join(self.categories))
        if self.tiers:
            bits.append("tier " + "/".join(self.tiers))
        return "  ·  ".join(bits)


def apply(frame: pd.DataFrame, filters: Filters, date_col: str = "Date",
          use_category: bool = True, use_zone: bool = True,
          use_tier: bool = True) -> pd.DataFrame:
    """Apply the sidebar filters to any frame that carries the right columns.

    Columns that are absent are skipped rather than raising, so the same call
    works for bookings, capacity, leads and forecast frames despite them having
    different shapes.
    """
    mask = ((frame[date_col] >= pd.Timestamp(filters.start))
            & (frame[date_col] <= pd.Timestamp(filters.end)))

    if use_zone and filters.zones and "Zone" in frame.columns:
        mask &= frame["Zone"].isin(filters.zones)
    if use_category and filters.categories and "ServiceCategory" in frame.columns:
        mask &= frame["ServiceCategory"].isin(filters.categories)
    if use_tier and filters.tiers and "DemandTier" in frame.columns:
        mask &= frame["DemandTier"].isin(filters.tiers)

    return frame[mask]


# ---------------------------------------------------------------------------
# Headline metrics - the same definitions as the DAX measures
# ---------------------------------------------------------------------------
def headline(frame: pd.DataFrame) -> Dict[str, float]:
    """Core KPIs for a filtered booking frame."""
    total = len(frame)
    completed = frame[frame["IsCompleted"] == 1]
    n_completed = len(completed)
    gmv = float(frame["FinalAmountINR"].sum())
    revenue = float(frame["PlatformRevenueINR"].sum())
    material = float(frame["MaterialCostINR"].sum())

    return {
        "bookings": total,
        "completed": n_completed,
        "completion_rate": n_completed / total if total else 0.0,
        "cancellation_rate": float(
            frame["BookingStatus"].isin(
                ["CancelledByCustomer", "CancelledByPro"]).mean()) if total else 0.0,
        "no_show_rate": float(
            (frame["BookingStatus"] == "NoShow").mean()) if total else 0.0,
        "gmv": gmv,
        "revenue": revenue,
        "take_rate": revenue / gmv if gmv else 0.0,
        "aov": gmv / n_completed if n_completed else 0.0,
        "gross_margin": (gmv - material) / gmv if gmv else 0.0,
        "sla_met": float(completed["SLAMetFlag"].mean()) if n_completed else 0.0,
        "time_to_assign": float(frame["TimeToAssignMins"].mean()) if total else 0.0,
        "response_time": float(frame["ResponseTimeMins"].mean()) if total else 0.0,
        "first_time_fix": float(completed["IsFirstTimeFix"].mean()) if n_completed else 0.0,
        "reopen_rate": float(completed["ReopenedWithin7Days"].mean()) if n_completed else 0.0,
        "csat": float(frame["CustomerRating"].mean()) if total else 0.0,
        "rated_pct": (float(frame["CustomerRating"].notna().sum()) / n_completed
                      if n_completed else 0.0),
        "repeat_rate": float(frame["IsRepeatCustomer"].mean()) if total else 0.0,
        "customers": int(frame["CustomerKey"].nunique()),
    }


def strain_split(frame: pd.DataFrame, quantile: float = 0.80) -> Dict[str, float]:
    """Split completed jobs by whether their day ran hot, and compare.

    This is the Ops page's core finding, computed rather than asserted.
    """
    strain = daily_strain()[["Date", "Strain"]]
    completed = frame[frame["IsCompleted"] == 1].merge(strain, on="Date", how="left")
    if completed.empty:
        return {}

    # The threshold is the 80th percentile across DAYS, not across bookings.
    # Taking it across bookings weights busy days more heavily and shifts the
    # cut-off upward, which made this app report 34.8% where validate.py
    # reported 32.5% for the same claim. Same definition in both places.
    in_scope = strain[strain["Date"].isin(completed["Date"].unique())]
    threshold = float(in_scope["Strain"].quantile(quantile))
    high = completed[completed["Strain"] >= threshold]
    normal = completed[completed["Strain"] < threshold]
    if high.empty or normal.empty:
        return {}

    high_breach = 1 - float(high["SLAMetFlag"].mean())
    normal_breach = 1 - float(normal["SLAMetFlag"].mean())
    return {
        "threshold": threshold,
        "high_n": len(high),
        "normal_n": len(normal),
        "high_breach": high_breach,
        "normal_breach": normal_breach,
        "ratio": high_breach / normal_breach if normal_breach else float("nan"),
        "high_tta": float(high["TimeToAssignMins"].mean()),
        "normal_tta": float(normal["TimeToAssignMins"].mean()),
        "high_rating": float(high["CustomerRating"].mean()),
        "normal_rating": float(normal["CustomerRating"].mean()),
    }


def monthly(frame: pd.DataFrame) -> pd.DataFrame:
    """Month-level aggregates, correctly ordered."""
    grouped = (frame.groupby(["MonthYearSort", "MonthYear"], as_index=False, observed=True)
               .agg(Bookings=("BookingID", "count"),
                    Completed=("IsCompleted", "sum"),
                    GMV=("FinalAmountINR", "sum"),
                    Revenue=("PlatformRevenueINR", "sum")))
    completed = frame[frame["IsCompleted"] == 1]
    sla = (completed.groupby(["MonthYearSort"], as_index=False, observed=True)["SLAMetFlag"]
           .mean().rename(columns={"SLAMetFlag": "SLAMet"}))
    grouped = grouped.merge(sla, on="MonthYearSort", how="left")
    grouped["Cancelled"] = grouped["Bookings"] - grouped["Completed"]
    return grouped.sort_values("MonthYearSort")


def model_status(value: float, goal: float, direction: str) -> str:
    """Traffic light honouring GoalDirection, matching [Model KPI Status]."""
    if pd.isna(value):
        return "No Data"
    ratio = value / goal if goal else np.nan
    if direction == "LowerIsBetter":
        if ratio <= 0.90:
            return "On Target"
        return "Watch" if ratio <= 1.0 else "Breach"
    if ratio >= 1.05:
        return "On Target"
    return "Watch" if ratio >= 1.0 else "Breach"
