"""
Visual language for the dashboard.

The palette is lifted directly from ``powerbi/THEME.json`` so the Streamlit app
and the Power BI report look like two views of one project rather than two
projects. The status colours in particular are the same hex values the
``[KPI Status Colour]`` DAX measure returns.
"""

from __future__ import annotations

from typing import Optional

import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# Palette - identical to powerbi/THEME.json
# ---------------------------------------------------------------------------
PRIMARY = "#2A6FB5"
CATEGORICAL = [
    "#2A6FB5", "#E07A3E", "#1B9E77", "#B5548A",
    "#6C6FC4", "#C9A227", "#4FA3C7", "#8A5A44",
]

GOOD = "#1B9E77"
WARN = "#E6A700"
BAD = "#D6455D"
MUTED_MARK = "#8A8F98"

INK = "#1F2933"
MUTED = "#5A6673"
FAINT = "#8A939E"
LINE = "#E3E7EB"
GRID = "#EDF0F3"
SURFACE = "#FFFFFF"
CANVAS = "#F4F6F8"

# Consistent colour per service category everywhere in the app. A category that
# is orange on one page and green on the next quietly costs the reader a second
# of re-orientation on every chart.
CATEGORY_COLOURS = {
    "AC Service": "#2A6FB5",
    "Appliance Repair": "#4FA3C7",
    "Carpenter": "#8A5A44",
    "Deep Cleaning": "#1B9E77",
    "Electrician": "#C9A227",
    "Painter": "#E07A3E",
    "Pest Control": "#6C6FC4",
    "Plumber": "#B5548A",
}

TIER_COLOURS = {"A": GOOD, "B": WARN, "C": BAD}
SKILL_COLOURS = {
    "Bronze": "#8A5A44", "Silver": "#8A939E",
    "Gold": "#C9A227", "Platinum": "#2A6FB5",
}

FONT = "Segoe UI, Inter, system-ui, -apple-system, sans-serif"


# ---------------------------------------------------------------------------
# Plotly
# ---------------------------------------------------------------------------
def style(fig: go.Figure, height: int = 320, legend: bool = True,
          y_title: Optional[str] = None, x_title: Optional[str] = None,
          y_tickformat: Optional[str] = None) -> go.Figure:
    """Apply the house style to a figure.

    Every chart in the app goes through here, which is the cheapest way to keep
    forty charts looking like one dashboard.
    """
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=12, color=MUTED),
        hoverlabel=dict(font_family=FONT, font_size=12, bgcolor=SURFACE,
                        bordercolor=LINE, font_color=INK),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left",
                    x=0, title_text="", font=dict(size=11)),
        colorway=CATEGORICAL,
    )
    fig.update_xaxes(
        showgrid=False, zeroline=False, showline=True, linecolor=LINE,
        ticks="outside", tickcolor=LINE, ticklen=4,
        tickfont=dict(size=11, color=FAINT), title_text=x_title or "",
        title_font=dict(size=11, color=FAINT),
    )
    fig.update_yaxes(
        showgrid=True, gridcolor=GRID, zeroline=False, showline=False,
        tickfont=dict(size=11, color=FAINT), title_text=y_title or "",
        title_font=dict(size=11, color=FAINT),
        tickformat=y_tickformat,
    )
    return fig


def hline(fig: go.Figure, y: float, label: str, colour: str = BAD) -> go.Figure:
    """A dashed reference line with a readable label.

    Used for every goal and threshold in the app. A chart with a target line is
    a judgement; a chart without one is just a shape.
    """
    fig.add_hline(
        y=y, line_dash="dash", line_color=colour, line_width=1.5,
        annotation_text=label, annotation_position="top left",
        annotation_font=dict(size=11, color=colour),
    )
    return fig


def status_colour(status: str) -> str:
    return {"On Target": GOOD, "Watch": WARN, "Breach": BAD}.get(status, MUTED_MARK)


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
CSS = f"""
<style>
    .block-container {{ padding-top: 2.2rem; padding-bottom: 2rem; max-width: 1500px; }}
    #MainMenu, footer {{ visibility: hidden; }}

    h1, h2, h3 {{ font-family: {FONT}; color: {INK}; letter-spacing: -0.01em; }}
    h1 {{ font-size: 1.7rem !important; font-weight: 600 !important; }}
    h2 {{ font-size: 1.15rem !important; font-weight: 600 !important;
          margin-top: 1.6rem !important; margin-bottom: 0.2rem !important; }}
    h3 {{ font-size: 0.95rem !important; font-weight: 600 !important; }}

    .page-sub {{ color: {MUTED}; font-size: 0.92rem; margin: -0.3rem 0 1.1rem 0;
                 line-height: 1.5; max-width: 90ch; }}
    .sec-note {{ color: {FAINT}; font-size: 0.82rem; margin: 0 0 0.7rem 0;
                 max-width: 95ch; line-height: 1.45; }}

    /* KPI tiles */
    .kpi {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 8px;
            padding: 0.75rem 0.9rem; height: 100%; }}
    .kpi-label {{ color: {MUTED}; font-size: 0.72rem; text-transform: uppercase;
                  letter-spacing: 0.06em; font-weight: 600; margin-bottom: 0.25rem; }}
    .kpi-value {{ color: {INK}; font-size: 1.55rem; font-weight: 600;
                  line-height: 1.1; font-variant-numeric: tabular-nums; }}
    .kpi-note {{ color: {FAINT}; font-size: 0.74rem; margin-top: 0.2rem; }}

    /* Callout used for the findings */
    .finding {{ background: {SURFACE}; border: 1px solid {LINE};
                border-left: 4px solid {PRIMARY}; border-radius: 6px;
                padding: 0.85rem 1rem; margin: 0.6rem 0 1.1rem 0;
                font-size: 0.9rem; color: {INK}; line-height: 1.55; }}
    .finding.bad {{ border-left-color: {BAD}; }}
    .finding.good {{ border-left-color: {GOOD}; }}
    .finding.warn {{ border-left-color: {WARN}; }}
    .finding b {{ color: {INK}; }}

    /* Synthetic-data banner */
    .synthetic {{ background: #FFF8E8; border: 1px solid #F0DCA8;
                  border-radius: 6px; padding: 0.55rem 0.85rem;
                  font-size: 0.82rem; color: #6B5312; margin-bottom: 1.1rem; }}

    [data-testid="stSidebar"] {{ background: {SURFACE}; border-right: 1px solid {LINE}; }}
    [data-testid="stSidebar"] .block-container {{ padding-top: 1.2rem; }}

    div[data-testid="stMetricValue"] {{ font-size: 1.4rem; }}
    hr {{ margin: 1.2rem 0; border-color: {LINE}; }}
</style>
"""


def kpi(label: str, value: str, note: str = "", colour: Optional[str] = None) -> str:
    """HTML for one KPI tile. ``colour`` overrides the value colour for status."""
    value_style = f' style="color:{colour}"' if colour else ""
    note_html = f'<div class="kpi-note">{note}</div>' if note else ""
    return (f'<div class="kpi"><div class="kpi-label">{label}</div>'
            f'<div class="kpi-value"{value_style}>{value}</div>{note_html}</div>')


def finding(text: str, kind: str = "") -> str:
    """HTML for a callout box carrying one insight."""
    return f'<div class="finding {kind}">{text}</div>'


# ---------------------------------------------------------------------------
# Number formatting - Indian conventions
# ---------------------------------------------------------------------------
def inr(value: float, decimals: int = 0) -> str:
    """Format rupees with Indian digit grouping (lakh and crore)."""
    if value is None:
        return "-"
    negative = value < 0
    value = abs(value)
    whole = int(value)
    fraction = f"{value - whole:.{decimals}f}"[2:] if decimals else ""

    digits = str(whole)
    if len(digits) > 3:
        last3 = digits[-3:]
        rest = digits[:-3]
        parts = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        grouped = ",".join(parts + [last3])
    else:
        grouped = digits

    out = f"{grouped}.{fraction}" if decimals else grouped
    return ("-" if negative else "") + out


def crore(value: float) -> str:
    """Compact Indian scale: crore above 1cr, lakh above 1L, else plain."""
    if value is None:
        return "-"
    if abs(value) >= 1e7:
        return f"{value / 1e7:,.2f} Cr"
    if abs(value) >= 1e5:
        return f"{value / 1e5:,.2f} L"
    return inr(value)


def pct(value: float, decimals: int = 1) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.{decimals}f}%"
