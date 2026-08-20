"""
Dynamic pricing service.

Produces a low / mid / high price band for a job, plus the probability that a
quote at the mid price gets accepted. This is the production sibling of the
``dynamic_price_engine`` model.

Four boosters are fitted: three quantile regressors at alpha 0.1, 0.5 and 0.9
for the band, and one binary classifier for accept probability. A single point
estimate is the wrong shape of answer here - the business decision is "what
range do we quote", and a band makes the uncertainty explicit instead of hiding
it behind a confident-looking number.

    Train:  python ml/pricing_service.py --train
    Serve:  uvicorn ml.pricing_service:app --port 8003
    Check:  curl http://127.0.0.1:8003/health
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from generator import config, seasonality  # noqa: E402
from ml.common import features as F, io  # noqa: E402

MODEL_NAME = "dynamic_price_engine"
SERVICE_VERSION = "1.6.0"

VALIDATION_START = dt.date(2026, 5, 1)
QUANTILES = (0.10, 0.50, 0.90)

QUANTILE_PARAMS = {
    "objective": "quantile",
    "metric": "quantile",
    "learning_rate": 0.06,
    "num_leaves": 63,
    "min_data_in_leaf": 40,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.9,
    "bagging_freq": 1,
    "verbosity": -1,
    "seed": config.SEED,
}
ACCEPT_PARAMS = {
    "objective": "binary",
    "metric": "auc",
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_data_in_leaf": 60,
    "feature_fraction": 0.9,
    "verbosity": -1,
    "seed": config.SEED,
}
NUM_ROUNDS = 400
NUM_ROUNDS_FAST = 60


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class PricingRequest(BaseModel):
    service_key: int = Field(..., ge=1, le=37, description="dim_service.ServiceKey")
    area_key: int = Field(..., ge=1, le=20, description="dim_area.AreaKey")
    as_of_date: str = Field(..., description="ISO date of the job")
    booking_hour: int = Field(default=10, ge=0, le=23)
    discount_pct: float = Field(default=0.0, ge=0.0, le=0.5,
                                description="Coupon as a fraction of the quote")

    model_config = {
        "json_schema_extra": {
            "example": {
                "service_key": 11,
                "area_key": 4,
                "as_of_date": "2026-07-15",
                "booking_hour": 10,
                "discount_pct": 0.1,
            }
        }
    }


class PricingResponse(BaseModel):
    service_key: int
    service_name: str
    service_category: str
    area_key: int
    area_name: str
    as_of_date: str
    base_price_inr: int
    price_low_inr: float
    price_mid_inr: float
    price_high_inr: float
    band_width_pct: float
    accept_probability: float
    seasonal_multiplier: float
    is_emergency: bool
    model_version: str


class HealthResponse(BaseModel):
    status: str
    service: str
    model_name: str
    model_version: str
    model_loaded: bool
    data_available: bool
    trained_at: Optional[str] = None
    holdout_metrics: Optional[Dict[str, float]] = None
    detail: Optional[str] = None


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------
def _pinball(actual: np.ndarray, predicted: np.ndarray, alpha: float) -> float:
    delta = actual - predicted
    return float(np.mean(np.maximum(alpha * delta, (alpha - 1.0) * delta)))


def train(fast: bool = False, verbose: bool = True) -> Dict[str, float]:
    """Fit the three quantile models and the accept classifier."""
    import lightgbm as lgb
    from sklearn.metrics import roc_auc_score

    io.require_data()
    frame = F.build_pricing_dataset()

    split = pd.Timestamp(VALIDATION_START)
    rounds = NUM_ROUNDS_FAST if fast else NUM_ROUNDS

    # --- price band: completed jobs only, because only they have a final price
    priced = frame[frame["BookingStatus"] == "Completed"]
    price_columns = F.pricing_feature_columns()
    p_train = priced[priced["BookingDate"] < split]
    p_valid = priced[priced["BookingDate"] >= split]

    boosters = {}
    metrics: Dict[str, float] = {}
    actual = p_valid["FinalAmountINR"].to_numpy(dtype=float)
    predictions = {}

    for alpha in QUANTILES:
        params = dict(QUANTILE_PARAMS, alpha=alpha)
        booster = lgb.train(
            params,
            lgb.Dataset(p_train[price_columns], label=p_train["FinalAmountINR"]),
            num_boost_round=rounds,
            valid_sets=[lgb.Dataset(p_valid[price_columns],
                                    label=p_valid["FinalAmountINR"])],
            callbacks=[lgb.early_stopping(40, verbose=False)] if not fast else [],
        )
        boosters[alpha] = booster
        predicted = booster.predict(p_valid[price_columns],
                                    num_iteration=booster.best_iteration)
        predictions[alpha] = predicted
        metrics[f"pinball_q{int(alpha * 100)}"] = round(
            _pinball(actual, predicted, alpha), 3)

    low = predictions[0.10]
    mid = predictions[0.50]
    high = predictions[0.90]

    # Quantile crossing is possible because each alpha is fitted independently.
    # Sorting is the standard, honest repair; the alternative is a monotone
    # model that costs more than the problem is worth at this scale.
    stacked = np.sort(np.vstack([low, mid, high]), axis=0)
    low, mid, high = stacked[0], stacked[1], stacked[2]
    crossings = int(np.sum(np.vstack([predictions[0.10] > predictions[0.50],
                                      predictions[0.50] > predictions[0.90]])))

    coverage = float(np.mean((actual >= low) & (actual <= high)))
    mae = float(np.mean(np.abs(mid - actual)))
    mape = float(np.mean(np.abs(mid - actual) / np.maximum(actual, 1.0)))
    band_width = float(np.mean((high - low) / np.maximum(mid, 1.0)))

    metrics.update({
        "band_coverage": round(coverage, 4),
        "band_coverage_target": 0.80,
        "median_mae_inr": round(mae, 2),
        "median_mape": round(mape, 4),
        "mean_band_width_pct": round(band_width, 4),
        "quantile_crossings": crossings,
        "n_price_train": int(len(p_train)),
        "n_price_valid": int(len(p_valid)),
    })

    # --- accept probability: every booking, completed or not
    accept_columns = F.accept_feature_columns()
    a_train = frame[frame["BookingDate"] < split]
    a_valid = frame[frame["BookingDate"] >= split]

    accept_booster = lgb.train(
        ACCEPT_PARAMS,
        lgb.Dataset(a_train[accept_columns], label=a_train["Accepted"]),
        num_boost_round=rounds,
        valid_sets=[lgb.Dataset(a_valid[accept_columns], label=a_valid["Accepted"])],
        callbacks=[lgb.early_stopping(40, verbose=False)] if not fast else [],
    )
    accept_pred = accept_booster.predict(a_valid[accept_columns],
                                         num_iteration=accept_booster.best_iteration)
    auc = float(roc_auc_score(a_valid["Accepted"], accept_pred))
    metrics.update({
        "accept_auc": round(auc, 4),
        "accept_base_rate": round(float(a_valid["Accepted"].mean()), 4),
        "n_accept_train": int(len(a_train)),
        "n_accept_valid": int(len(a_valid)),
    })

    io.save_artifact(
        MODEL_NAME,
        {
            "quantile_boosters": boosters,
            "accept_booster": accept_booster,
            "price_columns": price_columns,
            "accept_columns": accept_columns,
            "quantiles": QUANTILES,
            "version": SERVICE_VERSION,
        },
        metrics,
    )

    if verbose:
        print(f"  [{MODEL_NAME}] price band trained on {len(p_train):,} completed jobs, "
              f"validated on {len(p_valid):,}")
        print(f"  [{MODEL_NAME}] median MAE INR {mae:,.0f}  MAPE {mape:.1%}  "
              f"mean band width {band_width:.1%} of mid")
        print(f"  [{MODEL_NAME}] 10-90 band covers {coverage:.1%} of actuals "
              f"(target 80%), {crossings} quantile crossings repaired by sorting")
        print(f"  [{MODEL_NAME}] accept classifier AUC {auc:.3f} "
              f"against a {a_valid['Accepted'].mean():.1%} base rate")
        if auc < 0.62:
            print(f"  [{MODEL_NAME}] NOTE: that AUC is weak. Acceptance in this dataset "
                  f"is driven mostly by rain and")
            print(f"  [{MODEL_NAME}] capacity strain rather than by price, so there is "
                  f"genuinely little signal to find.")

    return metrics


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------
_state: Dict[str, object] = {
    "artifact": None, "services": None, "areas": None, "load": None,
}


def reset_state() -> None:
    for key in _state:
        _state[key] = None


def _artifact():
    if _state["artifact"] is None:
        _state["artifact"] = io.load_artifact(MODEL_NAME)
    return _state["artifact"]


def _services() -> pd.DataFrame:
    if _state["services"] is None:
        _state["services"] = io.load_table("dim_service").set_index("ServiceKey")
    return _state["services"]


def _areas() -> pd.DataFrame:
    if _state["areas"] is None:
        _state["areas"] = io.load_table("dim_area").set_index("AreaKey")
    return _state["areas"]


def _area_load() -> pd.DataFrame:
    if _state["load"] is None:
        _state["load"] = F.area_load_features(io.load_bookings()).set_index(
            ["AreaKey", "BookingDate"])
    return _state["load"]


def _area_load_for(area_key: int, as_of: dt.date) -> tuple:
    """Recent load for an area, as the accept model saw it during training.

    The accept model is fitted with AreaStrain and AreaVolume7, so inference has
    to supply them too. Building the single-row feature frame without these was
    a genuine training-serving skew bug: training passed, /predict raised a
    KeyError, and only the service smoke tests caught it.

    For a date outside the observed window the honest answer is "no recent load
    signal", which is neutral strain and that area's own average volume.
    """
    load = _area_load()
    key = (area_key, pd.Timestamp(as_of))
    if key in load.index:
        row = load.loc[key]
        return float(row["AreaStrain"]), float(row["AreaVolume7"])
    try:
        area_rows = load.xs(area_key, level="AreaKey")
        return 1.0, float(area_rows["AreaVolume7"].tail(28).mean())
    except KeyError:
        return 1.0, 0.0


def quote(service_key: int, area_key: int, as_of: dt.date,
          booking_hour: int, discount_pct: float) -> Dict:
    artifact = _artifact()
    if artifact is None:
        raise HTTPException(
            status_code=503,
            detail=f"{MODEL_NAME} has not been trained. Run: python ml/train_all.py",
        )

    services = _services()
    areas = _areas()
    if service_key not in services.index:
        raise HTTPException(status_code=422, detail=f"Unknown service_key {service_key}")
    if area_key not in areas.index:
        raise HTTPException(status_code=422, detail=f"Unknown area_key {area_key}")

    service = services.loc[service_key]
    area = areas.loc[area_key]
    category = str(service["ServiceCategory"])
    multiplier = seasonality.category_seasonal_multiplier(as_of, category)

    row = pd.DataFrame([{
        "ServiceKey": service_key,
        "CategoryCode": config.CATEGORY_ORDER.index(category),
        "BasePriceINR": float(service["BasePriceINR"]),
        "LogBasePrice": float(np.log1p(service["BasePriceINR"])),
        "AvgDurationMins": float(service["AvgDurationMins"]),
        "IsEmergency": int(service["IsEmergency"]),
        "MaterialCostPct": float(service["MaterialCostPct"]),
        "AreaKey": area_key,
        "DemandTierOrd": F.DEMAND_TIER_ORDER[str(area["DemandTier"])],
        "IncomeBandOrd": F.INCOME_BAND_ORDER[str(area["IncomeBand"])],
        "SeasonalMultiplier": multiplier,
        "IsWeekend": int(seasonality.is_weekend(as_of)),
        "IsMonsoon": int(seasonality.is_monsoon(as_of)),
        "IsFestivalWindow": int(seasonality.is_festival_window(as_of)),
        "IsMonthEnd": int(seasonality.is_month_end(as_of)),
        "MonthNo": as_of.month,
        "DayOfWeek": as_of.weekday(),
        "BookingHour": booking_hour,
    }])

    boosters = artifact["quantile_boosters"]
    price_columns = artifact["price_columns"]
    band = np.sort([float(boosters[a].predict(row[price_columns])[0])
                    for a in artifact["quantiles"]])
    low, mid, high = (max(float(v), 0.0) for v in band)

    area_strain, area_volume = _area_load_for(area_key, as_of)
    accept_row = row.copy()
    accept_row["QuoteToBaseRatio"] = mid / max(float(service["BasePriceINR"]), 1.0)
    accept_row["DiscountPct"] = discount_pct
    accept_row["AreaStrain"] = area_strain
    accept_row["AreaVolume7"] = area_volume
    accept_probability = float(
        artifact["accept_booster"].predict(accept_row[artifact["accept_columns"]])[0])

    return {
        "service_key": service_key,
        "service_name": str(service["ServiceName"]),
        "service_category": category,
        "area_key": area_key,
        "area_name": str(area["AreaName"]),
        "as_of_date": as_of.isoformat(),
        "base_price_inr": int(service["BasePriceINR"]),
        "price_low_inr": round(low, 2),
        "price_mid_inr": round(mid, 2),
        "price_high_inr": round(high, 2),
        "band_width_pct": round((high - low) / max(mid, 1.0), 4),
        "accept_probability": round(accept_probability, 4),
        "seasonal_multiplier": round(multiplier, 3),
        "is_emergency": bool(service["IsEmergency"]),
        "model_version": str(artifact["version"]),
    }


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Seek My Service - Dynamic Pricing",
    version=SERVICE_VERSION,
    description="Low / mid / high price band and accept probability for a job.",
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    artifact_present = io.artifact_exists(MODEL_NAME)
    metrics = io.load_metrics(MODEL_NAME) or {}
    try:
        io.require_data()
        data_ok = True
        detail = None
    except io.DataNotGeneratedError as exc:
        data_ok = False
        detail = str(exc).splitlines()[0]

    holdout = {k: v for k, v in metrics.items() if isinstance(v, (int, float))}
    return HealthResponse(
        status="ok" if (artifact_present and data_ok) else "degraded",
        service="pricing_service",
        model_name=MODEL_NAME,
        model_version=SERVICE_VERSION,
        model_loaded=artifact_present,
        data_available=data_ok,
        trained_at=metrics.get("trained_at"),
        holdout_metrics=holdout or None,
        detail=detail if detail else (
            None if artifact_present else "Model not trained. Run python ml/train_all.py"
        ),
    )


@app.post("/predict", response_model=PricingResponse)
def predict(request: PricingRequest) -> PricingResponse:
    try:
        as_of = dt.date.fromisoformat(request.as_of_date)
    except ValueError:
        raise HTTPException(status_code=422,
                            detail="as_of_date must be an ISO date, e.g. 2026-07-15")
    return PricingResponse(**quote(request.service_key, request.area_key, as_of,
                                   request.booking_hour, request.discount_pct))


@app.get("/services", response_model=List[Dict])
def services() -> List[Dict]:
    """The service catalogue, so a caller can look up a valid service_key."""
    frame = io.load_table("dim_service")
    return frame[["ServiceKey", "ServiceCategory", "ServiceName",
                  "BasePriceINR", "IsEmergency"]].to_dict(orient="records")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8003)
    args = parser.parse_args()

    if args.train:
        train(fast=args.fast)
        return 0
    if args.serve:
        import uvicorn
        uvicorn.run(app, host="127.0.0.1", port=args.port)
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
