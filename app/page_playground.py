"""
Model Playground.

Live predictions from the three trained models. This is the page a report
cannot do: pick an area and a date, and watch the actual fitted model respond.

The services are imported and called in-process rather than over HTTP, so the
whole app is one deployable process. The FastAPI wrappers still exist and are
still the production interface - this page just skips the network hop.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from fastapi import HTTPException

from app import components as ui, data, theme
from generator import config
from ml import forecast_service, match_service, pricing_service
from ml.common import io as mlio

# The forecaster needs 28 days of lag history and a 7-day forward target, so
# only dates inside that window have a complete feature row.
USABLE_START = config.DATE_START + dt.timedelta(days=29)
USABLE_END = config.DATE_END - dt.timedelta(days=8)
DEFAULT_DATE = dt.date(2026, 7, 15)


@st.cache_resource(show_spinner=False)
def ensure_models_trained() -> dict:
    """Train anything missing, once per session.

    Artefacts are gitignored - they are regenerated in about ten seconds - so a
    fresh clone or a cloud deploy arrives with none of them.
    """
    trained = {}
    jobs = [
        ("demand_forecaster", forecast_service.train),
        ("pro_match_ranker", match_service.train),
        ("dynamic_price_engine", pricing_service.train),
    ]
    missing = [name for name, _ in jobs if not mlio.artifact_exists(name)]
    if missing:
        with st.spinner(f"Training {len(missing)} model(s) for the first time — "
                        f"about 15 seconds..."):
            for name, trainer in jobs:
                if not mlio.artifact_exists(name):
                    trainer(fast=False, verbose=False)
    for module in (forecast_service, match_service, pricing_service):
        module.reset_state()
    for name, _ in jobs:
        trained[name] = mlio.load_metrics(name) or {}
    return trained


def render(filters: data.Filters) -> None:
    ui.page_header(
        "Model Playground",
        "Live predictions from the three trained models. Change an input and the "
        "actual fitted model responds — nothing here is pre-computed.",
    )

    metrics = ensure_models_trained()

    areas = data.areas()
    area_names = dict(zip(areas["AreaName"], areas["AreaKey"]))
    categories = list(config.CATEGORY_ORDER)

    forecast_tab, match_tab, price_tab = st.tabs([
        "Demand forecast", "Technician matching", "Dynamic pricing",
    ])

    # =======================================================================
    with forecast_tab:
        _forecast(area_names, categories, metrics.get("demand_forecaster", {}))

    # =======================================================================
    with match_tab:
        _match(area_names, categories, metrics.get("pro_match_ranker", {}))

    # =======================================================================
    with price_tab:
        _pricing(area_names, metrics.get("dynamic_price_engine", {}))


# ---------------------------------------------------------------------------
def _date_input(key: str) -> dt.date:
    return st.date_input(
        "As-of date", value=DEFAULT_DATE,
        min_value=USABLE_START, max_value=USABLE_END, key=key,
        help="The forecast covers the seven days after this date.",
    )


def _forecast(area_names: dict, categories: list, metrics: dict) -> None:
    st.markdown("#### How many jobs will this area need next week?")
    st.markdown(
        "<div class='sec-note'>LightGBM Poisson regression with a log exposure "
        "offset. The model predicts a <i>multiplier</i> on the recent baseline "
        "rather than an absolute count, because boosted trees cannot extrapolate "
        "a growth trend — the first version came back with a −40% bias.</div>",
        unsafe_allow_html=True)

    controls, output = st.columns([1, 2], gap="large")

    with controls:
        area_name = st.selectbox("Area", sorted(area_names), index=0, key="f_area")
        category = st.selectbox("Service category", categories,
                                index=categories.index("Plumber"), key="f_cat")
        as_of = _date_input("f_date")

    try:
        result = forecast_service.predict_one(area_names[area_name], category, as_of)
    except HTTPException as exc:
        with output:
            st.warning(f"{exc.detail}")
        return

    with output:
        ui.kpi_row([
            ("Predicted jobs, next 7 days", f"{result['predicted_jobs']:.1f}",
             f"range {result['prediction_interval_low']:.1f} – "
             f"{result['prediction_interval_high']:.1f}"),
            ("Recent daily average", f"{result['recent_daily_average']:.2f}",
             "trailing 28 days"),
            ("Seasonal multiplier", f"{result['seasonal_multiplier']:.2f}×",
             "monsoon" if result["is_monsoon"] else "off season"),
        ])

    # Show the prediction in the context of what actually happened.
    panel = data.bookings()
    history = panel[(panel["AreaKey"] == area_names[area_name])
                    & (panel["ServiceCategory"] == category)]
    daily = (history.groupby("Date").size().rename("Jobs").reset_index())
    window_start = pd.Timestamp(as_of) - pd.Timedelta(days=56)
    window_end = pd.Timestamp(as_of) + pd.Timedelta(days=7)
    daily = daily[(daily["Date"] >= window_start) & (daily["Date"] <= window_end)]

    rolling = daily.set_index("Date")["Jobs"].rolling(7).sum().reset_index()
    rolling.columns = ["Date", "Rolling7"]

    fig = go.Figure()
    fig.add_bar(x=daily["Date"], y=daily["Jobs"], name="Jobs that day",
                marker_color=theme.LINE)
    fig.add_scatter(x=rolling["Date"], y=rolling["Rolling7"], name="Actual 7-day total",
                    mode="lines", line=dict(color=theme.PRIMARY, width=2))
    fig.add_scatter(
        x=[pd.Timestamp(as_of) + pd.Timedelta(days=7)],
        y=[result["predicted_jobs"]], name="Model prediction",
        mode="markers",
        marker=dict(size=14, color=theme.CATEGORICAL[1], symbol="diamond",
                    line=dict(color="white", width=2)),
        error_y=dict(
            type="data", symmetric=False,
            array=[result["prediction_interval_high"] - result["predicted_jobs"]],
            arrayminus=[result["predicted_jobs"] - result["prediction_interval_low"]],
            color=theme.CATEGORICAL[1], thickness=1.5, width=6),
    )
    fig.add_vline(x=pd.Timestamp(as_of), line_dash="dot", line_color=theme.MUTED,
                  annotation_text="you are here", annotation_position="top left",
                  annotation_font=dict(size=10, color=theme.MUTED))
    theme.style(fig, height=330, y_title="Jobs")
    ui.chart(fig)

    actual = float(daily[(daily["Date"] > pd.Timestamp(as_of))
                         & (daily["Date"] <= pd.Timestamp(as_of) + pd.Timedelta(days=7))
                         ]["Jobs"].sum())
    error = abs(result["predicted_jobs"] - actual)
    ui.finding(
        f"For {area_name} · {category}, the model predicted "
        f"<b>{result['predicted_jobs']:.1f}</b> jobs for the seven days after "
        f"{as_of.strftime('%d %b %Y')}. What actually happened: <b>{actual:.0f}</b>. "
        f"Absolute error <b>{error:.1f} jobs</b>"
        + (f" ({error / actual:.0%})." if actual else "."),
        "good" if actual and error / max(actual, 1) < 0.25 else "warn")

    _metric_footer(metrics, [
        ("mape_area_grain", "Held-out MAPE at area grain", "pct"),
        ("mape", "MAPE at cell grain", "pct"),
        ("mape_noise_floor", "Irreducible Poisson noise floor", "pct"),
        ("bias", "Bias", "signed_pct"),
    ], note="Cell-grain MAPE looks poor until you compare it with the noise floor "
            "beside it. At day × area × category the mean target is single digits, "
            "so most of that error is counting noise no model can remove.")


# ---------------------------------------------------------------------------
def _match(area_names: dict, categories: list, metrics: dict) -> None:
    st.markdown("#### Which technician should get this job?")
    st.markdown(
        "<div class='sec-note'>LightGBM LambdaRank — a learning-to-rank model, the "
        "same family used for search results. It does not predict a number; it "
        "learns to order a list.</div>", unsafe_allow_html=True)

    controls, output = st.columns([1, 2], gap="large")

    with controls:
        area_name = st.selectbox("Job location", sorted(area_names), index=0, key="m_area")
        category = st.selectbox("Service category", categories,
                                index=categories.index("Plumber"), key="m_cat")
        as_of = _date_input("m_date")
        emergency = st.toggle("Emergency call-out", value=False, key="m_emerg")
        top_n = st.slider("Shortlist size", 3, 10, 5, key="m_top")

    try:
        result = match_service.rank_candidates(
            area_names[area_name], category, as_of, emergency, top_n)
    except HTTPException as exc:
        with output:
            st.warning(f"{exc.detail}")
        return

    ranked = pd.DataFrame([r.model_dump() for r in result["ranked"]])

    with output:
        ui.kpi_row([
            ("Candidates considered", f"{result['candidates_considered']:,}",
             "online with a free slot"),
            ("Shortlisted", f"{len(ranked)}"),
            ("Top match", ranked.iloc[0]["pro_name"] if not ranked.empty else "-",
             f"{ranked.iloc[0]['skill_tier']} · {ranked.iloc[0]['avg_rating']:.2f}★"
             if not ranked.empty else ""),
        ])

    if ranked.empty:
        return

    left, right = st.columns([1.3, 1], gap="large")

    with left:
        display = ranked[["rank", "pro_name", "skill_tier", "avg_rating",
                          "home_area", "distance_km", "category_match",
                          "load_ratio", "score"]].copy()
        display["avg_rating"] = display["avg_rating"].map(lambda v: f"{v:.2f}")
        display["distance_km"] = display["distance_km"].map(lambda v: f"{v:.1f} km")
        display["load_ratio"] = display["load_ratio"].map(theme.pct)
        display["score"] = display["score"].map(lambda v: f"{v:+.2f}")
        display["category_match"] = display["category_match"].map(
            {True: "yes", False: "no"})
        display.columns = ["#", "Technician", "Tier", "Rating", "Based in",
                           "Distance", "Right trade", "Load", "Score"]
        st.dataframe(display, width="stretch", hide_index=True)

    with right:
        fig = px.bar(ranked.sort_values("score"), x="score", y="pro_name",
                     orientation="h", color="skill_tier",
                     color_discrete_map=theme.SKILL_COLOURS)
        theme.style(fig, height=max(220, 42 * len(ranked)),
                    x_title="Ranking score")
        fig.update_yaxes(title_text="")
        ui.chart(fig)

    top = ranked.iloc[0]
    ui.finding(
        f"The model ranked <b>{top['pro_name']}</b> first out of "
        f"{result['candidates_considered']:,} technicians who were online with a "
        f"free slot: {top['skill_tier']} tier, {top['avg_rating']:.2f}★, "
        f"{top['distance_km']:.1f} km away, "
        f"{'the right trade' if top['category_match'] else 'a different trade'}, "
        f"currently {theme.pct(top['load_ratio'])} loaded. The strongest features "
        f"in the model are category match, current load and distance.")

    _metric_footer(metrics, [
        ("ndcg_at_5", "Held-out NDCG@5", "num"),
        ("ndcg_at_1", "NDCG@1", "num"),
        ("recall_at_1", "Chosen technician ranked first", "pct"),
        ("random_baseline_ndcg_at_5", "Random baseline", "num"),
    ], note="This score is optimistic and should be quoted with the caveat. The "
            "data generator assigns jobs using a known function of these same "
            "features, so the model is recovering a process rather than learning "
            "a messy human one. On production data, expect materially worse.",
        kind="warn")


# ---------------------------------------------------------------------------
def _pricing(area_names: dict, metrics: dict) -> None:
    st.markdown("#### What should we quote?")
    st.markdown(
        "<div class='sec-note'>Three LightGBM quantile regressors at the 10th, 50th "
        "and 90th percentile. A single number would hide real uncertainty; the "
        "business decision is what <i>range</i> to quote.</div>",
        unsafe_allow_html=True)

    services = data.services()
    labels = {f"{r.ServiceCategory} · {r.ServiceName}": r.ServiceKey
              for r in services.itertuples()}

    controls, output = st.columns([1, 2], gap="large")

    with controls:
        service_label = st.selectbox("Service", list(labels), index=10, key="p_svc")
        area_name = st.selectbox("Area", sorted(area_names), index=0, key="p_area")
        as_of = _date_input("p_date")
        hour = st.slider("Booking hour", 0, 23, 10, key="p_hour")
        discount = st.slider("Coupon discount", 0.0, 0.30, 0.10, 0.05,
                             format="%.0f%%", key="p_disc")

    try:
        result = pricing_service.quote(
            labels[service_label], area_names[area_name], as_of, hour, discount)
    except HTTPException as exc:
        with output:
            st.warning(f"{exc.detail}")
        return

    with output:
        ui.kpi_row([
            ("Quote this", f"₹{theme.inr(result['price_mid_inr'])}",
             "median estimate"),
            ("Band", f"₹{theme.inr(result['price_low_inr'])} – "
                     f"₹{theme.inr(result['price_high_inr'])}",
             f"width {theme.pct(result['band_width_pct'])} of mid"),
            ("Catalogue base", f"₹{theme.inr(result['base_price_inr'])}",
             f"seasonal {result['seasonal_multiplier']:.2f}×"),
        ])

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[result["price_high_inr"] - result["price_low_inr"]],
        y=["Price"], base=[result["price_low_inr"]], orientation="h",
        marker_color="rgba(42,111,181,0.20)", name="10th–90th percentile",
        hovertemplate="band ₹%{base:,.0f} – ₹%{x:,.0f}<extra></extra>"))
    for value, colour, label in (
        (result["price_low_inr"], theme.FAINT, "low"),
        (result["price_mid_inr"], theme.PRIMARY, "quote"),
        (result["price_high_inr"], theme.FAINT, "high"),
    ):
        fig.add_scatter(x=[value], y=["Price"], mode="markers+text",
                        marker=dict(size=16 if label == "quote" else 10,
                                    color=colour, symbol="line-ns",
                                    line=dict(width=3, color=colour)),
                        text=[f"₹{theme.inr(value)}"],
                        textposition="top center",
                        textfont=dict(size=11, color=colour),
                        showlegend=False, hoverinfo="skip")
    fig.add_vline(x=result["base_price_inr"], line_dash="dot",
                  line_color=theme.MUTED,
                  annotation_text="catalogue base",
                  annotation_font=dict(size=10, color=theme.MUTED))
    theme.style(fig, height=200, legend=False, x_title="INR")
    fig.update_yaxes(showticklabels=False)
    ui.chart(fig)

    ui.finding(
        f"<b>{result['service_name']}</b> in {result['area_name']} on "
        f"{as_of.strftime('%d %b %Y')}: quote <b>₹{theme.inr(result['price_mid_inr'])}</b>, "
        f"with a defensible range of ₹{theme.inr(result['price_low_inr'])} to "
        f"₹{theme.inr(result['price_high_inr'])}. The catalogue base is "
        f"₹{theme.inr(result['base_price_inr'])}; the difference is area income band, "
        f"season ({result['seasonal_multiplier']:.2f}×) and "
        f"{'emergency premium' if result['is_emergency'] else 'no emergency premium'}.")

    st.markdown(
        f"<div class='sec-note'>The model also returns an accept probability of "
        f"<b>{theme.pct(result['accept_probability'])}</b> — "
        f"<b>ignore it.</b> See the note below.</div>", unsafe_allow_html=True)

    _metric_footer(metrics, [
        ("median_mape", "Held-out price MAPE", "pct"),
        ("median_mae_inr", "Median absolute error", "inr"),
        ("band_coverage", "10–90 band coverage (target 80%)", "pct"),
        ("accept_auc", "Accept probability AUC", "num"),
    ], note="The price band is sound: coverage lands within two points of its 80% "
            "target with zero quantile crossings. The accept-probability classifier "
            "at AUC 0.527 is <b>not fit to ship</b> — adding operational load "
            "features moved it from 0.530 to 0.527, i.e. not at all. In this "
            "dataset, whether a booking completes is driven by a per-day rain draw "
            "that is not in the feature set. The fix is a weather feed, not more "
            "tuning.",
        kind="warn")


# ---------------------------------------------------------------------------
def _metric_footer(metrics: dict, rows: list, note: str = "",
                   kind: str = "") -> None:
    """Held-out performance for the model behind the tab."""
    if not metrics:
        return
    st.markdown("---")
    st.markdown("##### Held-out performance")
    st.markdown(
        "<div class='sec-note'>Measured on a forward-in-time split, not on the "
        "data the model trained on.</div>", unsafe_allow_html=True)

    tiles = []
    for key, label, kind_fmt in rows:
        if key not in metrics:
            continue
        value = metrics[key]
        if kind_fmt == "pct":
            shown = f"{value * 100:.1f}%"
        elif kind_fmt == "signed_pct":
            shown = f"{value * 100:+.1f}%"
        elif kind_fmt == "inr":
            shown = f"₹{theme.inr(value)}"
        else:
            shown = f"{value:.3f}"
        tiles.append((label, shown))
    if tiles:
        ui.kpi_row(tiles)
    if note:
        st.markdown("")
        ui.finding(note, kind)
