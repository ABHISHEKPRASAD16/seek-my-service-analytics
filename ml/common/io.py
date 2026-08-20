"""
Data loading and artefact persistence.

One place that knows where the CSVs live, what type every column is, and where
trained models are written. The three services and the test suite all import
from here, so they cannot disagree about whether ``CustomerRating`` is an int
or a float with holes in it.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import joblib
import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from generator import config  # noqa: E402

DATA_DIR = config.DATA_DIR
MODEL_DIR = config.MODEL_DIR

# Columns that are genuinely dates, per table. Everything else is left to
# pandas, which is safe because the generator writes strict ISO formats.
DATE_COLUMNS: Dict[str, list] = {
    "dim_date": ["Date"],
    "dim_professional": ["JoinDate", "ChurnedDate"],
    "dim_customer": ["SignupDate", "FirstBookingDate", "LastBookingDate"],
    "dim_model": ["DeployedDate"],
    "fact_bookings": ["BookingTimestamp"],
}


class DataNotGeneratedError(FileNotFoundError):
    """Raised with an actionable message rather than a bare path."""


def data_path(table: str) -> Path:
    return DATA_DIR / f"{table}.csv"


def require_data() -> None:
    """Fail loudly and usefully if the CSVs have not been generated yet."""
    missing = [t for t in config.TABLES if not data_path(t).exists()]
    if missing:
        raise DataNotGeneratedError(
            "Missing generated data: " + ", ".join(missing)
            + f"\nExpected in: {DATA_DIR}"
            + "\nRun:  python generator/generate.py"
        )


@lru_cache(maxsize=None)
def load_table(table: str) -> pd.DataFrame:
    """Load one CSV with dates parsed. Cached, because services re-read often."""
    path = data_path(table)
    if not path.exists():
        raise DataNotGeneratedError(
            f"{path} not found. Run:  python generator/generate.py"
        )
    frame = pd.read_csv(path)
    for column in DATE_COLUMNS.get(table, []):
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return frame


def load_bookings(with_context: bool = True) -> pd.DataFrame:
    """fact_bookings, optionally joined to the dimensions worth having inline.

    ``BookingDate`` is added as a normalised date column, because almost every
    feature builder wants a date rather than a timestamp and re-deriving it in
    four places is how the four places end up subtly different.
    """
    bookings = load_table("fact_bookings").copy()
    bookings["BookingDate"] = bookings["BookingTimestamp"].dt.normalize()
    if not with_context:
        return bookings

    services = load_table("dim_service")[
        ["ServiceKey", "ServiceCategory", "ServiceName", "BasePriceINR",
         "AvgDurationMins", "IsEmergency", "MaterialCostPct", "CommissionPct"]
    ]
    areas = load_table("dim_area")[
        ["AreaKey", "AreaName", "Zone", "Latitude", "Longitude",
         "DemandTier", "IncomeBand"]
    ]
    return bookings.merge(services, on="ServiceKey", how="left").merge(
        areas, on="AreaKey", how="left", suffixes=("", "_area")
    )


def load_capacity() -> pd.DataFrame:
    """fact_pro_capacity with a real date column attached."""
    capacity = load_table("fact_pro_capacity").copy()
    dates = load_table("dim_date")[["DateKey", "Date"]]
    return capacity.merge(dates, on="DateKey", how="left")


def load_professionals() -> pd.DataFrame:
    return load_table("dim_professional").copy()


def load_dates() -> pd.DataFrame:
    return load_table("dim_date").copy()


def clear_cache() -> None:
    """Drop the load cache. Tests use this after regenerating fixtures."""
    load_table.cache_clear()


# ---------------------------------------------------------------------------
# Model artefacts
# ---------------------------------------------------------------------------
def model_path(name: str) -> Path:
    return MODEL_DIR / f"{name}.joblib"


def metadata_path(name: str) -> Path:
    return MODEL_DIR / f"{name}.metrics.json"


def save_artifact(name: str, payload: Any, metrics: Optional[Dict] = None) -> Path:
    """Persist a fitted model plus whatever it needs at inference time."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    path = model_path(name)
    joblib.dump(payload, path)
    if metrics is not None:
        record = dict(metrics)
        record["trained_at"] = dt.datetime.now().isoformat(timespec="seconds")
        record["artifact"] = path.name
        metadata_path(name).write_text(json.dumps(record, indent=2), encoding="utf-8")
    return path


def load_artifact(name: str) -> Optional[Any]:
    """Return the persisted artefact, or None if it has not been trained yet."""
    path = model_path(name)
    if not path.exists():
        return None
    return joblib.load(path)


def load_metrics(name: str) -> Optional[Dict]:
    path = metadata_path(name)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def artifact_exists(name: str) -> bool:
    return model_path(name).exists()
