"""
ML Model Health.

The question: are the eight models in production still doing their job, and
would we know if one stopped?

This page is built around a real failure sequence with four beats, because a
monitoring dashboard that only ever shows green teaches people to stop looking
at it.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app import components as ui, data, theme
from generator import config

FORECASTER = "demand_forecaster"


def render(filters: data.Filters) -> None:
    metrics = data.model_metrics()
    metrics = metrics[(metrics["Date"] >= pd.Timestamp(filters.start))
                      & (metrics["Date"] <= pd.Timestamp(filters.end))]
    forecast = data.apply(data.forecast_accuracy(), filters,
                          use_category=False, use_tier=False)

    ui.page_header(
        "ML Model Health",
        "Are the eight models in production still doing their job — and would we "
        "know if one stopped?",
        filters.label,
    )

    if metrics.empty:
        ui.empty_state("No model telemetry in this date range.")
        return

    models_in_breach = int(metrics.loc[metrics["IsBreach"] == 1, "ModelKey"].nunique())
    avg_psi = float(metrics["PSIDriftScore"].mean())
    max_age = int(metrics["TrainingDataAgeDays"].max())
    volume = int(metrics["PredictionVolume"].sum())

    mape = float(forecast["APE"].mean()) if not forecast.empty else np.nan
    wape = (float(forecast["AbsError"].sum() / forecast["ActualJobs"].sum())
            if not forecast.empty and forecast["ActualJobs"].sum() else np.nan)
    phantom = int((forecast["ActualJobs"] == 0).sum()) if not forecast.empty else 0

    ui.kpi_row([
        ("Models in breach", f"{models_in_breach}", "over this period",
         theme.BAD if models_in_breach > 2 else theme.WARN if models_in_breach else theme.GOOD),
        ("Avg PSI drift", f"{avg_psi:.3f}", f"alert at {data.PSI_THRESHOLD}"),
        ("Forecast MAPE", theme.pct(mape) if mape == mape else "-"),
        ("Forecast WAPE", theme.pct(wape) if wape == wape else "-",
         "see below", theme.BAD),
        ("Max training age", f"{max_age}", "days", theme.BAD if max_age > 30 else None),
        ("Predictions served", f"{volume:,}"),
    ])

    # ------------------------------------------------------------ scorecard
    ui.section("Model scorecard",
               "Each model against its own goal, in its own units. Never total the "
               "value column — 12.0 is percentage points of error, 0.82 is an NDCG "
               "and 14.0 is minutes.")

    latest = (metrics.sort_values("Date")
              .groupby("ModelName", as_index=False, observed=True)
              .agg(Metric=("PrimaryMetric", "last"),
                   Value=("MetricValue", "mean"),
                   Goal=("MetricGoal", "last"),
                   Direction=("GoalDirection", "last"),
                   PSI=("PSIDriftScore", "mean"),
                   Age=("TrainingDataAgeDays", "max"),
                   Owner=("OwnerTeam", "last"),
                   Critical=("IsBusinessCritical", "last"),
                   Version=("ModelVersion", "last")))
    latest["Status"] = latest.apply(
        lambda r: data.model_status(r["Value"], r["Goal"], r["Direction"]), axis=1)
    latest = latest.sort_values(
        ["Critical", "Status"], ascending=[False, True])

    display = latest[["ModelName", "Metric", "Value", "Goal", "Status",
                      "PSI", "Age", "Owner", "Version"]].copy()
    display["Value"] = display["Value"].map(lambda v: f"{v:.3f}")
    display["Goal"] = display["Goal"].map(lambda v: f"{v:.2f}")
    display["PSI"] = display["PSI"].map(lambda v: f"{v:.3f}")
    display.columns = ["Model", "Metric", "Value", "Goal", "Status",
                       "PSI drift", "Train age", "Owner", "Version"]

    def colour_status(value: str) -> str:
        return f"color: {theme.status_colour(value)}; font-weight: 600"

    st.dataframe(
        display.style.map(colour_status, subset=["Status"]),
        width="stretch", hide_index=True, height=320,
    )

    # ------------------------------------------------------- the incident
    forecaster = metrics[metrics["ModelName"] == FORECASTER].sort_values("Date")
    if forecaster.empty:
        return

    st.markdown("---")
    ui.section("The June 2026 incident, in four beats",
               "A silent pipeline failure, a latent risk, a regime change that "
               "exposed it, and a recovery. Read the charts left to right.")

    beat1, beat2 = st.columns(2, gap="large")

    with beat1:
        st.markdown("##### Beat 1 · The root cause, four months early")
        st.markdown(
            f"<div class='sec-note'>How old the training data behind live "
            f"predictions was, day by day.</div>", unsafe_allow_html=True)
        fig = px.area(forecaster, x="Date", y="TrainingDataAgeDays")
        fig.update_traces(line=dict(color=theme.CATEGORICAL[1], width=1.5),
                          fillcolor="rgba(224,122,62,0.22)")
        theme.style(fig, height=280, legend=False, y_title="Days since last retrain")
        _mark(fig, config.RETRAIN_SILENT_FAILURE_DATE, "retrain job stops", theme.BAD)
        _mark(fig, config.RETRAIN_FIX_DATE, "retrain lands", theme.GOOD)
        ui.chart(fig)
        ui.finding(
            "That sawtooth is the weekly retrain working — climb to seven days, "
            "reset, climb again. On <b>15 March 2026</b> it stops and just climbs, "
            f"reaching <b>{int(forecaster['TrainingDataAgeDays'].max())} days</b>. "
            "The retrain job failed silently and <b>nothing alerted</b>, because the "
            "model kept returning predictions the whole time.",
            "bad")

    with beat2:
        st.markdown("##### Beat 2 · Accuracy, which held for three months")
        st.markdown(
            "<div class='sec-note'>Mean absolute percentage error against its "
            "12% goal.</div>", unsafe_allow_html=True)
        fig = px.line(forecaster, x="Date", y="MetricValue")
        fig.update_traces(line=dict(color=theme.PRIMARY, width=1.6))
        theme.style(fig, height=280, legend=False, y_title="MAPE (%)")
        theme.hline(fig, float(forecaster["MetricGoal"].iloc[0]), "goal 12%")
        _mark(fig, config.DRIFT_ONSET_DATE, "monsoon begins", theme.WARN)
        _mark(fig, config.RETRAIN_FIX_DATE, "retrain", theme.GOOD)
        ui.chart(fig)

        plateau = forecaster[
            (forecaster["Date"] >= pd.Timestamp(config.DRIFT_FULL_DATE))
            & (forecaster["Date"] < pd.Timestamp(config.RETRAIN_FIX_DATE))]
        before = forecaster[forecaster["Date"] < pd.Timestamp(config.DRIFT_ONSET_DATE)]
        after = forecaster[forecaster["Date"] >= pd.Timestamp(config.RETRAIN_FIX_DATE)
                           + pd.Timedelta(days=config.RETRAIN_RECOVERY_DAYS)]
        if not plateau.empty and not before.empty:
            ui.finding(
                f"Flat at about <b>{before['MetricValue'].mean():.1f}%</b> for over a "
                f"year — including three months while the model was already stale. "
                f"The monsoon changed the demand regime on 1 June and error climbed "
                f"to a plateau of <b>{plateau['MetricValue'].mean():.1f}%</b>. "
                + (f"After the retrain it recovered to "
                   f"<b>{after['MetricValue'].mean():.1f}%</b> within days."
                   if not after.empty else ""),
                "warn")

    beat3, beat4 = st.columns(2, gap="large")

    with beat3:
        st.markdown("##### Beat 3 · The monitor that finally fired")
        st.markdown(
            "<div class='sec-note'>Population stability index — how far the live "
            "input distribution has moved from the training one.</div>",
            unsafe_allow_html=True)
        fig = px.line(forecaster, x="Date", y="PSIDriftScore")
        fig.update_traces(line=dict(color=theme.CATEGORICAL[4], width=1.6))
        theme.style(fig, height=270, legend=False, y_title="PSI")
        theme.hline(fig, data.PSI_THRESHOLD, f"alert threshold {data.PSI_THRESHOLD}")
        ui.chart(fig)

    with beat4:
        st.markdown("##### Beat 4 · Forecast against what actually happened")
        st.markdown(
            "<div class='sec-note'>Monthly totals across every area and "
            "category.</div>", unsafe_allow_html=True)
        if not forecast.empty:
            by_month = (forecast.groupby(["MonthYearSort", "MonthYear"], as_index=False, observed=True)
                        .agg(Forecast=("ForecastedJobs", "sum"),
                             Actual=("ActualJobs", "sum")).sort_values("MonthYearSort"))
            fig = go.Figure()
            fig.add_bar(x=by_month["MonthYear"], y=by_month["Actual"],
                        name="Actual jobs", marker_color=theme.PRIMARY)
            fig.add_scatter(x=by_month["MonthYear"], y=by_month["Forecast"],
                            name="Forecast", mode="lines+markers",
                            line=dict(color=theme.CATEGORICAL[1], width=2))
            theme.style(fig, height=270)
            ui.chart(fig)

    ui.finding(
        "<b>The gap that matters is March to June.</b> The model was broken in March "
        "and only looked broken in June, because degradation needs staleness "
        "<i>plus</i> a change in the world — and between March and June the world did "
        "not change. The monsoon was the trigger, not the cause. The metric that "
        "would have caught it on 29 March is <b>training-data age</b>: one column, "
        "already collected, on every model. Almost nobody monitors it.",
        "bad")

    # ------------------------------------------------------ the phantom cells
    if not forecast.empty and mape == mape and wape == wape:
        st.markdown("---")
        ui.section("The finding MAPE cannot see",
                   "Two error metrics on the same model, both correct, telling "
                   "opposite stories.")

        real_jobs = int(forecast["ActualJobs"].sum())
        phantom_jobs = float(forecast.loc[forecast["ActualJobs"] == 0, "ForecastedJobs"].sum())
        live_cells = int((forecast["ActualJobs"] > 0).sum())

        left, right = st.columns([1, 1.2], gap="large")

        with left:
            fig = go.Figure()
            fig.add_bar(x=["MAPE", "WAPE"], y=[mape, wape],
                        marker_color=[theme.GOOD, theme.BAD],
                        text=[theme.pct(mape), theme.pct(wape)],
                        textposition="outside")
            theme.style(fig, height=280, legend=False, y_tickformat=".0%",
                        y_title="Error")
            fig.update_yaxes(range=[0, max(mape, wape) * 1.35])
            ui.chart(fig)

        with right:
            fig = go.Figure()
            fig.add_bar(y=["Cells"], x=[live_cells], name="Real demand",
                        orientation="h", marker_color=theme.PRIMARY)
            fig.add_bar(y=["Cells"], x=[phantom], name="Forecast, nothing arrived",
                        orientation="h", marker_color=theme.BAD)
            fig.add_bar(y=["Jobs"], x=[real_jobs], name="Real jobs",
                        orientation="h", marker_color=theme.PRIMARY, showlegend=False)
            fig.add_bar(y=["Jobs"], x=[phantom_jobs], name="Phantom jobs",
                        orientation="h", marker_color=theme.BAD, showlegend=False)
            fig.update_layout(barmode="stack")
            theme.style(fig, height=280, x_title="Count")
            ui.chart(fig)

        ui.finding(
            f"MAPE says <b>{theme.pct(mape)}</b>, which reads as a healthy model. "
            f"WAPE says <b>{theme.pct(wape)}</b>. Both are correct. The entire "
            f"difference is <b>{phantom:,} day-area-category cells where the model "
            f"forecast demand and nothing arrived at all</b> — about "
            f"{phantom_jobs:,.0f} phantom jobs against {real_jobs:,} real ones. "
            f"MAPE structurally cannot see them: a cell with zero actual jobs has no "
            f"denominator, so it is dropped from the average entirely.<br/><br/>"
            f"Every one of those is, in principle, a technician told to be somewhere "
            f"with no work. A monitoring page reporting only MAPE would have called "
            f"this model healthy for the whole period.",
            "bad")


def _mark(fig: go.Figure, when: dt.date, label: str, colour: str) -> None:
    """A dated vertical marker with a label."""
    fig.add_vline(x=pd.Timestamp(when), line_dash="dot", line_color=colour,
                  line_width=1.5, annotation_text=label,
                  annotation_position="top left",
                  annotation_font=dict(size=10, color=colour))
