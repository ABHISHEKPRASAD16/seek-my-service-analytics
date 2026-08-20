"""
Technician matching and ranking service.

Given an incoming job, ranks the technicians who are actually available that day
and returns the best few. This is the production sibling of the
``pro_match_ranker`` model.

The registry records the client's production implementation as XGBoost
LambdaMART. The reference implementation here is LightGBM ``lambdarank``, which
is the same LambdaMART algorithm, kept in LightGBM so the whole project has one
gradient-boosting dependency rather than two.

    Train:  python ml/match_service.py --train
    Serve:  uvicorn ml.match_service:app --port 8002
    Check:  curl http://127.0.0.1:8002/health
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

MODEL_NAME = "pro_match_ranker"
SERVICE_VERSION = "3.1.0"

TRAIN_BOOKINGS = 14_000
CANDIDATES_PER_JOB = 8
VALIDATION_GROUP_FRACTION = 0.2
DEFAULT_TOP_N = 5

LGB_PARAMS = {
    "objective": "lambdarank",
    "metric": "ndcg",
    "ndcg_eval_at": [1, 3, 5],
    "learning_rate": 0.06,
    "num_leaves": 31,
    "min_data_in_leaf": 30,
    "feature_fraction": 0.9,
    "lambdarank_truncation_level": 8,
    "verbosity": -1,
    "seed": config.SEED,
}
NUM_ROUNDS = 400
NUM_ROUNDS_FAST = 60


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class MatchRequest(BaseModel):
    area_key: int = Field(..., ge=1, le=20, description="Where the job is")
    service_category: str = Field(..., description="One of the eight categories")
    as_of_date: str = Field(..., description="ISO date of the job")
    is_emergency: bool = Field(default=False)
    top_n: int = Field(default=DEFAULT_TOP_N, ge=1, le=25)

    model_config = {
        "json_schema_extra": {
            "example": {
                "area_key": 4,
                "service_category": "Plumber",
                "as_of_date": "2026-07-15",
                "is_emergency": True,
                "top_n": 5,
            }
        }
    }


class RankedProfessional(BaseModel):
    rank: int
    pro_key: int
    pro_name: str
    score: float
    skill_tier: str
    avg_rating: float
    home_area: str
    distance_km: float
    same_area: bool
    category_match: bool
    load_ratio: float
    slots_available: int


class MatchResponse(BaseModel):
    area_key: int
    area_name: str
    service_category: str
    as_of_date: str
    candidates_considered: int
    ranked: List[RankedProfessional]
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
def _group_sizes(frame: pd.DataFrame) -> np.ndarray:
    """Rows per query group, in the order the frame is sorted."""
    return frame.groupby("GroupId", sort=False).size().to_numpy()


def train(fast: bool = False, verbose: bool = True) -> Dict[str, float]:
    """Fit the ranker and persist it. Returns held-out ranking metrics."""
    import lightgbm as lgb

    io.require_data()
    dataset = F.build_match_dataset(
        n_bookings=2_000 if fast else TRAIN_BOOKINGS,
        n_candidates=CANDIDATES_PER_JOB,
    )
    if dataset.empty:
        raise RuntimeError("Match dataset is empty. Has the generator been run?")

    dataset = dataset.sort_values("GroupId").reset_index(drop=True)
    columns = F.match_feature_columns()

    # Split by group, never by row. Splitting mid-group would put a job's
    # winning technician in train and its losers in validation, which makes the
    # ranking task trivially easy and the metric meaningless.
    groups = dataset["GroupId"].unique()
    cut = int(len(groups) * (1 - VALIDATION_GROUP_FRACTION))
    train_groups = set(groups[:cut])

    train_frame = dataset[dataset["GroupId"].isin(train_groups)]
    valid_frame = dataset[~dataset["GroupId"].isin(train_groups)]

    booster = lgb.train(
        LGB_PARAMS,
        lgb.Dataset(train_frame[columns], label=train_frame["Label"],
                    group=_group_sizes(train_frame)),
        num_boost_round=NUM_ROUNDS_FAST if fast else NUM_ROUNDS,
        valid_sets=[lgb.Dataset(valid_frame[columns], label=valid_frame["Label"],
                                group=_group_sizes(valid_frame))],
        callbacks=[lgb.early_stopping(40, verbose=False)] if not fast else [],
    )

    scored = valid_frame.copy()
    scored["Score"] = booster.predict(
        valid_frame[columns], num_iteration=booster.best_iteration)

    # NDCG@k with a single binary relevant item per group reduces to
    # mean(1/log2(rank+1)) when the item is inside the top k, 0 otherwise.
    scored["Rank"] = scored.groupby("GroupId")["Score"].rank(
        ascending=False, method="first")
    hit = scored[scored["Label"] == 1]

    def ndcg_at(k: int) -> float:
        inside = hit["Rank"] <= k
        gains = np.where(inside, 1.0 / np.log2(hit["Rank"] + 1.0), 0.0)
        return float(np.mean(gains))

    def recall_at(k: int) -> float:
        return float(np.mean(hit["Rank"] <= k))

    metrics = {
        "ndcg_at_1": round(ndcg_at(1), 4),
        "ndcg_at_3": round(ndcg_at(3), 4),
        "ndcg_at_5": round(ndcg_at(5), 4),
        "recall_at_1": round(recall_at(1), 4),
        "recall_at_3": round(recall_at(3), 4),
        "recall_at_5": round(recall_at(5), 4),
        "mean_rank_of_chosen": round(float(hit["Rank"].mean()), 3),
        "random_baseline_ndcg_at_5": round(
            float(np.mean([1.0 / np.log2(r + 1) for r in range(1, 6)])
                  * 5 / CANDIDATES_PER_JOB), 4),
        "n_train_groups": int(len(train_groups)),
        "n_valid_groups": int(valid_frame["GroupId"].nunique()),
        "candidates_per_group": CANDIDATES_PER_JOB,
        "best_iteration": int(booster.best_iteration or NUM_ROUNDS),
    }

    importance = dict(zip(columns, booster.feature_importance(importance_type="gain")))
    top = sorted(importance.items(), key=lambda kv: -kv[1])[:5]

    io.save_artifact(
        MODEL_NAME,
        {"booster": booster, "feature_columns": columns, "version": SERVICE_VERSION},
        metrics,
    )

    if verbose:
        print(f"  [{MODEL_NAME}] trained on {metrics['n_train_groups']:,} jobs, "
              f"validated on {metrics['n_valid_groups']:,}, "
              f"{CANDIDATES_PER_JOB} candidates each")
        print(f"  [{MODEL_NAME}] NDCG@5 {metrics['ndcg_at_5']:.3f}  "
              f"NDCG@1 {metrics['ndcg_at_1']:.3f}  "
              f"(random baseline ~{metrics['random_baseline_ndcg_at_5']:.3f})")
        print(f"  [{MODEL_NAME}] the chosen technician is ranked first "
              f"{metrics['recall_at_1']:.1%} of the time, top-5 "
              f"{metrics['recall_at_5']:.1%}")
        print(f"  [{MODEL_NAME}] top features by gain: "
              + ", ".join(k for k, _ in top))
        print(f"  [{MODEL_NAME}] CAVEAT: this score is optimistic. The generator "
              f"assigns jobs using a known function of")
        print(f"  [{MODEL_NAME}] these same features, so the model is recovering a "
              f"process rather than learning a")
        print(f"  [{MODEL_NAME}] messy human one. Read NDCG@1 ({metrics['ndcg_at_1']:.3f}), "
              f"not recall@5. See docs/MODEL_CARDS.md.")

    return metrics


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------
_state: Dict[str, object] = {"artifact": None, "state": None, "pros": None, "areas": None}


def reset_state() -> None:
    for key in _state:
        _state[key] = None


def _artifact():
    if _state["artifact"] is None:
        _state["artifact"] = io.load_artifact(MODEL_NAME)
    return _state["artifact"]


def _pro_state() -> pd.DataFrame:
    if _state["state"] is None:
        _state["state"] = F.build_pro_day_state()
    return _state["state"]


def _pros() -> pd.DataFrame:
    if _state["pros"] is None:
        _state["pros"] = io.load_professionals().set_index("ProKey")
    return _state["pros"]


def _areas() -> pd.DataFrame:
    if _state["areas"] is None:
        _state["areas"] = io.load_table("dim_area").set_index("AreaKey")
    return _state["areas"]


def rank_candidates(area_key: int, service_category: str, as_of: dt.date,
                    is_emergency: bool, top_n: int) -> Dict:
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

    date_key = as_of.year * 10000 + as_of.month * 100 + as_of.day
    state = _pro_state()
    available = state[(state["DateKey"] == date_key) & (state["IsOnline"] == 1)
                      & (state["SlotsAvailable"] > state["SlotsBooked"])]
    if available.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No technicians were online with a free slot on {as_of.isoformat()}.",
        )

    pros = _pros()
    areas = _areas()
    if area_key not in areas.index:
        raise HTTPException(status_code=422, detail=f"Unknown area_key {area_key}")

    job_lat = float(areas.loc[area_key, "Latitude"])
    job_lon = float(areas.loc[area_key, "Longitude"])
    job_zone = areas.loc[area_key, "Zone"]

    candidates = available.merge(
        pros.reset_index()[["ProKey", "ProName", "PrimaryServiceCategory", "HomeAreaKey",
                            "SkillTier", "AvgRating", "IsBackgroundVerified",
                            "LifetimeJobs"]],
        on="ProKey", how="inner")

    home_lat = areas.loc[candidates["HomeAreaKey"], "Latitude"].to_numpy()
    home_lon = areas.loc[candidates["HomeAreaKey"], "Longitude"].to_numpy()
    home_zone = areas.loc[candidates["HomeAreaKey"], "Zone"].to_numpy()

    candidates["DistanceKm"] = F.haversine_km(home_lat, home_lon, job_lat, job_lon)
    candidates["SameArea"] = (candidates["HomeAreaKey"] == area_key).astype(int)
    candidates["SameZone"] = (home_zone == job_zone).astype(int)
    candidates["CategoryMatch"] = (
        candidates["PrimaryServiceCategory"] == service_category).astype(int)
    candidates["SkillTierOrd"] = candidates["SkillTier"].map(F.SKILL_TIER_ORDER)
    candidates["ProRating"] = candidates["AvgRating"].astype(float)
    candidates["IsVerified"] = candidates["IsBackgroundVerified"].astype(int)
    candidates["IsEmergency"] = int(is_emergency)

    columns = artifact["feature_columns"]
    candidates["Score"] = artifact["booster"].predict(candidates[columns])
    candidates = candidates.sort_values("Score", ascending=False).head(top_n)

    ranked = []
    for position, row in enumerate(candidates.itertuples(index=False), start=1):
        ranked.append(RankedProfessional(
            rank=position,
            pro_key=int(row.ProKey),
            pro_name=str(row.ProName),
            score=round(float(row.Score), 4),
            skill_tier=str(row.SkillTier),
            avg_rating=round(float(row.AvgRating), 2),
            home_area=str(areas.loc[row.HomeAreaKey, "AreaName"]),
            distance_km=round(float(row.DistanceKm), 2),
            same_area=bool(row.SameArea),
            category_match=bool(row.CategoryMatch),
            load_ratio=round(float(row.LoadRatio), 3),
            slots_available=int(row.SlotsAvailable),
        ))

    return {
        "area_key": area_key,
        "area_name": str(areas.loc[area_key, "AreaName"]),
        "service_category": service_category,
        "as_of_date": as_of.isoformat(),
        "candidates_considered": int(len(available)),
        "ranked": ranked,
        "model_version": str(artifact["version"]),
    }


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Seek My Service - Technician Matching",
    version=SERVICE_VERSION,
    description="Ranks available technicians for an incoming job.",
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
        service="match_service",
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


@app.post("/predict", response_model=MatchResponse)
def predict(request: MatchRequest) -> MatchResponse:
    try:
        as_of = dt.date.fromisoformat(request.as_of_date)
    except ValueError:
        raise HTTPException(status_code=422,
                            detail="as_of_date must be an ISO date, e.g. 2026-07-15")
    return MatchResponse(**rank_candidates(
        request.area_key, request.service_category, as_of,
        request.is_emergency, request.top_n))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8002)
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
