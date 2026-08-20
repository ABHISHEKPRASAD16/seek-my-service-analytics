"""
Seek My Service - seasonality window logic.

This module owns the *logic*; ``config.SEASON_WINDOWS`` owns the *numbers*.
Nothing here hard-codes a date or a multiplier, and nothing in the generator
decides for itself whether a day is in the monsoon.

The public entry point is :func:`demand_multiplier`, which composes:

  * seasonal windows (monsoon, summer, Diwali, Ugadi) - these MULTIPLY when
    they overlap, so painting in the Diwali / north-east monsoon overlap lands
    at 2.4 * 0.65 = 1.56;
  * day shape (weekend uplift, month-end salary-cycle dip), which redistributes
    demand within a month rather than changing the month total.
"""

from __future__ import annotations

import calendar
import datetime as dt
import os
import sys
from typing import Dict, List, Sequence

# Allow both "python generator/seasonality.py" and "from generator import ...".
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from generator import config  # noqa: E402


# ---------------------------------------------------------------------------
# Window membership
# ---------------------------------------------------------------------------
def _in_window(day: dt.date, start_md: Sequence[int], end_md: Sequence[int]) -> bool:
    """Is ``day`` inside a (month, day) window that recurs every year?

    Windows that wrap the year boundary (for example 22 Dec to 5 Jan) are
    supported: when the end is earlier in the year than the start, membership
    is the union of the two halves.
    """
    md = (day.month, day.day)
    start = (start_md[0], start_md[1])
    end = (end_md[0], end_md[1])
    if start <= end:
        return start <= md <= end
    return md >= start or md <= end


def active_windows(day: dt.date) -> List[dict]:
    """Every configured window that contains ``day``, in configuration order."""
    return [w for w in config.SEASON_WINDOWS
            if _in_window(day, w["Start"], w["End"])]


def window_names(day: dt.date) -> List[str]:
    """Names of the active windows, useful for tests and for debugging."""
    return [w["Name"] for w in active_windows(day)]


def is_monsoon(day: dt.date) -> bool:
    """True inside either the south-west or the north-east monsoon."""
    return any(w["Kind"] == "Monsoon" for w in active_windows(day))


def is_festival_window(day: dt.date) -> bool:
    """True inside any window flagged as a festival."""
    return any(w["Kind"] == "Festival" for w in active_windows(day))


def festival_name(day: dt.date) -> str:
    """The festival window ``day`` belongs to, or an empty string.

    A named public holiday on the exact day wins over the surrounding window,
    so 20 Oct 2025 reads "Deepavali" rather than "Diwali".
    """
    holiday = config.PUBLIC_HOLIDAYS.get(day)
    if holiday is not None:
        return holiday
    for window in active_windows(day):
        if window["Kind"] == "Festival":
            return window["Name"]
    return config.BLANK


def is_holiday(day: dt.date) -> bool:
    """True on a national or Karnataka public holiday."""
    return day in config.PUBLIC_HOLIDAYS


# ---------------------------------------------------------------------------
# Seasonal multipliers
# ---------------------------------------------------------------------------
def category_seasonal_multiplier(day: dt.date, category: str) -> float:
    """Product of every active window multiplier for ``category``.

    A category absent from a window is unaffected by it. With no active window
    the result is exactly 1.0.
    """
    multiplier = 1.0
    for window in active_windows(day):
        multiplier *= window["Multipliers"].get(category, 1.0)
    return multiplier


def seasonal_multipliers_for_day(day: dt.date) -> Dict[str, float]:
    """The seasonal multiplier for every category on ``day``."""
    return {c: category_seasonal_multiplier(day, c) for c in config.CATEGORY_ORDER}


# ---------------------------------------------------------------------------
# Day shape: weekend uplift and the month-end salary cycle
# ---------------------------------------------------------------------------
def is_weekend(day: dt.date) -> bool:
    """Saturday or Sunday. ``weekday()`` is 0=Mon .. 6=Sun."""
    return day.weekday() >= 5


def weekend_factor(day: dt.date, category: str) -> float:
    """Overall weekend uplift, plus any category-specific extra."""
    if not is_weekend(day):
        return 1.0
    return config.WEEKEND_MULTIPLIER * config.WEEKEND_CATEGORY_EXTRA.get(category, 1.0)


def is_month_end(day: dt.date) -> bool:
    """True on the last ``MONTH_END_DAYS`` days of the calendar month."""
    last_day = calendar.monthrange(day.year, day.month)[1]
    return day.day > last_day - config.MONTH_END_DAYS


def month_end_factor(day: dt.date) -> float:
    """Discretionary spend defers across the salary cycle boundary."""
    return config.MONTH_END_MULTIPLIER if is_month_end(day) else 1.0


def day_shape_factor(day: dt.date, category: str) -> float:
    """Weekend uplift combined with the month-end dip."""
    return weekend_factor(day, category) * month_end_factor(day)


def normalised_day_shape(days: Sequence[dt.date], category: str) -> List[float]:
    """Day-shape factors for a month, rescaled to average exactly 1.0.

    Weekends and the salary cycle move demand *around inside* a month; they do
    not create or destroy a month's worth of it. Normalising keeps the growth
    curve readable while preserving the shape a weekday-versus-weekend visual
    needs, because a Saturday is still 1.35x the Tuesday beside it.
    """
    raw = [day_shape_factor(d, category) for d in days]
    mean = sum(raw) / len(raw)
    return [r / mean for r in raw]


# ---------------------------------------------------------------------------
# Composite
# ---------------------------------------------------------------------------
def demand_multiplier(day: dt.date, category: str) -> float:
    """Full multiplier: seasonal windows times un-normalised day shape.

    The generator uses the normalised form (see :func:`normalised_day_shape`);
    this composite exists for tests, for notebooks and for the ML feature
    builders, which want the same number the data was built from.
    """
    return category_seasonal_multiplier(day, category) * day_shape_factor(day, category)


def describe(day: dt.date, category: str) -> Dict[str, object]:
    """A flat, printable explanation of why a day has the multiplier it has."""
    return {
        "Date": day.isoformat(),
        "Category": category,
        "Windows": window_names(day),
        "SeasonalMultiplier": round(category_seasonal_multiplier(day, category), 6),
        "IsWeekend": is_weekend(day),
        "WeekendFactor": round(weekend_factor(day, category), 6),
        "IsMonthEnd": is_month_end(day),
        "MonthEndFactor": round(month_end_factor(day), 6),
        "IsMonsoon": is_monsoon(day),
        "IsFestivalWindow": is_festival_window(day),
        "FestivalName": festival_name(day),
        "DemandMultiplier": round(demand_multiplier(day, category), 6),
    }


# ---------------------------------------------------------------------------
# Monsoon operational pressure
# ---------------------------------------------------------------------------
def heavy_rain_probability(day: dt.date) -> float:
    """Probability that a monsoon day is a genuinely heavy-rain day.

    Outside the monsoon this is zero, which is what keeps the cancellation
    uplift confined to the window rather than smeared across the year.
    """
    return config.HEAVY_RAIN_DAY_PROB if is_monsoon(day) else 0.0


# ---------------------------------------------------------------------------
# Calendar helpers used by dim_date and by the trend solver
# ---------------------------------------------------------------------------
def date_range(start: dt.date, end: dt.date) -> List[dt.date]:
    """Every date from ``start`` to ``end`` inclusive, contiguous."""
    return [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]


def month_key(day: dt.date) -> int:
    """YYYYMM as an integer, used to bucket days into months."""
    return day.year * 100 + day.month


def fiscal_year_label(day: dt.date) -> str:
    """Indian fiscal year, April to March, formatted 'FY26-27'."""
    start_year = day.year if day.month >= config.FISCAL_YEAR_START_MONTH else day.year - 1
    return f"FY{start_year % 100:02d}-{(start_year + 1) % 100:02d}"


def fiscal_quarter_label(day: dt.date) -> str:
    """Indian fiscal quarter: Q1 is Apr-Jun, Q4 is Jan-Mar."""
    offset = (day.month - config.FISCAL_YEAR_START_MONTH) % 12
    return f"Q{offset // 3 + 1}"


if __name__ == "__main__":  # pragma: no cover - manual inspection aid
    import json

    samples = [
        (dt.date(2025, 10, 20), "Painter"),      # Diwali x north-east monsoon
        (dt.date(2025, 10, 20), "Deep Cleaning"),
        (dt.date(2026, 4, 15), "AC Service"),    # summer
        (dt.date(2026, 7, 12), "Plumber"),       # south-west monsoon, a Sunday
        (dt.date(2026, 2, 26), "Carpenter"),     # nothing at all
    ]
    for day, category in samples:
        print(json.dumps(describe(day, category), indent=2))
