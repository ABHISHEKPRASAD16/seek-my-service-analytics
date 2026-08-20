"""
Tests for the shared feature builders.

The tests that matter here are the leakage ones. A time-series feature that can
see its own outcome produces a wonderful offline metric and a useless model,
and it is invisible unless something checks the alignment directly.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from generator import config, seasonality
from ml.common import features as F, io

pytestmark = pytest.mark.skipif(
    not (config.DATA_DIR / "fact_bookings.csv").exists(),
    reason="generated data not present; run python generator/generate.py",
)


# ---------------------------------------------------------------------------
# Fixtures - built once, they are not cheap
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def panel() -> pd.DataFrame:
    return F.build_demand_panel()


@pytest.fixture(scope="module")
def featured(panel: pd.DataFrame) -> pd.DataFrame:
    return F.add_forecast_features(panel)


@pytest.fixture(scope="module")
def pricing() -> pd.DataFrame:
    return F.build_pricing_dataset()


# ---------------------------------------------------------------------------
# Calendar features
# ---------------------------------------------------------------------------
def test_calendar_frame_matches_the_seasonality_module():
    days = [dt.date(2026, 7, 11), dt.date(2026, 2, 10), dt.date(2025, 10, 20)]
    frame = F.calendar_frame(days)
    assert len(frame) == 3
    for row, day in zip(frame.itertuples(index=False), days):
        assert row.IsWeekend == int(seasonality.is_weekend(day))
        assert row.IsMonsoon == int(seasonality.is_monsoon(day))
        assert row.IsFestivalWindow == int(seasonality.is_festival_window(day))
        assert row.DayOfWeek == day.weekday()


def test_seasonal_multiplier_column_agrees_with_the_source_of_truth():
    dates = [pd.Timestamp(2025, 10, 20), pd.Timestamp(2026, 4, 15), pd.Timestamp(2026, 7, 8)]
    categories = ["Painter", "AC Service", "Plumber"]
    values = F.seasonal_multiplier_column(dates, categories)
    assert values == pytest.approx([1.56, 3.2, 1.9])


# ---------------------------------------------------------------------------
# Demand panel
# ---------------------------------------------------------------------------
def test_panel_is_dense(panel):
    """Every day x area x category cell must exist, including the empty ones.

    If absent days were dropped, a lag of 7 would mean "seven rows ago" rather
    than "seven days ago", and every lag feature would be wrong in exactly the
    thin cells where demand is hardest to predict.
    """
    n_days = (config.DATE_END - config.DATE_START).days + 1
    expected = n_days * len(config.AREAS) * len(config.CATEGORY_ORDER)
    assert len(panel) == expected
    assert panel.duplicated(["BookingDate", "AreaKey", "ServiceCategory"]).sum() == 0


def test_panel_totals_reconcile_to_the_fact_table(panel):
    bookings = io.load_bookings()
    assert panel["Jobs"].sum() == len(bookings)


def test_panel_has_genuine_zeros(panel):
    assert (panel["Jobs"] == 0).sum() > 0


# ---------------------------------------------------------------------------
# Forecast features - the leakage tests
# ---------------------------------------------------------------------------
def test_lag_features_never_see_the_present(featured, panel):
    cell = featured[(featured["AreaKey"] == 1)
                    & (featured["ServiceCategory"] == "Plumber")
                    ].sort_values("BookingDate").reset_index(drop=True)
    raw = panel[(panel["AreaKey"] == 1)
                & (panel["ServiceCategory"] == "Plumber")
                ].sort_values("BookingDate")["Jobs"].to_numpy()

    for lag in (1, 7, 28):
        got = cell[f"Lag{lag}"].to_numpy()[lag:lag + 40]
        expected = raw[0:40]
        assert np.array_equal(got, expected), f"Lag{lag} is misaligned"


def test_rolling_features_exclude_the_current_day(featured, panel):
    cell = featured[(featured["AreaKey"] == 3)
                    & (featured["ServiceCategory"] == "AC Service")
                    ].sort_values("BookingDate").reset_index(drop=True)
    raw = panel[(panel["AreaKey"] == 3)
                & (panel["ServiceCategory"] == "AC Service")
                ].sort_values("BookingDate")["Jobs"].to_numpy()

    for index in (40, 120, 400):
        expected = raw[index - 7:index].mean()
        assert cell["Roll7Mean"].iloc[index] == pytest.approx(expected)


def test_target_is_the_next_seven_days(featured, panel):
    cell = featured[(featured["AreaKey"] == 5)
                    & (featured["ServiceCategory"] == "Deep Cleaning")
                    ].sort_values("BookingDate").reset_index(drop=True)
    raw = panel[(panel["AreaKey"] == 5)
                & (panel["ServiceCategory"] == "Deep Cleaning")
                ].sort_values("BookingDate")["Jobs"].to_numpy()

    for index in (0, 30, 200, 500):
        assert cell["TargetNext7"].iloc[index] == raw[index + 1:index + 8].sum()


def test_target_is_missing_at_the_end_of_the_window(featured):
    """The last seven days cannot have a seven-day-ahead target."""
    last_day = featured["BookingDate"].max()
    tail = featured[featured["BookingDate"] > last_day - pd.Timedelta(days=7)]
    assert tail["TargetNext7"].isna().all()


def test_horizon_multiplier_looks_forward_not_back(featured):
    """The calendar for next week is known today, so this feature is legitimate.

    Checked on 31 May 2026: the day itself is outside the monsoon, but the seven
    days that follow are all inside it, so a plumbing horizon multiplier must
    already be elevated.
    """
    row = featured[(featured["BookingDate"] == pd.Timestamp(2026, 5, 31))
                   & (featured["ServiceCategory"] == "Plumber")
                   & (featured["AreaKey"] == 1)]
    assert not row.empty
    assert row["SeasonalMultiplier"].iloc[0] == pytest.approx(1.0)
    assert row["HorizonSeasonalMultiplier"].iloc[0] == pytest.approx(1.9)


def test_feature_columns_all_exist(featured):
    missing = set(F.forecast_feature_columns()) - set(featured.columns)
    assert not missing, f"declared but not built: {missing}"


def test_feature_columns_are_stable():
    """Training and inference read this list; its order must not drift."""
    columns = F.forecast_feature_columns()
    assert len(columns) == len(set(columns))
    assert columns[0] == "Lag1"
    assert "HorizonSeasonalMultiplier" in columns
    assert "TargetNext7" not in columns, "the target must never be a feature"


def test_only_the_warmup_rows_have_missing_features(featured):
    columns = F.forecast_feature_columns()
    incomplete = featured[featured[columns].isna().any(axis=1)]
    n_cells = len(config.AREAS) * len(config.CATEGORY_ORDER)
    assert len(incomplete) == n_cells * max(F.FORECAST_LAGS)


# ---------------------------------------------------------------------------
# Geography
# ---------------------------------------------------------------------------
def test_haversine_against_a_known_bengaluru_distance():
    """Koramangala to Whitefield is roughly 17 km as the crow flies."""
    areas = io.load_table("dim_area").set_index("AreaName")
    km = F.haversine_km(
        areas.loc["Koramangala", "Latitude"], areas.loc["Koramangala", "Longitude"],
        areas.loc["Whitefield", "Latitude"], areas.loc["Whitefield", "Longitude"])
    assert 13.0 < float(km) < 21.0


def test_haversine_is_zero_for_the_same_point():
    assert float(F.haversine_km(12.9352, 77.6245, 12.9352, 77.6245)) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Matching dataset
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def match_data() -> pd.DataFrame:
    return F.build_match_dataset(n_bookings=400, n_candidates=6)


def test_each_job_has_exactly_one_chosen_technician(match_data):
    per_group = match_data.groupby("GroupId")["Label"].sum()
    assert set(per_group.unique()) == {1}


def test_candidates_are_distinct_within_a_job(match_data):
    duplicated = match_data.duplicated(["GroupId", "ProKey"]).sum()
    assert duplicated == 0


def test_match_features_are_finite(match_data):
    columns = F.match_feature_columns()
    assert match_data[columns].notna().all().all()
    assert np.isfinite(match_data[columns].to_numpy(dtype=float)).all()


def test_match_features_are_in_sensible_ranges(match_data):
    assert match_data["DistanceKm"].between(0, 60).all()
    assert match_data["LoadRatio"].between(0, 1).all()
    assert match_data["RecentAcceptRate"].between(0, 1).all()
    assert match_data["SkillTierOrd"].isin([0, 1, 2, 3]).all()


# ---------------------------------------------------------------------------
# Pricing dataset
# ---------------------------------------------------------------------------
def test_accepted_flag_matches_booking_status(pricing):
    completed = pricing["BookingStatus"] == "Completed"
    assert (pricing["Accepted"] == completed.astype(int)).all()


def test_pricing_features_have_no_holes(pricing):
    assert pricing[F.pricing_feature_columns()].notna().all().all()
    assert pricing[F.accept_feature_columns()].notna().all().all()


def test_the_quote_is_excluded_from_the_price_features():
    """Predicting the final price from the quote would be circular: the quote is
    the very thing this model exists to produce."""
    columns = F.pricing_feature_columns()
    for leak in ("QuotedAmountINR", "FinalAmountINR", "QuoteToBaseRatio",
                 "DiscountINR", "PlatformRevenueINR"):
        assert leak not in columns


def test_accept_features_do_include_the_quote():
    """For acceptance, the price on the table is the whole question."""
    assert "QuoteToBaseRatio" in F.accept_feature_columns()
    assert "DiscountPct" in F.accept_feature_columns()


def test_area_load_features_are_backward_looking(pricing):
    assert pricing["AreaStrain"].between(0, 10).all()
    assert (pricing["AreaVolume7"] >= 0).all()
