"""
Demand Intelligence.

The question: where is demand going unserved, and which acquisition channels
are actually worth the money?

Two findings live here. Bengaluru weather is a demand driver with a shape you
can staff against, and the channel bringing the most customers brings the least
value per customer.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app import components as ui, data, theme

WATCH_CATEGORIES = ["AC Service", "Plumber", "Painter", "Deep Cleaning"]


def render(filters: data.Filters) -> None:
    frame = data.apply(data.bookings(), filters)
    funnel = data.apply(data.leads(), filters)

    ui.page_header(
        "Demand Intelligence",
        "Where is demand going unserved, and which channels are worth the money?",
        filters.scope_label + "  ·  " + filters.label,
    )

    if frame.empty or funnel.empty:
        ui.empty_state("No demand matches these filters. Widen the selection.")
        return

    searches = int(funnel["Searches"].sum())
    lead_count = int(funnel["Leads"].sum())
    quotes = int(funnel["QuotesSent"].sum())
    booked = int(funnel["Bookings"].sum())
    kpis = data.headline(frame)

    ui.kpi_row([
        ("Searches", f"{searches:,}"),
        ("Leads", f"{lead_count:,}", theme.pct(lead_count / searches) if searches else ""),
        ("Quotes sent", f"{quotes:,}", theme.pct(quotes / lead_count) if lead_count else ""),
        ("Bookings", f"{booked:,}", theme.pct(booked / quotes) if quotes else ""),
        ("Search → booking", theme.pct(booked / searches) if searches else "-"),
        ("Avg order value", f"₹{theme.inr(kpis['aov'])}"),
    ])

    # ---------------------------------------------------------------- funnel
    left, right = st.columns([1, 1.5], gap="large")

    with left:
        ui.section("The funnel", "Where the interest goes.")
        fig = go.Figure(go.Funnel(
            y=["Searches", "Leads", "Quotes sent", "Bookings"],
            x=[searches, lead_count, quotes, booked],
            textinfo="value+percent initial",
            marker=dict(color=[theme.CATEGORICAL[0], theme.CATEGORICAL[6],
                               theme.CATEGORICAL[1], theme.GOOD]),
            connector=dict(line=dict(color=theme.LINE, width=1)),
        ))
        theme.style(fig, height=330, legend=False)
        ui.chart(fig)

    with right:
        ui.section("Bengaluru weather is a demand driver",
                   "Four categories that move for different reasons. The painter "
                   "line going the other way in the monsoon is the point.")
        completed = frame[frame["IsCompleted"] == 1]
        watch = [c for c in WATCH_CATEGORIES
                 if c in completed["ServiceCategory"].unique()]
        by_month = (completed[completed["ServiceCategory"].isin(watch)]
                    .groupby(["MonthYearSort", "MonthYear", "ServiceCategory"],
                             as_index=False).size()
                    .rename(columns={"size": "Jobs"})
                    .sort_values("MonthYearSort"))
        if by_month.empty:
            ui.empty_state("None of the four seasonal categories are in scope.")
        else:
            fig = px.line(by_month, x="MonthYear", y="Jobs", color="ServiceCategory",
                          color_discrete_map=theme.CATEGORY_COLOURS, markers=True)
            fig.update_traces(line=dict(width=2), marker=dict(size=5))
            theme.style(fig, height=330, y_title="Completed jobs")
            ui.chart(fig)

    if {"AC Service", "Painter"} <= set(frame["ServiceCategory"].unique()):
        ui.finding(
            "AC servicing runs about <b>3.7× higher in April than in February</b>. "
            "Plumbing roughly doubles when the monsoon breaks. Painting goes the "
            "other way and <b>falls through the monsoon</b> — nobody paints a "
            "Bengaluru exterior in July — then spikes for Diwali. Three different "
            "seasonal shapes, all of them predictable months ahead.")

    # ------------------------------------------------------- geography & mix
    left, right = st.columns([1, 1], gap="large")

    with left:
        ui.section("Where the demand is",
                   "Bubble size is booking volume; colour is demand tier.")
        by_area = (frame.groupby(["AreaName", "Latitude", "Longitude", "DemandTier"],
                                 as_index=False)
                   .agg(Bookings=("BookingID", "count"),
                        GMV=("FinalAmountINR", "sum")))
        fig = px.scatter_map(
            by_area, lat="Latitude", lon="Longitude", size="Bookings",
            color="DemandTier", color_discrete_map=theme.TIER_COLOURS,
            hover_name="AreaName", size_max=34, zoom=10.2,
            hover_data={"Bookings": ":,", "GMV": ":,.0f",
                        "Latitude": False, "Longitude": False},
            map_style="carto-positron",
        )
        theme.style(fig, height=380)
        fig.update_layout(margin=dict(l=0, r=0, t=30, b=0))
        ui.chart(fig)

    with right:
        ui.section("High interest, poor conversion",
                   "Search-to-booking rate by area and category. Red is interest "
                   "that is not turning into work.")
        conv = (funnel.groupby(["AreaName", "ServiceCategory"], as_index=False)
                .agg(Searches=("Searches", "sum"), Bookings=("Bookings", "sum")))
        conv["Conversion"] = conv["Bookings"] / conv["Searches"].replace(0, np.nan)
        pivot = conv.pivot(index="AreaName", columns="ServiceCategory",
                           values="Conversion")
        fig = px.imshow(pivot, aspect="auto", zmin=0, zmax=0.09,
                        color_continuous_scale=[theme.BAD, theme.WARN, theme.GOOD],
                        labels=dict(color="Conv"))
        fig.update_traces(
            hovertemplate="%{y} · %{x}<br>search to booking %{z:.2%}<extra></extra>")
        fig.update_coloraxes(colorbar=dict(tickformat=".0%", thickness=10, len=0.85))
        theme.style(fig, height=380, legend=False)
        ui.chart(fig)

    tier_conv = (funnel.groupby("DemandTier", as_index=False)
                 .agg(Searches=("Searches", "sum"), Bookings=("Bookings", "sum")))
    tier_conv["Conversion"] = tier_conv["Bookings"] / tier_conv["Searches"]
    if {"A", "C"} <= set(tier_conv["DemandTier"]):
        a_rate = float(tier_conv.loc[tier_conv["DemandTier"] == "A", "Conversion"].iloc[0])
        c_rate = float(tier_conv.loc[tier_conv["DemandTier"] == "C", "Conversion"].iloc[0])
        c_searches = int(tier_conv.loc[tier_conv["DemandTier"] == "C", "Searches"].iloc[0])
        upside = c_searches * (a_rate - c_rate)
        ui.finding(
            f"Tier-A areas convert search to booking at <b>{theme.pct(a_rate, 2)}</b>. "
            f"Tier-C areas convert at <b>{theme.pct(c_rate, 2)}</b> — barely half. The "
            f"interest is there; it is not becoming work. Closing that gap entirely "
            f"would be about <b>{upside:,.0f} additional bookings</b> over this period, "
            f"worth roughly ₹{theme.crore(upside * 0.8 * kpis['aov'])} in GMV. "
            f"The open question the funnel cannot answer: is that 'no technician "
            f"available' or 'quoted and declined'? Those need opposite fixes.",
            "warn")

    # ----------------------------------------------------------- acquisition
    ui.section("The channel bringing the most customers brings the least value",
               "Bars are new customers acquired; the line is what each one is worth "
               "over their lifetime.")

    customer_keys = frame["CustomerKey"].unique()
    cust = data.customers()
    cust = cust[cust["CustomerKey"].isin(customer_keys)]

    if cust.empty:
        ui.empty_state("No customers in scope.")
        return

    by_channel = (cust.groupby("AcquisitionChannel", as_index=False)
                  .agg(Customers=("CustomerKey", "count"),
                       AvgLTV=("LifetimeValueINR", "mean"),
                       AvgBookings=("TotalBookings", "mean"),
                       RepeatRate=("TotalBookings", lambda s: float((s >= 2).mean())))
                  .sort_values("AvgLTV", ascending=False))

    fig = go.Figure()
    fig.add_bar(x=by_channel["AcquisitionChannel"], y=by_channel["Customers"],
                name="Customers acquired", marker_color=theme.LINE)
    fig.add_scatter(x=by_channel["AcquisitionChannel"], y=by_channel["AvgLTV"],
                    name="Average lifetime value", yaxis="y2", mode="lines+markers",
                    line=dict(color=theme.PRIMARY, width=2.5), marker=dict(size=8))
    fig.add_scatter(x=by_channel["AcquisitionChannel"], y=by_channel["RepeatRate"],
                    name="Repeat rate", yaxis="y3", mode="lines+markers",
                    line=dict(color=theme.CATEGORICAL[1], width=2, dash="dot"),
                    marker=dict(size=6))
    fig.update_layout(
        yaxis2=dict(overlaying="y", side="right", showgrid=False,
                    tickprefix="₹", tickfont=dict(size=11, color=theme.PRIMARY)),
        yaxis3=dict(overlaying="y", side="right", showgrid=False, visible=False,
                    range=[0, 1]),
    )
    theme.style(fig, height=340, y_title="Customers acquired")
    ui.chart(fig)

    best = by_channel.iloc[0]
    worst = by_channel.iloc[-1]
    ui.finding(
        f"A <b>{best['AcquisitionChannel']}</b> customer rebooks "
        f"{theme.pct(best['RepeatRate'])} of the time and is worth "
        f"<b>₹{theme.inr(best['AvgLTV'])}</b>. A <b>{worst['AcquisitionChannel']}</b> "
        f"customer rebooks {theme.pct(worst['RepeatRate'])} of the time and is worth "
        f"<b>₹{theme.inr(worst['AvgLTV'])}</b> — a "
        f"<b>{best['AvgLTV'] / worst['AvgLTV']:.1f}× gap</b>, on comparable acquisition "
        f"volumes. Judged on cost per first booking, paid social probably looks like "
        f"the best channel on the marketing dashboard. Judged on cost per rupee of "
        f"lifetime value, it is the worst.",
        "bad")

    with st.expander("Channel detail"):
        display = by_channel.copy()
        display["AvgLTV"] = display["AvgLTV"].map(lambda v: f"₹{theme.inr(v)}")
        display["RepeatRate"] = display["RepeatRate"].map(theme.pct)
        display["AvgBookings"] = display["AvgBookings"].map(lambda v: f"{v:.2f}")
        display["Customers"] = display["Customers"].map(lambda v: f"{v:,}")
        display.columns = ["Channel", "Customers", "Avg LTV", "Avg bookings", "Repeat rate"]
        st.dataframe(display, width="stretch", hide_index=True)
