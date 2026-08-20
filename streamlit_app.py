"""
Seek My Service - dashboard.

Run with:  streamlit run streamlit_app.py

Five pages: the four analytical views that mirror the Power BI report, plus a
Model Playground that serves live predictions from the three trained models.

The Power BI model and this app are deliberately two views of one project, not
two projects. Definitions, colours and thresholds are shared, so a number does
not change depending on which one you happen to be looking at.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

st.set_page_config(
    page_title="Seek My Service · Marketplace Analytics",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded",
)

from app import components as ui, data, theme  # noqa: E402
from generator import config  # noqa: E402

st.markdown(theme.CSS, unsafe_allow_html=True)

PAGES = {
    "Ops Control Room": "Delivery, service level and where it breaks down",
    "Demand Intelligence": "Funnel, seasonality and acquisition quality",
    "Supply Health": "Technician utilisation and the allocation problem",
    "ML Model Health": "Eight models, and the June 2026 drift incident",
    "Model Playground": "Live predictions from the trained models",
}


def main() -> None:
    if not data.data_is_present():
        st.title("Seek My Service")
        st.error(
            "The generated data is missing.\n\n"
            "Run this first, from the project folder:\n\n"
            "```\npython generator/generate.py\n```",
            icon=":material/error:")
        st.caption(f"Expected eleven CSVs in: {config.DATA_DIR}")
        return

    page, filters = sidebar()

    if page == "Ops Control Room":
        from app import page_ops
        page_ops.render(filters)
    elif page == "Demand Intelligence":
        from app import page_demand
        page_demand.render(filters)
    elif page == "Supply Health":
        from app import page_supply
        page_supply.render(filters)
    elif page == "ML Model Health":
        from app import page_ml
        page_ml.render(filters)
    else:
        from app import page_playground
        page_playground.render(filters)

    footer()


def sidebar():
    """Navigation and the global filters, shared by every analytical page."""
    with st.sidebar:
        st.markdown(
            f"<div style='font-size:1.05rem;font-weight:600;color:{theme.INK};"
            f"line-height:1.25'>Seek My Service</div>"
            f"<div style='font-size:0.78rem;color:{theme.FAINT};margin-bottom:1rem'>"
            f"Bengaluru home services · marketplace analytics</div>",
            unsafe_allow_html=True)

        # Read the page from the URL so individual pages are linkable - useful
        # when sending someone straight to the ML Model Health page rather than
        # asking them to find it.
        requested = st.query_params.get("page")
        names = list(PAGES)
        start_index = names.index(requested) if requested in PAGES else 0

        page = st.radio("Page", names, index=start_index,
                        label_visibility="collapsed",
                        captions=list(PAGES.values()))
        if st.query_params.get("page") != page:
            st.query_params["page"] = page

        st.markdown("---")

        low, high = data.date_bounds()
        if page == "Model Playground":
            # The playground has its own per-tab date control; a global range
            # filter here would only be confusing.
            st.caption("Filters do not apply to the playground — each tab has "
                       "its own controls.")
            return page, data.Filters(start=low, end=high)

        st.markdown("**Filters**")
        chosen = st.date_input(
            "Date range", value=(low, high), min_value=low, max_value=high,
            format="DD/MM/YYYY")
        if isinstance(chosen, tuple) and len(chosen) == 2:
            start, end = chosen
        else:
            start, end = low, high

        areas = data.areas()
        zones = st.multiselect("Zone", sorted(areas["Zone"].unique()),
                               placeholder="All zones")
        categories = st.multiselect("Service category", list(config.CATEGORY_ORDER),
                                    placeholder="All categories")
        tiers = st.multiselect("Demand tier", ["A", "B", "C"],
                               placeholder="All tiers")

        if st.button("Reset filters", width="stretch"):
            st.rerun()

        st.markdown("---")
        st.caption(
            f"**{config.N_CUSTOMERS:,}** customers · "
            f"**{config.N_PROFESSIONALS}** technicians\n\n"
            f"{low.strftime('%b %Y')} – {high.strftime('%b %Y')} · "
            f"seed `{config.SEED}`")

        return page, data.Filters(start=start, end=end, zones=zones,
                                  categories=categories, tiers=tiers)


def footer() -> None:
    st.markdown("---")
    st.markdown(
        f"<div style='color:{theme.FAINT};font-size:0.78rem;line-height:1.6'>"
        f"<b>Synthetic data.</b> Every booking, customer and technician was "
        f"generated from a fixed seed for this portfolio build — there is no real "
        f"company and no real customer records. The Bengaluru localities and their "
        f"pincodes, both monsoon seasons, the festival calendar, the Indian fiscal "
        f"year and the INR price points are real.<br/>"
        f"Built with pandas, LightGBM, FastAPI and Streamlit. The same data model "
        f"also drives a Power BI report with 119 DAX measures."
        f"</div>",
        unsafe_allow_html=True)


if __name__ == "__main__":
    main()
