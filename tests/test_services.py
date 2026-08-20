"""
Smoke tests for the three FastAPI services.

Covers the contract rather than the model: does the app start, does /health
tell the truth, does /predict return the documented shape, and does bad input
fail cleanly instead of 500-ing.

If model artefacts are missing, the session fixture trains them in fast mode so
the suite is self-contained on a fresh clone.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from generator import config
from ml.common import io

pytestmark = pytest.mark.skipif(
    not (config.DATA_DIR / "fact_bookings.csv").exists(),
    reason="generated data not present; run python generator/generate.py",
)

# A date comfortably inside the usable window: past the 28-day feature warm-up
# and more than seven days before the end, so a forward target exists.
GOOD_DATE = "2026-07-15"


@pytest.fixture(scope="session", autouse=True)
def trained_models():
    """Make sure every artefact exists, training quickly if it does not."""
    from ml import forecast_service, match_service, pricing_service

    trainers = {
        "demand_forecaster": forecast_service.train,
        "pro_match_ranker": match_service.train,
        "dynamic_price_engine": pricing_service.train,
    }
    for name, trainer in trainers.items():
        if not io.artifact_exists(name):
            trainer(fast=True, verbose=False)

    for module in (forecast_service, match_service, pricing_service):
        module.reset_state()
    yield


@pytest.fixture(scope="module")
def forecast_client() -> TestClient:
    from ml import forecast_service
    return TestClient(forecast_service.app)


@pytest.fixture(scope="module")
def match_client() -> TestClient:
    from ml import match_service
    return TestClient(match_service.app)


@pytest.fixture(scope="module")
def pricing_client() -> TestClient:
    from ml import pricing_service
    return TestClient(pricing_service.app)


# ===========================================================================
# Health
# ===========================================================================
@pytest.mark.parametrize("fixture_name, service, model", [
    ("forecast_client", "forecast_service", "demand_forecaster"),
    ("match_client", "match_service", "pro_match_ranker"),
    ("pricing_client", "pricing_service", "dynamic_price_engine"),
])
def test_health_reports_a_ready_service(request, fixture_name, service, model):
    client = request.getfixturevalue(fixture_name)
    response = client.get("/health")
    assert response.status_code == 200

    body = response.json()
    assert body["service"] == service
    assert body["model_name"] == model
    assert body["model_loaded"] is True
    assert body["data_available"] is True
    assert body["status"] == "ok"
    assert body["model_version"]


@pytest.mark.parametrize("fixture_name", ["forecast_client", "match_client", "pricing_client"])
def test_health_carries_holdout_metrics(request, fixture_name):
    """A health endpoint that only says 'up' is not worth calling."""
    body = request.getfixturevalue(fixture_name).get("/health").json()
    assert body["holdout_metrics"]
    assert all(isinstance(v, (int, float)) for v in body["holdout_metrics"].values())


# ===========================================================================
# Forecast service
# ===========================================================================
def test_forecast_predict_returns_the_documented_shape(forecast_client):
    response = forecast_client.post("/predict", json={
        "area_key": 4,
        "service_category": "Plumber",
        "as_of_date": GOOD_DATE,
    })
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["area_key"] == 4
    assert body["service_category"] == "Plumber"
    assert body["horizon_days"] == 7
    assert body["predicted_jobs"] >= 0
    assert body["prediction_interval_low"] <= body["predicted_jobs"]
    assert body["prediction_interval_high"] >= body["predicted_jobs"]
    assert body["area_name"]
    assert isinstance(body["is_monsoon"], bool)


def test_forecast_knows_july_is_the_monsoon(forecast_client):
    body = forecast_client.post("/predict", json={
        "area_key": 4, "service_category": "Plumber", "as_of_date": GOOD_DATE,
    }).json()
    assert body["is_monsoon"] is True
    assert body["seasonal_multiplier"] > 1.5


def test_forecast_lists_its_categories(forecast_client):
    response = forecast_client.get("/categories")
    assert response.status_code == 200
    assert response.json() == list(config.CATEGORY_ORDER)


def test_forecast_rejects_an_unknown_category(forecast_client):
    response = forecast_client.post("/predict", json={
        "area_key": 4, "service_category": "Astrology", "as_of_date": GOOD_DATE,
    })
    assert response.status_code == 422
    assert "Astrology" in response.json()["detail"]


def test_forecast_rejects_a_malformed_date(forecast_client):
    response = forecast_client.post("/predict", json={
        "area_key": 4, "service_category": "Plumber", "as_of_date": "15-07-2026",
    })
    assert response.status_code == 422


def test_forecast_rejects_an_out_of_range_area(forecast_client):
    response = forecast_client.post("/predict", json={
        "area_key": 99, "service_category": "Plumber", "as_of_date": GOOD_DATE,
    })
    assert response.status_code == 422


def test_forecast_404s_on_a_date_outside_the_usable_window(forecast_client):
    """Inside the 28-day feature warm-up there is no complete feature row."""
    response = forecast_client.post("/predict", json={
        "area_key": 4, "service_category": "Plumber", "as_of_date": "2025-01-03",
    })
    assert response.status_code == 404
    assert "Usable dates" in response.json()["detail"]


# ===========================================================================
# Match service
# ===========================================================================
def test_match_returns_a_ranked_list(match_client):
    response = match_client.post("/predict", json={
        "area_key": 4,
        "service_category": "Plumber",
        "as_of_date": GOOD_DATE,
        "is_emergency": True,
        "top_n": 5,
    })
    assert response.status_code == 200, response.text

    body = response.json()
    ranked = body["ranked"]
    assert 1 <= len(ranked) <= 5
    assert [r["rank"] for r in ranked] == list(range(1, len(ranked) + 1))
    # Scores must be monotonically non-increasing, or the ranking is not a ranking.
    scores = [r["score"] for r in ranked]
    assert scores == sorted(scores, reverse=True)
    assert body["candidates_considered"] >= len(ranked)


def test_match_returns_usable_technician_detail(match_client):
    body = match_client.post("/predict", json={
        "area_key": 4, "service_category": "Plumber", "as_of_date": GOOD_DATE,
    }).json()
    top = body["ranked"][0]
    assert top["pro_name"]
    assert top["skill_tier"] in {"Bronze", "Silver", "Gold", "Platinum"}
    assert 1.0 <= top["avg_rating"] <= 5.0
    assert top["distance_km"] >= 0
    assert 0.0 <= top["load_ratio"] <= 1.0


def test_match_prefers_the_right_trade(match_client):
    """The strongest feature in the model is category match; the top few results
    should reflect that rather than returning a random cross-section."""
    body = match_client.post("/predict", json={
        "area_key": 1, "service_category": "Plumber",
        "as_of_date": GOOD_DATE, "top_n": 5,
    }).json()
    matched = sum(1 for r in body["ranked"] if r["category_match"])
    assert matched >= 3


def test_match_respects_top_n(match_client):
    body = match_client.post("/predict", json={
        "area_key": 4, "service_category": "Carpenter",
        "as_of_date": GOOD_DATE, "top_n": 2,
    }).json()
    assert len(body["ranked"]) == 2


def test_match_rejects_an_unknown_category(match_client):
    response = match_client.post("/predict", json={
        "area_key": 4, "service_category": "Astrology", "as_of_date": GOOD_DATE,
    })
    assert response.status_code == 422


def test_match_rejects_an_absurd_top_n(match_client):
    response = match_client.post("/predict", json={
        "area_key": 4, "service_category": "Plumber",
        "as_of_date": GOOD_DATE, "top_n": 500,
    })
    assert response.status_code == 422


# ===========================================================================
# Pricing service
# ===========================================================================
def test_pricing_returns_an_ordered_band(pricing_client):
    response = pricing_client.post("/predict", json={
        "service_key": 11,
        "area_key": 4,
        "as_of_date": GOOD_DATE,
        "booking_hour": 10,
        "discount_pct": 0.1,
    })
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["price_low_inr"] <= body["price_mid_inr"] <= body["price_high_inr"]
    assert body["price_low_inr"] >= 0
    assert 0.0 <= body["accept_probability"] <= 1.0
    assert body["service_name"]
    assert body["band_width_pct"] >= 0


def test_pricing_scales_with_the_service(pricing_client):
    """A modular kitchen must not be quoted like a tap install."""
    def mid(service_key: int) -> float:
        return pricing_client.post("/predict", json={
            "service_key": service_key, "area_key": 4, "as_of_date": GOOD_DATE,
        }).json()["price_mid_inr"]

    tap_install = mid(12)          # Tap and Mixer Install, base 450
    modular_kitchen = mid(2)       # Modular Kitchen Install, base 45000
    assert modular_kitchen > tap_install * 10


def test_pricing_reflects_area_income_band(pricing_client):
    """The same job in a premium area should not price below a value area."""
    def mid(area_key: int) -> float:
        return pricing_client.post("/predict", json={
            "service_key": 21, "area_key": area_key, "as_of_date": GOOD_DATE,
        }).json()["price_mid_inr"]

    koramangala = mid(1)    # Premium
    kr_puram = mid(20)      # Value
    assert koramangala > kr_puram


def test_pricing_lists_its_catalogue(pricing_client):
    response = pricing_client.get("/services")
    assert response.status_code == 200
    catalogue = response.json()
    assert len(catalogue) == len(config.SERVICES)
    assert {"ServiceKey", "ServiceName", "BasePriceINR"} <= set(catalogue[0])


def test_pricing_rejects_an_unknown_service(pricing_client):
    response = pricing_client.post("/predict", json={
        "service_key": 999, "area_key": 4, "as_of_date": GOOD_DATE,
    })
    assert response.status_code == 422


def test_pricing_rejects_a_malformed_date(pricing_client):
    response = pricing_client.post("/predict", json={
        "service_key": 11, "area_key": 4, "as_of_date": "tomorrow",
    })
    assert response.status_code == 422


def test_pricing_rejects_an_absurd_discount(pricing_client):
    response = pricing_client.post("/predict", json={
        "service_key": 11, "area_key": 4, "as_of_date": GOOD_DATE, "discount_pct": 0.95,
    })
    assert response.status_code == 422


# ===========================================================================
# OpenAPI
# ===========================================================================
@pytest.mark.parametrize("fixture_name", ["forecast_client", "match_client", "pricing_client"])
def test_openapi_schema_is_served(request, fixture_name):
    """Every service documents itself at /docs, which is what makes these
    handover-ready rather than something only the author can call."""
    client = request.getfixturevalue(fixture_name)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "/predict" in schema["paths"]
    assert "/health" in schema["paths"]
    assert schema["info"]["title"].startswith("Seek My Service")
