"""
Demand forecasting service.

Predicts total job volume over the next seven days for a given area and service
category, so supply can be pre-positioned rather than reacted to.

This is the production sibling of the ``demand_forecaster`` model whose June
2026 drift incident the dashboard tells the story of.

    Train:  python ml/forecast_service.py --train
    Serve:  uvicorn ml.forecast_service:app --port 8001
    Check:  curl http://127.0.0.1:8001/health
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

from generator import config  # noqa: E402
from ml.common import features as F, io  # noqa: E402

MODEL_NAME = "demand_forecaster"
SERVICE_VERSION = "2.4.0"

# Time-based split. A random split would let the model see next Tuesday while
# predicting last Monday, and every metric below would be a comfortable lie.
VALIDATION_START = dt.date(2026, 5, 1)

LGB_PARAMS = {
    "objective": "poisson",     # counts, non-negative, plenty of zeros
    "metric": "poisson",
    "learning_rate": 0.05,
    "num_leaves": 63,
    "min_data_in_leaf": 40,
    "feature_fraction": 0.85,
    "bagging_fraction": 0.85,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "verbosity": -1,
    "seed": config.SEED,
}
NUM_ROUNDS = 600
NUM_ROUNDS_FAST = 80

# Floor for the exposure offset, so a cell with no recent demand at all still
# has a finite log baseline instead of negative infinity.
BASELINE_FLOOR = 0.05


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ForecastRequest(BaseModel):
    area_key: int = Field(..., ge=1, le=20, description="dim_area.AreaKey, 1-20")
    service_category: str = Field(..., description="One of the eight categories")
    as_of_date: str = Field(
        ...,
        description="ISO date. The forecast covers the seven days AFTER this date.",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "area_key": 4,
                "service_category": "Plumber",
                "as_of_date": "2026-07-15",
            }
        }
    }


class ForecastResponse(BaseModel):
    area_key: int
    area_name: str
    service_category: str
    as_of_date: str
    horizon_days: int
    predicted_jobs: float
    prediction_interval_low: float
    prediction_interval_high: float
    recent_daily_average: float
    seasonal_multiplier: float
    is_monsoon: bool
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
    data_window: Optional[str] = None
    detail: Optional[str] = None


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------
def _prepare(require_target: bool = True) -> pd.DataFrame:
    panel = F.build_demand_panel()
    frame = F.add_forecast_features(panel)
    columns = F.forecast_feature_columns()
    subset = columns + (["TargetNext7"] if require_target else [])
    frame = frame.dropna(subset=subset)
    frame["BaselineNext7"] = np.maximum(
        frame["Roll28Mean"] * F.FORECAST_HORIZON, BASELINE_FLOOR)
    return frame


def _offset(frame: pd.DataFrame) -> np.ndarray:
    """Log exposure offset: what next week would be if it matched recent weeks.

    Gradient-boosted trees cannot extrapolate. Demand here grows roughly 4.5x
    across the window, so a model trained to predict absolute volume simply
    caps out at the largest value it saw in training - the first version of this
    model came back with a -40% bias for exactly that reason.

    Passing log(7 x recent daily mean) as a Poisson offset turns the problem
    into "what MULTIPLE of the recent norm will next week be", which is both
    scale-free and the question a supply planner actually asks.
    """
    return np.log(frame["BaselineNext7"].to_numpy(dtype=float))


def _apply_offset(raw_score: np.ndarray, offset: np.ndarray) -> np.ndarray:
    """Re-attach the exposure offset. LightGBM does not persist init_score in
    the model file, so inference must add it back exactly as training did."""
    return np.exp(raw_score + offset)


def train(fast: bool = False, verbose: bool = True) -> Dict[str, float]:
    """Fit the forecaster and persist it. Returns held-out metrics."""
    import lightgbm as lgb

    io.require_data()
    frame = _prepare()
    columns = F.forecast_feature_columns()

    split = pd.Timestamp(VALIDATION_START)
    train_frame = frame[frame["BookingDate"] < split]
    valid_frame = frame[frame["BookingDate"] >= split]

    x_train = train_frame[columns]
    y_train = train_frame["TargetNext7"]
    x_valid = valid_frame[columns]
    y_valid = valid_frame["TargetNext7"]
    offset_train = _offset(train_frame)
    offset_valid = _offset(valid_frame)

    rounds = NUM_ROUNDS_FAST if fast else NUM_ROUNDS
    valid_set = lgb.Dataset(x_valid, label=y_valid, init_score=offset_valid)
    booster = lgb.train(
        LGB_PARAMS,
        lgb.Dataset(x_train, label=y_train, init_score=offset_train),
        num_boost_round=rounds,
        valid_sets=[valid_set],
        callbacks=[lgb.early_stopping(50, verbose=False)] if not fast else [],
    )

    predicted = _apply_offset(
        booster.predict(x_valid, num_iteration=booster.best_iteration, raw_score=True),
        offset_valid,
    )
    actual = y_valid.to_numpy(dtype=float)

    # MAPE is only defined where something actually happened. Reporting it over
    # zero-demand cells would either divide by zero or quietly drop them and
    # flatter the model - the exact failure the dashboard's WAPE tile exposes.
    nonzero = actual > 0
    mape = float(np.mean(np.abs(predicted[nonzero] - actual[nonzero]) / actual[nonzero]))
    wape = float(np.sum(np.abs(predicted - actual)) / np.sum(actual))
    mae = float(np.mean(np.abs(predicted - actual)))
    rmse = float(np.sqrt(np.mean((predicted - actual) ** 2)))
    bias = float(np.sum(predicted - actual) / np.sum(actual))

    residual_std = float(np.std(predicted - actual))

    # How much of that MAPE is irreducible? At day x area x category grain the
    # mean 7-day target is about four jobs, and a count that small is dominated
    # by its own Poisson noise. Simulating actuals from a perfectly calibrated
    # model gives the MAPE floor no model can beat - quoting model MAPE without
    # it invites a conclusion the number does not support.
    noise_rng = np.random.default_rng(config.SEED)
    simulated = noise_rng.poisson(np.maximum(predicted, 1e-9))
    sim_nonzero = simulated > 0
    noise_floor = float(np.mean(
        np.abs(simulated[sim_nonzero] - predicted[sim_nonzero]) / simulated[sim_nonzero]))

    # The same model judged at the grain a planner actually acts on. Nobody
    # staffs one category in one locality for one day; they staff a city-wide
    # category for a week.
    rolled = valid_frame[["BookingDate", "AreaKey", "ServiceCategory"]].copy()
    rolled["Actual"] = actual
    rolled["Predicted"] = predicted

    def _grain_mape(keys: List[str]) -> float:
        grouped = rolled.groupby(keys)[["Actual", "Predicted"]].sum()
        grouped = grouped[grouped["Actual"] > 0]
        return float(np.mean(
            np.abs(grouped["Predicted"] - grouped["Actual"]) / grouped["Actual"]))

    mape_by_category_day = _grain_mape(["BookingDate", "ServiceCategory"])
    mape_by_area_day = _grain_mape(["BookingDate", "AreaKey"])

    metrics = {
        "mape": round(mape, 4),
        "mape_noise_floor": round(noise_floor, 4),
        "mape_city_category_grain": round(mape_by_category_day, 4),
        "mape_area_grain": round(mape_by_area_day, 4),
        "wape": round(wape, 4),
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "bias": round(bias, 4),
        "mean_target": round(float(np.mean(actual)), 3),
        "n_train": int(len(train_frame)),
        "n_valid": int(len(valid_frame)),
        "n_valid_nonzero": int(nonzero.sum()),
        "best_iteration": int(booster.best_iteration or rounds),
        "residual_std": round(residual_std, 4),
    }

    importance = dict(zip(columns, booster.feature_importance(importance_type="gain")))
    top = sorted(importance.items(), key=lambda kv: -kv[1])[:8]

    io.save_artifact(
        MODEL_NAME,
        {
            "booster": booster,
            "feature_columns": columns,
            "residual_std": residual_std,
            "version": SERVICE_VERSION,
            "horizon": F.FORECAST_HORIZON,
        },
        metrics,
    )

    if verbose:
        print(f"  [{MODEL_NAME}] trained on {metrics['n_train']:,} rows, "
              f"validated on {metrics['n_valid']:,} from {VALIDATION_START}")
        print(f"  [{MODEL_NAME}] cell grain : MAPE {mape:.1%} vs a Poisson noise floor of "
              f"{noise_floor:.1%} (mean target {np.mean(actual):.1f} jobs)")
        print(f"  [{MODEL_NAME}] planner grain: MAPE {mape_by_category_day:.1%} by "
              f"category-day, {mape_by_area_day:.1%} by area-day")
        print(f"  [{MODEL_NAME}] WAPE {wape:.1%}  MAE {mae:.2f}  RMSE {rmse:.2f}  "
              f"bias {bias:+.1%}")
        print(f"  [{MODEL_NAME}] top features by gain: "
              + ", ".join(f"{k}" for k, _ in top[:5]))

    return metrics


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------
_state: Dict[str, object] = {"artifact": None, "frame": None, "areas": None}


def _artifact():
    if _state["artifact"] is None:
        _state["artifact"] = io.load_artifact(MODEL_NAME)
    return _state["artifact"]


def _frame() -> pd.DataFrame:
    if _state["frame"] is None:
        _state["frame"] = _prepare()
    return _state["frame"]


def _area_names() -> Dict[int, str]:
    if _state["areas"] is None:
        areas = io.load_table("dim_area")
        _state["areas"] = dict(zip(areas["AreaKey"], areas["AreaName"]))
    return _state["areas"]


def reset_state() -> None:
    """Drop cached model and features. Used by the tests after retraining."""
    _state["artifact"] = None
    _state["frame"] = None
    _state["areas"] = None


def predict_one(area_key: int, service_category: str, as_of: dt.date) -> Dict:
    artifact = _artifact()
    if artifact is None:
        raise HTTPException(
            status_code=503,
            detail=f"{MODEL_NAME} has not been trained. Run: python ml/train_all.py",
        )
    if service_category not in config.CATEGORY_ORDER:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown service_category {service_category!r}. "
                   f"Expected one of {config.CATEGORY_ORDER}",
        )

    frame = _frame()
    row = frame[
        (frame["BookingDate"] == pd.Timestamp(as_of))
        & (frame["AreaKey"] == area_key)
        & (frame["ServiceCategory"] == service_category)
    ]
    if row.empty:
        raise HTTPException(
            status_code=404,
            detail=(f"No feature row for area {area_key} / {service_category} on "
                    f"{as_of.isoformat()}. Usable dates run "
                    f"{frame['BookingDate'].min().date()} to "
                    f"{frame['BookingDate'].max().date()}."),
        )

    columns = artifact["feature_columns"]
    booster = artifact["booster"]
    predicted = float(_apply_offset(
        booster.predict(row[columns], raw_score=True), _offset(row))[0])
    spread = 1.96 * float(artifact["residual_std"])

    return {
        "area_key": area_key,
        "area_name": _area_names().get(area_key, "Unknown"),
        "service_category": service_category,
        "as_of_date": as_of.isoformat(),
        "horizon_days": int(artifact["horizon"]),
        "predicted_jobs": round(predicted, 2),
        "prediction_interval_low": round(max(predicted - spread, 0.0), 2),
        "prediction_interval_high": round(predicted + spread, 2),
        "recent_daily_average": round(float(row["Roll28Mean"].iloc[0]), 3),
        "seasonal_multiplier": round(float(row["HorizonSeasonalMultiplier"].iloc[0]), 3),
        "is_monsoon": bool(row["IsMonsoon"].iloc[0]),
        "model_version": str(artifact["version"]),
    }


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Seek My Service - Demand Forecasting",
    version=SERVICE_VERSION,
    description="Next-7-day job volume by area and service category.",
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness plus a genuine readiness signal.

    Reports 200 even when the model is missing, with model_loaded False. A
    health endpoint that only says 'up' is not worth calling.
    """
    artifact_present = io.artifact_exists(MODEL_NAME)
    metrics = io.load_metrics(MODEL_NAME) or {}
    try:
        io.require_data()
        data_ok = True
        detail = None
    except io.DataNotGeneratedError as exc:
        data_ok = False
        detail = str(exc).splitlines()[0]

    holdout = {k: v for k, v in metrics.items()
               if isinstance(v, (int, float)) and k not in {"n_train", "n_valid"}}

    return HealthResponse(
        status="ok" if (artifact_present and data_ok) else "degraded",
        service="forecast_service",
        model_name=MODEL_NAME,
        model_version=SERVICE_VERSION,
        model_loaded=artifact_present,
        data_available=data_ok,
        trained_at=metrics.get("trained_at"),
        holdout_metrics=holdout or None,
        data_window=f"{config.DATE_START} to {config.DATE_END}" if data_ok else None,
        detail=detail if detail else (
            None if artifact_present else "Model not trained. Run python ml/train_all.py"
        ),
    )


@app.post("/predict", response_model=ForecastResponse)
def predict(request: ForecastRequest) -> ForecastResponse:
    try:
        as_of = dt.date.fromisoformat(request.as_of_date)
    except ValueError:
        raise HTTPException(status_code=422,
                            detail="as_of_date must be an ISO date, e.g. 2026-07-15")
    return ForecastResponse(**predict_one(request.area_key,
                                          request.service_category, as_of))


@app.get("/categories", response_model=List[str])
def categories() -> List[str]:
    """The valid service_category values, so a caller need not guess."""
    return list(config.CATEGORY_ORDER)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", action="store_true", help="fit and persist the model")
    parser.add_argument("--fast", action="store_true", help="fewer boosting rounds")
    parser.add_argument("--serve", action="store_true", help="run uvicorn on port 8001")
    parser.add_argument("--port", type=int, default=8001)
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
