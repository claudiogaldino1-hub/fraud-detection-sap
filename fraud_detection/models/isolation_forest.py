"""
Isolation Forest anomaly detector for P2P financial transactions.
"""

import hashlib
import json
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

MODEL_DIR = Path(__file__).parent / "registry"
MODEL_DIR.mkdir(exist_ok=True)

NUMERIC_FEATURES = [
    "DMBTR",
    "WRBTR",
    "days_to_pay",
    "hour_of_entry",
    "vendor_payment_count_30d",
    "amount_deviation_from_vendor_mean",
    "is_round_amount",
    "days_since_vendor_created",
    "po_invoice_ratio",
]


def _build_features(bsak: pd.DataFrame, bkpf: pd.DataFrame, lfa1: pd.DataFrame) -> pd.DataFrame:
    df = bsak.copy()

    bkpf_map = bkpf.set_index("BELNR")[["CPUDT", "CPUTM", "BUDAT"]].to_dict("index")
    vendor_created = lfa1.set_index("LIFNR")["ERDAT"].to_dict()

    def _parse_hour(t: str) -> int:
        try:
            return int(str(t).split(":")[0])
        except Exception:
            return 12

    df["hour_of_entry"] = df["BELNR"].map(
        lambda b: _parse_hour(bkpf_map.get(b, {}).get("CPUTM", "12:00:00"))
    )
    df["BUDAT"] = pd.to_datetime(df["BUDAT"], errors="coerce")
    df["BLDAT"] = pd.to_datetime(df["BLDAT"], errors="coerce")
    df["AUGDT"] = pd.to_datetime(df["AUGDT"], errors="coerce")
    df["days_to_pay"] = (df["AUGDT"] - df["BUDAT"]).dt.days.fillna(0).clip(-365, 365)

    vendor_stats_mean = df.groupby("LIFNR")["DMBTR"].transform("mean")
    vendor_stats_std = df.groupby("LIFNR")["DMBTR"].transform("std")
    df["amount_deviation_from_vendor_mean"] = (
        (df["DMBTR"] - vendor_stats_mean) / (vendor_stats_std + 1)
    ).fillna(0)

    round_amounts = {5000, 10000, 25000, 50000, 100000, 250000, 500000}
    df["is_round_amount"] = df["DMBTR"].apply(lambda x: 1 if x in round_amounts else 0)

    vendor_created_dt = df["LIFNR"].map(vendor_created)
    df["days_since_vendor_created"] = (
        df["BUDAT"] - pd.to_datetime(vendor_created_dt, errors="coerce")
    ).dt.days.fillna(365).clip(0, 3650)

    df["vendor_payment_count_30d"] = (
        df.groupby("LIFNR")["BELNR"].transform("count")
    )
    df["po_invoice_ratio"] = df["DMBTR"] / (df["WRBTR"] + 1)

    return df


class IsolationForestDetector:
    def __init__(self, contamination: float = 0.02, n_estimators: int = 200, random_state: int = 42):
        self.contamination = contamination
        self.n_estimators = n_estimators
        self.random_state = random_state
        self.model: Optional[IsolationForest] = None
        self.scaler: Optional[StandardScaler] = None
        self.feature_names: List[str] = NUMERIC_FEATURES
        self.model_hash: str = ""
        self.version: str = ""

    def fit(self, bsak: pd.DataFrame, bkpf: pd.DataFrame, lfa1: pd.DataFrame) -> "IsolationForestDetector":
        features_df = _build_features(bsak, bkpf, lfa1)
        X = features_df[self.feature_names].fillna(0).values

        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        self.model = IsolationForest(
            contamination=self.contamination,
            n_estimators=self.n_estimators,
            random_state=self.random_state,
            n_jobs=-1,
        )
        self.model.fit(X_scaled)
        return self

    def predict(
        self, bsak: pd.DataFrame, bkpf: pd.DataFrame, lfa1: pd.DataFrame
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Returns (labels, scores). Label -1 = anomaly, 1 = normal."""
        features_df = _build_features(bsak, bkpf, lfa1)
        X = features_df[self.feature_names].fillna(0).values
        X_scaled = self.scaler.transform(X)
        labels = self.model.predict(X_scaled)
        scores = -self.model.score_samples(X_scaled)  # higher = more anomalous
        return labels, scores

    def predict_proba(
        self, bsak: pd.DataFrame, bkpf: pd.DataFrame, lfa1: pd.DataFrame
    ) -> np.ndarray:
        _, scores = self.predict(bsak, bkpf, lfa1)
        # Normalise to [0, 1]
        s_min, s_max = scores.min(), scores.max()
        if s_max > s_min:
            return (scores - s_min) / (s_max - s_min)
        return np.zeros_like(scores)

    def save(self, name: str = "isolation_forest") -> Path:
        payload = {"model": self.model, "scaler": self.scaler, "features": self.feature_names}
        path = MODEL_DIR / f"{name}.pkl"
        with open(path, "wb") as f:
            pickle.dump(payload, f)
        self.model_hash = _file_hash(path)
        self.version = name
        return path

    @classmethod
    def load(cls, name: str = "isolation_forest") -> "IsolationForestDetector":
        path = MODEL_DIR / f"{name}.pkl"
        with open(path, "rb") as f:
            payload = pickle.load(f)
        obj = cls()
        obj.model = payload["model"]
        obj.scaler = payload["scaler"]
        obj.feature_names = payload["features"]
        obj.model_hash = _file_hash(path)
        obj.version = name
        return obj

    def get_feature_names(self) -> List[str]:
        return self.feature_names


def _file_hash(path: Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()
