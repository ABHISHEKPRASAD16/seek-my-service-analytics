"""
Smoke tests for the Streamlit dashboard.

Streamlit apps fail at runtime rather than at import, so a page can be
completely broken and nothing notices until someone opens it. ``AppTest`` runs
the script headlessly and surfaces any exception, which makes these the only
tests that would have caught the MetricGoal join collision on the ML page - the
column existed on both fact and dimension, pandas silently renamed both, and
every downstream reference failed.

These are deliberately shallow: they assert the pages render and produce
content, not that any particular number is right. The numbers are covered by
validate.py and the feature tests.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from generator import config

APP = Path(__file__).resolve().parents[1] / "streamlit_app.py"

PAGES = [
    "Ops Control Room",
    "Demand Intelligence",
    "Supply Health",
    "ML Model Health",
    "Model Playground",
]

pytestmark = pytest.mark.skipif(
    not (config.DATA_DIR / "fact_bookings.csv").exists(),
    reason="generated data not present; run python generator/generate.py",
)


def _app(timeout: int = 300):
    from streamlit.testing.v1 import AppTest
    return AppTest.from_file(str(APP), default_timeout=timeout)


def _errors(at) -> str:
    return " | ".join(str(e.value)[:300] for e in at.exception)


@pytest.fixture(scope="module")
def base_app():
    at = _app()
    at.run()
    assert not at.exception, _errors(at)
    return at


def test_app_starts(base_app):
    """The default landing page renders without raising."""
    assert not base_app.exception
    assert len(base_app.markdown) > 5


def test_sidebar_offers_every_page(base_app):
    options = base_app.sidebar.radio[0].options
    assert list(options) == PAGES


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders(page):
    at = _app()
    at.run()
    assert not at.exception, _errors(at)

    at.sidebar.radio[0].set_value(page).run()
    assert not at.exception, f"{page} raised: {_errors(at)}"
    assert len(at.markdown) > 3, f"{page} produced almost no content"


@pytest.mark.parametrize("page", PAGES[:4])
def test_pages_produce_charts(page):
    """The four analytical pages are charts, not walls of text."""
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value(page).run()
    assert not at.exception, f"{page} raised: {_errors(at)}"
    assert len(at.get("plotly_chart")) >= 3, f"{page} rendered too few charts"


def test_narrow_filter_does_not_break_pages():
    """A single zone, single category, one month - the shape most likely to
    produce an empty group-by somewhere."""
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("Ops Control Room").run()

    at.sidebar.date_input[0].set_value(
        (dt.date(2026, 7, 1), dt.date(2026, 7, 31))).run()
    assert not at.exception, _errors(at)

    at.sidebar.multiselect[0].set_value(["East"]).run()
    assert not at.exception, _errors(at)

    at.sidebar.multiselect[1].set_value(["Plumber"]).run()
    assert not at.exception, f"narrow filter raised: {_errors(at)}"


def test_empty_selection_is_handled_gracefully():
    """A filter combination with no rows must show a message, not a traceback."""
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("Demand Intelligence").run()
    # Central zone has one locality; pairing it with a tier it does not have
    # yields nothing at all.
    at.sidebar.multiselect[0].set_value(["Central"]).run()
    at.sidebar.multiselect[2].set_value(["C"]).run()
    assert not at.exception, f"empty selection raised: {_errors(at)}"


def test_playground_serves_a_live_forecast():
    """The playground must actually call the model, not show a placeholder."""
    at = _app(timeout=600)
    at.run()
    at.sidebar.radio[0].set_value("Model Playground").run()
    assert not at.exception, _errors(at)

    text = " ".join(m.value for m in at.markdown if isinstance(m.value, str))
    assert "Predicted jobs" in text
    assert "Held-out performance" in text
