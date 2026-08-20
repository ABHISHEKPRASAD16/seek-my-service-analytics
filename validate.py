"""
Seek My Service - data integrity validation.

Runs sixteen checks over the generated CSVs and prints a pass/fail line for
each, followed by the tables a human actually wants to eyeball: the growth
curve, the seasonal signatures, the drift incident, and the money.

Exit code is 0 when every check passes and 1 otherwise, so this is safe to
wire into CI or a pre-commit hook.

Run with:  python validate.py
"""

from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from generator import config  # noqa: E402

WIDTH = 96
FORBIDDEN_CELLS = {"nan", "NaN", "NULL", "null", "None", "NaT", "inf", "-inf", "#N/A"}


# ---------------------------------------------------------------------------
# Result collection
# ---------------------------------------------------------------------------
class Report:
    """Collects check outcomes so the summary can be printed in one place."""

    def __init__(self) -> None:
        self.results: List[Tuple[int, str, bool, str]] = []

    def add(self, number: int, title: str, passed: bool, detail: str = "") -> None:
        self.results.append((number, title, passed, detail))
        flag = "PASS" if passed else "FAIL"
        print(f"  [{flag}] {number:>2}. {title}")
        if detail:
            for line in detail.splitlines():
                print(f"         {line}")

    @property
    def failed(self) -> List[Tuple[int, str, bool, str]]:
        return [r for r in self.results if not r[2]]

    @property
    def all_passed(self) -> bool:
        return not self.failed


def header(text: str) -> None:
    print()
    print("=" * WIDTH)
    print(text)
    print("=" * WIDTH)


def section(text: str) -> None:
    print()
    print("-" * WIDTH)
    print(text)
    print("-" * WIDTH)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_raw(name: str) -> pd.DataFrame:
    """Everything as text, blanks preserved. Used for formatting checks."""
    return pd.read_csv(config.DATA_DIR / f"{name}.csv", dtype=str,
                       keep_default_na=False, na_filter=False)


def load_typed(name: str) -> pd.DataFrame:
    """Normal type inference. Blanks become NaN, which is what we want here."""
    return pd.read_csv(config.DATA_DIR / f"{name}.csv")


def load_all() -> Tuple[Dict[str, pd.DataFrame], Dict[str, pd.DataFrame]]:
    raw = {t: load_raw(t) for t in config.TABLES}
    typed = {t: load_typed(t) for t in config.TABLES}
    return raw, typed


# ---------------------------------------------------------------------------
# Checks 1-8: hard integrity
# ---------------------------------------------------------------------------
def check_referential_integrity(report: Report, typed: Dict[str, pd.DataFrame]) -> None:
    """Every foreign key in every fact table must resolve to a dimension row."""
    dim_keys = {
        "DateKey": set(typed["dim_date"]["DateKey"]),
        "ServiceKey": set(typed["dim_service"]["ServiceKey"]),
        "AreaKey": set(typed["dim_area"]["AreaKey"]),
        "ProKey": set(typed["dim_professional"]["ProKey"]),
        "CustomerKey": set(typed["dim_customer"]["CustomerKey"]),
        "ModelKey": set(typed["dim_model"]["ModelKey"]),
    }
    facts = ["fact_bookings", "fact_pro_capacity", "fact_leads",
             "fact_model_metrics", "fact_forecast_accuracy"]

    problems: List[str] = []
    for fact in facts:
        frame = typed[fact]
        for column, valid in dim_keys.items():
            if column not in frame.columns:
                continue
            orphans = set(frame[column].dropna().unique()) - valid
            if orphans:
                problems.append(f"{fact}.{column}: {len(orphans)} unresolved "
                                f"(e.g. {sorted(orphans)[:3]})")

    # ServiceCategory on the forecast fact is a conformed text key.
    categories = set(typed["dim_service"]["ServiceCategory"])
    orphan_cats = set(typed["fact_forecast_accuracy"]["ServiceCategory"]) - categories
    if orphan_cats:
        problems.append(f"fact_forecast_accuracy.ServiceCategory: {sorted(orphan_cats)}")

    # Dimension-to-dimension keys count too.
    areas = dim_keys["AreaKey"]
    if set(typed["dim_professional"]["HomeAreaKey"]) - areas:
        problems.append("dim_professional.HomeAreaKey has unresolved areas")
    if set(typed["dim_customer"]["AreaKey"]) - areas:
        problems.append("dim_customer.AreaKey has unresolved areas")

    report.add(1, "Referential integrity across every fact and dimension",
               not problems, "\n".join(problems))


def check_date_continuity(report: Report, typed: Dict[str, pd.DataFrame]) -> None:
    """dim_date must be gapless and cover the declared window exactly."""
    dates = pd.to_datetime(typed["dim_date"]["Date"]).sort_values()
    expected = pd.date_range(config.DATE_START, config.DATE_END, freq="D")
    gaps = len(expected) - len(dates)
    matches = len(dates) == len(expected) and (dates.to_numpy() == expected.to_numpy()).all()
    duplicates = int(typed["dim_date"]["DateKey"].duplicated().sum())
    detail = (f"rows={len(dates)} expected={len(expected)} "
              f"missing={max(gaps, 0)} duplicates={duplicates} "
              f"range={dates.min().date()}..{dates.max().date()}")
    report.add(2, "dim_date is contiguous and covers the full range",
               bool(matches and duplicates == 0), detail)


def check_amounts(report: Report, typed: Dict[str, pd.DataFrame]) -> None:
    """No negative money, and the final amount respects its ceiling."""
    b = typed["fact_bookings"]
    money = ["QuotedAmountINR", "FinalAmountINR", "DiscountINR",
             "PlatformRevenueINR", "MaterialCostINR"]
    negatives = {c: int((b[c] < 0).sum()) for c in money}
    ceiling = b["QuotedAmountINR"] + b["DiscountINR"]
    over = int((b["FinalAmountINR"] > ceiling + 1e-6).sum())

    # PlatformRevenue must equal Final x Commission / 100 to 2dp.
    expected_rev = (b["FinalAmountINR"] * b["CommissionPct"] / 100.0).round(2)
    rev_mismatch = int((expected_rev - b["PlatformRevenueINR"]).abs().gt(0.011).sum())

    leads = typed["fact_leads"]
    lead_negatives = int((leads[["Searches", "Leads", "QuotesSent", "Bookings"]] < 0).sum().sum())

    passed = (sum(negatives.values()) == 0 and over == 0
              and rev_mismatch == 0 and lead_negatives == 0)
    detail = (f"negative money cells={sum(negatives.values())}  "
              f"Final>Quoted+Discount={over}  "
              f"PlatformRevenue mismatches={rev_mismatch}  "
              f"negative funnel cells={lead_negatives}")
    report.add(3, "No negative amounts; FinalAmount within Quoted+Discount", passed, detail)


def check_completed_only_columns(report: Report, raw: Dict[str, pd.DataFrame]) -> None:
    """Duration, SLA and first-time-fix belong to completed jobs and nobody else."""
    b = raw["fact_bookings"]
    completed = b["BookingStatus"] == "Completed"
    completed_only = ["JobDurationMins", "SLAMetFlag", "IsFirstTimeFix",
                      "ActualETAMins", "ReopenedWithin7Days"]

    problems = []
    for column in completed_only:
        missing_on_completed = int((completed & (b[column] == "")).sum())
        present_on_other = int((~completed & (b[column] != "")).sum())
        if missing_on_completed or present_on_other:
            problems.append(f"{column}: blank on {missing_on_completed} completed, "
                            f"populated on {present_on_other} non-completed")

    non_revenue = b["BookingStatus"].isin(config.NON_REVENUE_STATUSES)
    for column in ["FinalAmountINR", "PlatformRevenueINR", "MaterialCostINR"]:
        nonzero = int((non_revenue & (b[column].astype(float) != 0)).sum())
        if nonzero:
            problems.append(f"{column}: non-zero on {nonzero} cancelled/no-show rows")

    report.add(4, "Completed-only columns populated only for Completed",
               not problems, "\n".join(problems))


def check_date_ordering(report: Report, typed: Dict[str, pd.DataFrame]) -> None:
    """Signup precedes the first booking; JoinDate precedes the first job."""
    b = typed["fact_bookings"]
    booking_date = pd.to_datetime(b["BookingTimestamp"]).dt.normalize()

    first_customer = booking_date.groupby(b["CustomerKey"]).min()
    customers = typed["dim_customer"].set_index("CustomerKey")
    signup = pd.to_datetime(customers["SignupDate"])
    joined = signup.reindex(first_customer.index)
    bad_customers = int((joined > first_customer).sum())

    first_pro = booking_date.groupby(b["ProKey"]).min()
    pros = typed["dim_professional"].set_index("ProKey")
    join_date = pd.to_datetime(pros["JoinDate"]).reindex(first_pro.index)
    bad_pros = int((join_date > first_pro).sum())

    # A churned professional must not appear on a job after they left.
    churn = pd.to_datetime(pros["ChurnedDate"], errors="coerce")
    last_pro = booking_date.groupby(b["ProKey"]).max()
    churn_aligned = churn.reindex(last_pro.index)
    post_churn = int((churn_aligned.notna() & (last_pro >= churn_aligned)).sum())

    # dim_customer's own derived dates must agree with the facts.
    stated_first = pd.to_datetime(customers["FirstBookingDate"]).reindex(first_customer.index)
    first_mismatch = int((stated_first != first_customer).sum())

    passed = bad_customers == 0 and bad_pros == 0 and post_churn == 0 and first_mismatch == 0
    detail = (f"customers signing up after their first booking={bad_customers}  "
              f"pros joining after their first job={bad_pros}\n"
              f"pros working on or after their churn date={post_churn}  "
              f"FirstBookingDate mismatches={first_mismatch}")
    report.add(5, "SignupDate precedes first booking; JoinDate precedes first job",
               passed, detail)


def check_rating_pairing(report: Report, raw: Dict[str, pd.DataFrame]) -> None:
    """Rating and sentiment are blank together and populated together."""
    b = raw["fact_bookings"]
    rating_blank = b["CustomerRating"] == ""
    sentiment_blank = b["ReviewSentiment"] == ""
    mismatched = int((rating_blank != sentiment_blank).sum())

    present = ~rating_blank
    values = b.loc[present, "CustomerRating"]
    non_integer = int((~values.str.fullmatch(r"[1-5]")).sum())

    sentiments = b.loc[present, "ReviewSentiment"]
    numeric = values.astype(int)
    wrong_map = int(
        ((numeric >= 4) & (sentiments != "Positive")).sum()
        + ((numeric == 3) & (sentiments != "Neutral")).sum()
        + ((numeric <= 2) & (sentiments != "Negative")).sum()
    )

    completed = b["BookingStatus"] == "Completed"
    blank_share = float(rating_blank[completed].mean())

    passed = mismatched == 0 and non_integer == 0 and wrong_map == 0
    detail = (f"blank-together mismatches={mismatched}  non-integer ratings={non_integer}  "
              f"sentiment mapping errors={wrong_map}\n"
              f"unrated share of completed jobs={blank_share:.1%} (target ~38%)")
    report.add(6, "CustomerRating and ReviewSentiment blank together", passed, detail)


def check_funnel(report: Report, typed: Dict[str, pd.DataFrame]) -> None:
    """Monotonic funnel, and Bookings reconciles to fact_bookings exactly."""
    leads = typed["fact_leads"]
    mono = int((~(
        (leads["Searches"] >= leads["Leads"])
        & (leads["Leads"] >= leads["QuotesSent"])
        & (leads["QuotesSent"] >= leads["Bookings"])
    )).sum())

    actual = (typed["fact_bookings"]
              .groupby(["DateKey", "AreaKey", "ServiceKey"]).size()
              .rename("Actual").reset_index())
    merged = leads.merge(actual, on=["DateKey", "AreaKey", "ServiceKey"], how="outer")
    merged["Bookings"] = merged["Bookings"].fillna(0)
    merged["Actual"] = merged["Actual"].fillna(0)
    mismatches = int((merged["Bookings"] != merged["Actual"]).sum())

    zero_searches = int((leads["Searches"] <= 0).sum())

    passed = mono == 0 and mismatches == 0 and zero_searches == 0
    detail = (f"non-monotonic rows={mono}  booking reconciliation mismatches={mismatches}  "
              f"rows with zero searches={zero_searches}\n"
              f"funnel rows={len(leads):,}  of which zero-booking cells="
              f"{int((leads['Bookings'] == 0).sum()):,}")
    report.add(7, "Funnel is monotonic and reconciles to fact_bookings", passed, detail)


def check_capacity_reconciliation(report: Report, typed: Dict[str, pd.DataFrame]) -> None:
    """SlotsBooked equals the bookings actually assigned to that pro that day."""
    capacity = typed["fact_pro_capacity"]
    actual = (typed["fact_bookings"].groupby(["DateKey", "ProKey"]).size()
              .rename("Actual").reset_index())
    merged = capacity.merge(actual, on=["DateKey", "ProKey"], how="outer")
    merged["SlotsBooked"] = merged["SlotsBooked"].fillna(0)
    merged["Actual"] = merged["Actual"].fillna(0)
    mismatches = int((merged["SlotsBooked"] != merged["Actual"]).sum())
    missing_rows = int(merged["SlotsAvailable"].isna().sum())
    overbooked = int((capacity["SlotsBooked"] > capacity["SlotsAvailable"]).sum())
    offline_with_jobs = int(((capacity["IsOnline"] == 0) & (capacity["SlotsBooked"] > 0)).sum())

    passed = (mismatches == 0 and missing_rows == 0
              and overbooked == 0 and offline_with_jobs == 0)
    detail = (f"SlotsBooked mismatches={mismatches}  bookings with no capacity row="
              f"{missing_rows}\noverbooked pro-days={overbooked}  "
              f"offline pro-days carrying jobs={offline_with_jobs}")
    report.add(8, "fact_pro_capacity reconciles to bookings per pro per day", passed, detail)


# ---------------------------------------------------------------------------
# Checks 9-16: shape, story and money
# ---------------------------------------------------------------------------
def check_row_counts(report: Report, typed: Dict[str, pd.DataFrame]) -> None:
    """Row counts per table, with the two the brief pins down asserted."""
    lines = []
    for table in config.TABLES:
        lines.append(f"{table:<26}{len(typed[table]):>12,}")
    pros_ok = len(typed["dim_professional"]) == config.N_PROFESSIONALS
    customers_ok = len(typed["dim_customer"]) == config.N_CUSTOMERS
    dates_ok = len(typed["dim_date"]) == (config.DATE_END - config.DATE_START).days + 1
    capacity_ok = len(typed["fact_pro_capacity"]) <= config.PRO_CAPACITY_ROW_CAP
    detail = "\n".join(lines)
    detail += (f"\npros=={config.N_PROFESSIONALS}:{pros_ok}  "
               f"customers=={config.N_CUSTOMERS}:{customers_ok}  "
               f"dates==608:{dates_ok}  capacity<=350k:{capacity_ok}")
    report.add(9, "Row counts per table",
               bool(pros_ok and customers_ok and dates_ok and capacity_ok), detail)


def _bookings_with_context(typed: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    b = typed["fact_bookings"]
    return (b.merge(typed["dim_service"][["ServiceKey", "ServiceCategory"]], on="ServiceKey")
             .merge(typed["dim_date"][["DateKey", "MonthYear", "MonthYearSort"]], on="DateKey"))


def check_monthly_growth(report: Report, typed: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Monthly booking and completion counts, so the growth curve is eyeballable."""
    context = _bookings_with_context(typed)
    monthly = (context.groupby(["MonthYearSort", "MonthYear"])
               .agg(Bookings=("BookingID", "count"),
                    Completed=("BookingStatus", lambda s: int((s == "Completed").sum())),
                    GMV=("FinalAmountINR", "sum"))
               .reset_index())
    monthly["CompletionPct"] = monthly["Completed"] / monthly["Bookings"]

    first = int(monthly.iloc[0]["Completed"])
    last = int(monthly.iloc[-1]["Completed"])
    first_ok = abs(first - config.COMPLETED_ANCHOR_FIRST_MONTH) / config.COMPLETED_ANCHOR_FIRST_MONTH < 0.12
    last_ok = abs(last - config.COMPLETED_ANCHOR_LAST_MONTH) / config.COMPLETED_ANCHOR_LAST_MONTH < 0.12
    monotone_ish = last > first * 3

    lines = [f"{'month':<12}{'bookings':>10}{'completed':>11}{'compl%':>9}{'GMV INR':>16}"]
    for _, row in monthly.iterrows():
        lines.append(f"{row['MonthYear']:<12}{row['Bookings']:>10,}{row['Completed']:>11,}"
                     f"{row['CompletionPct']:>9.1%}{row['GMV']:>16,.0f}")
    lines.append(f"first month completed={first} (anchor {config.COMPLETED_ANCHOR_FIRST_MONTH}), "
                 f"last={last} (anchor {config.COMPLETED_ANCHOR_LAST_MONTH})")

    report.add(10, "Monthly booking counts show the growth curve",
               bool(first_ok and last_ok and monotone_ish), "\n".join(lines))
    return context


def check_seasonal_signatures(report: Report, context: pd.DataFrame) -> None:
    """Painter, Plumber and AC Service by month - the monsoon and summer story."""
    completed = context[context["BookingStatus"] == "Completed"]
    pivot = (completed.pivot_table(index=["MonthYearSort", "MonthYear"],
                                   columns="ServiceCategory", values="BookingID",
                                   aggfunc="count").fillna(0).astype(int))
    watch = ["Painter", "Plumber", "AC Service", "Deep Cleaning"]
    table = pivot[watch]

    def month(label: str) -> pd.Series:
        return table.xs(label, level="MonthYear").iloc[0]

    # Summer AC spike: Apr 2026 against Jan 2026.
    ac_spike = month("Apr 2026")["AC Service"] / max(month("Jan 2026")["AC Service"], 1)
    # Monsoon plumbing surge: Jul 2026 against Apr 2026.
    plumber_surge = month("Jul 2026")["Plumber"] / max(month("Apr 2026")["Plumber"], 1)
    # Monsoon painter dip: Jul 2026 against Apr 2026.
    painter_dip = month("Jul 2026")["Painter"] / max(month("Apr 2026")["Painter"], 1)
    # Diwali cleaning spike: Oct 2025 against Sep 2025.
    clean_spike = month("Oct 2025")["Deep Cleaning"] / max(month("Sep 2025")["Deep Cleaning"], 1)

    lines = [f"{'month':<12}" + "".join(f"{c:>16}" for c in watch)]
    for (_, label), row in table.iterrows():
        lines.append(f"{label:<12}" + "".join(f"{int(row[c]):>16,}" for c in watch))
    lines.append("")
    lines.append(f"summer AC spike      Apr26/Jan26 = {ac_spike:.2f}x  (expect > 2.0)")
    lines.append(f"monsoon plumber lift Jul26/Apr26 = {plumber_surge:.2f}x  (expect > 1.5)")
    lines.append(f"monsoon painter dip  Jul26/Apr26 = {painter_dip:.2f}x  (expect < 0.9)")
    lines.append(f"Diwali cleaning lift Oct25/Sep25 = {clean_spike:.2f}x  (expect > 1.6)")

    passed = (ac_spike > 2.0 and plumber_surge > 1.5
              and painter_dip < 0.9 and clean_spike > 1.6)
    report.add(11, "Monsoon dip, summer AC spike and Diwali cleaning spike are present",
               bool(passed), "\n".join(lines))


def check_drift_incident(report: Report, typed: Dict[str, pd.DataFrame]) -> None:
    """demand_forecaster MAPE by month, plus the incident-window plateau."""
    metrics = (typed["fact_model_metrics"]
               .merge(typed["dim_model"][["ModelKey", "ModelName"]], on="ModelKey")
               .merge(typed["dim_date"][["DateKey", "Date", "MonthYear", "MonthYearSort"]],
                      on="DateKey"))
    forecaster = metrics[metrics["ModelName"] == "demand_forecaster"].copy()
    forecaster["Date"] = pd.to_datetime(forecaster["Date"])

    monthly = (forecaster.groupby(["MonthYearSort", "MonthYear"])
               .agg(MAPE=("MetricValue", "mean"), PSI=("PSIDriftScore", "mean"),
                    MaxTrainAge=("TrainingDataAgeDays", "max"),
                    NullPct=("FeatureNullPct", "mean"),
                    BreachDays=("IsBreach", "sum"),
                    Version=("ModelVersion", "last")).reset_index())

    lines = [f"{'month':<12}{'MAPE%':>9}{'PSI':>8}{'trainAge':>10}{'null%':>8}"
             f"{'breach d':>10}{'version':>10}"]
    for _, row in monthly.iterrows():
        lines.append(f"{row['MonthYear']:<12}{row['MAPE']:>9.2f}{row['PSI']:>8.3f}"
                     f"{int(row['MaxTrainAge']):>10}{row['NullPct']:>8.2f}"
                     f"{int(row['BreachDays']):>10}{row['Version']:>10}")

    plateau = forecaster[(forecaster["Date"] >= pd.Timestamp(config.DRIFT_FULL_DATE))
                         & (forecaster["Date"] < pd.Timestamp(config.RETRAIN_FIX_DATE))]
    baseline = forecaster[(forecaster["Date"] >= pd.Timestamp(2026, 1, 1))
                          & (forecaster["Date"] < pd.Timestamp(config.DRIFT_ONSET_DATE))]
    recovered = forecaster[forecaster["Date"]
                           >= pd.Timestamp(config.RETRAIN_FIX_DATE)
                           + pd.Timedelta(days=config.RETRAIN_RECOVERY_DAYS)]

    plateau_mape = float(plateau["MetricValue"].mean())
    baseline_mape = float(baseline["MetricValue"].mean())
    recovered_mape = float(recovered["MetricValue"].mean())
    psi_peak = float(plateau["PSIDriftScore"].max())
    max_age = int(forecaster["TrainingDataAgeDays"].max())
    versions = forecaster["ModelVersion"].nunique()

    lines.append("")
    lines.append(f"daily plateau ({config.DRIFT_FULL_DATE} to {config.RETRAIN_FIX_DATE}) "
                 f"mean MAPE = {plateau_mape:.2f}%")
    lines.append(f"pre-incident baseline mean MAPE = {baseline_mape:.2f}%   "
                 f"post-retrain mean MAPE = {recovered_mape:.2f}%")
    lines.append(f"peak PSI during incident = {psi_peak:.3f} "
                 f"(alert threshold {config.PSI_ALERT_THRESHOLD})")
    lines.append(f"max TrainingDataAgeDays = {max_age} days   "
                 f"distinct model versions = {versions}")
    lines.append("note: the monthly mean dilutes the plateau because June contains the "
                 "ramp-up\n      and July contains the post-retrain recovery.")

    passed = (baseline_mape < 10.0 and plateau_mape > 17.0 and recovered_mape < 11.5
              and psi_peak > config.PSI_ALERT_THRESHOLD and max_age > 100 and versions == 2)
    report.add(12, "Drift incident and recovery are visible in the MAPE series",
               bool(passed), "\n".join(lines))


def check_strain_sla(report: Report, typed: Dict[str, pd.DataFrame]) -> None:
    """SLA breach rate on high-strain days against everything else."""
    b = typed["fact_bookings"]
    daily = b.groupby("DateKey").size().rename("Volume").to_frame()
    daily["Trailing"] = daily["Volume"].shift(1).rolling(
        config.STRAIN_TRAILING_DAYS, min_periods=1).mean()
    daily["Strain"] = daily["Volume"] / daily["Trailing"]

    completed = b[b["BookingStatus"] == "Completed"].merge(
        daily[["Strain"]], left_on="DateKey", right_index=True)
    threshold = float(daily["Strain"].quantile(0.80))
    high = completed[completed["Strain"] >= threshold]
    normal = completed[completed["Strain"] < threshold]

    high_breach = 1.0 - float(high["SLAMetFlag"].mean())
    normal_breach = 1.0 - float(normal["SLAMetFlag"].mean())
    ratio = high_breach / normal_breach if normal_breach else float("inf")

    high_tta = float(high["TimeToAssignMins"].mean())
    normal_tta = float(normal["TimeToAssignMins"].mean())
    high_rating = float(high["CustomerRating"].mean())
    normal_rating = float(normal["CustomerRating"].mean())

    detail = (f"strain threshold (80th percentile) = {threshold:.3f}\n"
              f"{'':<22}{'jobs':>10}{'SLA breach':>13}{'avg TTA min':>14}{'avg rating':>13}\n"
              f"{'high-strain days':<22}{len(high):>10,}{high_breach:>13.1%}"
              f"{high_tta:>14.1f}{high_rating:>13.2f}\n"
              f"{'normal days':<22}{len(normal):>10,}{normal_breach:>13.1%}"
              f"{normal_tta:>14.1f}{normal_rating:>13.2f}\n"
              f"breach ratio = {ratio:.2f}x  (expect > 1.3)")
    report.add(13, "SLA breach rate is worse on high-strain days",
               bool(ratio > 1.3 and high_tta > normal_tta), detail)


def check_acquisition_quality(report: Report, typed: Dict[str, pd.DataFrame]) -> None:
    """Referral and Organic must demonstrably out-repeat paid social."""
    customers = typed["dim_customer"]
    table = (customers.groupby("AcquisitionChannel")
             .agg(Customers=("CustomerKey", "count"),
                  AvgBookings=("TotalBookings", "mean"),
                  RepeatRate=("TotalBookings", lambda s: float((s >= 2).mean())),
                  AvgLTV=("LifetimeValueINR", "mean"))
             .sort_values("RepeatRate", ascending=False))

    lines = [f"{'channel':<22}{'customers':>11}{'avg bookings':>14}"
             f"{'repeat rate':>13}{'avg LTV INR':>14}"]
    for name, row in table.iterrows():
        lines.append(f"{name:<22}{int(row['Customers']):>11,}{row['AvgBookings']:>14.2f}"
                     f"{row['RepeatRate']:>13.1%}{row['AvgLTV']:>14,.0f}")

    referral = table.loc["Referral", "RepeatRate"]
    organic = table.loc["Organic Search", "RepeatRate"]
    meta = table.loc["Meta Ads", "RepeatRate"]
    google = table.loc["Google Ads", "RepeatRate"]
    ltv_gap = table.loc["Referral", "AvgLTV"] / table.loc["Meta Ads", "AvgLTV"]

    lines.append("")
    lines.append(f"Referral repeat {referral:.1%} and Organic {organic:.1%} "
                 f"vs Meta Ads {meta:.1%} and Google Ads {google:.1%}")
    lines.append(f"Referral LTV is {ltv_gap:.2f}x Meta Ads LTV")

    passed = referral > meta and organic > meta and referral > google and organic > google
    report.add(14, "Referral and Organic out-repeat paid social", bool(passed), "\n".join(lines))


def check_payment_mix(report: Report, typed: Dict[str, pd.DataFrame]) -> None:
    """India is UPI-first, and the payments slide has to show it."""
    b = typed["fact_bookings"]
    mix = b["PaymentMode"].value_counts(normalize=True)
    lines = [f"{'payment mode':<18}{'share':>10}{'bookings':>12}"]
    counts = b["PaymentMode"].value_counts()
    for mode in config.PAYMENT_MODES:
        lines.append(f"{mode:<18}{mix.get(mode, 0):>10.1%}{counts.get(mode, 0):>12,}")

    upi = float(mix.get("UPI", 0.0))
    lines.append("")
    lines.append(f"UPI share = {upi:.1%} (target ~58%)")
    dominant = upi == mix.max()
    report.add(15, "Payment mix is UPI-dominant at roughly 58%",
               bool(0.53 <= upi <= 0.63 and dominant), "\n".join(lines))


def check_totals(report: Report, typed: Dict[str, pd.DataFrame]) -> None:
    """The headline money for the whole period."""
    b = typed["fact_bookings"]
    completed = b[b["BookingStatus"] == "Completed"]
    gmv = float(b["FinalAmountINR"].sum())
    revenue = float(b["PlatformRevenueINR"].sum())
    material = float(b["MaterialCostINR"].sum())
    take_rate = revenue / gmv if gmv else 0.0
    aov = gmv / len(completed) if len(completed) else 0.0

    def crore(value: float) -> str:
        return f"{value / 1e7:,.2f} Cr"

    detail = (f"GMV                    INR {gmv:>16,.0f}   ({crore(gmv)})\n"
              f"Platform revenue       INR {revenue:>16,.0f}   ({crore(revenue)})\n"
              f"Material cost          INR {material:>16,.0f}   ({crore(material)})\n"
              f"Net of material        INR {gmv - material:>16,.0f}\n"
              f"Blended take rate      {take_rate:>19.2%}\n"
              f"Average order value    INR {aov:>16,.0f}\n"
              f"Completed jobs         {len(completed):>20,}")
    report.add(16, "Total GMV and platform revenue for the full period",
               bool(gmv > 0 and revenue > 0 and 0.10 < take_rate < 0.25), detail)


# ---------------------------------------------------------------------------
# Formatting guard
# ---------------------------------------------------------------------------
def check_csv_formatting(raw: Dict[str, pd.DataFrame]) -> Tuple[bool, str]:
    """No forbidden cell values, and no integer written with a decimal point.

    This is a cell-exact check rather than a substring scan, because plenty of
    perfectly good Bengaluru names contain the letters n-a-n.
    """
    integer_columns = {
        "dim_date": ["DateKey", "Year", "MonthNo", "MonthYearSort", "WeekNo", "DayOfWeekNo",
                     "IsWeekend", "IsMonsoon", "IsFestivalWindow", "IsMonthEnd", "IsHoliday",
                     "DaysFromToday"],
        "dim_service": ["ServiceKey", "BasePriceINR", "AvgDurationMins", "IsEmergency",
                        "ServiceSortOrder"],
        "dim_area": ["AreaKey", "AreaSortOrder"],
        "dim_professional": ["ProKey", "HomeAreaKey", "IsBackgroundVerified", "IsActive",
                             "LifetimeJobs"],
        "dim_customer": ["CustomerKey", "AreaKey", "IsAppUser", "TotalBookings"],
        "dim_model": ["ModelKey", "IsBusinessCritical"],
        "fact_bookings": ["DateKey", "CustomerKey", "ProKey", "ServiceKey", "AreaKey",
                          "TimeToAssignMins", "ResponseTimeMins", "JobDurationMins",
                          "SLAMetFlag", "CustomerRating", "IsRepeatCustomer",
                          "PredictedPriceINR", "PredictedETAMins", "ActualETAMins",
                          "IsFirstTimeFix", "ReopenedWithin7Days"],
        "fact_pro_capacity": ["DateKey", "ProKey", "AreaKey", "SlotsAvailable", "SlotsBooked",
                              "IsOnline", "HoursLoggedMins", "AcceptedJobs", "RejectedJobs"],
        "fact_leads": ["DateKey", "AreaKey", "ServiceKey", "Searches", "Leads",
                       "QuotesSent", "Bookings"],
        "fact_model_metrics": ["DateKey", "ModelKey", "IsBreach", "PredictionVolume",
                               "P95LatencyMs", "TrainingDataAgeDays"],
        "fact_forecast_accuracy": ["DateKey", "AreaKey", "ActualJobs"],
    }

    problems: List[str] = []
    for table, frame in raw.items():
        for column in frame.columns:
            values = frame[column]
            offenders = values[values.isin(FORBIDDEN_CELLS)]
            if len(offenders):
                problems.append(f"{table}.{column}: {len(offenders)} forbidden cells")
        for column in integer_columns.get(table, []):
            values = frame[column]
            populated = values[values != ""]
            bad = populated[~populated.str.fullmatch(r"-?\d+")]
            if len(bad):
                problems.append(f"{table}.{column}: {len(bad)} non-integer values "
                                f"(e.g. {bad.iloc[0]!r})")

    # BOM guard: Power Query will happily import a BOM as part of the first
    # column name, which then silently breaks every relationship.
    for table in raw:
        with open(config.DATA_DIR / f"{table}.csv", "rb") as handle:
            if handle.read(3) == b"\xef\xbb\xbf":
                problems.append(f"{table}.csv starts with a UTF-8 BOM")

    return not problems, "\n".join(problems)


def file_summary() -> str:
    lines = [f"{'file':<30}{'rows':>12}{'columns':>10}{'size':>14}"]
    total_rows = 0
    total_bytes = 0
    for table in config.TABLES:
        path = config.DATA_DIR / f"{table}.csv"
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False)
        size = path.stat().st_size
        total_rows += len(frame)
        total_bytes += size
        lines.append(f"{table + '.csv':<30}{len(frame):>12,}{len(frame.columns):>10}"
                     f"{size / 1024:>12,.0f} KB")
    lines.append("-" * 66)
    lines.append(f"{'TOTAL':<30}{total_rows:>12,}{'':>10}{total_bytes / 1024 / 1024:>12,.1f} MB")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    missing = [t for t in config.TABLES
               if not (config.DATA_DIR / f"{t}.csv").exists()]
    if missing:
        print("Missing CSVs: " + ", ".join(missing))
        print("Run:  python generator/generate.py")
        return 1

    header("Seek My Service - data validation")
    print(f"data folder: {config.DATA_DIR}")

    raw, typed = load_all()
    report = Report()

    section("Integrity checks")
    check_referential_integrity(report, typed)
    check_date_continuity(report, typed)
    check_amounts(report, typed)
    check_completed_only_columns(report, raw)
    check_date_ordering(report, typed)
    check_rating_pairing(report, raw)
    check_funnel(report, typed)
    check_capacity_reconciliation(report, typed)

    section("Shape, story and money")
    check_row_counts(report, typed)
    context = check_monthly_growth(report, typed)
    check_seasonal_signatures(report, context)
    check_drift_incident(report, typed)
    check_strain_sla(report, typed)
    check_acquisition_quality(report, typed)
    check_payment_mix(report, typed)
    check_totals(report, typed)

    section("CSV formatting guard")
    formatting_ok, formatting_detail = check_csv_formatting(raw)
    print(f"  [{'PASS' if formatting_ok else 'FAIL'}]  *. No nan / NULL cells, "
          f"no integer written with a decimal point, no BOM")
    if formatting_detail:
        for line in formatting_detail.splitlines():
            print(f"         {line}")

    section("File summary")
    print(file_summary())

    header("Validation summary")
    passed = sum(1 for r in report.results if r[2])
    print(f"{passed} of {len(report.results)} checks passed, "
          f"formatting guard {'passed' if formatting_ok else 'FAILED'}")
    if report.failed:
        print()
        for number, title, _, _ in report.failed:
            print(f"  FAILED {number:>2}. {title}")
    print()

    return 0 if (report.all_passed and formatting_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
