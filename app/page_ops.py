"""
Ops Control Room.

The question: are we delivering the jobs we take, and where is it breaking down?

The page is built around one finding - service level failures are not random,
they concentrate on days that run hotter than their own recent average, and
those days are predictable in advance.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app import components as ui, data, theme


def render(filters: data.Filters) -> None:
    frame = data.apply(data.bookings(), filters)

    ui.page_header(
        "Ops Control Room",
        "Are we delivering the jobs we take, and where is it breaking down?",
        filters.scope_label + "  ·  " + filters.label,
    )

    if frame.empty:
        ui.empty_state("No bookings match these filters. Widen the selection.")
        return

    kpis = data.headline(frame)
    sla_colour = (theme.GOOD if kpis["sla_met"] >= data.SLA_TARGET
                  else theme.WARN if kpis["sla_met"] >= data.SLA_TARGET - 0.05
                  else theme.BAD)

    ui.kpi_row([
        ("Bookings", f"{kpis['bookings']:,}"),
        ("Completion rate", theme.pct(kpis["completion_rate"])),
        ("SLA met", theme.pct(kpis["sla_met"]), "target 90.0%", sla_colour),
        ("Avg time to assign", f"{kpis['time_to_assign']:.1f}", "minutes"),
        ("GMV", f"₹{theme.crore(kpis['gmv'])}"),
        ("Platform revenue", f"₹{theme.crore(kpis['revenue'])}",
         f"take rate {theme.pct(kpis['take_rate'])}"),
    ])

    # ---------------------------------------------------------------- strain
    split = data.strain_split(frame)
    if split:
        ui.finding(
            f"Service level sits at <b>{theme.pct(kpis['sla_met'])}</b> against a 90% "
            f"promise, and the misses are not spread evenly. On the busiest 20% of "
            f"days the breach rate is <b>{theme.pct(split['high_breach'])}</b> against "
            f"<b>{theme.pct(split['normal_breach'])}</b> on every other day — "
            f"<b>{split['ratio']:.1f}×</b> worse. Time to assign rises from "
            f"{split['normal_tta']:.1f} to {split['high_tta']:.1f} minutes and the "
            f"average rating drops from {split['normal_rating']:.2f} to "
            f"{split['high_rating']:.2f} stars.",
            "bad")

    left, right = st.columns([1.35, 1], gap="large")

    with left:
        ui.section("Volume delivered against the promise",
                   "Bars are jobs; the line is the share arriving inside the "
                   "90-minute window.")
        by_month = data.monthly(frame)
        fig = go.Figure()
        fig.add_bar(x=by_month["MonthYear"], y=by_month["Completed"],
                    name="Completed", marker_color=theme.PRIMARY)
        fig.add_bar(x=by_month["MonthYear"], y=by_month["Cancelled"],
                    name="Not completed", marker_color=theme.LINE)
        fig.add_scatter(x=by_month["MonthYear"], y=by_month["SLAMet"],
                        name="SLA met", yaxis="y2", mode="lines+markers",
                        line=dict(color=theme.BAD, width=2),
                        marker=dict(size=5))
        fig.update_layout(
            barmode="stack",
            yaxis2=dict(overlaying="y", side="right", range=[0.5, 1.0],
                        tickformat=".0%", showgrid=False,
                        tickfont=dict(size=11, color=theme.FAINT)),
        )
        theme.style(fig, height=340)
        fig.add_hline(y=data.SLA_TARGET, yref="y2", line_dash="dash",
                      line_color=theme.BAD, line_width=1,
                      annotation_text="90% promise", annotation_position="bottom right",
                      annotation_font=dict(size=10, color=theme.BAD))
        ui.chart(fig)

    with right:
        ui.section("Every dot is one day",
                   "Across: how busy the day was versus its own trailing 30-day "
                   "average. Up: share of jobs that missed the promise.")
        daily = data.daily_strain()
        daily = daily[(daily["Date"] >= pd.Timestamp(filters.start))
                      & (daily["Date"] <= pd.Timestamp(filters.end))]
        daily = daily.dropna(subset=["Strain", "SLABreach"])

        fig = px.scatter(
            daily, x="Strain", y="SLABreach", size="Volume",
            color="SLABreach", color_continuous_scale=[theme.GOOD, theme.WARN, theme.BAD],
            hover_data={"Date": "|%d %b %Y", "Volume": True,
                        "Strain": ":.2f", "SLABreach": ":.1%"},
        )
        fig.update_traces(marker=dict(opacity=0.55, line=dict(width=0)))

        # Least-squares fit computed here rather than via px.trendline, which
        # would pull in statsmodels for a single straight line.
        if len(daily) > 2:
            slope, intercept = np.polyfit(daily["Strain"], daily["SLABreach"], 1)
            xs = np.array([daily["Strain"].min(), daily["Strain"].max()])
            fig.add_scatter(x=xs, y=slope * xs + intercept, mode="lines",
                            line=dict(color=theme.INK, width=2, dash="dash"),
                            name="trend", hoverinfo="skip", showlegend=False)
        fig.update_coloraxes(showscale=False)
        theme.style(fig, height=340, legend=False,
                    x_title="Capacity strain (1.0 = a normal day)",
                    y_title="SLA breach rate", y_tickformat=".0%")
        ui.chart(fig)

    # ------------------------------------------------------------- breakdown
    left, right = st.columns([1.35, 1], gap="large")

    with left:
        ui.section("Where it breaks, by zone and month",
                   "Red is a zone-month where more than a quarter of jobs missed "
                   "the window.")
        completed = frame[frame["IsCompleted"] == 1]
        pivot = (completed.pivot_table(index="Zone", columns="MonthYear",
                                       values="SLAMetFlag", aggfunc="mean")
                 .reindex(columns=data.monthly(frame)["MonthYear"].tolist()))
        breach = 1 - pivot
        fig = px.imshow(
            breach, aspect="auto", color_continuous_scale=[theme.GOOD, theme.WARN, theme.BAD],
            zmin=0, zmax=0.45, labels=dict(color="Breach"),
        )
        fig.update_traces(hovertemplate="%{y} · %{x}<br>breach %{z:.1%}<extra></extra>")
        fig.update_coloraxes(colorbar=dict(tickformat=".0%", thickness=10, len=0.8))
        theme.style(fig, height=300, legend=False)
        ui.chart(fig)

    with right:
        ui.section("Slowest areas to dispatch",
                   "Thin supply shows up here first.")
        by_area = (frame.groupby("AreaName")
                   .agg(TimeToAssign=("TimeToAssignMins", "mean"),
                        SLAMet=("SLAMetFlag", "mean"),
                        Jobs=("BookingID", "count"),
                        Tier=("DemandTier", "first"))
                   .sort_values("TimeToAssign", ascending=False).head(8).reset_index())
        fig = px.bar(by_area.sort_values("TimeToAssign"), x="TimeToAssign", y="AreaName",
                     orientation="h", color="Tier",
                     color_discrete_map=theme.TIER_COLOURS,
                     hover_data={"Jobs": ":,", "SLAMet": ":.1%"})
        theme.style(fig, height=300, x_title="Average minutes to assign")
        fig.update_yaxes(title_text="")
        ui.chart(fig)

    # ------------------------------------------------------------ failure mix
    left, right = st.columns(2, gap="large")

    with left:
        ui.section("Failure modes", "Completed jobs excluded, so the tail is readable.")
        failures = (frame[frame["IsCompleted"] == 0]["BookingStatus"]
                    .value_counts().reset_index())
        failures.columns = ["Status", "Bookings"]
        fig = px.bar(failures.sort_values("Bookings"), x="Bookings", y="Status",
                     orientation="h")
        fig.update_traces(marker_color=theme.CATEGORICAL[1])
        theme.style(fig, height=250, legend=False)
        fig.update_yaxes(title_text="")
        ui.chart(fig)

    with right:
        ui.section("Quality tail",
                   "First-time fix and reopen rate move together with strain.")
        ui.kpi_row([
            ("First-time fix", theme.pct(kpis["first_time_fix"])),
            ("Reopen rate", theme.pct(kpis["reopen_rate"])),
        ])
        ui.kpi_row([
            ("Avg CSAT", f"{kpis['csat']:.2f}", "of 5"),
            ("Jobs rated", theme.pct(kpis["rated_pct"])),
        ])
        st.markdown("")
        ui.finding(
            "Ratings are only collected on about 62% of completed jobs, so CSAT is "
            "a sample and not a census. It is still the best early warning you have: "
            "it moves before churn does.")
