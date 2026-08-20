"""Small reusable pieces of UI, so the five pages stay consistent."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import streamlit as st

from app import theme


def page_header(title: str, subtitle: str, scope: str = "") -> None:
    st.markdown(f"# {title}")
    scope_line = f"<br/><span style='color:{theme.FAINT}'>{scope}</span>" if scope else ""
    st.markdown(f"<div class='page-sub'>{subtitle}{scope_line}</div>",
                unsafe_allow_html=True)


def section(title: str, note: str = "") -> None:
    st.markdown(f"## {title}")
    if note:
        st.markdown(f"<div class='sec-note'>{note}</div>", unsafe_allow_html=True)


def kpi_row(items: Sequence[Tuple]) -> None:
    """Render a row of KPI tiles.

    Each item is (label, value) or (label, value, note) or
    (label, value, note, colour).
    """
    columns = st.columns(len(items), gap="small")
    for column, item in zip(columns, items):
        label, value = item[0], item[1]
        note = item[2] if len(item) > 2 else ""
        colour = item[3] if len(item) > 3 else None
        with column:
            st.markdown(theme.kpi(label, value, note, colour), unsafe_allow_html=True)


def finding(text: str, kind: str = "") -> None:
    """A callout carrying one insight. ``kind`` is '', 'good', 'warn' or 'bad'."""
    st.markdown(theme.finding(text, kind), unsafe_allow_html=True)


def synthetic_banner() -> None:
    st.markdown(
        "<div class='synthetic'><b>Synthetic data.</b> Every booking, customer and "
        "technician here was generated from a fixed seed for this portfolio build. "
        "No real company and no real customer records. The Bengaluru localities, "
        "monsoon seasons, festival calendar and INR price points are real.</div>",
        unsafe_allow_html=True,
    )


def chart(fig, **kwargs) -> None:
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False},
                    **kwargs)


def empty_state(message: str) -> None:
    st.info(message, icon=":material/filter_alt:")
