"""
Tests for the seasonality window logic.

These matter more than they look. Every demand number in the dataset is a
product of these multipliers, so a boundary error here would quietly move the
monsoon by a day across 58,000 bookings and nothing else would notice.
"""

from __future__ import annotations

import datetime as dt

import pytest

from generator import config, seasonality


# ---------------------------------------------------------------------------
# Window membership and boundaries
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("day, expected", [
    (dt.date(2025, 5, 31), False),   # day before the south-west monsoon
    (dt.date(2025, 6, 1), True),     # first day
    (dt.date(2025, 9, 30), True),    # last day
    (dt.date(2025, 10, 1), False),   # the gap between the two monsoons
    (dt.date(2025, 10, 9), False),   # day before the north-east monsoon
    (dt.date(2025, 10, 10), True),   # first day
    (dt.date(2025, 11, 20), True),   # last day
    (dt.date(2025, 11, 21), False),  # day after
    (dt.date(2026, 2, 14), False),   # deep winter, nothing at all
])
def test_monsoon_boundaries_are_inclusive(day, expected):
    assert seasonality.is_monsoon(day) is expected


def test_monsoon_windows_are_the_only_monsoon_windows():
    """Guards against a window being retyped as Monsoon by accident."""
    monsoon = {w["Name"] for w in config.SEASON_WINDOWS if w["Kind"] == "Monsoon"}
    assert monsoon == {"South West Monsoon", "North East Monsoon"}


# ---------------------------------------------------------------------------
# The headline multipliers
# ---------------------------------------------------------------------------
def test_painter_in_diwali_and_monsoon_overlap_is_1_56():
    """The single most specific claim in the brief, asserted exactly.

    Diwali lifts painting 2.4x, the north-east monsoon suppresses it to 0.65,
    and overlapping windows multiply: 2.4 * 0.65 = 1.56. Demand rises for the
    festival but the rain still restrains it.
    """
    day = dt.date(2025, 10, 20)
    assert seasonality.is_monsoon(day)
    assert seasonality.is_festival_window(day)
    assert seasonality.category_seasonal_multiplier(day, "Painter") == pytest.approx(1.56)


def test_deep_cleaning_peaks_at_diwali():
    day = dt.date(2025, 10, 20)
    assert seasonality.category_seasonal_multiplier(day, "Deep Cleaning") == pytest.approx(2.8)


def test_ac_service_triples_in_summer():
    day = dt.date(2026, 4, 15)
    assert seasonality.category_seasonal_multiplier(day, "AC Service") == pytest.approx(3.2)


def test_plumbing_surges_in_the_monsoon():
    day = dt.date(2026, 7, 8)
    assert seasonality.category_seasonal_multiplier(day, "Plumber") == pytest.approx(1.9)


def test_painting_is_suppressed_by_rain_alone():
    """Monsoon with no festival: the dip must stand on its own."""
    day = dt.date(2026, 7, 8)
    assert not seasonality.is_festival_window(day)
    assert seasonality.category_seasonal_multiplier(day, "Painter") == pytest.approx(0.65)


def test_ugadi_lifts_cleaning_and_painting():
    day = dt.date(2026, 3, 20)
    assert seasonality.category_seasonal_multiplier(day, "Deep Cleaning") == pytest.approx(1.8)
    # Ugadi overlaps summer, which does not touch painting, so 1.4 stands alone.
    assert seasonality.category_seasonal_multiplier(day, "Painter") == pytest.approx(1.4)


def test_neutral_day_leaves_every_category_untouched():
    day = dt.date(2026, 2, 10)
    assert seasonality.active_windows(day) == []
    for category in config.CATEGORY_ORDER:
        assert seasonality.category_seasonal_multiplier(day, category) == 1.0


def test_a_category_absent_from_a_window_is_unaffected_by_it():
    """Carpentry is not in the summer window, so summer must not move it."""
    day = dt.date(2026, 4, 15)
    assert "Summer" in seasonality.window_names(day)
    assert seasonality.category_seasonal_multiplier(day, "Carpenter") == 1.0


def test_every_configured_category_is_a_real_category():
    """A typo in a window's Multipliers dict would silently do nothing."""
    known = set(config.CATEGORY_ORDER)
    for window in config.SEASON_WINDOWS:
        unknown = set(window["Multipliers"]) - known
        assert not unknown, f"{window['Name']} references unknown categories {unknown}"


# ---------------------------------------------------------------------------
# Day shape
# ---------------------------------------------------------------------------
def test_weekend_detection():
    assert seasonality.is_weekend(dt.date(2026, 7, 11))       # Saturday
    assert seasonality.is_weekend(dt.date(2026, 7, 12))       # Sunday
    assert not seasonality.is_weekend(dt.date(2026, 7, 13))   # Monday


def test_weekend_uplift_and_the_cleaning_extra():
    saturday = dt.date(2026, 7, 11)
    assert seasonality.weekend_factor(saturday, "Plumber") == pytest.approx(1.35)
    # Deep cleaning carries an additional 1.6x on top of the general uplift.
    assert seasonality.weekend_factor(saturday, "Deep Cleaning") == pytest.approx(1.35 * 1.6)


def test_month_end_covers_exactly_the_last_five_days():
    assert not seasonality.is_month_end(dt.date(2026, 4, 25))
    assert seasonality.is_month_end(dt.date(2026, 4, 26))
    assert seasonality.is_month_end(dt.date(2026, 4, 30))
    # February, and a leap-year February, must both work off the real month length.
    assert seasonality.is_month_end(dt.date(2026, 2, 24))
    assert not seasonality.is_month_end(dt.date(2026, 2, 23))


def test_month_end_factor_is_a_discount():
    assert seasonality.month_end_factor(dt.date(2026, 4, 28)) == pytest.approx(0.85)
    assert seasonality.month_end_factor(dt.date(2026, 4, 10)) == 1.0


def test_normalised_day_shape_averages_to_one():
    """Weekends and the salary cycle redistribute demand inside a month; they
    must not create or destroy any of it."""
    days = seasonality.date_range(dt.date(2026, 4, 1), dt.date(2026, 4, 30))
    for category in config.CATEGORY_ORDER:
        shape = seasonality.normalised_day_shape(days, category)
        assert sum(shape) / len(shape) == pytest.approx(1.0)


def test_normalised_day_shape_keeps_the_weekday_weekend_ratio():
    days = seasonality.date_range(dt.date(2026, 4, 1), dt.date(2026, 4, 30))
    shape = seasonality.normalised_day_shape(days, "Plumber")
    saturday = shape[days.index(dt.date(2026, 4, 11))]
    tuesday = shape[days.index(dt.date(2026, 4, 14))]
    assert saturday / tuesday == pytest.approx(1.35)


def test_demand_multiplier_composes_season_and_day_shape():
    sunday_in_monsoon = dt.date(2026, 7, 12)
    assert seasonality.demand_multiplier(sunday_in_monsoon, "Plumber") == pytest.approx(1.9 * 1.35)


# ---------------------------------------------------------------------------
# Calendar helpers
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("day, label", [
    (dt.date(2025, 1, 1), "FY24-25"),
    (dt.date(2025, 3, 31), "FY24-25"),
    (dt.date(2025, 4, 1), "FY25-26"),
    (dt.date(2026, 3, 31), "FY25-26"),
    (dt.date(2026, 4, 1), "FY26-27"),
    (dt.date(2026, 8, 31), "FY26-27"),
])
def test_indian_fiscal_year_runs_april_to_march(day, label):
    assert seasonality.fiscal_year_label(day) == label


@pytest.mark.parametrize("day, quarter", [
    (dt.date(2026, 4, 1), "Q1"),
    (dt.date(2026, 6, 30), "Q1"),
    (dt.date(2026, 7, 1), "Q2"),
    (dt.date(2025, 10, 1), "Q3"),
    (dt.date(2026, 1, 1), "Q4"),
    (dt.date(2026, 3, 31), "Q4"),
])
def test_indian_fiscal_quarters(day, quarter):
    assert seasonality.fiscal_quarter_label(day) == quarter


def test_date_range_is_contiguous_and_inclusive():
    days = seasonality.date_range(config.DATE_START, config.DATE_END)
    assert len(days) == 608
    assert days[0] == config.DATE_START
    assert days[-1] == config.DATE_END
    gaps = [(b - a).days for a, b in zip(days, days[1:])]
    assert set(gaps) == {1}


def test_festival_name_prefers_the_exact_holiday():
    """Inside the Diwali window, the day itself should say Deepavali."""
    assert seasonality.festival_name(dt.date(2025, 10, 20)) == "Deepavali"
    assert seasonality.festival_name(dt.date(2025, 10, 15)) == "Diwali"
    assert seasonality.festival_name(dt.date(2026, 2, 10)) == ""


def test_heavy_rain_only_happens_in_the_monsoon():
    assert seasonality.heavy_rain_probability(dt.date(2026, 7, 8)) > 0
    assert seasonality.heavy_rain_probability(dt.date(2026, 2, 10)) == 0.0


def test_describe_is_self_consistent():
    detail = seasonality.describe(dt.date(2025, 10, 20), "Painter")
    assert detail["SeasonalMultiplier"] == pytest.approx(1.56)
    assert detail["DemandMultiplier"] == pytest.approx(
        detail["SeasonalMultiplier"] * detail["WeekendFactor"] * detail["MonthEndFactor"])
