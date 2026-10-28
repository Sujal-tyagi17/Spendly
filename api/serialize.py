"""Turn pandas / dataclass results into JSON-safe structures."""

from __future__ import annotations

import math
from dataclasses import asdict, is_dataclass
from datetime import date

import numpy as np
import pandas as pd


def clean(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        f = float(value)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, date)):
        return value.isoformat()[:10]
    if value is pd.NaT or value is None:
        return None
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if is_dataclass(value):
        return clean(asdict(value))
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def records(frame: pd.DataFrame, columns: list[str] | None = None) -> list[dict]:
    if frame is None or frame.empty:
        return []
    if columns:
        frame = frame[columns]
    return [clean(row) for row in frame.to_dict(orient="records")]


TRANSACTION_FIELDS = {
    "id": "id",
    "date": "transaction_date",
    "merchant": "normalized_merchant",
    "description": "description",
    "amount_paise": "amount_paise",
    "direction": "direction",
    "type": "transaction_type",
    "category": "category",
    "method": "categorization_method",
    "review_status": "review_status",
    "review_reason": "review_reason",
    "is_possible_duplicate": "is_possible_duplicate",
    "balance_paise": "balance_paise",
}


def transaction_rows(frame: pd.DataFrame) -> list[dict]:
    if frame is None or frame.empty:
        return []
    out = []
    for row in frame.to_dict(orient="records"):
        item = {key: clean(row.get(col)) for key, col in TRANSACTION_FIELDS.items()}
        item["is_possible_duplicate"] = bool(item["is_possible_duplicate"])
        out.append(item)
    return out
