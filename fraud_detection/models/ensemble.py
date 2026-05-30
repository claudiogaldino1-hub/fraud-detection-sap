"""
Ensemble detector — combines Isolation Forest, AutoEncoder and Graph scores.
Produces a unified fraud_score in [0, 1] and a risk tier: HIGH / MEDIUM / LOW.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .autoencoder import AutoEncoderDetector
from .graph_analysis import GraphAlert, GraphAnalyzer
from .isolation_forest import IsolationForestDetector


@dataclass
class DetectionResult:
    record_index: int
    if_score: float
    ae_score: float
    graph_alert: bool
    ensemble_score: float
    risk_tier: str                  # HIGH | MEDIUM | LOW
    triggered_rules: List[str] = field(default_factory=list)
    graph_alerts: List[GraphAlert] = field(default_factory=list)


class EnsembleDetector:
    """
    Weighted ensemble of three detectors.
    Weights are configurable; default gives equal weight to each signal.
    """

    def __init__(
        self,
        if_weight: float = 0.35,
        ae_weight: float = 0.35,
        graph_weight: float = 0.30,
        high_threshold: float = 0.70,
        medium_threshold: float = 0.40,
    ):
        self.if_weight = if_weight
        self.ae_weight = ae_weight
        self.graph_weight = graph_weight
        self.high_threshold = high_threshold
        self.medium_threshold = medium_threshold

        self.if_detector: Optional[IsolationForestDetector] = None
        self.ae_detector: Optional[AutoEncoderDetector] = None
        self.graph_analyzer: Optional[GraphAnalyzer] = None

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def fit(
        self,
        tables: Dict[str, pd.DataFrame],
        ae_epochs: int = 50,
    ) -> "EnsembleDetector":
        bsak = tables["BSAK"]
        bkpf = tables["BKPF"]
        lfa1 = tables["LFA1"]
        ekko = tables["EKKO"]

        print("Fitting Isolation Forest...")
        self.if_detector = IsolationForestDetector()
        self.if_detector.fit(bsak, bkpf, lfa1)

        print("Fitting AutoEncoder...")
        self.ae_detector = AutoEncoderDetector(epochs=ae_epochs)
        self.ae_detector.fit(bsak, bkpf, lfa1)

        print("Building graph...")
        self.graph_analyzer = GraphAnalyzer()
        self.graph_analyzer.build(lfa1=lfa1, ekko=ekko, bkpf=bkpf, bsak=bsak)
        self.graph_analyzer.detect_all()

        return self

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def predict(self, tables: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        bsak = tables["BSAK"]
        bkpf = tables["BKPF"]
        lfa1 = tables["LFA1"]

        if_proba = self.if_detector.predict_proba(bsak, bkpf, lfa1)
        ae_proba = self.ae_detector.predict_proba(bsak, bkpf, lfa1)

        # Graph alerts mapped to LIFNR-level score boost
        graph_alerts = self.graph_analyzer.alerts
        flagged_vendors: set = set()
        for a in graph_alerts:
            for e in a.entities:
                if e.startswith("V"):
                    flagged_vendors.add(e)

        graph_scores = np.array([
            1.0 if str(lifnr) in flagged_vendors else 0.0
            for lifnr in bsak["LIFNR"].fillna("")
        ])

        ensemble = (
            self.if_weight * if_proba
            + self.ae_weight * ae_proba
            + self.graph_weight * graph_scores
        )

        results = bsak.copy()
        results["if_score"]       = if_proba
        results["ae_score"]       = ae_proba
        results["graph_score"]    = graph_scores
        results["ensemble_score"] = ensemble
        results["risk_tier"] = pd.cut(
            ensemble,
            bins=[-0.001, self.medium_threshold, self.high_threshold, 1.001],
            labels=["LOW", "MEDIUM", "HIGH"],
        )
        results["is_alert"] = results["ensemble_score"] >= self.medium_threshold

        return results

    def compare_detectors(self, results: pd.DataFrame) -> pd.DataFrame:
        """Returns a summary comparing detector agreement."""
        summary = pd.DataFrame({
            "if_alert":    results["if_score"] >= 0.5,
            "ae_alert":    results["ae_score"] >= 0.5,
            "graph_alert": results["graph_score"] >= 0.5,
            "ensemble":    results["ensemble_score"] >= self.medium_threshold,
        })
        agreement = summary.sum()
        unanimous = (summary["if_alert"] & summary["ae_alert"] & summary["graph_alert"]).sum()
        two_of_three = (
            (summary["if_alert"] & summary["ae_alert"]) |
            (summary["if_alert"] & summary["graph_alert"]) |
            (summary["ae_alert"] & summary["graph_alert"])
        ).sum()
        return pd.DataFrame([{
            "if_alerts":       int(agreement["if_alert"]),
            "ae_alerts":       int(agreement["ae_alert"]),
            "graph_alerts":    int(agreement["graph_alert"]),
            "ensemble_alerts": int(agreement["ensemble"]),
            "unanimous":       int(unanimous),
            "two_of_three":    int(two_of_three),
            "total_records":   len(results),
        }])

    def save_all(self, prefix: str = "v1"):
        if self.if_detector:
            self.if_detector.save(f"isolation_forest_{prefix}")
        if self.ae_detector:
            self.ae_detector.save(f"autoencoder_{prefix}")

    def load_all(self, prefix: str = "v1"):
        self.if_detector = IsolationForestDetector.load(f"isolation_forest_{prefix}")
        self.ae_detector = AutoEncoderDetector.load(f"autoencoder_{prefix}")
        self.graph_analyzer = GraphAnalyzer()
