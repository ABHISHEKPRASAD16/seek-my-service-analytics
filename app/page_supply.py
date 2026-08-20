"""
Supply Health.

The question: do we have the right technicians, in the right places, doing
enough work?

The finding: platform-wide utilisation looks like massive oversupply. Split it
by trade and season and it stops being an oversupply story and becomes an
allocation story - which is a far cheaper problem to fix.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app import components as ui, data, theme

AT_RISK_RATING = 4.0


def render(filters: data.Filters) -> None:
    # Capacity carries the technician's own trade, not the booking's category,
    # so category filtering is applied on PrimaryServiceCategory instead.
    cap = data.apply(data.capacity(), filters, use_category=False, use_tier=False)
    if filters.categories:
        cap = cap[cap["PrimaryServiceCategory"].isin(filters.categories)]

    frame = data.apply(data.bookings(), filters)
    pros = data.professionals()

    ui.page_header(
        "Supply Health",
        "Do we have the right technicians, in the right places, doing enough work?",
        filters.scope_label + "  ·  " + filters.label,
    )

    if cap.empty:
        ui.empty_state("No capacity rows match these filters.")
        return

    slots_available = int(cap["SlotsAvailable"].sum())
    slots_booked = int(cap["SlotsBooked"].sum())
    utilisation = slots_booked / slots_available if slots_available else 0.0
    active = int(cap.loc[cap["SlotsBooked"] > 0, "ProKey"].nunique())
    roster = int(cap["ProKey"].nunique())
    accepted = int(cap["AcceptedJobs"].sum())
    rejected = int(cap["RejectedJobs"].sum())
    acceptance = accepted / (accepted + rejected) if (accepted + rejected) else 0.0
    completed = int((frame["IsCompleted"] == 1).sum())

    in_scope = pros[pros["ProKey"].isin(cap["ProKey"].unique())]
    at_risk = int(((in_scope["IsActive"] == 1)
                   & (in_scope["AvgRating"] < AT_RISK_RATING)).sum())
    churned = int((in_scope["IsActive"] == 0).sum())

    ui.kpi_row([
        ("Active technicians", f"{active:,}", f"of {roster:,} on roster"),
        ("Utilisation", theme.pct(utilisation), f"{slots_booked:,} of {slots_available:,} slots"),
        ("Jobs per active tech", f"{completed / active:.1f}" if active else "-"),
        ("Offer acceptance", theme.pct(acceptance)),
        ("At risk", f"{at_risk:,}", f"rated below {AT_RISK_RATING}",
         theme.WARN if at_risk else None),
        ("Churned", f"{churned:,}"),
    ])

    ui.finding(
        f"Utilisation of <b>{theme.pct(utilisation)}</b> looks like three times more "
        f"technicians than the work supports. Hold that thought — the two charts "
        f"below show it is not an oversupply problem at all.")

    # -------------------------------------------------- the allocation story
    ui.section("The monsoon is an allocation problem, not a shortage",
               "The same roster, split by trade and by season. Some trades strain "
               "while others go idle, in the same four months.")

    season = (cap.groupby(["PrimaryServiceCategory", "IsMonsoon"], as_index=False)
              .agg(Available=("SlotsAvailable", "sum"), Booked=("SlotsBooked", "sum")))
    season["Utilisation"] = season["Booked"] / season["Available"].replace(0, np.nan)
    season["Season"] = season["IsMonsoon"].map({0: "Dry season", 1: "Monsoon"})

    left, right = st.columns([1.4, 1], gap="large")

    with left:
        fig = px.bar(season, x="PrimaryServiceCategory", y="Utilisation",
                     color="Season", barmode="group",
                     color_discrete_map={"Dry season": theme.CATEGORICAL[6],
                                         "Monsoon": theme.PRIMARY})
        theme.style(fig, height=330, y_title="Slot utilisation", y_tickformat=".0%")
        fig.update_xaxes(title_text="")
        ui.chart(fig)

    with right:
        wide = season.pivot(index="PrimaryServiceCategory", columns="Season",
                            values="Utilisation")
        if {"Dry season", "Monsoon"} <= set(wide.columns):
            wide["Change"] = wide["Monsoon"] / wide["Dry season"] - 1
            wide = wide.sort_values("Change", ascending=False)
            display = wide.reset_index()
            display.columns = ["Trade", "Dry", "Monsoon", "Change"]
            display["Dry"] = display["Dry"].map(theme.pct)
            display["Monsoon"] = display["Monsoon"].map(theme.pct)
            display["Change"] = display["Change"].map(lambda v: f"{v:+.0%}")
            st.dataframe(display, width="stretch", hide_index=True,
                         height=330)

            risers = wide[wide["Change"] > 0.25].index.tolist()
            fallers = wide[wide["Change"] < -0.05].index.tolist()
            if risers and fallers:
                ui.finding(
                    f"In the monsoon, <b>{', '.join(risers)}</b> strain hard while "
                    f"<b>{', '.join(fallers)}</b> go idle. Same four months, same "
                    f"roster. You do not have a supply shortage — you have "
                    f"<b>idle capacity wearing the wrong tool belt</b>. Cross-training "
                    f"costs a training programme; recruiting plumbers costs a "
                    f"recruitment pipeline, every year, forever.",
                    "good")

    # ------------------------------------------------------- the inequality
    left, right = st.columns([1.3, 1], gap="large")

    with left:
        ui.section("A small number of technicians do most of the work",
                   "Each dot is one technician. Right is capacity they opened; "
                   "up is jobs they actually got.")
        per_pro = (cap.groupby("ProKey", as_index=False)
                   .agg(Available=("SlotsAvailable", "sum"),
                        Booked=("SlotsBooked", "sum"),
                        Tier=("SkillTier", "first"),
                        Name=("ProName", "first"),
                        Rating=("AvgRating", "first")))
        per_pro = per_pro[per_pro["Available"] > 0]
        fig = px.scatter(
            per_pro, x="Available", y="Booked", color="Tier",
            color_discrete_map=theme.SKILL_COLOURS,
            hover_name="Name", hover_data={"Rating": ":.2f", "Tier": False},
            category_orders={"Tier": ["Bronze", "Silver", "Gold", "Platinum"]},
        )
        fig.update_traces(marker=dict(size=7, opacity=0.6, line=dict(width=0)))
        theme.style(fig, height=340, x_title="Slots opened", y_title="Jobs taken")
        ui.chart(fig)

    with right:
        ui.section("Utilisation by tier", "The spread is the story.")
        by_tier = (cap.groupby("SkillTier", as_index=False)
                   .agg(Available=("SlotsAvailable", "sum"),
                        Booked=("SlotsBooked", "sum"),
                        Pros=("ProKey", "nunique")))
        by_tier["Utilisation"] = by_tier["Booked"] / by_tier["Available"]
        order = ["Bronze", "Silver", "Gold", "Platinum"]
        by_tier["SkillTier"] = pd.Categorical(by_tier["SkillTier"], order, ordered=True)
        by_tier = by_tier.sort_values("SkillTier")
        fig = px.bar(by_tier, x="SkillTier", y="Utilisation", color="SkillTier",
                     color_discrete_map=theme.SKILL_COLOURS,
                     hover_data={"Pros": ":,", "Booked": ":,"})
        theme.style(fig, height=340, legend=False, y_tickformat=".0%",
                    y_title="Slot utilisation")
        fig.update_xaxes(title_text="")
        ui.chart(fig)

    jobs = per_pro.sort_values("Booked", ascending=False)["Booked"]
    if len(jobs) > 20 and jobs.sum() > 0:
        top_decile = int(len(jobs) * 0.1)
        top_share = jobs.head(top_decile).sum() / jobs.sum()
        bottom_share = jobs.tail(int(len(jobs) * 0.5)).sum() / jobs.sum()
        ui.finding(
            f"The <b>top 10% of technicians take {theme.pct(top_share)} of all jobs</b>. "
            f"The bottom half take {theme.pct(bottom_share)}. The ranker concentrates "
            f"work on proven people, which is right for the customer today and "
            f"corrosive for supply retention tomorrow — a technician who never gets "
            f"work churns. An exploration floor, reserving a small share of offers "
            f"for under-used but adequately-rated technicians, is the standard remedy "
            f"and is not currently implemented.",
            "warn")

    # ----------------------------------------------------- capacity vs usage
    left, right = st.columns([1.3, 1], gap="large")

    with left:
        ui.section("Capacity opened against capacity used")
        by_month = (cap.groupby(["MonthYearSort", "MonthYear"], as_index=False)
                    .agg(Available=("SlotsAvailable", "sum"),
                         Booked=("SlotsBooked", "sum")).sort_values("MonthYearSort"))
        by_month["Utilisation"] = by_month["Booked"] / by_month["Available"]
        fig = go.Figure()
        fig.add_bar(x=by_month["MonthYear"], y=by_month["Available"],
                    name="Slots opened", marker_color=theme.LINE)
        fig.add_bar(x=by_month["MonthYear"], y=by_month["Booked"],
                    name="Slots used", marker_color=theme.PRIMARY)
        fig.add_scatter(x=by_month["MonthYear"], y=by_month["Utilisation"],
                        name="Utilisation", yaxis="y2", mode="lines",
                        line=dict(color=theme.CATEGORICAL[1], width=2))
        fig.update_layout(
            barmode="overlay",
            yaxis2=dict(overlaying="y", side="right", tickformat=".0%",
                        showgrid=False, range=[0, 0.4],
                        tickfont=dict(size=11, color=theme.FAINT)))
        theme.style(fig, height=330)
        ui.chart(fig)

    with right:
        ui.section("Technicians needing attention",
                   f"Active, rated below {AT_RISK_RATING}. Ratings are shrunk towards "
                   "a tier prior, so this is a sustained pattern rather than one bad "
                   "week.")
        worked = (cap.groupby("ProKey", as_index=False)["SlotsBooked"].sum()
                  .rename(columns={"SlotsBooked": "Jobs"}))
        risk = (in_scope[(in_scope["IsActive"] == 1)
                         & (in_scope["AvgRating"] < AT_RISK_RATING)]
                .merge(worked, on="ProKey", how="left")
                .sort_values("AvgRating")
                [["ProName", "PrimaryServiceCategory", "SkillTier", "AvgRating", "Jobs"]]
                .head(12))
        risk.columns = ["Technician", "Trade", "Tier", "Rating", "Jobs"]
        st.dataframe(risk, width="stretch", hide_index=True, height=330)
